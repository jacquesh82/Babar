"""Traçabilité : *pourquoi* ce contexte a été injecté pour cette requête.

Double usage :
  * **debug** : quels faits ont été activés, avec quels scores, et pourquoi ils
    ont (ou non) passé le budget de tokens ;
  * **audit** : trace persistée des rappels (``recall_log``) et des contradictions
    résolues (``contradiction_log``), pour conformité / RGPD.

Journalisation **structurée** (structlog, sortie JSON-friendly). La persistance
en base est *best-effort* : une indisponibilité DB ne casse jamais la requête.
Chaque rappel produit un ``trace_id`` corrélant la sortie et son explication.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import structlog

from interface.common.schemas import TenantContext

logger = structlog.get_logger("memory")


def new_trace_id() -> str:
    """Génère un identifiant de trace pour corréler requête ↔ explication."""
    return uuid4().hex


def log_recall(
    trace_id: str,
    tenant: TenantContext,
    query: str,
    selected: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    tokens_used: int,
    token_budget: int,
) -> None:
    """Journalise (structuré) la décision d'injection (retenus/écartés + budget)."""
    logger.info(
        "recall",
        trace_id=trace_id,
        tenant_id=str(tenant.tenant_id),
        query=query,
        selected=len(selected),
        rejected=len(rejected),
        tokens_used=tokens_used,
        token_budget=token_budget,
    )


async def persist_recall(
    trace_id: str,
    tenant: TenantContext,
    query: str,
    selected: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    tokens_used: int,
    token_budget: int,
) -> None:
    """Persiste la trace de rappel dans ``recall_log`` (audit). Best-effort."""
    try:
        from storage.db import acquire

        async with acquire() as conn:
            await conn.execute(
                """
                INSERT INTO recall_log
                    (tenant_id, trace_id, query, selected, rejected, tokens_used, token_budget)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                tenant.tenant_id,
                trace_id,
                query,
                selected,
                rejected,
                tokens_used,
                token_budget,
            )
    except Exception:
        logger.warning("persist_recall indisponible", trace_id=trace_id)


def log_contradiction(
    tenant: TenantContext,
    kept_edge_id: UUID | None,
    dropped_edge_id: UUID | None,
    strategy: str,
    detail: dict[str, Any],
) -> None:
    """Journalise (structuré) une contradiction résolue (obligatoire, #4).

    La persistance en base est faite par ``consolidation/merger`` (contradiction_log).
    """
    logger.warning(
        "contradiction",
        tenant_id=str(tenant.tenant_id),
        kept_edge_id=str(kept_edge_id) if kept_edge_id else None,
        dropped_edge_id=str(dropped_edge_id) if dropped_edge_id else None,
        strategy=strategy,
        detail=detail,
    )
