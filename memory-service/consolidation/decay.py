"""Décroissance d'importance des faits.

Exécuté par le worker de consolidation. Réduit progressivement l'``importance``
des faits **situationnels** pour que la mémoire privilégie l'information vive.

Contrainte non négociable #3 : **pas de decay uniforme**. La distinction est
portée par les données elles-mêmes :
  * ``permanent = TRUE``  → fait "permanent déclaré", **jamais** de decay
    (ex: date de naissance, préférence stable revendiquée).
  * ``permanent = FALSE`` → fait "situationnel", decay actif au ``decay_rate``
    propre de la ligne (0 = pas de decay).

Aucune fonction globale n'est appliquée aveuglément à toutes les lignes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from interface.common.schemas import TenantContext
from storage.db import acquire


@dataclass
class DecayReport:
    edges_decayed: int = 0
    nodes_decayed: int = 0
    skipped_permanent: int = 0


def new_importance(current: float, decay_rate: float, elapsed_seconds: float) -> float:
    """Calcule la nouvelle importance après decay (fonction pure).

    Modèle exponentiel : ``current * exp(-decay_rate * jours_écoulés)``, borné
    dans [0, 1]. Renvoie ``current`` inchangé si ``decay_rate`` ou l'élapsé ≤ 0.
    """
    if decay_rate <= 0 or elapsed_seconds <= 0:
        return current
    elapsed_days = elapsed_seconds / 86400.0
    decayed = current * math.exp(-decay_rate * elapsed_days)
    return max(0.0, min(1.0, decayed))


async def _decay_table(conn, table: str, tenant: TenantContext) -> int:
    rows = await conn.fetch(
        f"""
        SELECT id, importance, decay_rate,
               EXTRACT(EPOCH FROM (now() - importance_updated_at)) AS elapsed
          FROM {table}
         WHERE tenant_id = $1 AND permanent = FALSE AND decay_rate > 0
        """,
        tenant.tenant_id,
    )
    count = 0
    for row in rows:
        updated = new_importance(row["importance"], row["decay_rate"], float(row["elapsed"]))
        await conn.execute(
            f"UPDATE {table} SET importance = $3, importance_updated_at = now() "
            f"WHERE id = $1 AND tenant_id = $2",
            row["id"],
            tenant.tenant_id,
            updated,
        )
        count += 1
    return count


async def apply_decay(tenant: TenantContext) -> DecayReport:
    """Applique le decay aux faits situationnels du tenant.

    Ne traite QUE ``permanent = FALSE`` (les permanents sont comptés en skip et
    jamais modifiés). Ne supprime jamais par decay (un seuil d'oubli éventuel
    serait une décision séparée et documentée).
    """
    async with acquire() as conn:
        async with conn.transaction():
            edges = await _decay_table(conn, "memory_edges", tenant)
            nodes = await _decay_table(conn, "memory_nodes", tenant)
            skipped = await conn.fetchval(
                "SELECT count(*) FROM memory_edges WHERE tenant_id = $1 AND permanent = TRUE",
                tenant.tenant_id,
            )
    return DecayReport(edges_decayed=edges, nodes_decayed=nodes, skipped_permanent=int(skipped))
