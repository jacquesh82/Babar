"""Fixtures partagées des tests.

``storage.db`` (pool asyncpg) et ``storage.buffer_store`` (client Redis) exposent
un singleton lié à la boucle asyncio courante. pytest-asyncio crée une boucle par
test → on réinitialise ces singletons avant/après chaque test pour que chaque
test d'intégration crée ses connexions sur SA boucle (sinon skip faussement).
"""

from __future__ import annotations

import pytest

from storage import buffer_store, db


@pytest.fixture(autouse=True)
async def _reset_backends():
    db._pool = None
    buffer_store._redis = None
    yield
    try:
        await db.close_pool()
    except Exception:
        pass
    try:
        if buffer_store._redis is not None:
            await buffer_store._redis.aclose()
    except Exception:
        pass
    buffer_store._redis = None
