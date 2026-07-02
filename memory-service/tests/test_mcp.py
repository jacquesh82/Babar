"""Tests de la surface MCP (JSON-RPC).

Le dispatch (initialize / tools/list / erreurs) est testé sans backend. Un appel
d'outil bout-en-bout (tools/call) nécessite Postgres → skip sinon.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from interface import mcp_server
from interface.common.schemas import TenantContext, Triple
from storage import db, graph_store

pytestmark = pytest.mark.asyncio


async def test_initialize_returns_server_info():
    resp = await mcp_server.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert resp["result"]["serverInfo"]["name"] == "memory-service"
    assert "tools" in resp["result"]["capabilities"]


async def test_tools_list_exposes_three_tools_with_schema():
    resp = await mcp_server.handle_jsonrpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert names == {"memory.recall", "memory.ingest", "memory.correct"}
    for tool in resp["result"]["tools"]:
        assert "inputSchema" in tool and tool["inputSchema"]["type"] == "object"


async def test_unknown_method_is_jsonrpc_error():
    resp = await mcp_server.handle_jsonrpc({"jsonrpc": "2.0", "id": 3, "method": "nope"})
    assert resp["error"]["code"] == -32601


async def test_unknown_tool_is_jsonrpc_error():
    resp = await mcp_server.handle_jsonrpc(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "memory.unknown"}}
    )
    assert resp["error"]["code"] == -32602


async def test_invalid_arguments_is_jsonrpc_error():
    # arguments manquants (pas de tenant/query) → erreur de validation → -32603
    resp = await mcp_server.handle_jsonrpc(
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
         "params": {"name": "memory.recall", "arguments": {}}}
    )
    assert "error" in resp


async def test_tools_call_recall_end_to_end():
    if not await db.ping():
        pytest.skip("Postgres indisponible — test d'intégration skippé")
    tenant = TenantContext(tenant_id=uuid4())
    await graph_store.add_edge(tenant, Triple(subject="user", predicate="lives_in", object="paris"))

    resp = await mcp_server.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "memory.recall",
                "arguments": {
                    "tenant": {"tenant_id": str(tenant.tenant_id)},
                    "query": "where does user live",
                    "token_budget": 200,
                },
            },
        }
    )
    assert "User" in resp["result"]["structuredContent"]["context"]
    assert resp["result"]["content"][0]["type"] == "text"
