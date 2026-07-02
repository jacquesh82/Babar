"""Client Redis partagé (hors buffer short-term).

Fournit un singleton Redis pour les usages transverses (cache de requêtes,
invalidation…). Le buffer short-term garde son propre client dans
``buffer_store`` ; ce module sert les autres besoins pour éviter d'y coupler
d'autres modules.
"""

from __future__ import annotations

from config import settings

_client = None


def get_redis():
    """Client Redis partagé, créé au premier appel (import paresseux)."""
    global _client
    if _client is None:
        import redis.asyncio as aioredis

        _client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def close() -> None:
    """Ferme le client partagé (arrêt propre / reset de test)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
