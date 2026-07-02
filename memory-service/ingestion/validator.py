"""Dédoublonnage et contrôle de cohérence des triples.

Dernière étape de l'ingestion avant écriture buffer. Reçoit des triples déjà
résolus (coréférence faite en amont dans ``coref_resolver.py``) et :
  * écarte les doublons **quasi** (égalité après normalisation casse/espaces) ;
  * vérifie la cohérence de forme (parties non vides, ``confidence`` ∈ [0, 1]) ;
  * **marque** les contradictions candidates (même sujet + prédicat fonctionnel,
    objets différents) sans les résoudre — l'arbitrage revient au worker de
    consolidation (``consolidation/merger.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from interface.common.schemas import TenantContext, Triple

# Prédicats mono-valués : deux objets différents = contradiction candidate.
_FUNCTIONAL_PREDICATES = {"has_name", "has_age", "lives_in", "born_in", "works_at"}


@dataclass
class ValidationResult:
    accepted: list[Triple] = field(default_factory=list)
    rejected: list[Triple] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    # Contradictions détectées (non résolues) : {subject, predicate, objects}.
    contradiction_candidates: list[dict] = field(default_factory=list)


def _norm(value: str) -> str:
    """Normalise pour la comparaison : minuscule + espaces compactés."""
    return " ".join(value.strip().lower().split())


def _fingerprint(triple: Triple) -> str:
    return f"{_norm(triple.subject)}|{_norm(triple.predicate)}|{_norm(triple.object)}"


def validate(triples: list[Triple], tenant: TenantContext) -> ValidationResult:
    """Dédoublonne (quasi) et contrôle la cohérence d'un lot de triples.

    Ne résout pas les contradictions : elle les **signale** pour le worker.
    """
    result = ValidationResult()
    seen: set[str] = set()
    functional_objects: dict[tuple[str, str], str] = {}

    for triple in triples:
        parts_ok = all(_norm(p) for p in (triple.subject, triple.predicate, triple.object))
        if not parts_ok:
            result.rejected.append(triple)
            result.reasons.append(f"incohérent (partie vide) : {_fingerprint(triple)}")
            continue
        if not 0.0 <= triple.confidence <= 1.0:
            result.rejected.append(triple)
            result.reasons.append(f"confidence hors [0,1] : {_fingerprint(triple)}")
            continue

        fingerprint = _fingerprint(triple)
        if fingerprint in seen:
            result.rejected.append(triple)
            result.reasons.append(f"doublon : {fingerprint}")
            continue
        seen.add(fingerprint)

        subject, predicate, obj = _norm(triple.subject), _norm(triple.predicate), _norm(triple.object)
        if predicate in _FUNCTIONAL_PREDICATES:
            key = (subject, predicate)
            previous = functional_objects.get(key)
            if previous is not None and previous != obj:
                result.contradiction_candidates.append(
                    {"subject": subject, "predicate": predicate, "objects": [previous, obj]}
                )
                result.reasons.append(
                    f"contradiction candidate : {subject} {predicate} {previous!r} vs {obj!r}"
                )
            else:
                functional_objects[key] = obj

        result.accepted.append(triple)

    return result
