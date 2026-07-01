"""Décroissance d'importance des faits.

Exécuté par le worker de consolidation. Réduit progressivement l'``importance``
des faits **situationnels** pour que la mémoire privilégie l'information vive.

Contrainte non négociable #3 : **pas de decay uniforme**. La distinction est
portée par les données elles-mêmes :
  * ``permanent = TRUE``  → fait "permanent déclaré", **jamais** de decay
    (ex: date de naissance, préférence stable revendiquée).
  * ``permanent = FALSE`` → fait "situationnel", decay actif au ``decay_rate``
    propre de la ligne (0 = pas de decay).

Aucune fonction globale n'est appliquée aveuglément à toutes les lignes.
"""
from __future__ import annotations

from dataclasses import dataclass

from interface.common.schemas import TenantContext


@dataclass
class DecayReport:
    edges_decayed: int = 0
    nodes_decayed: int = 0
    skipped_permanent: int = 0


def new_importance(current: float, decay_rate: float, elapsed_seconds: float) -> float:
    """Calcule la nouvelle importance après decay (fonction pure).

    TODO: choisir le modèle (exponentiel ``current * exp(-rate * t)`` recommandé),
    borné dans [0,1]. Renvoie ``current`` inchangé si ``decay_rate == 0``.
    """
    raise NotImplementedError("decay.new_importance — stub")


async def apply_decay(tenant: TenantContext) -> DecayReport:
    """Applique le decay aux faits situationnels du tenant.

    TODO:
        - Ne traiter QUE ``permanent = FALSE`` (compter les skips permanents).
        - Recalculer importance via ``new_importance`` par ligne.
        - Ne jamais supprimer par decay ici (seuil d'oubli à décider séparément).
    """
    raise NotImplementedError("decay.apply_decay — stub")
