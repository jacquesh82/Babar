"""Corrections explicites de la mémoire par l'utilisateur ("forget that I…").

Permet à l'utilisateur de corriger, invalider ou supprimer un souvenir de façon
explicite. Trois actions (voir ``CorrectionAction``) :
  * ``FORGET``      : fermeture temporelle (``valid_until = now``), conservée
    pour l'audit — le fait n'est plus actif mais reste traçable.
  * ``HARD_DELETE`` : suppression définitive (droit à l'oubli RGPD).
  * ``UPDATE``      : remplace un fait (ferme l'ancien, ouvre le nouveau).

Toute correction est tracée via ``observability/tracing.py``.
"""
from __future__ import annotations

from interface.common.schemas import (
    CorrectionAction,
    CorrectionRequest,
    CorrectionResponse,
    TenantContext,
)


async def apply_correction(req: CorrectionRequest) -> CorrectionResponse:
    """Applique une correction utilisateur sur la mémoire du tenant.

    TODO:
        - Résoudre la cible (edge_ids/node_ids explicites OU natural_language
          via entity_linker/vector_search).
        - FORGET → graph_store.close_edge ; HARD_DELETE → graph_store.hard_delete ;
          UPDATE → close + add_edge(replacement).
        - Tracer chaque action (qui, quoi, quand, pourquoi) pour audit RGPD.
    """
    raise NotImplementedError("corrections.apply_correction — stub")
