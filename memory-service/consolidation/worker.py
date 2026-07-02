"""Point d'entrée du worker de consolidation (job asynchrone périodique).

Déclenché par cron nocturne (``CONSOLIDATION_CRON``). Orchestre, par tenant :
  1. promotion short-term → long-term (``buffer_store.drain_promotable`` → ``graph_store.add_edge``)
  2. fusion doublons + résolution contradictions (``consolidation/merger``)
  3. decay des faits situationnels (``consolidation/decay``)

Le choix de l'ordonnanceur (Celery vs arq) est ISOLÉ ici et n'impacte aucun
autre module. Ce fichier fournit un ``main`` minimal exécutable par
``python -m consolidation.worker`` (voir docker-compose service ``worker``).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

from config import settings
from consolidation import decay, merger
from interface.common.schemas import TenantContext
from storage import buffer_store, graph_store
from storage.db import acquire, close_pool

logger = logging.getLogger("memory.worker")


@dataclass
class CycleReport:
    tenants: int = 0
    promoted: int = 0
    merged_edges: int = 0
    contradictions_resolved: int = 0
    edges_decayed: int = 0


async def promote_tenant(tenant: TenantContext) -> int:
    """Promeut les faits éligibles du buffer short-term vers le long-term."""
    promotable = await buffer_store.drain_promotable(tenant)
    for triple in promotable:
        await graph_store.add_edge(tenant, triple)
    return len(promotable)


async def _active_tenants() -> set[UUID]:
    """Découvre les tenants actifs (présents en base OU dans le buffer Redis)."""
    tenants: set[UUID] = set()
    async with acquire() as conn:
        for row in await conn.fetch("SELECT DISTINCT tenant_id FROM memory_nodes"):
            tenants.add(row["tenant_id"])
    try:
        redis = buffer_store._get_redis()
        async for key in redis.scan_iter("mem:buffer:*"):
            tenants.add(UUID(key.rsplit(":", 1)[-1]))
    except Exception:  # Redis optionnel pour la découverte
        logger.warning("découverte des tenants via Redis indisponible", exc_info=True)
    return tenants


async def run_consolidation_cycle() -> CycleReport:
    """Exécute un cycle complet de consolidation pour tous les tenants actifs."""
    strategy = merger.ContradictionStrategy(settings.contradiction_strategy)
    report = CycleReport()
    for tenant_id in await _active_tenants():
        tenant = TenantContext(tenant_id=tenant_id)
        report.promoted += await promote_tenant(tenant)
        try:  # indexation vectorielle des nouveaux nœuds (best-effort sans pgvector)
            from storage import vector_store

            await vector_store.reindex_tenant(tenant)
        except Exception:
            logger.warning("réindexation vectorielle indisponible", exc_info=True)
        report.merged_edges += (await merger.merge_duplicates(tenant)).merged_edges
        report.contradictions_resolved += (
            await merger.resolve_contradictions(tenant, strategy)
        ).contradictions_resolved
        report.edges_decayed += (await decay.apply_decay(tenant)).edges_decayed
        report.tenants += 1
    logger.info(
        "cycle terminé : %d tenants, %d promus, %d fusions, %d contradictions, %d decays",
        report.tenants,
        report.promoted,
        report.merged_edges,
        report.contradictions_resolved,
        report.edges_decayed,
    )
    return report


def main() -> None:
    """Entrée CLI. Exécution one-shot ; le scheduler (Celery/arq) reste à brancher.

    TODO: remplacer par l'ordonnanceur choisi, planifié sur ``CONSOLIDATION_CRON``.
    """
    logging.basicConfig(level=settings.log_level)

    async def _run() -> None:
        try:
            await run_consolidation_cycle()
        finally:
            await close_pool()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
