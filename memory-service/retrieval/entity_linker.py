"""Question → entités candidates, avec cache des requêtes fréquentes.

Première étape du flux de lecture : identifier, à partir de la question du LLM
cible, les nœuds d'entrée dans le graphe (points d'activation pour le
``graph_walker``).

Implémentation actuelle : liaison par **correspondance exacte** (canonical_key
ou label) des termes significatifs de la question. La liaison sémantique
(fallback vecteur) et le cache Redis des requêtes fréquentes sont prévus
(voir TODOs) mais volontairement non branchés au stade fondations.
"""
from __future__ import annotations

import re
from uuid import UUID

from interface.common.schemas import TenantContext
from storage.graph_store import find_nodes

# Termes trop courts / vides de sens : ignorés lors de la liaison exacte.
_MIN_TERM_LEN = 3
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def _terms(query: str) -> list[str]:
    """Découpe la question en termes candidats (unigrammes significatifs)."""
    return [t for t in _TOKEN_RE.findall(query.lower()) if len(t) >= _MIN_TERM_LEN]


async def link(tenant: TenantContext, query: str, limit: int = 10) -> list[UUID]:
    """Retourne les ids de nœuds candidats servant de points d'entrée.

    TODO:
        - Fallback vecteur (``vector_search.search``) si aucune entité exacte.
        - Cache Redis clé = hash(tenant, query normalisée) → ``cache_get``.
    """
    cached = await cache_get(tenant, query)
    if cached is not None:
        return cached
    return await find_nodes(tenant, _terms(query), limit=limit)


async def cache_get(tenant: TenantContext, query: str) -> list[UUID] | None:
    """Lecture du cache des requêtes fréquentes (ou None si non branché).

    TODO: brancher Redis ; pour l'instant, pas de cache (retourne None).
    """
    return None
