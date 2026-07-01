"""Tests d'intégration de ``storage/graph_store`` (nécessitent un Postgres réel).

Ces tests sont automatiquement **skippés** si aucune base joignable n'est
configurée (``DATABASE_URL``). Ils valident le CRUD, l'isolation par tenant et
la bi-temporalité (fermeture d'arête / requête ``as_of``).

Lancement avec une base : ``docker compose up -d postgres`` puis
``DATABASE_URL=postgresql://memory:change-me@localhost:5432/memory pytest``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from interface.common.schemas import NodeType, TenantContext, Triple
from storage import db, graph_store

pytestmark = pytest.mark.asyncio


async def _db_available() -> bool:
    return await db.ping()


@pytest.fixture
async def tenant():
    if not await _db_available():
        pytest.skip("Postgres indisponible — test d'intégration skippé")
    # Tenant unique par run pour éviter les collisions.
    yield TenantContext(tenant_id=uuid4())


async def test_upsert_node_is_idempotent(tenant):
    n1 = await graph_store.upsert_node(tenant, "alice", "Alice", NodeType.PERSON)
    n2 = await graph_store.upsert_node(tenant, "alice", "Alice Cooper", NodeType.PERSON)
    assert n1 == n2
    node = await graph_store.get_node(tenant, n1)
    assert node["label"] == "Alice Cooper"


async def test_get_node_isolated_by_tenant(tenant):
    node_id = await graph_store.upsert_node(tenant, "bob", "Bob")
    other = TenantContext(tenant_id=uuid4())
    assert await graph_store.get_node(other, node_id) is None


async def test_add_edge_and_neighbors(tenant):
    triple = Triple(subject="alice", predicate="knows", object="bob")
    edge_id = await graph_store.add_edge(tenant, triple)
    assert isinstance(edge_id, UUID)
    subject = await graph_store.upsert_node(tenant, "alice", "alice")
    neigh = await graph_store.neighbors(tenant, subject, top_k=10)
    assert any(e["id"] == edge_id for e in neigh)


async def test_close_edge_bitemporal_as_of(tenant):
    triple = Triple(subject="alice", predicate="lives_in", object="paris")
    edge_id = await graph_store.add_edge(tenant, triple)
    subject = await graph_store.upsert_node(tenant, "alice", "alice")

    before_close = datetime.now(timezone.utc)
    await graph_store.close_edge(tenant, edge_id, valid_until=before_close)

    # Actuellement : l'arête fermée n'apparaît plus.
    current = await graph_store.neighbors(tenant, subject)
    assert all(e["id"] != edge_id for e in current)
