"""Test d'intégration du graph_walker (nécessite un Postgres réel — skip sinon)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from interface.common.schemas import TenantContext, Triple
from retrieval import graph_walker
from storage import db, graph_store

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def tenant():
    if not await db.ping():
        pytest.skip("Postgres indisponible — test d'intégration skippé")
    yield TenantContext(tenant_id=uuid4())


async def test_walk_two_hops_collects_enriched_edges(tenant):
    # alice -knows-> bob -lives_in-> paris
    await graph_store.add_edge(tenant, Triple(subject="alice", predicate="knows", object="bob"))
    await graph_store.add_edge(tenant, Triple(subject="bob", predicate="lives_in", object="paris"))
    alice = await graph_store.upsert_node(tenant, "alice", "alice")

    result = await graph_walker.walk(tenant, [alice], max_hops=2, top_k_per_node=10)

    predicates = {e["predicate"] for e in result.edges}
    assert {"knows", "lives_in"} <= predicates
    # Les arêtes sont enrichies (labels + hops) pour le scorer.
    assert all("subject_label" in e and "hops" in e for e in result.edges)


async def test_walk_respects_max_hops(tenant):
    await graph_store.add_edge(tenant, Triple(subject="a", predicate="r1", object="b"))
    await graph_store.add_edge(tenant, Triple(subject="b", predicate="r2", object="c"))
    a = await graph_store.upsert_node(tenant, "a", "a")

    result = await graph_walker.walk(tenant, [a], max_hops=1)
    assert {e["predicate"] for e in result.edges} == {"r1"}  # r2 est au 2e saut
