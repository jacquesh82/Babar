"""Tests unitaires du write path (extraction / coréférence / validation / promotion).

Purs — sans Redis ni DB.
"""

from __future__ import annotations

from uuid import uuid4

from ingestion import coref_resolver, extractor, validator
from interface.common.schemas import TenantContext, Triple
from storage.buffer_store import should_promote

TENANT = TenantContext(tenant_id=uuid4())


# --- extractor -------------------------------------------------------------- #
def test_extractor_pulls_personal_facts():
    text = "My name is Alice. I live in Paris. I love coffee."
    triples = extractor.extract_triples(text, TENANT)
    by_pred = {t.predicate: t for t in triples}
    assert by_pred["has_name"].object == "Alice"
    assert by_pred["lives_in"].object == "Paris"
    assert by_pred["likes"].object == "coffee"


def test_extractor_marks_permanence():
    triples = extractor.extract_triples("My name is Bob. I live in Berlin.", TENANT)
    by_pred = {t.predicate: t for t in triples}
    assert by_pred["has_name"].permanent is True  # nom = permanent
    assert by_pred["lives_in"].permanent is False  # résidence = situationnel
    assert by_pred["lives_in"].decay_rate > 0.0


def test_extractor_empty_when_no_match():
    assert extractor.extract_triples("The weather is nice today.", TENANT) == []


# --- coref_resolver --------------------------------------------------------- #
def test_canonicalize_maps_first_person_to_user():
    assert coref_resolver.canonicalize("I") == "user"
    assert coref_resolver.canonicalize("  My ") == "user"


def test_canonicalize_normalizes_whitespace_and_case():
    assert coref_resolver.canonicalize("  New   York ") == "new york"


def test_resolve_rewrites_subject_object():
    t = Triple(subject="I", predicate="lives_in", object="  Paris ")
    (out,) = coref_resolver.resolve([t], TENANT)
    assert out.subject == "user"
    assert out.object == "paris"


# --- validator -------------------------------------------------------------- #
def test_validator_dedupes_exact():
    t = Triple(subject="user", predicate="likes", object="coffee")
    result = validator.validate([t, t], TENANT)
    assert len(result.accepted) == 1
    assert len(result.rejected) == 1
    assert any("doublon" in r for r in result.reasons)


def test_validator_rejects_empty_part():
    bad = Triple(subject="user", predicate="likes", object="   ")
    result = validator.validate([bad], TENANT)
    assert result.accepted == []
    assert len(result.rejected) == 1


# --- should_promote (critère explicite) ------------------------------------- #
def test_promote_permanent_immediately():
    t = Triple(subject="user", predicate="has_name", object="Alice", permanent=True)
    assert should_promote(t, occurrences=1, age_seconds=0.0) is True


def test_promote_on_repetition():
    t = Triple(subject="user", predicate="likes", object="coffee")
    assert should_promote(t, occurrences=3, age_seconds=0.0) is True
    assert should_promote(t, occurrences=1, age_seconds=0.0) is False


def test_promote_on_age_and_confidence():
    t = Triple(subject="user", predicate="likes", object="tea", confidence=0.9)
    assert should_promote(t, occurrences=1, age_seconds=7200.0) is True
    low_conf = Triple(subject="user", predicate="likes", object="tea", confidence=0.3)
    assert should_promote(low_conf, occurrences=1, age_seconds=7200.0) is False
