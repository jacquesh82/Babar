"""Sélection budgétée des faits → texte naturel injectable.

Dernière étape avant ``interface/``. Prend la liste de ``ScoredFact`` (triée par
score décroissant) et produit une chaîne de texte prête à être injectée dans le
prompt du LLM cible.

Contrainte non négociable #6 : **budget de tokens strict et configurable**, avec
**sélection gloutonne par score décroissant** — on ajoute les faits du plus au
moins pertinent tant que le budget n'est pas dépassé, puis on s'arrête.

Contrainte de découplage #1 : la sortie est du **texte + métadonnées légères**
(``RecallResponse``), jamais une structure propriétaire à un provider.
"""
from __future__ import annotations

from interface.common.schemas import MemoryItem, RecallResponse, TenantContext
from retrieval.scorer import ScoredFact


def count_tokens(text: str) -> int:
    """Estime le nombre de tokens d'un texte (approximation provider-agnostic).

    TODO: tokenizer léger indépendant du provider (ex: tiktoken-like local ou
    heuristique mots*facteur). Ne doit pas dépendre d'un LLM cible.
    """
    raise NotImplementedError("linearizer.count_tokens — stub")


def verbalize(fact: ScoredFact) -> str:
    """Transforme un fait (triple scoré) en phrase naturelle concise."""
    raise NotImplementedError("linearizer.verbalize — stub")


def linearize(
    tenant: TenantContext,
    facts: list[ScoredFact],
    token_budget: int,
) -> RecallResponse:
    """Sélection gloutonne budgétée → ``RecallResponse`` (texte + trace).

    Algorithme:
        1. Parcourir ``facts`` par score décroissant.
        2. Verbaliser, mesurer les tokens, ajouter tant que budget non dépassé.
        3. S'arrêter au premier fait qui ferait déborder le budget (strict).

    TODO:
        - Implémenter la boucle gloutonne + garde de budget stricte.
        - Peupler ``items[].reason`` depuis ``fact.components`` (observabilité).
    """
    raise NotImplementedError("linearizer.linearize — stub")
