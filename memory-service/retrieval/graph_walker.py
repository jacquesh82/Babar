"""Traversée N-sauts du graphe, avec limite de degré.

À partir des entités d'entrée (``entity_linker``), explore le voisinage jusqu'à
``max_hops`` sauts. Pour éviter l'explosion combinatoire, chaque nœud n'expose
que ses **top-K arêtes triées par poids** (limite de degré, déléguée à
``graph_store.neighbors``).

Respecte la bi-temporalité : si ``as_of`` est fourni, ne traverse que les
arêtes valides à cette date.

Produit des "candidats" enrichis (labels résolus, distance en sauts, chemin
d'activation) directement consommables par ``retrieval/scorer``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from interface.common.schemas import TenantContext
from storage.graph_store import get_node, neighbors


@dataclass
class WalkResult:
    node_ids: set[UUID] = field(default_factory=set)
    edge_ids: set[UUID] = field(default_factory=set)
    # Arêtes candidates enrichies (row + hops + labels + path), pour le scorer.
    edges: list[dict] = field(default_factory=list)
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

    BFS borné par ``max_hops`` et ``top_k_per_node``. Les nœuds déjà visités ne
    sont pas ré-explorés (dédup / évite les cycles). Chaque arête est enrichie
    des labels sujet/objet et de sa distance en sauts pour le scoring.
    """
    result = WalkResult()
    label_cache: dict[UUID, str] = {}

    async def label_of(node_id: UUID) -> str:
        if node_id not in label_cache:
            node = await get_node(tenant, node_id)
            label_cache[node_id] = node["label"] if node else str(node_id)
        return label_cache[node_id]

    visited: set[UUID] = set()
    frontier: list[tuple[UUID, list[UUID]]] = []
    for seed in seed_nodes:
        if seed not in visited:
            visited.add(seed)
            result.node_ids.add(seed)
            frontier.append((seed, [seed]))

    hops = 0
    while frontier and hops < max_hops:
        hops += 1
        next_frontier: list[tuple[UUID, list[UUID]]] = []
        for node_id, path in frontier:
            for edge in await neighbors(tenant, node_id, top_k=top_k_per_node, as_of=as_of):
                object_id = edge["object_id"]
                new_path = path + [object_id]

                candidate = dict(edge)
                candidate["edge_id"] = edge["id"]
                candidate["hops"] = hops
                candidate["subject_label"] = await label_of(edge["subject_id"])
                candidate["object_label"] = await label_of(object_id)
                candidate["path"] = new_path

                result.edge_ids.add(edge["id"])
                result.edges.append(candidate)
                result.paths.append(new_path)

                if object_id not in visited:
                    visited.add(object_id)
                    result.node_ids.add(object_id)
                    next_frontier.append((object_id, new_path))
        frontier = next_frontier

    return result
