"""Tests d'intégration du feedback /v1/correct (nécessitent Postgres — skip sinon)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from feedback.corrections import apply_correction
from interface.common.schemas import (
    CorrectionAction,
    CorrectionRequest,
    TenantContext,
    Triple,
)
from storage import db, graph_store

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def tenant():
    if not await db.ping():
        pytest.skip("Postgres indisponible — test d'intégration skippé")
    yield TenantContext(tenant_id=uuid4())


async def _open_edges(tenant, predicate="lives_in") -> int:
    async with db.acquire() as conn:
        return await conn.fetchval(
            "SELECT count(*) FROM memory_edges "
            "WHERE tenant_id = $1 AND predicate = $2 AND valid_until IS NULL",
            tenant.tenant_id,
            predicate,
        )


async def test_forget_closes_edge_but_keeps_row(tenant):
    edge_id = await graph_store.add_edge(
        tenant, Triple(subject="user", predicate="lives_in", object="paris")
    )
    req = CorrectionRequest(tenant=tenant, action=CorrectionAction.FORGET, edge_ids=[edge_id])

    resp = await apply_correction(tenant, req)
    assert resp.affected_edges == 1
    assert await _open_edges(tenant) == 0  # plus valide
    # La ligne existe toujours (audit préservé).
    async with db.acquire() as conn:
        still_there = await conn.fetchval(
            "SELECT count(*) FROM memory_edges WHERE id = $1", edge_id
        )
    assert still_there == 1


async def test_forget_by_natural_language(tenant):
    await graph_store.add_edge(tenant, Triple(subject="user", predicate="lives_in", object="paris"))
    req = CorrectionRequest(
        tenant=tenant, action=CorrectionAction.FORGET, natural_language="forget where user lives"
    )
    resp = await apply_correction(tenant, req)
    assert resp.affected_edges >= 1
    assert await _open_edges(tenant) == 0


async def test_update_closes_old_and_opens_new(tenant):
    old = await graph_store.add_edge(
        tenant, Triple(subject="user", predicate="lives_in", object="paris")
    )
    req = CorrectionRequest(
        tenant=tenant,
        action=CorrectionAction.UPDATE,
        edge_ids=[old],
        replacement=Triple(subject="user", predicate="lives_in", object="london"),
    )
    resp = await apply_correction(tenant, req)
    assert resp.affected_edges == 2  # 1 fermée + 1 ouverte
    assert await _open_edges(tenant) == 1  # seul "london" reste ouvert


async def test_hard_delete_removes_row(tenant):
    edge_id = await graph_store.add_edge(
        tenant, Triple(subject="user", predicate="likes", object="coffee")
    )
    req = CorrectionRequest(tenant=tenant, action=CorrectionAction.HARD_DELETE, edge_ids=[edge_id])
    await apply_correction(tenant, req)
    async with db.acquire() as conn:
        remaining = await conn.fetchval("SELECT count(*) FROM memory_edges WHERE id = $1", edge_id)
    assert remaining == 0
