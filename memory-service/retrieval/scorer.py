"""Fusion et scoring des candidats (graphe + vecteur).

Combine les résultats du ``graph_walker`` et du ``vector_search`` en un score
unique par fait candidat, selon quatre axes bornés dans [0, 1] :
  * **relevance**   : proximité à la question (proximité de graphe ∨ similarité vecteur)
  * **recency**     : fraîcheur (``valid_from`` vs ``now``, demi-vie configurable)
  * **importance**  : ``importance`` de l'arête (déjà modulée par le decay)
  * **relational**  : ``weight`` de l'arête, normalisé

Le score final est une **combinaison linéaire pondérée** normalisée. Les
pondérations sont configurables ; les composantes sont conservées dans
``ScoredFact.components`` pour l'observabilité ("pourquoi ce rang").

Fonction **pure et déterministe** (``now`` injectable) — testable sans DB.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from interface.common.schemas import TenantContext

# Pondérations par défaut (somme = 1.0, mais non requis : on normalise).
DEFAULT_WEIGHTS: dict[str, float] = {
    "relevance": 0.4,
    "recency": 0.2,
    "importance": 0.2,
    "relational": 0.2,
}

_DEFAULT_HALF_LIFE_DAYS = 30.0


@dataclass
class ScoredFact:
    edge_id: UUID | None
    node_ids: list[UUID]
    text: str                       # forme brute du fait (non encore linéarisée)
    score: float
    # Décomposition du score pour l'observabilité (pourquoi ce fait, ce rang).
    components: dict[str, float] = field(default_factory=dict)
    reason: dict[str, Any] = field(default_factory=dict)


def _recency(valid_from: datetime | None, now: datetime | None, half_life_days: float) -> float:
    """Décroissance exponentielle de fraîcheur, bornée [0, 1] (0.5 si inconnu)."""
    if valid_from is None or now is None:
        return 0.5
    age_days = max((now - valid_from).total_seconds() / 86400.0, 0.0)
    return math.exp(-math.log(2) * age_days / half_life_days)


def _relational(weight: float) -> float:
    """Normalise un poids [0, +inf) vers [0, 1) via w / (w + 1)."""
    w = max(weight, 0.0)
    return w / (w + 1.0)


def score(
    tenant: TenantContext,
    graph_candidates: list[dict],
    vector_candidates: list[tuple[UUID, float]] | None = None,
    weights: dict[str, float] | None = None,
    now: datetime | None = None,
    half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
) -> list[ScoredFact]:
    """Fusionne et classe les candidats par score décroissant.

    Args:
        graph_candidates: arêtes enrichies issues du ``graph_walker`` (dicts).
        vector_candidates: ``[(node_id, similarité∈[0,1])]`` issus du vector_search.
        weights: pondérations {relevance, recency, importance, relational}.
        now: instant de référence pour la récence (injecté pour déterminisme).

    Les candidats sont supposés déjà scopés au tenant (garanti en amont).
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    w_sum = sum(w.values()) or 1.0
    vec = {node_id: sim for node_id, sim in (vector_candidates or [])}

    facts: list[ScoredFact] = []
    for cand in graph_candidates:
        hops = int(cand.get("hops", 1))
        proximity = 1.0 / (1.0 + max(hops - 1, 0))          # hops=1 → 1.0, hops=2 → 0.5
        similarity = max(
            vec.get(cand.get("subject_id"), 0.0),
            vec.get(cand.get("object_id"), 0.0),
        )
        components = {
            "relevance": max(proximity, similarity),
            "recency": _recency(cand.get("valid_from"), now, half_life_days),
            "importance": min(max(float(cand.get("importance", 0.5)), 0.0), 1.0),
            "relational": _relational(float(cand.get("weight", 1.0))),
        }
        final = sum(w[k] * components[k] for k in components) / w_sum

        subject = cand.get("subject_label") or str(cand.get("subject_id"))
        obj = cand.get("object_label") or str(cand.get("object_id"))
        node_ids = [n for n in (cand.get("subject_id"), cand.get("object_id")) if n is not None]

        facts.append(
            ScoredFact(
                edge_id=cand.get("edge_id") or cand.get("id"),
                node_ids=node_ids,
                text=f"{subject} {cand.get('predicate', '?')} {obj}",
                score=final,
                components=components,
                reason={"hops": hops, "path": cand.get("path")},
            )
        )

    facts.sort(key=lambda f: f.score, reverse=True)
    return facts
