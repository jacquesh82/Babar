"""Exposition pour Claude via MCP (Model Context Protocol).

Adaptateur "côté abonnement" : permet à Claude d'appeler la mémoire sans que le
service consomme d'API payante. Il traduit les outils MCP vers le **contrat
commun** et **délègue au service commun** (``interface/common/service``) — aucune
logique métier propre.

Outils MCP exposés (mêmes opérations que le REST) :
  * ``memory.recall``  : question → contexte injectable
  * ``memory.ingest``  : mémoriser un tour de conversation
  * ``memory.correct`` : corriger/oublier un souvenir

Transport : **Streamable HTTP** conforme MCP (spec 2024-11-05), monté sur ``/mcp`` :
  * ``POST`` — messages JSON-RPC 2.0 (``initialize`` / ``tools/list`` /
    ``tools/call`` / notifications). Réponse ``application/json`` pour les
    requêtes, ``202 Accepted`` pour les notifications seules.
  * ``GET`` — flux SSE serveur→client : non offert ici → ``405`` (autorisé par la
    spec quand le serveur n'émet pas de messages spontanés).
  * ``DELETE`` — terminaison explicite de session.
  Chaque ``initialize`` alloue un ``Mcp-Session-Id`` (header) que le client
  renvoie sur les appels suivants ; une session inconnue force une ré-init (404).

Auth : la surface MCP est **authentifiée comme les autres adaptateurs** via
``auth.tenant_isolation`` (mode ``header`` / ``jwt`` / ``single`` selon
``TENANT_MODE``). Le ``TenantContext`` est **résolu depuis la requête HTTP**
(Bearer JWT ou ``X-Tenant-Id``) et **écrase** tout ``tenant`` présent dans le
corps : le client/LLM n'a pas à — et ne peut pas — choisir son tenant.

Découplage #1 : seul endroit autorisé à connaître les spécificités de MCP/Claude.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from auth.tenant_isolation import TenantIsolationError, resolve_tenant_context_async
from config import settings
from interface.common import service
from interface.common.schemas import (
    CorrectionRequest,
    CorrectionResponse,
    IngestRequest,
    IngestResponse,
    RecallRequest,
    RecallResponse,
    TenantContext,
)

_PROTOCOL_VERSION = "2024-11-05"
_SESSION_HEADER = "mcp-session-id"

# Registre de sessions (process-local). Suffisant pour un déploiement mono-worker
# derrière un reverse proxy ; pour scaler horizontalement, adosser à Redis.
_SESSIONS: set[str] = set()


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


def _tenant_payload(tenant: TenantContext) -> dict[str, str]:
    """Sérialise le tenant authentifié pour l'injecter dans les arguments d'outil."""
    payload = {"tenant_id": str(tenant.tenant_id)}
    if tenant.user_id:
        payload["user_id"] = str(tenant.user_id)
    return payload


async def _dispatch(payload: Any, tenant: TenantContext | None = None) -> dict[str, Any] | None:
    """Traite UN message JSON-RPC MCP.

    Retourne la réponse JSON-RPC, ou ``None`` pour une notification (aucun ``id``,
    donc pas de réponse attendue). Quand ``tenant`` est fourni (chemin HTTP
    authentifié), il **écrase** le ``tenant`` du corps sur ``tools/call`` : la
    source de vérité est le token, jamais le client.
    """
    if not isinstance(payload, dict):
        return _error(None, -32600, "message JSON-RPC invalide")

    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}
    is_notification = "id" not in payload

    try:
        if method == "initialize":
            result: dict[str, Any] = {
                # On renvoie la version demandée par le client si présente, sinon la nôtre.
                "protocolVersion": params.get("protocolVersion", _PROTOCOL_VERSION),
                "serverInfo": {"name": "memory-service", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": [_descriptor(name, spec) for name, spec in TOOLS.items()]}
        elif method == "tools/call":
            name = params.get("name")
            spec = TOOLS.get(name)
            if spec is None:
                return _error(request_id, -32602, f"outil inconnu : {name}")
            arguments = dict(params.get("arguments") or {})
            if tenant is not None:
                # Sécurité : le tenant vient de l'auth, on écrase toute valeur cliente.
                arguments["tenant"] = _tenant_payload(tenant)
            req = spec["input_model"].model_validate(arguments)
            response = await spec["handler"](req)
            data = response.model_dump(mode="json")
            result = {
                "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                "structuredContent": data,
            }
        else:
            # Méthode inconnue : erreur pour une requête, silence pour une notification.
            if is_notification:
                return None
            return _error(request_id, -32601, f"méthode inconnue : {method}")
    except Exception as exc:  # noqa: BLE001 — toute erreur devient une erreur JSON-RPC
        if is_notification:
            return None
        return _error(request_id, -32603, str(exc))

    if is_notification:
        return None
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


async def handle_jsonrpc(payload: Any, tenant: TenantContext | None = None) -> dict[str, Any]:
    """Cœur JSON-RPC MCP mono-message (testable sans transport HTTP).

    Conserve la signature historique ; ``tenant`` optionnel pour compat. Une
    notification est acquittée par un résultat vide.
    """
    response = await _dispatch(payload, tenant)
    return response if response is not None else {"jsonrpc": "2.0", "id": None, "result": {}}


def _messages(payload: Any) -> list[Any]:
    """Normalise le corps (message unique ou batch JSON-RPC) en liste."""
    return payload if isinstance(payload, list) else [payload]


def _requires_session(messages: list[Any]) -> bool:
    """Vraie si le lot contient autre chose qu'un ``initialize`` (⇒ session requise)."""
    return any(
        isinstance(m, dict) and m.get("method") and m.get("method") != "initialize"
        for m in messages
    )


