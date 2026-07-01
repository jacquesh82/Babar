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
from config import settings
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
    """Vérifie la disponibilité Postgres (et Redis si le client est présent)."""
    from storage.db import ping as pg_ping

    postgres_ok = await pg_ping()

    redis_ok = False
    try:  # Redis optionnel au stade bootstrap : best-effort, non bloquant.
        import redis.asyncio as aioredis  # type: ignore

        client = aioredis.from_url(settings.redis_url)
        redis_ok = bool(await client.ping())
        await client.aclose()
    except Exception:
        redis_ok = False

    status = "ok" if postgres_ok else "degraded"
    return HealthResponse(status=status, postgres=postgres_ok, redis=redis_ok)


@app.post("/v1/ingest", response_model=IngestResponse)
async def ingest(
    req: IngestRequest,
    tenant: TenantContext = Depends(resolve_tenant),
) -> IngestResponse:
    """Ingestion incrémentale d'un tour de conversation.

    Flux : extractor → coref_resolver → validator → buffer_store.push. Les faits
    validés sont posés en short-term ; la promotion long-term relève du worker de
    consolidation (``consolidation/worker``), pas de cet endpoint.
    """
    from ingestion import coref_resolver, extractor, validator
    from storage import buffer_store

    triples = list(req.triples)
    if req.turn_text:
        triples += extractor.extract_triples(req.turn_text, tenant)

    resolved = coref_resolver.resolve(triples, tenant, req.conversation_id)
    result = validator.validate(resolved, tenant)

    buffered = 0
    for triple in result.accepted:
        await buffer_store.push(tenant, triple, req.conversation_id)
        buffered += 1

    return IngestResponse(
        accepted=len(result.accepted),
        buffered=buffered,
        rejected=len(result.rejected),
        detail=result.reasons,
    )


@app.post("/v1/recall", response_model=RecallResponse)
async def recall(
    req: RecallRequest,
    tenant: TenantContext = Depends(resolve_tenant),
) -> RecallResponse:
    """Question → contexte mémoire injectable (texte + trace).

    Flux : entity_linker → graph_walker → scorer → linearize. La recherche
    vectorielle (``vector_search``) n'est pas encore branchée (stub) ; le read
    path fonctionne sur l'activation par graphe seule.
    """
    from datetime import datetime, timezone

    from context_builder.linearizer import linearize
    from observability.tracing import log_recall, new_trace_id
    from retrieval import entity_linker, graph_walker, scorer

    trace_id = new_trace_id()
    now = req.as_of or datetime.now(timezone.utc)

    seeds = await entity_linker.link(tenant, req.query)
    if not seeds:
        return RecallResponse(context="", token_budget=req.token_budget, trace_id=trace_id)

    walk = await graph_walker.walk(tenant, seeds, max_hops=req.max_hops, as_of=req.as_of)
    facts = scorer.score(tenant, walk.edges, vector_candidates=None, now=now)
    response = linearize(tenant, facts, req.token_budget, trace_id=trace_id)

    selected_ids = {i.edge_ids[0] for i in response.items if i.edge_ids}
    log_recall(
        trace_id,
        tenant,
        req.query,
        selected=[{"edge_id": str(e)} for e in selected_ids],
        rejected=[{"edge_id": str(f.edge_id)} for f in facts if f.edge_id not in selected_ids],
        tokens_used=response.tokens_used,
        token_budget=req.token_budget,
    )
    return response


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
