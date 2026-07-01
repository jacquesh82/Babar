"""Résolution de coréférence et désambiguïsation d'entités.

Sous-module **dédié** (volontairement PAS fusionné dans ``validator.py``) :
la coréférence ("il", "cette ville", "mon frère") et la désambiguïsation
("Paris" la ville vs "Paris" la personne) sont une étape à part entière, en
amont de la validation.

Rôle : mapper les mentions textuelles de triples fraîchement extraits vers des
entités canoniques (``canonical_key`` des ``memory_nodes``), en résolvant les
pronoms et en fusionnant les alias.
"""
from __future__ import annotations

from interface.common.schemas import TenantContext, Triple


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

    Returns:
        Triples dont ``subject``/``object`` pointent vers des clés canoniques.

    TODO:
        - Fenêtre de coréférence par ``conversation_id`` (Redis short-term).
        - Stratégie de désambiguïsation (embedding de contexte + type d'entité).
        - Créer une nouvelle entité canonique si aucune correspondance fiable.
    """
    raise NotImplementedError("coref_resolver.resolve — stub")