def _first_request_id(messages: list[Any]) -> Any:
    for m in messages:
        if isinstance(m, dict) and "id" in m:
            return m["id"]
    return None


def _resource_metadata_url() -> str:
    """URL du document *Protected Resource Metadata* annoncé aux clients MCP."""
    return settings.public_base_url.rstrip("/") + "/.well-known/oauth-protected-resource/mcp"


def _unauthorized(detail: str) -> JSONResponse:
    # RFC 9728 : le header pointe vers les métadonnées de la ressource, d'où le
    # client MCP découvre le serveur d'autorisation (Mindlog.id) et lance le login.
    challenge = (
        'Bearer realm="memory-service", error="invalid_token", '
        f'error_description="{detail}", resource_metadata="{_resource_metadata_url()}"'
    )
    return JSONResponse(
        _error(None, -32001, f"non authentifié : {detail}"),
        status_code=401,
        headers={"WWW-Authenticate": challenge},
    )


def build_mcp_server() -> APIRouter:
    """Construit le router FastAPI exposant la surface MCP Streamable HTTP sur ``/mcp``.

    Monté par ``api_rest``. ``TOOLS`` / ``handle_jsonrpc`` restent réutilisables
    tels quels par un runtime MCP officiel qui remplacerait ce transport.
    """
    router = APIRouter(tags=["mcp"])

    @router.post("/mcp")
    async def mcp_post(request: Request) -> Response:
        # 1. Parse du corps.
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse(_error(None, -32700, "corps JSON invalide"), status_code=400)
        messages = _messages(payload)

        # 2. Auth transport-level (obligatoire) : tenant depuis OIDC/JWT ou X-Tenant-Id.
        try:
            tenant = await resolve_tenant_context_async(
                request.headers.get("x-tenant-id"),
                request.headers.get("authorization"),
            )
        except TenantIsolationError as exc:
            return _unauthorized(str(exc))

        # 3. Gestion de session : initialize en alloue une ; les autres la présentent.
        session_id = request.headers.get(_SESSION_HEADER)
        new_session: str | None = None
        if any(isinstance(m, dict) and m.get("method") == "initialize" for m in messages):
            new_session = uuid4().hex
        elif _requires_session(messages):
            if not session_id:
                return JSONResponse(
                    _error(_first_request_id(messages), -32600, "header Mcp-Session-Id requis"),
                    status_code=400,
                )
            if session_id not in _SESSIONS:
                return JSONResponse(
                    _error(_first_request_id(messages), -32001, "session inconnue — ré-initialiser"),
                    status_code=404,
                )

        # 4. Dispatch de chaque message (le tenant authentifié écrase celui du corps).
        responses = [r for m in messages if (r := await _dispatch(m, tenant)) is not None]

        if new_session is not None:
            _SESSIONS.add(new_session)

        # 5. Réponse HTTP.
        headers: dict[str, str] = {"MCP-Protocol-Version": _PROTOCOL_VERSION}
        if new_session is not None:
            headers[_SESSION_HEADER] = new_session

        if not responses:
            # Que des notifications → accusé de réception sans corps.
            return Response(status_code=202, headers=headers)

        body: Any = responses if isinstance(payload, list) else responses[0]
        return JSONResponse(body, headers=headers)

    @router.get("/.well-known/oauth-protected-resource/mcp")
    @router.get("/.well-known/oauth-protected-resource")
    async def oauth_protected_resource() -> dict[str, Any]:
        # RFC 9728 : découverte du serveur d'autorisation (Mindlog.id) par le client.
        from auth.oidc import protected_resource_metadata

        return protected_resource_metadata()

    @router.get("/mcp")
    async def mcp_get() -> Response:
        # Pas de flux serveur→client spontané : la spec autorise un 405 ici.
        return Response(status_code=405, headers={"Allow": "POST, DELETE"})

    @router.delete("/mcp")
    async def mcp_delete(request: Request) -> Response:
        _SESSIONS.discard(request.headers.get(_SESSION_HEADER))
        return Response(status_code=204)

    return router
