"""Fusion des doublons et résolution des contradictions.

Exécuté par le worker de consolidation (cron nocturne). Deux responsabilités :
  1. **Fusion de doublons** : arêtes ouvertes identiques → une seule.
  2. **Résolution de contradictions** : deux faits incompatibles sur le même
     sujet/prédicat *fonctionnel* (mono-valué : ``has_name``, ``lives_in``…).

Règle d'arbitrage retenue : **dernière-écriture-gagne (LWW) avec fermeture
temporelle** — l'arête la plus récente (``recorded_at``) reste ouverte, les plus
anciennes en conflit reçoivent ``valid_until = now`` (elles restent auditables).
La stratégie ``llm_arbitration`` est prévue mais retombe pour l'instant sur LWW
(loggué), pour ne jamais bloquer la consolidation.

Contrainte non négociable #4 : TOUTE contradiction traitée est **loguée**
(``contradiction_log`` + ``observability/tracing``), jamais résolue silencieusement.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from interface.common.schemas import TenantContext
from observability.tracing import log_contradiction
from storage.db import acquire

# Prédicats mono-valués : un seul objet valide à la fois → arbitrage LWW.
# (Les prédicats multi-valués comme "likes" ne créent pas de contradiction.)
_FUNCTIONAL_PREDICATES = ["has_name", "has_age", "lives_in", "born_in", "works_at"]


class ContradictionStrategy(str, Enum):
    LWW = "lww"                       # dernière-écriture-gagne (défaut)
    LLM_ARBITRATION = "llm_arbitration"


@dataclass
class MergeReport:
    merged_nodes: int = 0
    merged_edges: int = 0
    contradictions_resolved: int = 0


async def merge_duplicates(tenant: TenantContext) -> MergeReport:
    """Fusionne les arêtes ouvertes strictement identiques (même triple).

    Conserve la plus ancienne, supprime les surnuméraires. Les nœuds sont déjà
    dédoublonnés par la contrainte ``UNIQUE (tenant_id, canonical_key)``.
    """
    report = MergeReport()
    async with acquire() as conn:
        groups = await conn.fetch(
            """
            SELECT array_agg(id ORDER BY recorded_at) AS ids
              FROM memory_edges
             WHERE tenant_id = $1 AND valid_until IS NULL
             GROUP BY subject_id, predicate, object_id
            HAVING count(*) > 1
            """,
            tenant.tenant_id,
        )
        for group in groups:
            surplus = group["ids"][1:]  # on garde le premier (le plus ancien)
            if surplus:
                await conn.execute(
                    "DELETE FROM memory_edges WHERE tenant_id = $1 AND id = ANY($2::uuid[])",
                    tenant.tenant_id,
                    surplus,
                )
                report.merged_edges += len(surplus)
    return report


async def resolve_contradictions(
    tenant: TenantContext,
    strategy: ContradictionStrategy = ContradictionStrategy.LWW,
) -> MergeReport:
    """Résout les contradictions des prédicats fonctionnels (LWW + fermeture).

    Pour chaque ``(sujet, prédicat)`` fonctionnel ayant plusieurs arêtes ouvertes
    vers des objets différents : on garde la plus récente, on ferme les autres et
    on LOGUE chaque décision (obligatoire).
    """
    report = MergeReport()
    async with acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """
                SELECT id, subject_id, predicate, object_id, recorded_at
                  FROM memory_edges
                 WHERE tenant_id = $1
                   AND valid_until IS NULL
                   AND predicate = ANY($2)
                 ORDER BY subject_id, predicate, recorded_at DESC
                """,
                tenant.tenant_id,
                _FUNCTIONAL_PREDICATES,
            )

            # Groupement (sujet, prédicat) — la 1re ligne de chaque groupe est la
            # plus récente (kept) grâce à l'ORDER BY recorded_at DESC.
            groups: dict[tuple, list] = {}
            for row in rows:
                groups.setdefault((row["subject_id"], row["predicate"]), []).append(row)

            for (subject_id, predicate), edges in groups.items():
                kept = edges[0]
                for dropped in edges[1:]:
                    if dropped["object_id"] == kept["object_id"]:
                        continue  # même objet → doublon (géré par merge_duplicates)
                    await conn.execute(
                        """
                        UPDATE memory_edges SET valid_until = now()
                         WHERE id = $1 AND tenant_id = $2 AND valid_until IS NULL
                        """,
                        dropped["id"],
                        tenant.tenant_id,
                    )
                    detail = {
                        "predicate": predicate,
                        "kept_object": str(kept["object_id"]),
                        "dropped_object": str(dropped["object_id"]),
                        "strategy": strategy.value,
                    }
                    await conn.execute(
                        """
                        INSERT INTO contradiction_log
                            (tenant_id, kept_edge_id, dropped_edge_id, strategy, detail)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        tenant.tenant_id,
                        kept["id"],
                        dropped["id"],
                        strategy.value,
                        detail,
                    )
                    log_contradiction(tenant, kept["id"], dropped["id"], strategy.value, detail)
                    report.contradictions_resolved += 1
    return report
