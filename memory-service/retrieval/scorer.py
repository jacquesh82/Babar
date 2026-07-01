"""Fusion et scoring des candidats (graphe + vecteur).

Combine les résultats du ``graph_walker`` et du ``vector_search`` en un score
unique par fait candidat, selon quatre axes :
  * **pertinence**       : proximité à la question (vecteur + distance de graphe)
  * **récence**          : fraîcheur (``recorded_at`` / ``valid_from``)
  * **importance**       : ``importance`` du nœud/arête, modulée par le decay
  * **poids relationnel** : ``weight`` de l'arête

La formule exacte et les pondérations NE SONT PAS figées ici (à valider). Le
scorer produit une liste ordonnée décroissante consommée par le linearizer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from interface.common.schemas import TenantContext


@dataclass
class ScoredFact:
    edge_id: UUID
    node_ids: list[UUID]
    text: str                       # forme brute du fait (non encore linéarisée)
    score: float
    # Décomposition du score pour l'observabilité (pourquoi ce fait, ce rang).
    components: dict[str, float] = field(default_factory=dict)
    reason: dict[str, Any] = field(default_factory=dict)


def score(
    tenant: TenantContext,
    graph_candidates: list[dict],
    vector_candidates: list[tuple[UUID, float]],
    weights: dict[str, float] | None = None,
) -> list[ScoredFact]:
    """Fusionne et classe les candidats par score décroissant.

    Args:
        weights: pondérations {pertinence, recence, importance, poids_relationnel}.

    TODO:
        - Définir la fonction de fusion (linéaire pondérée par défaut).
        - Conserver ``components`` pour la trace d'observabilité.
        - Ne jamais mélanger les candidats de tenants différents.
    """
    raise NotImplementedError("scorer.score — stub")
