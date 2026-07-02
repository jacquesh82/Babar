"""Tests de l'endpoint /health (statut HTTP selon la santé des backends)."""

from __future__ import annotations

import pytest
from fastapi import Response

from interface.api_rest import health
from storage import db


@pytest.mark.asyncio
async def test_health_503_when_postgres_down(monkeypatch):
    async def _no_pg():
        return False

    monkeypatch.setattr(db, "ping", _no_pg)
    response = Response()
    body = await health(response)
    assert response.status_code == 503
    assert body.postgres is False
    assert body.status == "degraded"


@pytest.mark.asyncio
async def test_health_ok_when_backends_up():
    if not await db.ping():
        pytest.skip("Postgres indisponible — test d'intégration skippé")
    response = Response()
    body = await health(response)
    assert body.postgres is True
    # 200 par défaut (Response() n'a pas de status_code forcé) tant que PG est up.
    assert response.status_code in (None, 200)
