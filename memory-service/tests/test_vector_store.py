"""Tests du vector store.

L'embedding local est **pur et déterministe** → testé sans backend. Le stockage
et la recherche ANN nécessitent pgvector (extension) → *skippés* sinon.
"""
from __future__ import annotations

import math
from uuid import uuid4

import pytest

from config import settings
from interface.common.schemas import TenantContext
from storage import db, vector_store


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # vecteurs déjà normalisés L2


# --- embedding (pur) -------------------------------------------------------- #
def test_embed_has_configured_dimension():
    assert len(vector_store.embed("hello world")) == settings.embedding_dim


def test_embed_is_l2_normalized():
    norm = math.sqrt(sum(v * v for v in vector_store.embed("paris france")))
    assert norm == pytest.approx(1.0, abs=1e-6)


def test_embed_is_deterministic():
    assert vector_store.embed("same text") == vector_store.embed("same text")


def test_identical_text_has_cosine_one():
    v = vector_store.embed("alice lives in paris")
    assert _cosine(v, v) == pytest.approx(1.0, abs=1e-6)


def test_related_text_more_similar_than_unrelated():
    base = vector_store.embed("paris france capital")
    related = vector_store.embed("paris is the capital of france")
    unrelated = vector_store.embed("quantum chromodynamics lattice")
    assert _cosine(base, related) > _cosine(base, unrelated)


def test_empty_text_yields_zero_vector():
    assert all(v == 0.0 for v in vector_store.embed(""))


# --- stockage / recherche ANN (intégration pgvector) ------------------------ #
pytestmark_note = "pgvector requis"


async def _pgvector_available() -> bool:
    if not await db.ping():
        return False
    try:
        async with db.acquire() as conn:
            return bool(await conn.fetchval("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
    except Exception:
        return False


@pytest.fixture
async def tenant():
    if not await _pgvector_available():
        pytest.skip("pgvector indisponible — test d'intégration skippé")
    yield TenantContext(tenant_id=uuid4())


@pytest.mark.asyncio
async def test_search_returns_nearest_node(tenant):
    from storage import graph_store

    paris = await graph_store.upsert_node(tenant, "paris", "Paris")
    berlin = await graph_store.upsert_node(tenant, "berlin", "Berlin")
    await vector_store.upsert_embedding(tenant, paris, vector_store.embed("Paris"))
    await vector_store.upsert_embedding(tenant, berlin, vector_store.embed("Berlin"))

    hits = await vector_store.search(tenant, vector_store.embed("Paris"), top_k=1)
    assert hits and hits[0][0] == paris
