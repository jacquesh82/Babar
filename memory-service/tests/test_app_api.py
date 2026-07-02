"""Tests de l'API du visualiseur web (``/app``) : config publique, auth, browse."""

from __future__ import annotations

from uuid import uuid4

import pytest
from starlette.testclient import TestClient

from config import settings
from interface.api_rest import app
from interface.common.schemas import Provenance, TenantContext, Triple
from storage import db, graph_store

client = TestClient(app)


def test_webapp_config_is_public_and_structured():
    r = client.get("/v1/webapp/config")
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_mode"] == settings.tenant_mode.lower()
    assert body["oidc"]["redirect_uri"].endswith("/app/")
    # Aucun secret ne doit fuiter par cet endpoint public.
    assert "jwt_secret" not in body and "secret" not in str(body).lower()


def test_browse_requires_tenant(monkeypatch):
    """En mode header, /v1/memory/* rejette toute requête sans tenant (401)."""
    monkeypatch.setattr(settings, "tenant_mode", "header")
    assert client.get("/v1/memory/graph").status_code == 401
    assert client.get("/v1/memory/stats").status_code == 401


def test_config_reflects_oidc_settings(monkeypatch):
    monkeypatch.setattr(settings, "tenant_mode", "oidc")
    monkeypatch.setattr(settings, "oidc_client_id", "public-web-client")
    body = client.get("/v1/webapp/config").json()
    assert body["auth_required"] is True
    assert body["oidc"]["client_id"] == "public-web-client"


def test_single_mode_needs_no_auth(monkeypatch):
    monkeypatch.setattr(settings, "tenant_mode", "single")
    assert client.get("/v1/webapp/config").json()["auth_required"] is False


@pytest.mark.asyncio
async def test_list_graph_roundtrip():
    """list_graph + graph_stats renvoient un fait fraîchement inséré (intégration)."""
    if not await db.ping():
        pytest.skip("Postgres indisponible — test d'intégration skippé")

    tenant = TenantContext(tenant_id=uuid4())
    triple = Triple(
        subject="alice",
        predicate="lives_in",
        object="paris",
        permanent=True,
        source=Provenance.CONVERSATION,
    )
    edge_id = await graph_store.add_edge(tenant, triple)
    try:
        graph = await graph_store.list_graph(tenant)
        edges = graph["edges"]
        assert any(e["id"] == edge_id for e in edges)
        row = next(e for e in edges if e["id"] == edge_id)
        assert row["subject_label"] == "alice"
        assert row["object_label"] == "paris"
        assert row["predicate"] == "lives_in"
        assert row["valid_until"] is None  # fait actif

        stats = await graph_store.graph_stats(tenant)
        assert stats["active_edges"] >= 1
        assert stats["permanent_edges"] >= 1
        assert stats["nodes"] >= 2

        # Filtre q insensible à la casse.
        assert any(e["id"] == edge_id for e in (await graph_store.list_graph(tenant, q="PARIS"))["edges"])
    finally:
        # Nettoyage : isolation par tenant éphémère, on retire nœuds + arête.
        node_ids = [e["subject_id"] for e in graph["edges"]] + [e["object_id"] for e in graph["edges"]]
        await graph_store.hard_delete(tenant, list(set(node_ids)), [edge_id])
