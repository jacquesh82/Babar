"""Recherche de similarité sémantique (ANN) via pgvector.

Complète l'activation par graphe : capte les faits sémantiquement proches de la
question même sans lien de graphe direct avec les entités identifiées.

Délègue à ``storage/vector_store`` : orchestre embedding(question) → search et
renvoie des similarités normalisées [0, 1] pour le ``scorer``.
"""

from __future__ import annotations

from uuid import UUID

from interface.common.schemas import TenantContext
from storage import vector_store


async def search(tenant: TenantContext, query: str, top_k: int = 20) -> list[tuple[UUID, float]]:
    """Retourne ``[(node_id, similarité)]`` sémantiquement proches de la question."""
    query_embedding = vector_store.embed(query)
    return await vector_store.search(tenant, query_embedding, top_k=top_k)
