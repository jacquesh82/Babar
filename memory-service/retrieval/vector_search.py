"""Recherche de similarité sémantique (ANN) via pgvector.

Complète l'activation par graphe : capte les faits sémantiquement proches de la
question même sans lien de graphe direct avec les entités identifiées.

Fine délégation à ``storage/vector_store``. Ce module se limite à orchestrer
embedding(question) → search → normalisation des scores pour le ``scorer``.
"""
from __future__ import annotations

from uuid import UUID

from interface.common.schemas import TenantContext


async def search(tenant: TenantContext, query: str, top_k: int = 20) -> list[tuple[UUID, float]]:
    """Retourne ``[(node_id, similarité)]`` sémantiquement proches de la question.

    TODO:
        - embed(query) via vector_store, puis vector_store.search scopé tenant.
        - Normaliser la similarité dans [0,1] pour fusion avec les scores graphe.
    """
    raise NotImplementedError("vector_search.search — stub")
