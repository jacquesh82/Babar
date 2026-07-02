"""Résolution de coréférence et désambiguïsation d'entités.

Sous-module **dédié** (volontairement PAS fusionné dans ``validator.py``) :
la coréférence ("il", "cette ville", "mon frère") et la désambiguïsation
("Paris" la ville vs "Paris" la personne) sont une étape à part entière, en
amont de la validation.

Implémentation actuelle : normalisation en **clé canonique** (minuscule, espaces
compactés) et résolution des pronoms à la première personne vers l'entité
``user``. La désambiguïsation contextuelle avancée (embeddings + type) est
prévue (TODO).
"""

from __future__ import annotations

import re

from interface.common.schemas import TenantContext, Triple

# Pronoms/mentions renvoyant à l'utilisateur courant.
_SELF_MENTIONS = {"i", "me", "my", "myself", "mine", "moi", "je", "mon", "ma", "mes"}
_SELF_CANONICAL = "user"
_WS = re.compile(r"\s+")


def canonicalize(mention: str) -> str:
    """Normalise une mention en clé canonique (idempotent)."""
    text = _WS.sub(" ", mention.strip().lower())
    return _SELF_CANONICAL if text in _SELF_MENTIONS else text


def _rules_resolve(
    triples: list[Triple], tenant: TenantContext, conversation_id: str | None
) -> list[Triple]:
    """Backend "rules" : canonicalisation + pronoms 1re personne."""
    return [
        triple.model_copy(
            update={
                "subject": canonicalize(triple.subject),
                "object": canonicalize(triple.object),
            }
        )
        for triple in triples
    ]


# Registre pluggable ; un backend modèle (désambiguïsation contextuelle) s'y branche.
_BACKENDS = {"rules": _rules_resolve}


def resolve(
    triples: list[Triple],
    tenant: TenantContext,
    conversation_id: str | None = None,
) -> list[Triple]:
    """Résout coréférences et alias, renvoie des triples à entités canoniques.

    Dispatche vers ``COREF_BACKEND`` (défaut : ``rules``) ; backend inconnu →
    retombe sur les règles (jamais d'échec dur).

    TODO:
        - Fenêtre de coréférence par ``conversation_id`` (antécédents récents).
        - Désambiguïsation par embedding de contexte + type d'entité.
    """
    from config import settings

    backend = _BACKENDS.get(settings.coref_backend, _rules_resolve)
    return backend(triples, tenant, conversation_id)
