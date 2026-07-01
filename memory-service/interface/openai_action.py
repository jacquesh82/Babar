"""Exposition pour Custom GPT via Actions (OpenAPI).

Adaptateur "côté abonnement" pour ChatGPT : un Custom GPT appelle ces endpoints
décrits par un schéma OpenAPI. Comme les autres adaptateurs, il traduit vers le
**contrat commun** et délègue au même domaine — aucune divergence de
comportement entre Claude (MCP), ChatGPT (Action) et REST direct.

Découplage #1 : seul endroit autorisé à connaître les spécificités d'OpenAI
Actions ; rien de propriétaire ne descend dans le domaine.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from auth.tenant_isolation import resolve_tenant
from interface.common.schemas import (
    IngestRequest,
    IngestResponse,
    RecallRequest,
    RecallResponse,
    TenantContext,
)

# Router monté par ``api_rest`` sous un préfixe dédié (ex: /actions).
router = APIRouter(prefix="/actions", tags=["openai-action"])


@router.post("/recall", response_model=RecallResponse, operation_id="recallMemory")
async def action_recall(
    req: RecallRequest,
    tenant: TenantContext = Depends(resolve_tenant),
) -> RecallResponse:
    """Action ``recallMemory``. TODO: déléguer au même domaine que api_rest.recall."""
    raise NotImplementedError("openai_action.action_recall — stub")


@router.post("/ingest", response_model=IngestResponse, operation_id="ingestMemory")
async def action_ingest(
    req: IngestRequest,
    tenant: TenantContext = Depends(resolve_tenant),
) -> IngestResponse:
    """Action ``ingestMemory``. TODO: déléguer au pipeline d'ingestion."""
    raise NotImplementedError("openai_action.action_ingest — stub")


def openapi_schema() -> dict:
    """Retourne le schéma OpenAPI à fournir au Custom GPT (Actions).

    TODO: dériver de ``app.openapi()`` filtré sur le router /actions.
    """
    raise NotImplementedError("openai_action.openapi_schema — stub")
