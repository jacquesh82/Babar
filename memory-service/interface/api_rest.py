"""Accès direct REST (fallback API classique) + application FastAPI racine.

C'est le point de montage principal : l'app FastAPI expose les endpoints REST et
monte les routers des autres adaptateurs (MCP, OpenAI Action) afin qu'ils
partagent le MÊME contrat (``interface/common/schemas.py``) et la MÊME logique
métier. Aucune divergence entre connecteurs.

Découplage #1 : cet adaptateur ne connaît aucun LLM ; il parle le contrat commun.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI

from auth.tenant_isolation import resolve_tenant
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
async def health() -> HealthResponse:
    """Vérifie la disponibilité Postgres/Redis. TODO: pings réels."""
    raise NotImplementedError("api_rest.health — stub")


@app.post("/v1/ingest", response_model=IngestResponse)
async def ingest(
    req: IngestRequest,
    tenant: TenantContext = Depends(resolve_tenant),
) -> IngestResponse:
    """Ingestion incrémentale d'un tour de conversation.

    TODO: extractor → coref_resolver → validator → buffer_store.push.
    """
    raise NotImplementedError("api_rest.ingest — stub")


@app.post("/v1/recall", response_model=RecallResponse)
async def recall(
    req: RecallRequest,
    tenant: TenantContext = Depends(resolve_tenant),
) -> RecallResponse:
    """Question → contexte mémoire injectable (texte + trace).

    TODO: entity_linker → (graph_walker ∥ vector_search) → scorer → linearize.
    """
    raise NotImplementedError("api_rest.recall — stub")


@app.post("/v1/correct", response_model=CorrectionResponse)
async def correct(
    req: CorrectionRequest,
    tenant: TenantContext = Depends(resolve_tenant),
) -> CorrectionResponse:
    """Correction/suppression explicite d'un souvenir ("forget that I…").

    TODO: déléguer à feedback.corrections.apply_correction.
    """
    raise NotImplementedError("api_rest.correct — stub")


# Montage des autres adaptateurs (mêmes schémas, même domaine).
# TODO: importer et inclure les routers une fois implémentés, ex:
#   from interface.mcp_server import router as mcp_router
#   from interface.openai_action import router as action_router
#   app.include_router(mcp_router)
#   app.include_router(action_router)
