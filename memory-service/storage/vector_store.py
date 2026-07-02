"""Stockage et recherche d'embeddings via pgvector.

Table ``memory_embeddings`` (1 vecteur par nœud). Volontairement séparé de
``graph_store`` pour rester agnostique du modèle/dimension d'embedding.

Provider-agnostic : le backend d'embedding est encapsulé ici. L'implémentation
actuelle est un **embedding local déterministe** (hashing de n-grammes de
caractères, normalisé L2) — sans dépendance ni API payante. Il est remplaçable
par un vrai modèle local (ONNX/sentence-transformers) via ``EMBEDDING_BACKEND``
sans impacter les autres modules (voir TODO).
"""

from __future__ import annotations

import hashlib
import math
import re
from uuid import UUID

from config import settings
from interface.common.schemas import TenantContext
from storage.db import acquire

_MODEL_NAME = "local-hash-v1"
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


def _features(text: str) -> list[str]:
    """Traits d'un texte : mots + trigrammes de caractères (robustesse fautes).

    Retourne une liste vide si le texte ne contient aucun mot (→ vecteur nul).
    """
    words = _WORD_RE.findall(text.lower())
    feats: list[str] = list(words)
    for word in words:
        padded = f"#{word}#"
        feats.extend(padded[i : i + 3] for i in range(len(padded) - 2))
    return feats


def embed(text: str) -> list[float]:
    """Calcule l'embedding d'un texte via le backend configuré (déterministe).

    Dimension = ``EMBEDDING_DIM``. Vecteur normalisé L2 (cosinus stable).

    TODO: brancher un vrai modèle local si ``EMBEDDING_BACKEND != "local"``.
    """
    dim = settings.embedding_dim
    vec = [0.0] * dim
    for feature in _features(text):
        digest = int(hashlib.md5(feature.encode("utf-8")).hexdigest(), 16)
        vec[digest % dim] += 1.0 if (digest >> 7) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


async def upsert_embedding(
    tenant: TenantContext, node_id: UUID, embedding: list[float], model: str = _MODEL_NAME
) -> None:
    """Enregistre/actualise le vecteur d'un nœud (pgvector requis)."""
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO memory_embeddings (node_id, tenant_id, model, embedding)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (node_id) DO UPDATE
                SET embedding = EXCLUDED.embedding,
                    model     = EXCLUDED.model,
                    recorded_at = now()
            """,
            node_id,
            tenant.tenant_id,
            model,
            embedding,
        )


async def search(
    tenant: TenantContext, query_embedding: list[float], top_k: int = 20
) -> list[tuple[UUID, float]]:
    """Recherche ANN (cosine) scopée tenant → ``[(node_id, similarité∈[0,1])]``.

    Le filtre ``tenant_id`` est appliqué AVANT le tri vectoriel : aucune fuite
    inter-tenant. ``<=>`` est la distance cosinus pgvector ; similarité = 1 - dist.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT node_id, 1 - (embedding <=> $2) AS similarity
              FROM memory_embeddings
             WHERE tenant_id = $1
             ORDER BY embedding <=> $2
             LIMIT $3
            """,
            tenant.tenant_id,
            query_embedding,
            top_k,
        )
        return [(r["node_id"], float(r["similarity"])) for r in rows]


async def reindex_tenant(tenant: TenantContext, model: str = _MODEL_NAME) -> int:
    """Calcule les embeddings manquants des nœuds du tenant. Retourne le nombre créé.

    Appelé par le worker de consolidation après promotion. Idempotent : ne
    (re)traite que les nœuds dépourvus d'embedding.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, label FROM memory_nodes n
             WHERE tenant_id = $1
               AND NOT EXISTS (
                   SELECT 1 FROM memory_embeddings e WHERE e.node_id = n.id
               )
            """,
            tenant.tenant_id,
        )
    for row in rows:
        await upsert_embedding(tenant, row["id"], embed(row["label"]), model)
    return len(rows)
