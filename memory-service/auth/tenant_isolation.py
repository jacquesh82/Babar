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

import time
from uuid import UUID, uuid5

from fastapi import Header
from starlette.concurrency import run_in_threadpool

from auth.jwt_utils import JWTError, decode_hs256
from config import settings
from interface.common.schemas import TenantContext

# Tenant de développement utilisé uniquement en mode "single" (jamais en prod).
_DEV_TENANT = UUID("00000000-0000-0000-0000-000000000001")

# Namespace stable pour dériver un UUID des identifiants Mindlog.id (org/sub) qui
# ne sont pas forcément des UUID. La dérivation est déterministe : même id → même
# tenant, toujours.
_MINDLOG_NS = UUID("2f1e7c0a-9b3d-5e64-8a17-6d4c9f0b2e11")


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
        return _tenant_from_jwt(authorization)

    if mode == "oidc":
        return _tenant_from_oidc(authorization)

    raise TenantIsolationError(f"TENANT_MODE inconnu : {mode!r}")


def _coerce_uuid(value: str) -> UUID:
    """Identifiant → UUID : direct si déjà un UUID, sinon dérivation uuid5 stable."""
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return uuid5(_MINDLOG_NS, str(value))


def _tenant_from_oidc(authorization: str | None) -> TenantContext:
    """Extrait le tenant d'un jeton d'accès OIDC (Mindlog.id) vérifié via JWKS.

    ``org``-claim → ``tenant_id`` (isolation), ``sub``-claim → ``user_id``. Les
    identifiants Mindlog.id non-UUID sont dérivés en UUID de façon déterministe.
    """
    # Import local : ne tire PyJWT/cryptography que si le mode oidc est actif.
    from auth.oidc import OIDCError, verify_oidc_token

    if not authorization or not authorization.lower().startswith("bearer "):
        raise TenantIsolationError("header Authorization Bearer manquant")

    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = verify_oidc_token(token)
    except OIDCError as exc:
        raise TenantIsolationError(f"jeton OIDC invalide : {exc}") from exc

    org_value = claims.get(settings.oidc_tenant_claim)
    if not org_value:
        raise TenantIsolationError(f"claim tenant '{settings.oidc_tenant_claim}' absent")
    user_value = claims.get(settings.oidc_user_claim)
    return TenantContext(
        tenant_id=_coerce_uuid(org_value),
        user_id=_coerce_uuid(user_value) if user_value else None,
    )


async def resolve_tenant_context_async(
    tenant_header: str | None,
    authorization: str | None,
    mode: str | None = None,
) -> TenantContext:
    """Variante async : déporte la résolution en threadpool.

    Le mode ``oidc`` peut faire un appel réseau (récupération JWKS) ; on l'exécute
    hors de la boucle événementielle pour ne pas la bloquer. Les autres modes sont
    purs, l'overhead est négligeable.
    """
    return await run_in_threadpool(resolve_tenant_context, tenant_header, authorization, mode)


def _tenant_from_jwt(authorization: str | None) -> TenantContext:
    """Extrait le tenant d'un ``Authorization: Bearer <jwt>`` HS256 vérifié."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise TenantIsolationError("header Authorization Bearer manquant")
    if not settings.jwt_secret:
        raise TenantIsolationError("JWT_SECRET non configuré")

    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = decode_hs256(token, settings.jwt_secret, now=time.time())
    except JWTError as exc:
        raise TenantIsolationError(f"JWT invalide : {exc}") from exc

    tenant_value = claims.get(settings.jwt_tenant_claim)
    if not tenant_value:
        raise TenantIsolationError(f"claim tenant '{settings.jwt_tenant_claim}' absent")
    user_value = claims.get(settings.jwt_user_claim)
    return TenantContext(
        tenant_id=_parse_uuid(str(tenant_value), "claim tenant"),
        user_id=_parse_uuid(str(user_value), "claim user") if user_value else None,
    )


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
        return await resolve_tenant_context_async(x_tenant_id, authorization)
    except TenantIsolationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def assert_same_tenant(ctx: TenantContext, resource_tenant_id: UUID | str | None) -> None:
    """Garde-fou : vérifie qu'une ressource appartient bien au tenant courant.

    Défense en profondeur applicative (la base garantit déjà l'isolation).
    """
    if resource_tenant_id is None:
        raise TenantIsolationError("ressource sans tenant_id")
    resource_uuid = (
        resource_tenant_id
        if isinstance(resource_tenant_id, UUID)
        else UUID(str(resource_tenant_id))
    )
    if resource_uuid != ctx.tenant_id:
        raise TenantIsolationError("accès inter-tenant refusé")
