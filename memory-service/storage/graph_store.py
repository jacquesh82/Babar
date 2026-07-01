"""CRUD nœuds/arêtes du graphe, avec bi-temporalité.

Source de vérité long-term. Toutes les opérations sont **scopées par tenant**
(isolation non négociable #5) et respectent la bi-temporalité (#2) :
  * une mise à jour de fait n'écrase JAMAIS l'arête existante — elle la ferme
    (``valid_until = now``) et en ouvre une nouvelle (``valid_from = now``) ;
  * ``recorded_at`` (temps transaction) est distinct de ``valid_from/until``
    (temps de validité réel) → audit "que savais-tu à telle date ?".

Mappe les tables ``memory_nodes`` / ``memory_edges`` (voir
``storage/migrations/0001_init.sql``).
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from interface.common.schemas import NodeType, TenantContext, Triple


# --------------------------------------------------------------------------- #
# Nœuds
# --------------------------------------------------------------------------- #
async def upsert_node(
    tenant: TenantContext,
    canonical_key: str,
    label: str,
    node_type: NodeType,
    attributes: dict | None = None,
    permanent: bool = False,
    decay_rate: float = 0.0,
) -> UUID:
    """Crée ou met à jour un nœud (idempotent sur ``(tenant_id, canonical_key)``)."""
    raise NotImplementedError("graph_store.upsert_node — stub")


async def get_node(tenant: TenantContext, node_id: UUID) -> dict | None:
    """Retourne un nœud du tenant, ou None."""
    raise NotImplementedError("graph_store.get_node — stub")


# --------------------------------------------------------------------------- #
# Arêtes (bi-temporelles)
# --------------------------------------------------------------------------- #
async def add_edge(tenant: TenantContext, triple: Triple) -> UUID:
    """Insère une arête (triple) avec ``valid_from``/``recorded_at``.

    Ne ferme pas d'éventuelles arêtes contradictoires : c'est le rôle de
    ``consolidation/merger.py``.
    """
    raise NotImplementedError("graph_store.add_edge — stub")


async def close_edge(
    tenant: TenantContext, edge_id: UUID, valid_until: datetime
) -> None:
    """Ferme temporellement une arête (fin de validité) sans la supprimer.

    Utilisé pour les corrections "forget" et la résolution de contradiction.
    """
    raise NotImplementedError("graph_store.close_edge — stub")


async def neighbors(
    tenant: TenantContext,
    node_id: UUID,
    top_k: int = 10,
    as_of: datetime | None = None,
) -> list[dict]:
    """Arêtes sortantes d'un nœud, **triées par poids**, limitées à ``top_k``.

    Support direct du ``graph_walker`` (limite de degré). Si ``as_of`` est
    fourni, ne renvoie que les arêtes valides à cette date (bi-temporalité).

    TODO: n'inclure que ``valid_until IS NULL OR valid_until > as_of``.
    """
    raise NotImplementedError("graph_store.neighbors — stub")


async def hard_delete(tenant: TenantContext, node_ids: list[UUID], edge_ids: list[UUID]) -> int:
    """Suppression définitive (droit à l'oubli RGPD). Retourne le nb de lignes."""
    raise NotImplementedError("graph_store.hard_delete — stub")
