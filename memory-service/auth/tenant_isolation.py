"""Isolation stricte multi-utilisateur / multi-tenant.

Obligatoire en usage SaaS. Fournit :
  * l'extraction/validation du ``TenantContext`` depuis la requête entrante
    (header ``X-Tenant-Id``, JWT, ou mode ``single`` en dev — cf. ``TENANT_MODE``) ;
  * une dépendance FastAPI réutilisable par tous les adaptateurs ``interface/``.

Rappel contrainte non négociable #5 : l'isolation est aussi garantie **au niveau
base** (``tenant_id NOT NULL`` + index par tenant, cf. migration). Ce module est
la première ligne de défense applicative ; la base est le filet de sécurité.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import Header

from config import settings
from interface.common.schemas import TenantContext

# Tenant de développement utilisé uniquement en mode "single" (jamais en prod).
_DEV_TENANT = UUID("00000000-0000-0000-0000-000000000001")


class TenantIsolationError(Exception):
    """Levée quand le tenant est absent, invalide, ou incohérent."""


def _parse_uuid(value: str, field: str) -> UUID:
    try:
        return UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise TenantIsolationError(f"{field} invalide : identifiant non-UUID") from exc


def resolve_tenant_context(
    tenant_header: str | None,
    authorization: str | None,
    mode: str | None = None,
) -> TenantContext:
    """Cœur pur (testable sans FastAPI) : résout le tenant selon le mode.

    Args:
        tenant_header: valeur du header ``X-Tenant-Id`` (mode "header").
        authorization: valeur du header ``Authorization`` (mode "jwt").
        mode: override du mode ; par défaut ``settings.tenant_mode``.
    """
    mode = (mode or settings.tenant_mode).lower()

    if mode == "single":
        # Dév uniquement : un tenant fixe, jamais d'isolation réelle.
        return TenantContext(tenant_id=_DEV_TENANT)

    if mode == "header":
        if not tenant_header:
            raise TenantIsolationError("header X-Tenant-Id manquant")
        return TenantContext(tenant_id=_parse_uuid(tenant_header, "X-Tenant-Id"))

    if mode == "jwt":
        # TODO: décoder/vérifier le JWT (lib + secret) et en extraire tenant_id/user_id.
        raise TenantIsolationError("mode JWT non encore implémenté")

    raise TenantIsolationError(f"TENANT_MODE inconnu : {mode!r}")


async def resolve_tenant(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    authorization: str | None = Header(default=None),
) -> TenantContext:
    """Dépendance FastAPI : résout le ``TenantContext`` de la requête.

    Rejette toute requête sans tenant exploitable avant qu'elle n'atteigne le
    domaine. Traduit ``TenantIsolationError`` en 401.
    """
    from fastapi import HTTPException  # import local pour garder le cœur pur importable

    try:
        return resolve_tenant_context(x_tenant_id, authorization)
    except TenantIsolationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def assert_same_tenant(ctx: TenantContext, resource_tenant_id: UUID | str | None) -> None:
    """Garde-fou : vérifie qu'une ressource appartient bien au tenant courant.

    Défense en profondeur applicative (la base garantit déjà l'isolation).
    """
    if resource_tenant_id is None:
        raise TenantIsolationError("ressource sans tenant_id")
    resource_uuid = resource_tenant_id if isinstance(resource_tenant_id, UUID) else UUID(str(resource_tenant_id))
    if resource_uuid != ctx.tenant_id:
        raise TenantIsolationError("accès inter-tenant refusé")
