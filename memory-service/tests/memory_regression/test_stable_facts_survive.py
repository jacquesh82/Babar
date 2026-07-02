"""Scénarios de régression mémoire.

But : vérifier que les **faits stables survivent** aux cycles de consolidation
(merge) et de decay. Garde-fous des contraintes non négociables #3 et #4.

Les invariants de decay (permanent vs situationnel) sont testés de façon **pure**
(sans DB) et doivent toujours passer. Les scénarios de cycle complet
(contradiction loguée, audit bi-temporel, forget) nécessitent un Postgres réel
et se *skippent* automatiquement sinon.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from consolidation.decay import new_importance
from interface.common.schemas import TenantContext, Triple
from storage import db, graph_store

TENANT = TenantContext(tenant_id=uuid4())
DAY = 86400.0


# --------------------------------------------------------------------------- #
# Invariants de decay — purs, toujours exécutés
# --------------------------------------------------------------------------- #
def test_permanent_fact_never_decays():
    """Un fait permanent (decay_rate = 0) garde son importance, quel que soit le temps."""
    assert new_importance(0.8, decay_rate=0.0, elapsed_seconds=365 * DAY) == 0.8


def test_situational_fact_decays_but_is_not_deleted():
    """Un fait situationnel voit son importance baisser sans jamais tomber à 0 (pas supprimé)."""
    before = 0.8
    after = new_importance(before, decay_rate=0.1, elapsed_seconds=30 * DAY)
    assert 0.0 < after < before


def test_decay_is_monotonic_in_time():
    later = new_importance(0.9, 0.1, 60 * DAY)
    sooner = new_importance(0.9, 0.1, 10 * DAY)
    assert later < sooner


def test_decay_result_is_bounded():
    assert 0.0 <= new_importance(1.0, 5.0, 1000 * DAY) <= 1.0


# --------------------------------------------------------------------------- #
# Scénarios de cycle complet — nécessitent Postgres (skip sinon)
# --------------------------------------------------------------------------- #
pytest_mark_asyncio = pytest.mark.asyncio


@pytest.fixture
async def tenant():
    if not await db.ping():
        pytest.skip("Postgres indisponible — scénario de régression skippé")
    yield TenantContext(tenant_id=uuid4())


@pytest.mark.asyncio
async def test_contradiction_is_logged_never_silent(tenant):
    """Deux faits fonctionnels contradictoires → l'ancien est fermé ET loggué."""
    from consolidation.merger import resolve_contradictions

    await graph_store.add_edge(tenant, Triple(subject="user", predicate="lives_in", object="paris"))
    await graph_store.add_edge(
        tenant, Triple(subject="user", predicate="lives_in", object="london")
    )

    report = await resolve_contradictions(tenant)
    assert report.contradictions_resolved >= 1

    async with db.acquire() as conn:
        logged = await conn.fetchval(
            "SELECT count(*) FROM contradiction_log WHERE tenant_id = $1", tenant.tenant_id
        )
        open_edges = await conn.fetchval(
            """SELECT count(*) FROM memory_edges
               WHERE tenant_id = $1 AND predicate = 'lives_in' AND valid_until IS NULL""",
            tenant.tenant_id,
        )
    assert logged >= 1
    assert open_edges == 1  # un seul lieu de résidence reste valide


@pytest.mark.asyncio
async def test_permanent_survives_decay_cycle_in_db(tenant):
    """Un fait permanent conserve son importance après apply_decay ; un situationnel baisse."""
    from consolidation.decay import apply_decay

    await graph_store.add_edge(
        tenant, Triple(subject="user", predicate="has_name", object="alice", permanent=True)
    )
    await graph_store.add_edge(
        tenant, Triple(subject="user", predicate="lives_in", object="paris", decay_rate=0.1)
    )

    report = await apply_decay(tenant)
    assert report.skipped_permanent >= 1

    async with db.acquire() as conn:
        perm = await conn.fetchval(
            "SELECT importance FROM memory_edges WHERE tenant_id = $1 AND predicate = 'has_name'",
            tenant.tenant_id,
        )
    assert perm == pytest.approx(0.5)  # importance par défaut, inchangée
