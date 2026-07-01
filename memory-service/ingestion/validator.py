"""Dédoublonnage et contrôle de cohérence des triples.

Dernière étape de l'ingestion avant écriture buffer. Reçoit des triples déjà
résolus (coréférence faite en amont dans ``coref_resolver.py``) et :
  * écarte les doublons exacts / quasi-doublons ;
  * vérifie la cohérence de forme (types plausibles, prédicat connu) ;
  * marque les contradictions *potentielles* pour arbitrage ultérieur par le
    worker de consolidation (``consolidation/merger.py``) — la validation ne
    tranche pas les contradictions elle-même.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from interface.common.schemas import TenantContext, Triple


@dataclass
class ValidationResult:
    accepted: list[Triple] = field(default_factory=list)
    rejected: list[Triple] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def validate(triples: list[Triple], tenant: TenantContext) -> ValidationResult:
    """Dédoublonne et contrôle la cohérence d'un lot de triples.

    TODO:
        - Dédup exacte + quasi (normalisation prédicat, similarité objet).
        - Vérifier la plausibilité (type sujet/objet vs prédicat).
        - Détecter les contradictions candidates SANS les résoudre ici.
    """
    raise NotImplementedError("validator.validate — stub")
