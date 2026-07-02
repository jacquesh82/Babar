"""Test d'intégration du write path (nécessite Redis — skip sinon).

Couvre ``/v1/ingest`` : texte → extraction → buffer short-term, puis relecture
du buffer et sélection des faits promouvables.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from interface.api_rest import ingest
from interface.common.schemas import IngestRequest, TenantContext
from storage import buffer_store

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def tenant():
    # Le client Redis est lié à la boucle asyncio courante ; pytest-asyncio en
    # crée une par test → on repart d'un client neuf à chaque test.
    buffer_store._redis = None
    try:
        await buffer_store._get_redis().ping()
    except Exception:
        pytest.skip("Redis indisponible — test d'intégration skippé")

    ctx = TenantContext(tenant_id=uuid4())
    yield ctx

    # Nettoyage du buffer du tenant de test + fermeture du client.
    redis = buffer_store._get_redis()
    await redis.delete(buffer_store._buffer_key(ctx))
    await redis.aclose()
    buffer_store._redis = None


async def test_ingest_buffers_extracted_facts(tenant):
    req = IngestRequest(tenant=tenant, turn_text="My name is Alice. I live in Paris.")
    resp = await ingest(req, tenant=tenant)
    assert resp.accepted >= 2
    assert resp.buffered == resp.accepted

    buffered = await buffer_store.peek(tenant)
    predicates = {t.predicate for t in buffered}
    assert {"has_name", "lives_in"} <= predicates


async def test_permanent_fact_is_promotable(tenant):
    await ingest(IngestRequest(tenant=tenant, turn_text="My name is Bob."), tenant=tenant)
    promotable = await buffer_store.drain_promotable(tenant)
    # "has_name" est permanent → immédiatement promouvable.
    assert any(t.predicate == "has_name" for t in promotable)
    # Après drainage, le buffer ne contient plus le fait promu.
    assert all(t.predicate != "has_name" for t in await buffer_store.peek(tenant))
