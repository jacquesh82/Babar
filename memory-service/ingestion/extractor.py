"""Extraction incrémentale de triples.

Responsabilité : transformer **un tour de conversation** (pas la conversation
entière en fin de session) en triples candidats sujet-prédicat-objet.

L'extraction se fait **tour par tour** pour capter l'information au plus tôt et
alimenter le buffer short-term sans attendre la fin de l'échange.

Découplage : l'extraction peut s'appuyer sur un modèle (local de préférence,
pour rester provider-agnostic) mais n'expose jamais l'identité du LLM cible ;
elle produit uniquement des ``Triple`` du contrat commun.
"""
from __future__ import annotations

from interface.common.schemas import TenantContext, Triple


def extract_triples(turn_text: str, tenant: TenantContext) -> list[Triple]:
    """Extrait les triples candidats d'un tour de conversation.

    Args:
        turn_text: le texte du tour courant (message utilisateur ou assistant).
        tenant: contexte d'isolation (jamais mélanger les tenants).

    Returns:
        Liste de ``Triple`` non encore dédoublonnés/validés.

    TODO:
        - Choisir le backend d'extraction (modèle local / règles / hybride).
        - Détecter la politique de rétention (permanent vs decay) à partir de
          marqueurs linguistiques ("toujours", "désormais", "aujourd'hui", …).
        - Rattacher chaque triple à ``conversation_id`` pour la provenance.
    """
    raise NotImplementedError("extractor.extract_triples — stub")
