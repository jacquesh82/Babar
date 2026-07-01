"""Exposition pour Claude via MCP (Model Context Protocol).

Adaptateur "côté abonnement" : permet à Claude d'appeler la mémoire sans que le
service consomme d'API payante. Il traduit les outils MCP vers le **contrat
commun** et **délègue au service commun** (``interface/common/service``) — aucune
logique métier propre.

Outils MCP exposés (mêmes opérations que le REST) :
  * ``memory.recall``  : question → contexte injectable
  * ``memory.ingest``  : mémoriser un tour de conversation
  * ``memory.correct`` : corriger/oublier un souvenir

Découplage #1 : seul endroit autorisé à connaître les spécificités de MCP/Claude.

NB: le runtime MCP concret (SDK) n'est pas embarqué à ce stade. Les fonctions
``tool_*`` sont fonctionnelles et testables ; ``build_mcp_server`` décrit les
outils et reste à relier au transport MCP réel (TODO). Le ``TenantContext`` est
pris du corps de requête ici ; à terme il proviendra de la session MCP
authentifiée (TODO).
"""
from __future__ import annotations

from interface.common import service
from interface.common.schemas import (
    CorrectionRequest,
    CorrectionResponse,
    IngestRequest,
    IngestResponse,
    RecallRequest,
    RecallResponse,
)


async def tool_recall(req: RecallRequest) -> RecallResponse:
    """Outil MCP ``memory.recall``."""
    return await service.do_recall(req.tenant, req)


async def tool_ingest(req: IngestRequest) -> IngestResponse:
    """Outil MCP ``memory.ingest``."""
    return await service.do_ingest(req.tenant, req)


async def tool_correct(req: CorrectionRequest) -> CorrectionResponse:
    """Outil MCP ``memory.correct``."""
    return await service.do_correct(req.tenant, req)


# Déclaration des outils (nom → handler + schéma d'entrée), consommée par le
# runtime MCP au moment du binding.
TOOLS = {
    "memory.recall": {"handler": tool_recall, "input_model": RecallRequest},
    "memory.ingest": {"handler": tool_ingest, "input_model": IngestRequest},
    "memory.correct": {"handler": tool_correct, "input_model": CorrectionRequest},
}


def build_mcp_server():
    """Construit le serveur MCP en enregistrant ``TOOLS``.

    TODO: brancher un runtime MCP (ex: SDK ``mcp``) et enregistrer chaque outil
    de ``TOOLS`` avec son ``input_model`` comme schéma. Peut aussi être exposé en
    transport HTTP monté sur l'app FastAPI de ``api_rest``.
    """
    raise NotImplementedError("mcp_server.build_mcp_server — runtime MCP à brancher (TODO)")
