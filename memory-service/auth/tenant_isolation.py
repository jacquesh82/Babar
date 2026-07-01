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

from interface.common.schemas import TenantContext


class TenantIsolationError(Exception):
    """Levée quand le tenant est absent, invalide, ou incohérent."""


async def resolve_tenant(
    tenant_header: str | None = None,
    authorization: str | None = None,
) -> TenantContext:
    """Résout le ``TenantContext`` de la requête (dépendance FastAPI).

    TODO:
        - Selon ``TENANT_MODE`` : parser X-Tenant-Id, décoder le JWT, ou single.
        - Rejeter (TenantIsolationError) si aucun tenant exploitable.
        - Ne jamais laisser passer une requête sans tenant vers le domaine.
    """
    raise NotImplementedError("tenant_isolation.resolve_tenant — stub")


def assert_same_tenant(ctx: TenantContext, resource_tenant_id) -> None:
    """Garde-fou : vérifie qu'une ressource appartient bien au tenant courant."""
    raise NotImplementedError("tenant_isolation.assert_same_tenant — stub")
