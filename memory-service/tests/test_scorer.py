"""Tests unitaires du scorer (fonction pure, sans DB)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from interface.common.schemas import TenantContext
from retrieval.scorer import DEFAULT_WEIGHTS, score

TENANT = TenantContext(tenant_id=uuid4())
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _cand(**over):
    base = {
        "id": uuid4(),
        "subject_id": uuid4(),
        "object_id": uuid4(),
        "predicate": "knows",
        "subject_label": "Alice",
        "object_label": "Bob",
        "weight": 1.0,
        "importance": 0.5,
        "valid_from": NOW,
        "hops": 1,
    }
    base.update(over)
    return base


def test_components_are_bounded_0_1():
    facts = score(TENANT, [_cand()], now=NOW)
    comp = facts[0].components
    assert set(comp) == set(DEFAULT_WEIGHTS)
    assert all(0.0 <= v <= 1.0 for v in comp.values())
    assert 0.0 <= facts[0].score <= 1.0


def test_closer_hop_ranks_higher_all_else_equal():
    near = _cand(hops=1, importance=0.5)
    far = _cand(hops=3, importance=0.5)
    facts = score(TENANT, [far, near], now=NOW)
    assert facts[0].reason["hops"] == 1        # le plus proche remonte en tête


def test_higher_importance_ranks_higher():
    strong = _cand(importance=0.9)
    weak = _cand(importance=0.1)
    facts = score(TENANT, [weak, strong], now=NOW)
    assert facts[0].components["importance"] == 0.9


def test_recency_decays_with_age():
    fresh = _cand(valid_from=NOW)
    old = _cand(valid_from=NOW - timedelta(days=365))
    facts = score(TENANT, [old, fresh], now=NOW)
    fresh_fact = next(f for f in facts if f.components["recency"] > 0.9)
    old_fact = next(f for f in facts if f.components["recency"] < 0.1)
    assert fresh_fact.score > old_fact.score


def test_vector_similarity_feeds_relevance():
    subj = uuid4()
    cand = _cand(subject_id=subj, hops=3)          # loin dans le graphe
    facts = score(TENANT, [cand], vector_candidates=[(subj, 0.95)], now=NOW)
    # La forte similarité vecteur domine la faible proximité de graphe.
    assert facts[0].components["relevance"] == 0.95


def test_text_uses_labels():
    facts = score(TENANT, [_cand(subject_label="Alice", object_label="Paris", predicate="lives_in")], now=NOW)
    assert facts[0].text == "Alice lives_in Paris"
