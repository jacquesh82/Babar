"""Tests unitaires du linearizer (sélection gloutonne budgétée, sans DB)."""

from __future__ import annotations

from uuid import uuid4

from context_builder.linearizer import count_tokens, linearize, verbalize
from interface.common.schemas import TenantContext
from retrieval.scorer import ScoredFact

TENANT = TenantContext(tenant_id=uuid4())


def _fact(text: str, s: float) -> ScoredFact:
    return ScoredFact(edge_id=None, node_ids=[], text=text, score=s, components={"relevance": s})


def test_count_tokens_heuristic():
    assert count_tokens("") == 0
    assert count_tokens("a") == 1
    assert count_tokens("abcd") == 1  # 4 chars ≈ 1 token
    assert count_tokens("abcde") == 2


def test_verbalize_capitalizes_and_punctuates():
    assert verbalize(_fact("alice knows bob", 1.0)) == "Alice knows bob."
    assert verbalize(_fact("Bob lives in Paris.", 1.0)) == "Bob lives in Paris."


def test_all_facts_fit_under_large_budget():
    facts = [_fact("alice knows bob", 0.9), _fact("bob lives in paris", 0.5)]
    resp = linearize(TENANT, facts, token_budget=1000)
    assert len(resp.items) == 2
    assert resp.tokens_used <= 1000
    assert resp.items[0].text.startswith("Alice")
    assert resp.context.splitlines() == [i.text for i in resp.items]


def test_budget_is_strict():
    facts = [_fact("alice knows bob", 0.9), _fact("bob lives in paris", 0.5)]
    first_cost = count_tokens(verbalize(facts[0]))
    # Budget = coût du premier fait exactement → un seul fait sélectionné.
    resp = linearize(TENANT, facts, token_budget=first_cost)
    assert len(resp.items) == 1
    assert resp.tokens_used == first_cost


def test_budget_smaller_than_first_fact_selects_nothing():
    facts = [_fact("alice knows bob", 0.9)]
    resp = linearize(TENANT, facts, token_budget=1)
    assert resp.items == []
    assert resp.context == ""
    assert resp.tokens_used == 0


def test_selection_stops_at_first_overflow():
    # Deux faits de coût connu ; budget laisse passer seulement le premier.
    big = _fact("x" * 40, 0.9)  # ~10 tokens
    small = _fact("y" * 4, 0.5)  # ~1 token
    budget = count_tokens(verbalize(big))  # juste de quoi le premier
    resp = linearize(TENANT, [big, small], token_budget=budget)
    assert len(resp.items) == 1
    assert resp.items[0].text.startswith("X")
