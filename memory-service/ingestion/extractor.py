"""Extraction incrémentale de triples.

Responsabilité : transformer **un tour de conversation** (pas la conversation
entière en fin de session) en triples candidats sujet-prédicat-objet.

Implémentation actuelle : extraction **heuristique déterministe** par motifs
(regex) sur des énoncés personnels courants ("my name is…", "I live in…"). Elle
est volontairement **provider-agnostic** et sans appel API payante ; le
remplacement par un modèle d'extraction (local de préférence) est prévu (TODO).

La politique de rétention est déduite du motif : un nom / lieu de naissance est
``permanent``, une préférence ou un lieu de résidence est *situationnel* (decay).
"""
from __future__ import annotations

import re

from interface.common.schemas import Provenance, TenantContext, Triple

# Sujet par défaut des énoncés à la première personne (résolu ensuite en entité).
_SELF = "user"

# (regex, prédicat, permanent, decay_rate). Objet capturé dans le groupe 1.
_PATTERNS: list[tuple[re.Pattern[str], str, bool, float]] = [
    (re.compile(r"\bmy name is ([\w][\w'’-]*)", re.I), "has_name", True, 0.0),
    (re.compile(r"\bi was born (?:in|on) ([\w][\w\s'’-]*?)(?:[.,;!?]|$)", re.I), "born_in", True, 0.0),
    (re.compile(r"\bi(?:'m| am) (\d{1,3}) years old", re.I), "has_age", False, 0.1),
    (re.compile(r"\bi (?:live|living) in ([\w][\w\s'’-]*?)(?:[.,;!?]|$)", re.I), "lives_in", False, 0.05),
    (re.compile(r"\bi (?:work|working) (?:at|for) ([\w][\w\s'’-]*?)(?:[.,;!?]|$)", re.I), "works_at", False, 0.05),
    (re.compile(r"\bi (?:like|love|enjoy) ([\w][\w\s'’-]*?)(?:[.,;!?]|$)", re.I), "likes", False, 0.05),
]


def extract_triples(turn_text: str, tenant: TenantContext) -> list[Triple]:
    """Extrait les triples candidats d'un tour de conversation.

    Args:
        turn_text: le texte du tour courant (message utilisateur ou assistant).
        tenant: contexte d'isolation (jamais mélanger les tenants).

    Returns:
        Liste de ``Triple`` non encore dédoublonnés/validés.

    TODO:
        - Remplacer/compléter l'heuristique par un modèle d'extraction local.
        - Étendre la détection de permanence (marqueurs "toujours", "désormais"…).
    """
    triples: list[Triple] = []
    for pattern, predicate, permanent, decay_rate in _PATTERNS:
        for match in pattern.finditer(turn_text):
            obj = match.group(1).strip()
            if not obj:
                continue
            triples.append(
                Triple(
                    subject=_SELF,
                    predicate=predicate,
                    object=obj,
                    permanent=permanent,
                    decay_rate=decay_rate,
                    source=Provenance.CONVERSATION,
                )
            )
    return triples
