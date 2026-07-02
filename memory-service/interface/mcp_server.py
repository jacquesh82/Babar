"""Exposition pour Claude via MCP (Model Context Protocol).

Adaptateur "côté abonnement" : permet à Claude d'appeler la mémoire sans que le
service consomme d'API payante. Il traduit les outils MCP vers le **contrat
commun** et **délègue au service commun** (``interface/common/service``) — aucune
logique métier propre.

Outils MCP exposés (mêmes opérations que le REST) :
  * ``memory.recall``  : question → contexte injectable
  * ``memory.ingest``  : mémoriser un tour de conversation
  * ``memory.correct`` : corriger/oublier un souvenir

Transport : une surface **JSON-RPC 2.0** conforme MCP (``initialize`` /
``tools/list`` / ``tools/call``) montée sur l'app FastAPI (``build_mcp_server``).
Elle est indépendante d'un SDK propriétaire ; un runtime MCP officiel peut la
remplacer sans toucher aux handlers ni au domaine.

Découplage #1 : seul endroit autorisé à connaître les spécificités de MCP/Claude.

NB: le ``TenantContext`` provient ici du corps de requête (champ ``tenant``) ; en
déploiement réel il proviendra de la session MCP authentifiée (TODO auth).
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request

from interface.common import service
from interface.common.schemas import (
    CorrectionRequest,
    CorrectionResponse,
    IngestRequest,
    IngestResponse,
    RecallRequest,
    RecallResponse,
)

_PROTOCOL_VERSION = "2024-11-05"


async def tool_recall(req: RecallRequest) -> RecallResponse:
    """Outil MCP ``memory.recall``."""
    return await service.do_recall(req.tenant, req)


async def tool_ingest(req: IngestRequest) -> IngestResponse:
    """Outil MCP ``memory.ingest``."""
    return await service.do_ingest(req.tenant, req)


async def tool_correct(req: CorrectionRequest) -> CorrectionResponse:
    """Outil MCP ``memory.correct``."""
    return await service.do_correct(req.tenant, req)


# Déclaration des outils (nom → handler + schéma d'entrée + description).
TOOLS: dict[str, dict[str, Any]] = {
    "memory.recall": {
        "handler": tool_recall,
        "input_model": RecallRequest,
        "description": "Récupère un contexte mémoire pertinent pour une question.",
    },
    "memory.ingest": {
        "handler": tool_ingest,
        "input_model": IngestRequest,
        "description": "Mémorise un tour de conversation (extraction incrémentale).",
    },
    "memory.correct": {
        "handler": tool_correct,
        "input_model": CorrectionRequest,
        "description": "Corrige ou oublie un souvenir explicitement.",
    },
}


def _descriptor(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "description": spec["description"],
        "inputSchema": spec["input_model"].model_json_schema(),
    }


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


async def handle_jsonrpc(payload: dict[str, Any]) -> dict[str, Any]:
    """Cœur JSON-RPC MCP (testable sans transport HTTP).

    Supporte ``initialize``, ``tools/list`` et ``tools/call``. Les erreurs
    d'outil sont renvoyées comme erreurs JSON-RPC, jamais propagées en exception.
    """
    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}

    try:
        if method == "initialize":
            result: dict[str, Any] = {
                "protocolVersion": _PROTOCOL_VERSION,
                "serverInfo": {"name": "memory-service", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            }
        elif method == "tools/list":
            result = {"tools": [_descriptor(name, spec) for name, spec in TOOLS.items()]}
        elif method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            spec = TOOLS.get(name)
            if spec is None:
                return _error(request_id, -32602, f"outil inconnu : {name}")
            req = spec["input_model"].model_validate(arguments)
            response = await spec["handler"](req)
            data = response.model_dump(mode="json")
            result = {
                "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                "structuredContent": data,
            }
        else:
            return _error(request_id, -32601, f"méthode inconnue : {method}")
    except Exception as exc:  # noqa: BLE001 — toute erreur devient une erreur JSON-RPC
        return _error(request_id, -32603, str(exc))

    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def build_mcp_server():
    """Construit le router FastAPI exposant la surface MCP (JSON-RPC sur ``/mcp``).

    Monté par ``api_rest``. Un runtime MCP officiel (SDK) pourrait remplacer ce
    transport en réutilisant ``TOOLS`` et ``handle_jsonrpc`` tels quels.
    """
    router = APIRouter(tags=["mcp"])

    @router.post("/mcp")
    async def mcp_rpc(request: Request) -> dict[str, Any]:
        payload = await request.json()
        return await handle_jsonrpc(payload)

    return router
