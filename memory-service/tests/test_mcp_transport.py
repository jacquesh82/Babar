"""Tests du transport MCP Streamable HTTP (session + auth), sans Postgres.

Ne couvre que le transport : initialize / tools/list / gestion de session /
rejets d'auth. Les ``tools/call`` (qui touchent la base) sont testés ailleurs
(cf. ``test_adapters.py``).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from auth.jwt_utils import encode_hs256
from config import settings
from interface.api_rest import app

_SESSION_HEADER = "mcp-session-id"
_SECRET = "s3cr3t-de-test"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def single_mode(monkeypatch):
    # Mode "single" : tenant de dev fixe, aucune auth requise → isole le test du transport.
    monkeypatch.setattr(settings, "tenant_mode", "single")


def _init(client) -> str:
    """Ouvre une session MCP et renvoie son id."""
    resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert resp.status_code == 200
    session = resp.headers.get(_SESSION_HEADER)
    assert session
    return session


# --- session ---------------------------------------------------------------- #
def test_initialize_allocates_session(client, single_mode):
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2024-11-05"}},
    )
    assert resp.status_code == 200
    assert resp.headers.get(_SESSION_HEADER)
    body = resp.json()
    assert body["result"]["serverInfo"]["name"] == "memory-service"
    assert body["result"]["protocolVersion"] == "2024-11-05"


def test_tools_list_lists_three_tools(client, single_mode):
    session = _init(client)
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        headers={_SESSION_HEADER: session},
    )
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert names == {"memory.recall", "memory.ingest", "memory.correct"}


def test_non_initialize_requires_session(client, single_mode):
    resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert resp.status_code == 400


def test_unknown_session_forces_reinit(client, single_mode):
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        headers={_SESSION_HEADER: "session-bidon"},
    )
    assert resp.status_code == 404


def test_notification_returns_202(client, single_mode):
    session = _init(client)
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers={_SESSION_HEADER: session},
    )
    assert resp.status_code == 202


def test_delete_terminates_session(client, single_mode):
    session = _init(client)
    assert client.delete("/mcp", headers={_SESSION_HEADER: session}).status_code == 204
    # La session n'est plus reconnue.
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        headers={_SESSION_HEADER: session},
    )
    assert resp.status_code == 404


def test_get_not_allowed(client, single_mode):
    resp = client.get("/mcp")
    assert resp.status_code == 405
    assert "POST" in resp.headers.get("Allow", "")


# --- auth ------------------------------------------------------------------- #
def test_jwt_mode_rejects_missing_token(client, monkeypatch):
    monkeypatch.setattr(settings, "tenant_mode", "jwt")
    monkeypatch.setattr(settings, "jwt_secret", _SECRET)
    resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate", "").startswith("Bearer")


def test_jwt_mode_accepts_valid_token(client, monkeypatch):
    monkeypatch.setattr(settings, "tenant_mode", "jwt")
    monkeypatch.setattr(settings, "jwt_secret", _SECRET)
    token = encode_hs256({"tenant_id": str(uuid4())}, _SECRET)
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.headers.get(_SESSION_HEADER)
