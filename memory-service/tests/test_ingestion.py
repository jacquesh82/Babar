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


def test_extractor_ignores_negation_object():
    # "my name is not Bob" ne doit pas produire has_name="not".
    triples = extractor.extract_triples("My name is not Bob.", TENANT)
    assert all(t.object.lower() != "not" for t in triples)


def test_extractor_family_relation():
    triples = extractor.extract_triples("My sister is Alice. My dog is Rex.", TENANT)
    by_pred = {t.predicate: t for t in triples}
    assert by_pred["has_sister"].object == "Alice"
    assert by_pred["has_sister"].permanent is True
    assert by_pred["has_dog"].object == "Rex"


def test_extractor_job_as():
    triples = extractor.extract_triples("I work as a nurse.", TENANT)
    by_pred = {t.predicate: t for t in triples}
    assert by_pred["works_as"].object == "nurse"


def test_extractor_backend_is_pluggable():
    # Un backend inconnu retombe sur l'heuristique (pas d'échec dur).
    from config import settings

    original = settings.extraction_backend
    try:
        settings.extraction_backend = "does-not-exist"
        assert extractor.extract_triples("My name is Bob.", TENANT)
    finally:
        settings.extraction_backend = original


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


def test_validator_quasi_dedupes_case_and_spaces():
    a = Triple(subject="user", predicate="likes", object="Coffee")
    b = Triple(subject="User", predicate="likes", object=" coffee ")
    result = validator.validate([a, b], TENANT)
    assert len(result.accepted) == 1  # normalisation → même empreinte
    assert len(result.rejected) == 1


def test_validator_flags_contradiction_candidate():
    a = Triple(subject="user", predicate="lives_in", object="paris")
    b = Triple(subject="user", predicate="lives_in", object="london")
    result = validator.validate([a, b], TENANT)
    # Les deux sont acceptés (le worker tranchera), mais la contradiction est signalée.
    assert len(result.accepted) == 2
    assert len(result.contradiction_candidates) == 1
    cand = result.contradiction_candidates[0]
    assert cand["predicate"] == "lives_in"
    assert set(cand["objects"]) == {"paris", "london"}


def test_validator_multivalue_predicate_not_flagged():
    a = Triple(subject="user", predicate="likes", object="coffee")
    b = Triple(subject="user", predicate="likes", object="tea")
    result = validator.validate([a, b], TENANT)
    assert len(result.accepted) == 2
    assert result.contradiction_candidates == []  # "likes" est multi-valué


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
