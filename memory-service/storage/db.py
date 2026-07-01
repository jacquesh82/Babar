"""Gestion du pool de connexions PostgreSQL (asyncpg).

Fournit un pool partagé, initialisé paresseusement. Les modules de storage
acquièrent une connexion via ``acquire()`` (context manager) ou utilisent
directement le pool. Le worker et l'API partagent la même configuration DSN.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg

from config import settings

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Configure chaque connexion : codec JSON/JSONB transparent."""
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    await conn.set_type_codec(
        "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def get_pool() -> asyncpg.Pool:
    """Retourne le pool partagé, en le créant au premier appel."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.asyncpg_dsn,
            min_size=1,
            max_size=10,
            init=_init_connection,
        )
    return _pool


@asynccontextmanager
async def acquire() -> AsyncIterator[asyncpg.Connection]:
    """Acquiert une connexion du pool (context manager async)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def close_pool() -> None:
    """Ferme le pool (arrêt propre de l'app/worker)."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def ping() -> bool:
    """Vérifie la connectivité Postgres (health check)."""
    try:
        async with acquire() as conn:
            return await conn.fetchval("SELECT 1") == 1
    except Exception:
        return False
