"""Accès direct REST (fallback API classique) + application FastAPI racine.

C'est le point de montage principal : l'app FastAPI expose les endpoints REST et
monte les routers des autres adaptateurs (MCP, OpenAI Action) afin qu'ils
partagent le MÊME contrat (``interface/common/schemas.py``) et la MÊME logique
métier. Aucune divergence entre connecteurs.

Découplage #1 : cet adaptateur ne connaît aucun LLM ; il parle le contrat commun.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Response

from auth.tenant_isolation import resolve_tenant
from interface.common import service
from interface.common.schemas import (
    CorrectionRequest,
    CorrectionResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    RecallRequest,
    RecallResponse,
    TenantContext,
)

app = FastAPI(
    title="memory-service",
    version="0.1.0",
    description="Mémoire persistante en graphe, agnostique du LLM consommateur.",
)


@app.get("/health", response_model=HealthResponse)
async def health(response: Response) -> HealthResponse:
    """Liveness/readiness : pings Postgres + Redis.

    Renvoie **503** si Postgres (source de vérité) est indisponible, afin que les
    orchestrateurs (compose/k8s) puissent retirer l'instance du service.
    """
    from storage.db import ping as pg_ping
    from storage.redis_client import get_redis

    postgres_ok = await pg_ping()

    try:
        redis_ok = bool(await get_redis().ping())
    except Exception:
        redis_ok = False

    healthy = postgres_ok and redis_ok
    if not postgres_ok:
        response.status_code = 503
    return HealthResponse(
        status="ok" if healthy else "degraded",
        postgres=postgres_ok,
        redis=redis_ok,
    )


@app.post("/v1/ingest", response_model=IngestResponse)
async def ingest(
    req: IngestRequest,
    tenant: TenantContext = Depends(resolve_tenant),
) -> IngestResponse:
    """Ingestion incrémentale d'un tour de conversation.

    Flux (délégué à ``service.do_ingest``) : extractor → coref_resolver →
    validator → buffer_store.push. Les faits validés sont posés en short-term ;
    la promotion long-term relève du worker de consolidation, pas de cet endpoint.
    """
    return await service.do_ingest(tenant, req)


@app.post("/v1/recall", response_model=RecallResponse)
async def recall(
    req: RecallRequest,
    tenant: TenantContext = Depends(resolve_tenant),
) -> RecallResponse:
    """Question → contexte mémoire injectable (texte + trace).

    Flux (délégué à ``service.do_recall``) : entity_linker → graph_walker →
    scorer → linearize. La recherche vectorielle n'est pas encore branchée ; le
    read path fonctionne sur l'activation par graphe seule.
    """
    return await service.do_recall(tenant, req)


@app.post("/v1/correct", response_model=CorrectionResponse)
async def correct(
    req: CorrectionRequest,
    tenant: TenantContext = Depends(resolve_tenant),
) -> CorrectionResponse:
    """Correction/suppression explicite d'un souvenir ("forget that I…").

    Délégué à ``service.do_correct`` → ``feedback.corrections.apply_correction``.
    """
    return await service.do_correct(tenant, req)


# Montage des adaptateurs (mêmes schémas, même domaine commun).
from interface.mcp_server import build_mcp_server  # noqa: E402
from interface.openai_action import router as _action_router  # noqa: E402

app.include_router(_action_router)
app.include_router(build_mcp_server())
