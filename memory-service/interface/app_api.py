"""API de consultation pour le visualiseur web (``/app``).

Endpoints de **lecture** du graphe mémoire (le read path ``/v1/recall`` est
orienté question ; ici on veut *parcourir* tout le contenu) + un endpoint de
**configuration publique** que le SPA lit au démarrage pour savoir comment
s'authentifier (mode tenant, paramètres OAuth PKCE vers Mindlog.id).

Auth : **identique aux autres adaptateurs** — ``Depends(resolve_tenant)`` résout
le ``TenantContext`` depuis le Bearer OIDC/JWT ou ``X-Tenant-Id`` (selon
``TENANT_MODE``). Les corrections passent par ``/v1/correct`` existant : ce
module n'ajoute que de la lecture.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from auth.tenant_isolation import resolve_tenant
from config import settings
from interface.common.schemas import TenantContext
from storage import graph_store

router = APIRouter(tags=["webapp"])


class PendingRef(BaseModel):
    """Désigne un fait du buffer short-term par son triple (subject|predicate|object)."""

    subject: str
    predicate: str
    object: str


class PendingUpdate(PendingRef):
    """Édition d'un fait en attente (le sujet est conservé)."""

    new_predicate: str
    new_object: str
    permanent: bool | None = None


@router.get("/v1/memory/graph")
async def memory_graph(
    tenant: TenantContext = Depends(resolve_tenant),
    q: str | None = Query(default=None, description="Filtre libellé/prédicat (insensible casse)"),
    include_closed: bool = Query(default=False, description="Inclure les faits oubliés/périmés"),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Contenu du graphe du tenant (arêtes enrichies + nœuds incidents)."""
    return await graph_store.list_graph(
        tenant, q=q, include_closed=include_closed, limit=limit, offset=offset
    )


@router.get("/v1/memory/stats")
async def memory_stats(
    tenant: TenantContext = Depends(resolve_tenant),
) -> dict[str, Any]:
    """Compteurs agrégés du graphe (en-tête du visualiseur)."""
    return await graph_store.graph_stats(tenant)


@router.get("/v1/memory/pending")
async def memory_pending(
    tenant: TenantContext = Depends(resolve_tenant),
    limit: int = Query(default=500, ge=1, le=2000),
) -> dict[str, Any]:
    """Faits ingérés en attente de consolidation (buffer short-term Redis).

    Rend visible dans l'UI ce qui vient d'être mémorisé mais n'a pas encore été
    promu vers le graphe long-term par le worker. Best-effort : si Redis est
    indisponible, renvoie une liste vide plutôt que d'échouer le chargement.
    """
    from storage import buffer_store

    try:
        return {"pending": await buffer_store.list_pending(tenant, limit=limit)}
    except Exception:
        return {"pending": []}


@router.post("/v1/memory/pending/update")
async def pending_update(
    body: PendingUpdate,
    tenant: TenantContext = Depends(resolve_tenant),
) -> dict[str, Any]:
    """Modifie un souvenir encore en attente (buffer short-term)."""
    from storage import buffer_store

    ok = await buffer_store.update_pending(
        tenant,
        body.subject,
        body.predicate,
        body.object,
        body.new_predicate,
        body.new_object,
        body.permanent,
    )
    return {"updated": ok}


@router.post("/v1/memory/pending/delete")
async def pending_delete(
    body: PendingRef,
    tenant: TenantContext = Depends(resolve_tenant),
) -> dict[str, Any]:
    """Retire un souvenir encore en attente (buffer short-term)."""
    from storage import buffer_store

    ok = await buffer_store.delete_pending(tenant, body.subject, body.predicate, body.object)
    return {"deleted": ok}


@router.get("/v1/webapp/config")
async def webapp_config() -> dict[str, Any]:
    """Configuration **publique** consommée par le SPA au démarrage.

    Ne contient aucun secret : mode d'auth + paramètres OAuth *publics* (client
    public PKCE). Permet au front de s'adapter (login OIDC vs saisie de tenant/
    Bearer en dev) sans recompiler.
    """
    mode = settings.tenant_mode.lower()
    return {
        "tenant_mode": mode,
        "auth_required": mode != "single",
        "oidc": {
            "issuer": settings.oidc_issuer,
            "client_id": settings.oidc_client_id,
            "authorization_endpoint": settings.oidc_authorization_endpoint,
            "token_endpoint": settings.oidc_token_endpoint,
            "redirect_uri": settings.public_base_url.rstrip("/") + "/app/",
            "scopes": settings.oidc_scopes,
            "audience": settings.oidc_audience,
            "resource": settings.mcp_resource,
        },
    }
