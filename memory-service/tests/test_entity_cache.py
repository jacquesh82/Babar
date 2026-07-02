"""Tests du cache de requêtes de l'entity_linker (nécessitent Redis — skip sinon)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from interface.common.schemas import TenantContext
from retrieval import entity_linker
from storage import db, graph_store, redis_client

pytestmark = pytest.mark.asyncio


async def _redis_ok() -> bool:
    try:
        await redis_client.get_redis().ping()
        return True
    except Exception:
        return False


@pytest.fixture
async def tenant():
    if not await _redis_ok():
        pytest.skip("Redis indisponible — test d'intégration skippé")
    yield TenantContext(tenant_id=uuid4())


async def test_cache_set_then_get_roundtrip(tenant):
    ids = [uuid4(), uuid4()]
    assert await entity_linker.cache_get(tenant, "où habite alice") is None
    await entity_linker.cache_set(tenant, "où habite alice", ids)
    assert await entity_linker.cache_get(tenant, "où habite alice") == ids


async def test_cache_is_scoped_by_tenant(tenant):
    other = TenantContext(tenant_id=uuid4())
    await entity_linker.cache_set(tenant, "q", [uuid4()])
    assert await entity_linker.cache_get(other, "q") is None


async def test_invalidate_clears_tenant_cache(tenant):
    await entity_linker.cache_set(tenant, "q1", [uuid4()])
    await entity_linker.cache_set(tenant, "q2", [uuid4()])
    await entity_linker.invalidate(tenant)
    assert await entity_linker.cache_get(tenant, "q1") is None
    assert await entity_linker.cache_get(tenant, "q2") is None


async def test_link_populates_cache(tenant):
    if not await db.ping():
        pytest.skip("Postgres indisponible — test d'intégration skippé")
    await graph_store.upsert_node(tenant, "alice", "Alice")

    first = await entity_linker.link(tenant, "alice")
    assert first  # entité trouvée
    # La requête est désormais en cache et rend le même résultat.
    assert await entity_linker.cache_get(tenant, "alice") == first
