"""Tests unitaires de l'isolation multi-tenant (cœur pur, sans DB ni réseau)."""

from __future__ import annotations

from uuid import UUID

import pytest

from auth.tenant_isolation import (
    TenantIsolationError,
    assert_same_tenant,
    resolve_tenant_context,
)
from interface.common.schemas import TenantContext

TENANT_A = UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = UUID("22222222-2222-2222-2222-222222222222")


def test_single_mode_returns_fixed_dev_tenant():
    ctx = resolve_tenant_context(None, None, mode="single")
    assert isinstance(ctx, TenantContext)
    assert ctx.tenant_id == UUID("00000000-0000-0000-0000-000000000001")


def test_header_mode_parses_valid_uuid():
    ctx = resolve_tenant_context(str(TENANT_A), None, mode="header")
    assert ctx.tenant_id == TENANT_A


def test_header_mode_missing_header_rejected():
    with pytest.raises(TenantIsolationError):
        resolve_tenant_context(None, None, mode="header")


def test_header_mode_invalid_uuid_rejected():
    with pytest.raises(TenantIsolationError):
        resolve_tenant_context("not-a-uuid", None, mode="header")


def test_jwt_mode_not_yet_implemented():
    with pytest.raises(TenantIsolationError):
        resolve_tenant_context(None, "Bearer x", mode="jwt")


def test_unknown_mode_rejected():
    with pytest.raises(TenantIsolationError):
        resolve_tenant_context(str(TENANT_A), None, mode="wat")


def test_assert_same_tenant_allows_matching():
    ctx = TenantContext(tenant_id=TENANT_A)
    assert_same_tenant(ctx, TENANT_A)  # ne lève pas
    assert_same_tenant(ctx, str(TENANT_A))  # accepte aussi la forme str


def test_assert_same_tenant_blocks_cross_tenant():
    ctx = TenantContext(tenant_id=TENANT_A)
    with pytest.raises(TenantIsolationError):
        assert_same_tenant(ctx, TENANT_B)


def test_assert_same_tenant_rejects_missing():
    ctx = TenantContext(tenant_id=TENANT_A)
    with pytest.raises(TenantIsolationError):
        assert_same_tenant(ctx, None)
