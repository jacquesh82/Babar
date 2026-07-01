"""Corrections explicites de la mémoire par l'utilisateur ("forget that I…").

Permet à l'utilisateur de corriger, invalider ou supprimer un souvenir de façon
explicite. Trois actions (voir ``CorrectionAction``) :
  * ``FORGET``      : fermeture temporelle (``valid_until = now``), conservée
    pour l'audit — le fait n'est plus actif mais reste traçable.
  * ``HARD_DELETE`` : suppression définitive (droit à l'oubli RGPD).
  * ``UPDATE``      : remplace un fait (ferme l'ancien, ouvre le nouveau).

La cible est soit explicite (``edge_ids``/``node_ids``), soit décrite en langage
naturel (résolue via ``entity_linker`` + ``graph_walker``). Toute correction est
tracée pour l'audit.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from interface.common.schemas import (
    CorrectionAction,
    CorrectionRequest,
    CorrectionResponse,
    TenantContext,
)
from observability.tracing import new_trace_id
from retrieval import entity_linker, graph_walker
from storage import graph_store

logger = logging.getLogger("memory.corrections")


async def _resolve_target_edges(tenant: TenantContext, req: CorrectionRequest) -> list:
    """Détermine les arêtes visées : ids explicites, sinon langage naturel."""
    if req.edge_ids:
        return list(req.edge_ids)
    if req.natural_language:
        seeds = await entity_linker.link(tenant, req.natural_language)
        if seeds:
            walk = await graph_walker.walk(tenant, seeds, max_hops=1)
            return list(walk.edge_ids)
    return []


async def apply_correction(tenant: TenantContext, req: CorrectionRequest) -> CorrectionResponse:
    """Applique une correction utilisateur sur la mémoire du tenant."""
    trace_id = new_trace_id()
    now = datetime.now(timezone.utc)
    edge_ids = await _resolve_target_edges(tenant, req)
    affected_edges = 0
    affected_nodes = 0

    if req.action == CorrectionAction.FORGET:
        for edge_id in edge_ids:
            await graph_store.close_edge(tenant, edge_id, valid_until=now)
            affected_edges += 1

    elif req.action == CorrectionAction.HARD_DELETE:
        await graph_store.hard_delete(tenant, req.node_ids, edge_ids)
        affected_edges = len(edge_ids)
        affected_nodes = len(req.node_ids)

    elif req.action == CorrectionAction.UPDATE:
        for edge_id in edge_ids:
            await graph_store.close_edge(tenant, edge_id, valid_until=now)
            affected_edges += 1
        if req.replacement is not None:
            await graph_store.add_edge(tenant, req.replacement)
            affected_edges += 1

    logger.info(
        "correction trace=%s tenant=%s action=%s edges=%d nodes=%d",
        trace_id,
        tenant.tenant_id,
        req.action.value,
        affected_edges,
        affected_nodes,
    )
    return CorrectionResponse(
        affected_nodes=affected_nodes,
        affected_edges=affected_edges,
        trace_id=trace_id,
    )
