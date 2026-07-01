"""Exposition pour Claude via MCP (Model Context Protocol).

Adaptateur "côté abonnement" : permet à Claude d'appeler la mémoire sans que le
service consomme d'API payante. Il traduit les outils MCP vers le **contrat
commun** (``interface/common/schemas.py``) et n'implémente AUCUNE logique métier
propre — il délègue au même domaine que ``api_rest`` et ``openai_action``.

Outils MCP prévus (mêmes opérations que le REST) :
  * ``memory.recall``  : question → contexte injectable
  * ``memory.ingest``  : mémoriser un tour de conversation
  * ``memory.correct`` : corriger/oublier un souvenir

Découplage #1 : c'est le SEUL type d'endroit autorisé à connaître les
spécificités de Claude/MCP. Il ne fuit rien de propriétaire vers le domaine.
"""
from __future__ import annotations

from interface.common.schemas import (
    CorrectionRequest,
    CorrectionResponse,
    IngestRequest,
    IngestResponse,
    RecallRequest,
    RecallResponse,
)


async def tool_recall(req: RecallRequest) -> RecallResponse:
    """Outil MCP ``memory.recall``. TODO: mapper MCP → domaine → RecallResponse."""
    raise NotImplementedError("mcp_server.tool_recall — stub")


async def tool_ingest(req: IngestRequest) -> IngestResponse:
    """Outil MCP ``memory.ingest``. TODO: déléguer au pipeline d'ingestion."""
    raise NotImplementedError("mcp_server.tool_ingest — stub")


async def tool_correct(req: CorrectionRequest) -> CorrectionResponse:
    """Outil MCP ``memory.correct``. TODO: déléguer à feedback.corrections."""
    raise NotImplementedError("mcp_server.tool_correct — stub")


def build_mcp_server():
    """Construit et retourne le serveur MCP (déclaration des outils ci-dessus).

    TODO: brancher un runtime MCP (ex: mcp SDK) et enregistrer les outils.
    Peut aussi être monté comme router sur l'app FastAPI de ``api_rest``.
    """
    raise NotImplementedError("mcp_server.build_mcp_server — stub")
