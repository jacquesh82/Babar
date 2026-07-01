"""Traçabilité : *pourquoi* ce contexte a été injecté pour cette requête.

Double usage :
  * **debug** : comprendre quels faits ont été activés, avec quels scores, et
    pourquoi ils ont (ou non) passé le budget de tokens ;
  * **audit** : conserver la trace des contradictions résolues (contrainte #4)
    et des corrections utilisateur, pour conformité / RGPD.

Chaque requête de rappel produit un ``trace_id`` réutilisé dans
``RecallResponse`` pour corréler la sortie et son explication.

Implémentation actuelle : journalisation structurée via ``logging`` standard.
La persistance en base (ex: ``contradiction_log``) pour l'audit long terme est
laissée en TODO — le contrat d'appel, lui, est stable.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from interface.common.schemas import TenantContext

logger = logging.getLogger("memory.tracing")


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
    """Journalise la décision d'injection (faits retenus/écartés + scores).

    TODO: sortie structlog + persistance optionnelle pour audit long terme.
    """
    logger.info(
        "recall trace=%s tenant=%s selected=%d rejected=%d tokens=%d/%d query=%r",
        trace_id,
        tenant.tenant_id,
        len(selected),
        len(rejected),
        tokens_used,
        token_budget,
        query,
    )


def log_contradiction(
    tenant: TenantContext,
    kept_edge_id: UUID | None,
    dropped_edge_id: UUID | None,
    strategy: str,
    detail: dict[str, Any],
) -> None:
    """Journalise une contradiction résolue (obligatoire, contrainte #4).

    TODO: INSERT dans ``contradiction_log`` en plus du log applicatif.
    """
    logger.warning(
        "contradiction tenant=%s kept=%s dropped=%s strategy=%s detail=%s",
        tenant.tenant_id,
        kept_edge_id,
        dropped_edge_id,
        strategy,
        detail,
    )
