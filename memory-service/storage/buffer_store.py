"""Buffer short-term (Redis) avec critère explicite de promotion.

Rôle : conserver les faits fraîchement extraits (tour par tour) avant leur
consolidation en long-term. La promotion short-term → long-term est **explicite**
(non automatique) et pilotée par ``should_promote``.

Critère de promotion (explicite, contrainte #… "critère de promotion") :
  * fait marqué ``permanent`` à l'extraction, OU
  * fait revu/renforcé au moins ``_PROMOTE_MIN_OCCURRENCES`` fois, OU
  * ancienneté dans le buffer ≥ ``_PROMOTE_MIN_AGE_S`` ET ``confidence`` ≥ 0.7.

Stockage : un hash Redis par tenant ``mem:buffer:{tenant_id}`` dont chaque champ
(empreinte du triple) porte ``{triple, count, first_seen}``.
"""
from __future__ import annotations

import json
import time

from interface.common.schemas import TenantContext, Triple
from config import settings

_PROMOTE_MIN_OCCURRENCES = 3
_PROMOTE_MIN_AGE_S = 3600.0
_PROMOTE_MIN_CONFIDENCE = 0.7

_redis = None


def _get_redis():
    """Client Redis partagé (import paresseux pour rester importable sans redis)."""
    global _redis
    if _redis is None:
        import redis.asyncio as aioredis

        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _buffer_key(tenant: TenantContext) -> str:
    return f"mem:buffer:{tenant.tenant_id}"


def _fingerprint(triple: Triple) -> str:
    return f"{triple.subject}|{triple.predicate}|{triple.object}"


def should_promote(triple: Triple, occurrences: int, age_seconds: float) -> bool:
    """Décide si un fait short-term doit être promu en long-term (fonction pure)."""
    if triple.permanent:
        return True
    if occurrences >= _PROMOTE_MIN_OCCURRENCES:
        return True
    return age_seconds >= _PROMOTE_MIN_AGE_S and triple.confidence >= _PROMOTE_MIN_CONFIDENCE


async def push(tenant: TenantContext, triple: Triple, conversation_id: str | None = None) -> None:
    """Ajoute/renforce un triple dans le buffer short-term du tenant."""
    redis = _get_redis()
    key = _buffer_key(tenant)
    field = _fingerprint(triple)
    existing = await redis.hget(key, field)
    if existing:
        entry = json.loads(existing)
        entry["count"] += 1
    else:
        entry = {"triple": triple.model_dump(mode="json"), "count": 1, "first_seen": time.time()}
    await redis.hset(key, field, json.dumps(entry))


async def peek(tenant: TenantContext, limit: int = 100) -> list[Triple]:
    """Liste les triples en attente (sans les retirer)."""
    redis = _get_redis()
    entries = await redis.hvals(_buffer_key(tenant))
    triples = [Triple.model_validate(json.loads(e)["triple"]) for e in entries[:limit]]
    return triples


async def drain_promotable(tenant: TenantContext) -> list[Triple]:
    """Retire et renvoie les triples éligibles à la promotion long-term."""
    redis = _get_redis()
    key = _buffer_key(tenant)
    now = time.time()
    all_entries = await redis.hgetall(key)
    promotable: list[Triple] = []
    to_delete: list[str] = []
    for field, raw in all_entries.items():
        entry = json.loads(raw)
        triple = Triple.model_validate(entry["triple"])
        age = now - float(entry.get("first_seen", now))
        if should_promote(triple, entry.get("count", 1), age):
            promotable.append(triple)
            to_delete.append(field)
    if to_delete:
        await redis.hdel(key, *to_delete)
    return promotable
