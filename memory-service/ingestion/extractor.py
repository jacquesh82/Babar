"""Extraction incrémentale de triples.

Responsabilité : transformer **un tour de conversation** (pas la conversation
entière en fin de session) en triples candidats sujet-prédicat-objet.

Architecture **pluggable** : ``extract_triples`` dispatche vers un backend
d'extraction choisi par ``EXTRACTION_BACKEND``. Le backend par défaut
(``heuristic``) est déterministe, **provider-agnostic** et sans API payante ; un
backend modèle (local de préférence) peut être enregistré dans ``_BACKENDS`` sans
toucher au reste du pipeline.

La politique de rétention est déduite du motif : un nom / lieu de naissance /
lien familial est ``permanent``, une préférence ou un lieu de résidence est
*situationnel* (decay).
"""

from __future__ import annotations

import re
from collections.abc import Callable

from config import settings
from interface.common.schemas import Provenance, TenantContext, Triple

# Sujet par défaut des énoncés à la première personne (résolu ensuite en entité).
_SELF = "user"

# Objets manifestement issus d'une négation captée par erreur → ignorés.
_NEGATION_OBJECTS = {"not", "no", "never", "none"}

# (regex, prédicat, permanent, decay_rate). Objet capturé dans le groupe 1
# (ou groupe 2 pour les motifs à relation).
_PATTERNS: list[tuple[re.Pattern[str], str, bool, float]] = [
    (re.compile(r"\bmy name is ([\w][\w'’-]*)", re.I), "has_name", True, 0.0),
    (
        re.compile(r"\bi was born (?:in|on) ([\w][\w\s'’-]*?)(?:[.,;!?]|$)", re.I),
        "born_in",
        True,
        0.0,
    ),
    (re.compile(r"\bi(?:'m| am) (\d{1,3}) years old", re.I), "has_age", False, 0.1),
    (
        re.compile(r"\bi (?:live|living) in ([\w][\w\s'’-]*?)(?:[.,;!?]|$)", re.I),
        "lives_in",
        False,
        0.05,
    ),
    (
        re.compile(r"\bi (?:work|working) (?:at|for) ([\w][\w\s'’-]*?)(?:[.,;!?]|$)", re.I),
        "works_at",
        False,
        0.05,
    ),
    (
        re.compile(r"\bi (?:work|working) as (?:an? )?([\w][\w\s'’-]*?)(?:[.,;!?]|$)", re.I),
        "works_as",
        False,
        0.05,
    ),
    (
        re.compile(r"\bi (?:like|love|enjoy) ([\w][\w\s'’-]*?)(?:[.,;!?]|$)", re.I),
        "likes",
        False,
        0.05,
    ),
]

# Motifs à relation : "my <relation> is <name>" → prédicat has_<relation>.
_RELATION_RE = re.compile(
    r"\bmy (mother|father|sister|brother|wife|husband|son|daughter|friend|partner|dog|cat) "
    r"is (?:called |named )?([\w][\w'’-]*)",
    re.I,
)


def _heuristic_extract(turn_text: str, tenant: TenantContext) -> list[Triple]:
    """Backend d'extraction par motifs (regex), déterministe."""
    triples: list[Triple] = []

    for pattern, predicate, permanent, decay_rate in _PATTERNS:
        for match in pattern.finditer(turn_text):
            obj = match.group(1).strip()
            if not obj or obj.lower() in _NEGATION_OBJECTS:
                continue  # objet vide ou négation captée par erreur
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

    for match in _RELATION_RE.finditer(turn_text):
        relation, name = match.group(1).lower(), match.group(2).strip()
        if name and name.lower() not in _NEGATION_OBJECTS:
            triples.append(
                Triple(
                    subject=_SELF,
                    predicate=f"has_{relation}",
                    object=name,
                    permanent=True,  # lien familial/relationnel = stable
                    source=Provenance.CONVERSATION,
                )
            )

    return triples


# Registre des backends d'extraction. Un backend modèle (local) s'y branche ici.
_BACKENDS: dict[str, Callable[[str, TenantContext], list[Triple]]] = {
    "heuristic": _heuristic_extract,
}


def extract_triples(turn_text: str, tenant: TenantContext) -> list[Triple]:
    """Extrait les triples candidats d'un tour de conversation.

    Dispatche vers le backend ``EXTRACTION_BACKEND`` (défaut : ``heuristic``).
    Un backend inconnu retombe sur l'heuristique (jamais d'échec dur).
    """
    backend = _BACKENDS.get(settings.extraction_backend, _heuristic_extract)
    return backend(turn_text, tenant)
