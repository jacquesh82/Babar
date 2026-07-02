"""Tests unitaires de l'auth JWT (purs, sans réseau)."""

from __future__ import annotations

import base64
import json
from uuid import uuid4

import pytest

from auth import tenant_isolation
from auth.jwt_utils import JWTError, decode_hs256, encode_hs256
from auth.tenant_isolation import TenantIsolationError
from config import settings

SECRET = "s3cr3t-de-test"


# --- jwt_utils -------------------------------------------------------------- #
def test_encode_decode_roundtrip():
    token = encode_hs256({"tenant_id": "abc", "role": "admin"}, SECRET)
    claims = decode_hs256(token, SECRET)
    assert claims["tenant_id"] == "abc"
    assert claims["role"] == "admin"


def test_bad_signature_rejected():
    token = encode_hs256({"tenant_id": "abc"}, SECRET)
    with pytest.raises(JWTError):
        decode_hs256(token, "mauvais-secret")


def test_expired_rejected():
    token = encode_hs256({"tenant_id": "abc", "exp": 1000}, SECRET)
    with pytest.raises(JWTError):
        decode_hs256(token, SECRET, now=2000)


def test_not_expired_when_exp_in_future():
    token = encode_hs256({"tenant_id": "abc", "exp": 5000}, SECRET)
    assert decode_hs256(token, SECRET, now=1000)["tenant_id"] == "abc"


def test_non_hs256_algorithm_rejected():
    def seg(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    forged = f"{seg({'alg': 'none'})}.{seg({'tenant_id': 'abc'})}.x"
    with pytest.raises(JWTError):
        decode_hs256(forged, SECRET)


def test_malformed_token_rejected():
    with pytest.raises(JWTError):
        decode_hs256("pas-un-jwt", SECRET)


# --- tenant_isolation mode jwt ---------------------------------------------- #
@pytest.fixture
def jwt_secret(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", SECRET)


def test_resolve_jwt_extracts_tenant_and_user(jwt_secret):
    tid, uid = uuid4(), uuid4()
    token = encode_hs256({"tenant_id": str(tid), "user_id": str(uid)}, SECRET)
    ctx = tenant_isolation.resolve_tenant_context(None, f"Bearer {token}", mode="jwt")
    assert ctx.tenant_id == tid
    assert ctx.user_id == uid


def test_resolve_jwt_missing_header_rejected(jwt_secret):
    with pytest.raises(TenantIsolationError):
        tenant_isolation.resolve_tenant_context(None, None, mode="jwt")


def test_resolve_jwt_without_secret_rejected(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "")
    token = encode_hs256({"tenant_id": str(uuid4())}, SECRET)
    with pytest.raises(TenantIsolationError):
        tenant_isolation.resolve_tenant_context(None, f"Bearer {token}", mode="jwt")


def test_resolve_jwt_bad_token_rejected(jwt_secret):
    with pytest.raises(TenantIsolationError):
        tenant_isolation.resolve_tenant_context(None, "Bearer not.a.jwt", mode="jwt")


def test_resolve_jwt_missing_tenant_claim_rejected(jwt_secret):
    token = encode_hs256({"foo": "bar"}, SECRET)
    with pytest.raises(TenantIsolationError):
        tenant_isolation.resolve_tenant_context(None, f"Bearer {token}", mode="jwt")
