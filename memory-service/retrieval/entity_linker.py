"""Question → entités candidates, avec cache des requêtes fréquentes.

Première étape du flux de lecture : identifier, à partir de la question du LLM
cible, les nœuds d'entrée dans le graphe (points d'activation pour le
``graph_walker``). Un cache (Redis) mémorise les liaisons des requêtes
fréquentes pour accélérer l'activation.
"""
from __future__ import annotations

from uuid import UUID

from interface.common.schemas import TenantContext


async def link(tenant: TenantContext, query: str, limit: int = 10) -> list[UUID]:
    """Retourne les ids de nœuds candidats servant de points d'entrée.

    TODO:
        - Extraction de mentions dans ``query`` + matching canonical_key.
        - Fallback vector (``vector_store.search``) si aucune entité exacte.
        - Cache Redis clé=hash(tenant, query normalisée).
    """
    raise NotImplementedError("entity_linker.link — stub")


async def cache_get(tenant: TenantContext, query: str) -> list[UUID] | None:
    """Lecture du cache des requêtes fréquentes (ou None)."""
    raise NotImplementedError("entity_linker.cache_get — stub")
