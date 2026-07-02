"""Exposition pour Custom GPT via Actions (OpenAPI).

Adaptateur "côté abonnement" pour ChatGPT : un Custom GPT appelle ces endpoints
décrits par un schéma OpenAPI. Comme les autres adaptateurs, il **délègue au
service commun** (``interface/common/service``) — aucune divergence de
comportement entre Claude (MCP), ChatGPT (Action) et REST direct.

Découplage #1 : seul endroit autorisé à connaître les spécificités d'OpenAI
Actions ; rien de propriétaire ne descend dans le domaine.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from auth.tenant_isolation import resolve_tenant
from interface.common import service
from interface.common.schemas import (
    CorrectionRequest,
    CorrectionResponse,
    IngestRequest,
    IngestResponse,
    RecallRequest,
    RecallResponse,
    TenantContext,
)

# Router monté par ``api_rest`` sous un préfixe dédié.
router = APIRouter(prefix="/actions", tags=["openai-action"])


@router.post("/recall", response_model=RecallResponse, operation_id="recallMemory")
async def action_recall(
    req: RecallRequest,
    tenant: TenantContext = Depends(resolve_tenant),
) -> RecallResponse:
    """Action ``recallMemory`` — question → contexte mémoire injectable."""
    return await service.do_recall(tenant, req)


@router.post("/ingest", response_model=IngestResponse, operation_id="ingestMemory")
async def action_ingest(
    req: IngestRequest,
    tenant: TenantContext = Depends(resolve_tenant),
) -> IngestResponse:
    """Action ``ingestMemory`` — mémoriser un tour de conversation."""
    return await service.do_ingest(tenant, req)


@router.post("/correct", response_model=CorrectionResponse, operation_id="correctMemory")
async def action_correct(
    req: CorrectionRequest,
    tenant: TenantContext = Depends(resolve_tenant),
) -> CorrectionResponse:
    """Action ``correctMemory`` — corriger/oublier un souvenir."""
    return await service.do_correct(tenant, req)


def openapi_schema() -> dict:
    """Retourne le schéma OpenAPI (routes /actions) à fournir au Custom GPT.

    Génère un mini-app FastAPI ne contenant que ce router, puis exporte son
    OpenAPI — évite d'exposer les endpoints internes au Custom GPT.
    """
    from fastapi import FastAPI

    sub = FastAPI(title="memory-service actions", version="0.1.0")
    sub.include_router(router)
    return sub.openapi()
