"""Point d'entrée du worker de consolidation (job asynchrone périodique).

Déclenché par cron nocturne (``CONSOLIDATION_CRON``). Orchestre, par tenant :
  1. promotion short-term → long-term (``storage/buffer_store.drain_promotable``)
  2. fusion doublons + résolution contradictions (``consolidation/merger``)
  3. decay des faits situationnels (``consolidation/decay``)

Le choix de l'ordonnanceur (Celery vs arq) est ISOLÉ ici et n'impacte aucun
autre module. Ce fichier fournit un ``main`` minimal exécutable par
``python -m consolidation.worker`` (voir docker-compose service ``worker``).
"""
from __future__ import annotations


async def run_consolidation_cycle() -> None:
    """Exécute un cycle complet de consolidation pour tous les tenants.

    TODO:
        - Itérer les tenants actifs.
        - Enchaîner promotion → merge → decay avec journalisation par étape.
        - Rendre chaque étape idempotente / réentrante.
    """
    raise NotImplementedError("worker.run_consolidation_cycle — stub")


def main() -> None:
    """Entrée CLI. À remplacer par l'ordonnanceur choisi (Celery/arq).

    TODO: brancher le scheduler réel ; pour l'instant, exécution one-shot.
    """
    raise NotImplementedError("worker.main — stub (Celery/arq à trancher)")


if __name__ == "__main__":
    main()
