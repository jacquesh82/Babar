"""Contrat commun requête/réponse partagé par TOUS les adaptateurs.

Ce module est le point d'unification entre ``mcp_server.py``, ``openai_action.py``
et ``api_rest.py``. Objectif : **éviter la divergence** — un seul schéma de
requête/réponse, quel que soit le connecteur du LLM consommateur.

Contrainte de découplage (non négociable #1) : ce contrat ne transporte que du
**texte + métadonnées légères (JSON simple)**. Aucune structure propriétaire à
un provider (pas de format de message Anthropic/OpenAI/… ici). Les adaptateurs
dans ``interface/`` sont seuls responsables de traduire *ces* schémas vers/depuis
le format natif du provider.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Types communs
# --------------------------------------------------------------------------- #
class NodeType(str, Enum):
    PERSON = "person"
    PLACE = "place"
    CONCEPT = "concept"
    EVENT = "event"
    OBJECT = "object"
    OTHER = "other"


class Provenance(str, Enum):
    """D'où vient une donnée, pour l'audit — jamais quel LLM la consomme."""
    CONVERSATION = "conversation"
    IMPORT = "import"
    USER_CORRECTION = "user_correction"
    CONSOLIDATION = "consolidation"


class TenantContext(BaseModel):
    """Contexte d'isolation injecté par ``auth/tenant_isolation.py``.

    Présent sur toute requête entrante ; garantit qu'aucune opération ne
    traverse la frontière d'un tenant.
    """
    tenant_id: UUID
    user_id: UUID | None = None


# --------------------------------------------------------------------------- #
# Écriture (ingestion) — entrée
# --------------------------------------------------------------------------- #
class Triple(BaseModel):
    """Fait élémentaire sujet-prédicat-objet, avec métadonnées de mémoire."""
    subject: str
    predicate: str
    object: str
    # Politique de rétention EXPLICITE (pas de decay uniforme, contrainte #3).
    permanent: bool = False
    decay_rate: float = Field(default=0.0, ge=0.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    valid_from: datetime | None = None
    source: Provenance = Provenance.CONVERSATION


class IngestRequest(BaseModel):
    """Ingestion incrémentale : un tour de conversation → triples candidats."""
    tenant: TenantContext
    # Soit du texte brut à extraire, soit des triples déjà formés.
    turn_text: str | None = None
    triples: list[Triple] = Field(default_factory=list)
    conversation_id: str | None = None


class IngestResponse(BaseModel):
    accepted: int
    buffered: int          # posés en short-term (Redis) en attente de promotion
    rejected: int          # écartés par le validator (doublon / incohérence)
    detail: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Lecture (retrieval + context building) — le cœur du service
# --------------------------------------------------------------------------- #
class RecallRequest(BaseModel):
    """Question du LLM cible → contexte mémoire à injecter."""
    tenant: TenantContext
    query: str
    # Budget de tokens STRICT respecté par le linearizer (contrainte #6).
    token_budget: int = Field(default=2000, gt=0)
    # Fenêtre temporelle d'audit : "que savais-tu à cette date ?" (bi-temporalité).
    as_of: datetime | None = None
    max_hops: int = Field(default=2, ge=1, le=5)


class MemoryItem(BaseModel):
    """Un fait retenu, avec la trace de *pourquoi* il a été sélectionné."""
    text: str                          # forme naturelle linéarisée
    score: float
    node_ids: list[UUID] = Field(default_factory=list)
    edge_ids: list[UUID] = Field(default_factory=list)
    # Trace d'observabilité (contrainte #… / observability/tracing.py).
    reason: dict[str, Any] = Field(default_factory=dict)


class RecallResponse(BaseModel):
    """Contrat de sortie vers ``interface/`` : TEXTE + métadonnées légères.

    ``context`` est directement injectable dans le prompt du LLM cible.
    ``items`` et ``trace_id`` servent au debug/audit, pas au provider.
    """
    context: str
    items: list[MemoryItem] = Field(default_factory=list)
    tokens_used: int = 0
    token_budget: int = 0
    trace_id: str | None = None


# --------------------------------------------------------------------------- #
# Feedback (corrections explicites) — "forget that I…"
# --------------------------------------------------------------------------- #
class CorrectionAction(str, Enum):
    FORGET = "forget"          # invalide (valid_until = now), conserve pour audit
    HARD_DELETE = "hard_delete"  # suppression RGPD (droit à l'oubli)
    UPDATE = "update"          # remplace la valeur d'un fait


class CorrectionRequest(BaseModel):
    tenant: TenantContext
    action: CorrectionAction
    # Cible : soit des ids précis, soit une description en langage naturel.
    edge_ids: list[UUID] = Field(default_factory=list)
    node_ids: list[UUID] = Field(default_factory=list)
    natural_language: str | None = None
    replacement: Triple | None = None   # requis si action == UPDATE


class CorrectionResponse(BaseModel):
    affected_nodes: int
    affected_edges: int
    trace_id: str | None = None


# --------------------------------------------------------------------------- #
# Divers
# --------------------------------------------------------------------------- #
class HealthResponse(BaseModel):
    status: str = "ok"
    postgres: bool = False
    redis: bool = False
