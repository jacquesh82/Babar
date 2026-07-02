"""Test d'intégration du flux de rappel complet (nécessite Postgres — skip sinon).

Couvre le read path bout-en-bout : ingestion d'arêtes → ``entity_linker`` →
``graph_walker`` → ``scorer`` → ``linearizer``, via l'endpoint applicatif.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from interface.api_rest import recall
from interface.common.schemas import RecallRequest, TenantContext, Triple
from storage import db, graph_store

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def tenant():
    if not await db.ping():
        pytest.skip("Postgres indisponible — test d'intégration skippé")
    yield TenantContext(tenant_id=uuid4())


async def test_recall_returns_relevant_context(tenant):
    await graph_store.add_edge(
        tenant, Triple(subject="alice", predicate="lives_in", object="paris")
    )
    await graph_store.add_edge(tenant, Triple(subject="alice", predicate="likes", object="coffee"))

    req = RecallRequest(tenant=tenant, query="Where does alice live?", token_budget=200)
    resp = await recall(req, tenant=tenant)

    assert "Alice" in resp.context
    assert resp.tokens_used <= 200
    assert resp.trace_id


async def test_recall_no_entity_returns_empty(tenant):
    req = RecallRequest(tenant=tenant, query="unknown topic zzz", token_budget=200)
    resp = await recall(req, tenant=tenant)
    assert resp.context == ""
    assert resp.trace_id
