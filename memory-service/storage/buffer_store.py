"""Buffer short-term (Redis) avec critère explicite de promotion.

Rôle : conserver les faits fraîchement extraits (tour par tour) avant leur
consolidation en long-term. La promotion short-term → long-term est **explicite**
(non automatique) et pilotée par ``should_promote``.

Critère de promotion proposé (à documenter/affiner) :
  * fait revu/renforcé au moins N fois (compteur d'occurrences), OU
  * marqué ``permanent`` à l'extraction, OU
  * ancienneté dans le buffer > seuil ET ``confidence`` >= seuil.
"""
from __future__ import annotations

from interface.common.schemas import TenantContext, Triple


async def push(tenant: TenantContext, triple: Triple, conversation_id: str | None = None) -> None:
    """Ajoute un triple au buffer short-term du tenant (TTL Redis)."""
    raise NotImplementedError("buffer_store.push — stub")


async def peek(tenant: TenantContext, limit: int = 100) -> list[Triple]:
    """Liste les triples en attente (sans les retirer)."""
    raise NotImplementedError("buffer_store.peek — stub")


def should_promote(triple: Triple, occurrences: int, age_seconds: float) -> bool:
    """Décide si un fait short-term doit être promu en long-term.

    Critère EXPLICITE (voir docstring du module). Retourne True/False, ne
    réalise pas la promotion elle-même.
    """
    raise NotImplementedError("buffer_store.should_promote — stub")


async def drain_promotable(tenant: TenantContext) -> list[Triple]:
    """Retire et renvoie les triples éligibles à la promotion long-term."""
    raise NotImplementedError("buffer_store.drain_promotable — stub")
