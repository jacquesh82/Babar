"""Traversée N-sauts du graphe, avec limite de degré.

À partir des entités d'entrée (``entity_linker``), explore le voisinage jusqu'à
``max_hops`` sauts. Pour éviter l'explosion combinatoire, chaque nœud n'expose
que ses **top-K arêtes triées par poids** (limite de degré, déléguée à
``graph_store.neighbors``).

Respecte la bi-temporalité : si ``as_of`` est fourni, ne traverse que les
arêtes valides à cette date.

NB: la logique fine (pondération de chemin, pruning) N'EST PAS implémentée à ce
stade — architecture à valider d'abord.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from interface.common.schemas import TenantContext


@dataclass
class WalkResult:
    node_ids: set[UUID] = field(default_factory=set)
    edge_ids: set[UUID] = field(default_factory=set)
    # Chemin d'activation par arête, pour l'observabilité (pourquoi retenu).
    paths: list[list[UUID]] = field(default_factory=list)


async def walk(
    tenant: TenantContext,
    seed_nodes: list[UUID],
    max_hops: int = 2,
    top_k_per_node: int = 10,
    as_of: datetime | None = None,
) -> WalkResult:
    """Traverse le graphe en largeur depuis ``seed_nodes``.

    TODO:
        - BFS borné par ``max_hops`` + ``top_k_per_node`` (via graph_store).
        - Détection de cycles / dédup des nœuds visités.
        - Conservation des chemins pour ``observability/tracing.py``.
    """
    raise NotImplementedError("graph_walker.walk — stub")
