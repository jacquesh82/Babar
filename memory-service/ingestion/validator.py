"""Dédoublonnage et contrôle de cohérence des triples.

Dernière étape de l'ingestion avant écriture buffer. Reçoit des triples déjà
résolus (coréférence faite en amont dans ``coref_resolver.py``) et :
  * écarte les doublons exacts (même sujet/prédicat/objet dans le lot) ;
  * vérifie la cohérence de forme (parties non vides, ``confidence`` ∈ [0, 1]) ;
  * (à venir) marque les contradictions *potentielles* pour arbitrage par le
    worker de consolidation — la validation ne tranche pas les contradictions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from interface.common.schemas import TenantContext, Triple


@dataclass
class ValidationResult:
    accepted: list[Triple] = field(default_factory=list)
    rejected: list[Triple] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def _fingerprint(triple: Triple) -> str:
    return f"{triple.subject}|{triple.predicate}|{triple.object}"


def validate(triples: list[Triple], tenant: TenantContext) -> ValidationResult:
    """Dédoublonne et contrôle la cohérence d'un lot de triples.

    TODO:
        - Dédup quasi (similarité objet), au-delà de l'égalité stricte.
        - Détecter les contradictions candidates SANS les résoudre ici.
    """
    result = ValidationResult()
    seen: set[str] = set()
    for triple in triples:
        parts_ok = all(p and p.strip() for p in (triple.subject, triple.predicate, triple.object))
        conf_ok = 0.0 <= triple.confidence <= 1.0
        if not parts_ok:
            result.rejected.append(triple)
            result.reasons.append(f"incohérent (partie vide) : {_fingerprint(triple)}")
            continue
        if not conf_ok:
            result.rejected.append(triple)
            result.reasons.append(f"confidence hors [0,1] : {_fingerprint(triple)}")
            continue
        fp = _fingerprint(triple)
        if fp in seen:
            result.rejected.append(triple)
            result.reasons.append(f"doublon : {fp}")
            continue
        seen.add(fp)
        result.accepted.append(triple)
    return result
