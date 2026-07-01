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


def resolve(
    triples: list[Triple],
    tenant: TenantContext,
    conversation_id: str | None = None,
) -> list[Triple]:
    """Résout coréférences et alias, renvoie des triples à entités canoniques.

    Args:
        triples: triples bruts issus de ``extractor``.
        tenant: contexte d'isolation.
        conversation_id: contexte de dialogue pour résoudre les pronoms.

    TODO:
        - Fenêtre de coréférence par ``conversation_id`` (antécédents récents).
        - Désambiguïsation par embedding de contexte + type d'entité.
    """
    resolved: list[Triple] = []
    for triple in triples:
        resolved.append(
            triple.model_copy(
                update={
                    "subject": canonicalize(triple.subject),
                    "object": canonicalize(triple.object),
                }
            )
        )
    return resolved
