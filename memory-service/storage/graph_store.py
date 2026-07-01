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
from storage.db import acquire


# --------------------------------------------------------------------------- #
# Nœuds
# --------------------------------------------------------------------------- #
async def upsert_node(
    tenant: TenantContext,
    canonical_key: str,
    label: str,
    node_type: NodeType = NodeType.OTHER,
    attributes: dict | None = None,
    permanent: bool = False,
    decay_rate: float = 0.0,
) -> UUID:
    """Crée ou met à jour un nœud (idempotent sur ``(tenant_id, canonical_key)``)."""
    node_type_value = node_type.value if isinstance(node_type, NodeType) else str(node_type)
    async with acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO memory_nodes
                (tenant_id, node_type, canonical_key, label, attributes, permanent, decay_rate)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
            ON CONFLICT (tenant_id, canonical_key) DO UPDATE
                SET label      = EXCLUDED.label,
                    node_type  = EXCLUDED.node_type,
                    attributes = EXCLUDED.attributes,
                    permanent  = EXCLUDED.permanent,
                    decay_rate = EXCLUDED.decay_rate
            RETURNING id
            """,
            tenant.tenant_id,
            node_type_value,
            canonical_key,
            label,
            attributes or {},
            permanent,
            decay_rate,
        )


async def get_node(tenant: TenantContext, node_id: UUID) -> dict | None:
    """Retourne un nœud du tenant, ou None."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM memory_nodes WHERE id = $1 AND tenant_id = $2",
            node_id,
            tenant.tenant_id,
        )
        return dict(row) if row else None


# --------------------------------------------------------------------------- #
# Arêtes (bi-temporelles)
# --------------------------------------------------------------------------- #
async def add_edge(tenant: TenantContext, triple: Triple) -> UUID:
    """Insère une arête (triple) avec ``valid_from``/``recorded_at``.

    Les nœuds sujet/objet sont garantis présents (upsert par ``canonical_key``
    = libellé fourni ; l'enrichissement de type/attributs relève de l'ingestion).
    Ne ferme pas d'éventuelles arêtes contradictoires : c'est le rôle de
    ``consolidation/merger.py``.
    """
    subject_id = await upsert_node(tenant, triple.subject, triple.subject)
    object_id = await upsert_node(tenant, triple.object, triple.object)
    async with acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO memory_edges
                (tenant_id, subject_id, predicate, object_id,
                 permanent, decay_rate, confidence, source, valid_from)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, COALESCE($9::timestamptz, now()))
            RETURNING id
            """,
            tenant.tenant_id,
            subject_id,
            triple.predicate,
            object_id,
            triple.permanent,
            triple.decay_rate,
            triple.confidence,
            triple.source.value,
            triple.valid_from,
        )


async def close_edge(
    tenant: TenantContext, edge_id: UUID, valid_until: datetime
) -> None:
    """Ferme temporellement une arête (fin de validité) sans la supprimer.

    Utilisé pour les corrections "forget" et la résolution de contradiction.
    Idempotent : ne ré-ouvre jamais une arête déjà fermée antérieurement.
    """
    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE memory_edges
               SET valid_until = $3
             WHERE id = $1 AND tenant_id = $2
               AND (valid_until IS NULL OR valid_until > $3)
            """,
            edge_id,
            tenant.tenant_id,
            valid_until,
        )


async def neighbors(
    tenant: TenantContext,
    node_id: UUID,
    top_k: int = 10,
    as_of: datetime | None = None,
) -> list[dict]:
    """Arêtes sortantes d'un nœud, **triées par poids**, limitées à ``top_k``.

    Support direct du ``graph_walker`` (limite de degré). Si ``as_of`` est
    fourni, ne renvoie que les arêtes valides à cette date (bi-temporalité) ;
    sinon, uniquement les arêtes actuellement ouvertes.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, subject_id, predicate, object_id, weight, importance,
                   permanent, decay_rate, confidence, source,
                   valid_from, valid_until, recorded_at
              FROM memory_edges
             WHERE tenant_id = $1
               AND subject_id = $2
               AND valid_from <= COALESCE($3::timestamptz, now())
               AND (valid_until IS NULL OR valid_until > COALESCE($3::timestamptz, now()))
             ORDER BY weight DESC, importance DESC
             LIMIT $4
            """,
            tenant.tenant_id,
            node_id,
            as_of,
            top_k,
        )
        return [dict(r) for r in rows]


async def hard_delete(
    tenant: TenantContext, node_ids: list[UUID], edge_ids: list[UUID]
) -> int:
    """Suppression définitive (droit à l'oubli RGPD). Retourne le nb de lignes.

    Supprime d'abord les arêtes ciblées, puis les nœuds ciblés (le CASCADE de la
    FK retire au passage les arêtes incidentes des nœuds supprimés).
    """
    affected = 0
    async with acquire() as conn:
        async with conn.transaction():
            if edge_ids:
                res = await conn.execute(
                    "DELETE FROM memory_edges WHERE tenant_id = $1 AND id = ANY($2::uuid[])",
                    tenant.tenant_id,
                    edge_ids,
                )
                affected += _rowcount(res)
            if node_ids:
                res = await conn.execute(
                    "DELETE FROM memory_nodes WHERE tenant_id = $1 AND id = ANY($2::uuid[])",
                    tenant.tenant_id,
                    node_ids,
                )
                affected += _rowcount(res)
    return affected


def _rowcount(status: str) -> int:
    """Extrait le nombre de lignes affectées d'un tag de commande asyncpg."""
    # Format : "DELETE <n>" / "UPDATE <n>" / "INSERT 0 <n>".
    parts = status.split()
    return int(parts[-1]) if parts and parts[-1].isdigit() else 0
