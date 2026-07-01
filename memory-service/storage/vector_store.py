"""Stockage et recherche d'embeddings via pgvector.

Table ``memory_embeddings`` (1 vecteur par nœud). Volontairement séparé de
``graph_store`` pour rester agnostique du modèle/dimension d'embedding.

Provider-agnostic : le backend d'embedding (local/ONNX de préférence) est
encapsulé ici ; aucun autre module ne connaît le modèle utilisé.
"""
from __future__ import annotations

from uuid import UUID

from interface.common.schemas import TenantContext


async def upsert_embedding(
    tenant: TenantContext, node_id: UUID, embedding: list[float], model: str
) -> None:
    """Enregistre/actualise le vecteur d'un nœud."""
    raise NotImplementedError("vector_store.upsert_embedding — stub")


async def search(
    tenant: TenantContext, query_embedding: list[float], top_k: int = 20
) -> list[tuple[UUID, float]]:
    """Recherche ANN (cosine) scopée tenant → ``[(node_id, similarité)]``.

    TODO: filtre ``WHERE tenant_id = :tenant`` AVANT l'ORDER BY vector, pour
    ne jamais fuiter d'un tenant à l'autre.
    """
    raise NotImplementedError("vector_store.search — stub")


def embed(text: str) -> list[float]:
    """Calcule l'embedding d'un texte via le backend configuré.

    TODO: brancher EMBEDDING_BACKEND (local recommandé). Dimension = EMBEDDING_DIM.
    """
    raise NotImplementedError("vector_store.embed — stub")
