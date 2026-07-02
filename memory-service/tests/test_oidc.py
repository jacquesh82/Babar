"""Tests de l'auth OIDC (Mindlog.id) — RS256 vérifié pour de vrai, sans réseau.

On génère une paire RSA de test, on signe des jetons RS256, et on court-circuite
la récupération JWKS (``_signing_key``) pour injecter la clé publique de test. La
vérification de signature / ``exp`` / ``iss`` / ``aud`` est bien exécutée par PyJWT.
"""

from __future__ import annotations

import time
from uuid import UUID, uuid5

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from auth import oidc, tenant_isolation
from auth.oidc import OIDCError, verify_oidc_token
from config import settings
from interface.api_rest import app

_ISSUER = "https://mindlog.id"
_AUDIENCE = "https://memory.mindlog.today/mcp"


@pytest.fixture(scope="module")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def oidc_env(monkeypatch, rsa_key):
    monkeypatch.setattr(settings, "tenant_mode", "oidc")
    monkeypatch.setattr(settings, "oidc_issuer", _ISSUER)
    monkeypatch.setattr(settings, "oidc_audience", _AUDIENCE)
    monkeypatch.setattr(settings, "oidc_tenant_claim", "org_id")
    monkeypatch.setattr(settings, "oidc_user_claim", "sub")
    # Court-circuite le JWKS : renvoie directement la clé publique de test.
    monkeypatch.setattr(oidc, "_signing_key", lambda token: rsa_key.public_key())
    return rsa_key


def _token(rsa_key, **claims) -> str:
    payload = {"iss": _ISSUER, "aud": _AUDIENCE, "exp": int(time.time()) + 300, **claims}
    return jwt.encode(payload, rsa_key, algorithm="RS256")


# --- vérification du jeton -------------------------------------------------- #
def test_valid_token_returns_claims(oidc_env):
    claims = verify_oidc_token(_token(oidc_env, org_id="acme", sub="user-42"))
    assert claims["org_id"] == "acme"
    assert claims["sub"] == "user-42"


def test_wrong_audience_rejected(oidc_env):
    token = jwt.encode(
        {"iss": _ISSUER, "aud": "https://autre.example", "exp": int(time.time()) + 300},
        oidc_env,
        algorithm="RS256",
    )
    with pytest.raises(OIDCError):
        verify_oidc_token(token)


def test_wrong_issuer_rejected(oidc_env):
    token = jwt.encode(
        {"iss": "https://evil.example", "aud": _AUDIENCE, "exp": int(time.time()) + 300},
        oidc_env,
        algorithm="RS256",
    )
    with pytest.raises(OIDCError):
        verify_oidc_token(token)


def test_expired_rejected(oidc_env):
    token = jwt.encode(
        {"iss": _ISSUER, "aud": _AUDIENCE, "exp": int(time.time()) - 10},
        oidc_env,
        algorithm="RS256",
    )
    with pytest.raises(OIDCError):
        verify_oidc_token(token)


# --- mapping tenant --------------------------------------------------------- #
def test_org_maps_to_tenant_and_sub_to_user(oidc_env):
    token = _token(oidc_env, org_id="acme", sub="user-42")
    ctx = tenant_isolation.resolve_tenant_context(None, f"Bearer {token}", mode="oidc")
    # org non-UUID → dérivation uuid5 déterministe.
    assert ctx.tenant_id == uuid5(tenant_isolation._MINDLOG_NS, "acme")
    assert ctx.user_id == uuid5(tenant_isolation._MINDLOG_NS, "user-42")


def test_uuid_org_used_directly(oidc_env):
    org = "11111111-1111-1111-1111-111111111111"
    token = _token(oidc_env, org_id=org, sub="user-42")
    ctx = tenant_isolation.resolve_tenant_context(None, f"Bearer {token}", mode="oidc")
    assert ctx.tenant_id == UUID(org)


def test_missing_org_claim_rejected(oidc_env):
    token = _token(oidc_env, sub="user-42")  # pas d'org_id
    with pytest.raises(tenant_isolation.TenantIsolationError):
        tenant_isolation.resolve_tenant_context(None, f"Bearer {token}", mode="oidc")


def test_missing_bearer_rejected(oidc_env):
    with pytest.raises(tenant_isolation.TenantIsolationError):
        tenant_isolation.resolve_tenant_context(None, None, mode="oidc")


# --- flux OAuth MCP (métadonnées + challenge) ------------------------------- #
def test_protected_resource_metadata_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "oidc_issuer", _ISSUER)
    monkeypatch.setattr(settings, "mcp_resource", _AUDIENCE)
    client = TestClient(app)
    resp = client.get("/.well-known/oauth-protected-resource/mcp")
    assert resp.status_code == 200
    body = resp.json()
    assert body["resource"] == _AUDIENCE
    assert body["authorization_servers"] == [_ISSUER]


def test_unauthorized_points_to_resource_metadata(monkeypatch):
    monkeypatch.setattr(settings, "tenant_mode", "oidc")
    monkeypatch.setattr(settings, "public_base_url", "https://memory.mindlog.today")
    client = TestClient(app)
    resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert resp.status_code == 401
    www = resp.headers.get("WWW-Authenticate", "")
    assert "resource_metadata=" in www
    assert "/.well-known/oauth-protected-resource/mcp" in www
