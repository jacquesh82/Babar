"""Fusion des doublons et résolution des contradictions.

Exécuté par le worker de consolidation (cron nocturne). Deux responsabilités :
  1. **Fusion de doublons** : nœuds/arêtes quasi identiques → une seule entité.
  2. **Résolution de contradictions** : deux faits incompatibles sur le même
     sujet/prédicat.

Règle d'arbitrage (À TRANCHER ET DOCUMENTER) — choix par défaut proposé :
  **dernière-écriture-gagne (LWW) avec fermeture temporelle** : l'arête la plus
  ancienne reçoit ``valid_until = now`` (via ``graph_store.close_edge``), la plus
  récente reste ouverte. Alternative optionnelle : **arbitrage LLM** (plus fin,
  coûteux, non déterministe), activable via ``CONTRADICTION_STRATEGY``.

Contrainte non négociable #4 : TOUTE contradiction traitée est **loguée** dans
``contradiction_log`` (via ``observability/tracing.py``), jamais résolue
silencieusement.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from interface.common.schemas import TenantContext


class ContradictionStrategy(str, Enum):
    LWW = "lww"                       # dernière-écriture-gagne (défaut)
    LLM_ARBITRATION = "llm_arbitration"


@dataclass
class MergeReport:
    merged_nodes: int = 0
    merged_edges: int = 0
    contradictions_resolved: int = 0


async def merge_duplicates(tenant: TenantContext) -> MergeReport:
    """Fusionne les doublons de nœuds/arêtes du tenant.

    TODO: détection (canonical_key + similarité), réattachement des arêtes,
    conservation de la provenance.
    """
    raise NotImplementedError("merger.merge_duplicates — stub")


async def resolve_contradictions(
    tenant: TenantContext,
    strategy: ContradictionStrategy = ContradictionStrategy.LWW,
) -> MergeReport:
    """Résout les contradictions selon la stratégie choisie.

    TODO:
        - Identifier les arêtes contradictoires (même subject+predicate, objets
          incompatibles, périodes de validité chevauchantes).
        - Appliquer LWW (fermeture temporelle) ou arbitrage LLM.
        - LOGUER chaque décision dans contradiction_log (obligatoire).
    """
    raise NotImplementedError("merger.resolve_contradictions — stub")
