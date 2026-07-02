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

import hashlib
import json
import re
from uuid import UUID

from interface.common.schemas import TenantContext
from storage.graph_store import find_nodes
from storage.redis_client import get_redis

# Termes trop courts / vides de sens : ignorés lors de la liaison exacte.
_MIN_TERM_LEN = 3
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)

# Cache des requêtes fréquentes (Redis). TTL court : la mémoire évolue.
_CACHE_TTL_S = 300
_CACHE_PREFIX = "mem:qcache"


def _terms(query: str) -> list[str]:
    """Découpe la question en termes candidats (unigrammes significatifs)."""
    return [t for t in _TOKEN_RE.findall(query.lower()) if len(t) >= _MIN_TERM_LEN]


async def link(tenant: TenantContext, query: str, limit: int = 10) -> list[UUID]:
    """Retourne les ids de nœuds candidats servant de points d'entrée.

    Ordre : cache → correspondance exacte → **fallback sémantique** (vecteur).
    Le fallback est best-effort : indisponible sans pgvector, il retourne alors
    simplement la liste exacte (éventuellement vide).

    TODO: cache Redis clé = hash(tenant, query normalisée) → ``cache_get``.
    """
    cached = await cache_get(tenant, query)
    if cached is not None:
        return cached

    exact = await find_nodes(tenant, _terms(query), limit=limit)
    if exact:
        await cache_set(tenant, query, exact)
        return exact

    try:  # fallback sémantique si aucune entité exacte
        from retrieval import vector_search

        hits = await vector_search.search(tenant, query, top_k=limit)
        result = [node_id for node_id, _ in hits]
    except Exception:
        return exact

    if result:
        await cache_set(tenant, query, result)
    return result


def _cache_key(tenant: TenantContext, query: str) -> str:
    """Clé de cache scopée tenant (préfixe en clair → invalidation par SCAN)."""
    normalized = " ".join(_terms(query))
    digest = hashlib.md5(normalized.encode("utf-8")).hexdigest()  # noqa: S324 (non crypto)
    return f"{_CACHE_PREFIX}:{tenant.tenant_id}:{digest}"


async def cache_get(tenant: TenantContext, query: str) -> list[UUID] | None:
    """Lecture du cache Redis des requêtes fréquentes (ou None). Best-effort."""
    try:
        raw = await get_redis().get(_cache_key(tenant, query))
    except Exception:
        return None
    if raw is None:
        return None
    return [UUID(x) for x in json.loads(raw)]


async def cache_set(tenant: TenantContext, query: str, node_ids: list[UUID]) -> None:
    """Écrit un résultat de liaison dans le cache (TTL court). Best-effort."""
    try:
        await get_redis().set(
            _cache_key(tenant, query),
            json.dumps([str(x) for x in node_ids]),
            ex=_CACHE_TTL_S,
        )
    except Exception:
        pass


async def invalidate(tenant: TenantContext) -> None:
    """Invalide tout le cache de requêtes du tenant (après écriture mémoire)."""
    try:
        redis = get_redis()
        keys = [key async for key in redis.scan_iter(f"{_CACHE_PREFIX}:{tenant.tenant_id}:*")]
        if keys:
            await redis.delete(*keys)
    except Exception:
        pass
