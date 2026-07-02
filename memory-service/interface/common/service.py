"""Service applicatif commun — logique métier partagée par TOUS les adaptateurs.

``mcp_server``, ``openai_action`` et ``api_rest`` délèguent **ici** : un seul
chemin de code pour ingest / recall / correct, quel que soit le connecteur du
LLM. C'est le pendant comportemental de ``interface/common/schemas`` (contrat de
données) : ensemble, ils garantissent qu'aucun adaptateur ne diverge.

Le ``TenantContext`` passé est celui **résolu par l'authentification** (source de
vérité), jamais celui potentiellement présent dans le corps de requête client.
"""

from __future__ import annotations

from datetime import UTC, datetime

from context_builder.linearizer import linearize
from feedback import corrections
from ingestion import coref_resolver, extractor, validator
from interface.common.schemas import (
    CorrectionRequest,
    CorrectionResponse,
    IngestRequest,
    IngestResponse,
    RecallRequest,
    RecallResponse,
    TenantContext,
)
from observability.tracing import log_recall, new_trace_id, persist_recall
from retrieval import entity_linker, graph_walker, scorer
from storage import buffer_store


async def do_ingest(tenant: TenantContext, req: IngestRequest) -> IngestResponse:
    """Ingestion incrémentale : texte/triples → buffer short-term."""
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


async def do_recall(tenant: TenantContext, req: RecallRequest) -> RecallResponse:
    """Question → contexte mémoire injectable (activation par graphe)."""
    trace_id = new_trace_id()
    now = req.as_of or datetime.now(UTC)

    seeds = await entity_linker.link(tenant, req.query)
    if not seeds:
        return RecallResponse(context="", token_budget=req.token_budget, trace_id=trace_id)

    walk = await graph_walker.walk(tenant, seeds, max_hops=req.max_hops, as_of=req.as_of)

    vector_candidates = None
    try:  # similarité sémantique pour affiner le scoring (best-effort sans pgvector)
        from retrieval import vector_search

        vector_candidates = await vector_search.search(tenant, req.query, top_k=20)
    except Exception:
        vector_candidates = None

    facts = scorer.score(tenant, walk.edges, vector_candidates=vector_candidates, now=now)
    response = linearize(tenant, facts, req.token_budget, trace_id=trace_id)

    selected_ids = {i.edge_ids[0] for i in response.items if i.edge_ids}
    selected = [{"edge_id": str(e)} for e in selected_ids]
    rejected = [{"edge_id": str(f.edge_id)} for f in facts if f.edge_id not in selected_ids]
    log_recall(
        trace_id, tenant, req.query, selected, rejected, response.tokens_used, req.token_budget
    )
    await persist_recall(
        trace_id, tenant, req.query, selected, rejected, response.tokens_used, req.token_budget
    )
    return response


async def do_correct(tenant: TenantContext, req: CorrectionRequest) -> CorrectionResponse:
    """Correction/suppression explicite d'un souvenir ("forget that I…")."""
    return await corrections.apply_correction(tenant, req)
