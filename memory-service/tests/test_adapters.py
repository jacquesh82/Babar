"""Tests des adaptateurs d'interface.

Vérifie que les trois connecteurs (REST, OpenAI Action, MCP) partagent le même
service commun et ne divergent pas. Les vérifications de câblage sont pures ; un
test d'intégration confirme la délégation bout-en-bout (skip sans Postgres).
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from interface import mcp_server, openai_action
from interface.api_rest import app
from interface.common.schemas import RecallRequest, TenantContext, Triple
from storage import db, graph_store


# --- câblage (pur) ---------------------------------------------------------- #
def test_rest_app_mounts_action_router():
    # Le router Action est monté sur l'app REST → il apparaît dans l'OpenAPI
    # (app.routes est résolu paresseusement selon la version de FastAPI).
    paths = set(app.openapi()["paths"])
    assert "/actions/recall" in paths
    assert "/actions/ingest" in paths
    assert "/v1/recall" in paths


def test_action_openapi_schema_exposes_only_actions():
    schema = openai_action.openapi_schema()
    paths = set(schema["paths"])
    assert "/actions/recall" in paths
    assert all(p.startswith("/actions/") for p in paths)   # pas d'endpoint interne exposé


def test_mcp_declares_three_tools():
    assert set(mcp_server.TOOLS) == {"memory.recall", "memory.ingest", "memory.correct"}
    for spec in mcp_server.TOOLS.values():
        assert callable(spec["handler"])


# --- délégation bout-en-bout (intégration, skip sans Postgres) -------------- #
@pytest.mark.asyncio
async def test_mcp_and_action_recall_agree():
    if not await db.ping():
        pytest.skip("Postgres indisponible — test d'intégration skippé")
    tenant = TenantContext(tenant_id=uuid4())
    await graph_store.add_edge(tenant, Triple(subject="user", predicate="lives_in", object="paris"))

    req = RecallRequest(tenant=tenant, query="where does user live", token_budget=200)
    via_mcp = await mcp_server.tool_recall(req)
    via_action = await openai_action.action_recall(req, tenant=tenant)

    # Même domaine → même contexte (hors trace_id qui est unique par appel).
    assert via_mcp.context == via_action.context
    assert "User" in via_mcp.context
