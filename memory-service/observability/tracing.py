"""Traçabilité : *pourquoi* ce contexte a été injecté pour cette requête.

Double usage :
  * **debug** : comprendre quels faits ont été activés, avec quels scores, et
    pourquoi ils ont (ou non) passé le budget de tokens ;
  * **audit** : conserver la trace des contradictions résolues (contrainte #4)
    et des corrections utilisateur, pour conformité / RGPD.

Chaque requête de rappel produit un ``trace_id`` réutilisé dans
``RecallResponse`` pour corréler la sortie et son explication.
"""
from __future__ import annotations

from typing import Any

from interface.common.schemas import TenantContext


def new_trace_id() -> str:
    """Génère un identifiant de trace pour corréler requête ↔ explication."""
    raise NotImplementedError("tracing.new_trace_id — stub")


def log_recall(
    trace_id: str,
    tenant: TenantContext,
    query: str,
    selected: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    tokens_used: int,
    token_budget: int,
) -> None:
    """Journalise la décision d'injection (faits retenus/écartés + scores).

    TODO: sortie structurée (structlog) + persistance optionnelle pour audit.
    """
    raise NotImplementedError("tracing.log_recall — stub")


def log_contradiction(
    tenant: TenantContext,
    kept_edge_id,
    dropped_edge_id,
    strategy: str,
    detail: dict[str, Any],
) -> None:
    """Journalise une contradiction résolue dans ``contradiction_log`` (obligatoire)."""
    raise NotImplementedError("tracing.log_contradiction — stub")
