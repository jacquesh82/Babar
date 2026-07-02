"""Tests de l'observabilité (tracing).

``new_trace_id`` et la journalisation structurée sont purs. La persistance de la
trace de rappel nécessite Postgres (table ``recall_log``) → skip sinon.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from interface.common.schemas import TenantContext
from observability import tracing
from storage import db

TENANT = TenantContext(tenant_id=uuid4())


def test_new_trace_id_is_unique_hex():
    a, b = tracing.new_trace_id(), tracing.new_trace_id()
    assert a != b
    assert len(a) == 32 and all(c in "0123456789abcdef" for c in a)


def test_log_recall_does_not_raise():
    # Journalisation structurée : ne doit jamais lever.
    tracing.log_recall("t1", TENANT, "q", [{"edge_id": "x"}], [], 5, 100)


@pytest.mark.asyncio
async def test_persist_recall_writes_row():
    if not await db.ping():
        pytest.skip("Postgres indisponible — test d'intégration skippé")
    tenant = TenantContext(tenant_id=uuid4())
    trace_id = tracing.new_trace_id()
    await tracing.persist_recall(
        trace_id, tenant, "où habite alice", [{"edge_id": "e1"}], [], 12, 200
    )
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT query, tokens_used FROM recall_log WHERE trace_id = $1", trace_id
        )
    assert row is not None
    assert row["query"] == "où habite alice"
    assert row["tokens_used"] == 12


@pytest.mark.asyncio
async def test_persist_recall_is_best_effort():
    # persist_recall attrape toute erreur interne (DB absente/table manquante) :
    # l'appel ne doit jamais lever, quel que soit l'état du backend.
    await tracing.persist_recall("t", TENANT, "q", [], [], 0, 0)
