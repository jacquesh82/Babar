"""Sélection budgétée des faits → texte naturel injectable.

Dernière étape avant ``interface/``. Prend la liste de ``ScoredFact`` (triée par
score décroissant) et produit une chaîne de texte prête à être injectée dans le
prompt du LLM cible.

Contrainte non négociable #6 : **budget de tokens strict et configurable**, avec
**sélection gloutonne par score décroissant** — on ajoute les faits du plus au
moins pertinent tant que le budget n'est pas dépassé, puis on s'arrête au premier
fait qui déborderait.

Contrainte de découplage #1 : la sortie est du **texte + métadonnées légères**
(``RecallResponse``), jamais une structure propriétaire à un provider.
"""
from __future__ import annotations

import math

from interface.common.schemas import MemoryItem, RecallResponse, TenantContext
from retrieval.scorer import ScoredFact


def count_tokens(text: str) -> int:
    """Estime le nombre de tokens d'un texte (approximation provider-agnostic).

    Heuristique ~4 caractères / token, indépendante de tout tokenizer propriétaire.
    Volontairement conservatrice (au moins 1 token pour un texte non vide).
    """
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def verbalize(fact: ScoredFact) -> str:
    """Transforme un fait (triple scoré) en phrase naturelle concise."""
    text = fact.text.strip()
    if not text:
        return ""
    if not text.endswith((".", "!", "?")):
        text += "."
    return text[0].upper() + text[1:]


def linearize(
    tenant: TenantContext,
    facts: list[ScoredFact],
    token_budget: int,
    trace_id: str | None = None,
) -> RecallResponse:
    """Sélection gloutonne budgétée → ``RecallResponse`` (texte + trace).

    Algorithme:
        1. Parcourir ``facts`` par score décroissant (ordre d'entrée respecté).
        2. Verbaliser, mesurer les tokens, ajouter tant que budget non dépassé.
        3. S'arrêter au premier fait qui ferait déborder le budget (strict).
    """
    lines: list[str] = []
    items: list[MemoryItem] = []
    used = 0

    for fact in facts:
        sentence = verbalize(fact)
        if not sentence:
            continue
        cost = count_tokens(sentence)
        if used + cost > token_budget:
            break  # budget strict : on n'entame pas un fait qui déborde
        used += cost
        lines.append(sentence)
        items.append(
            MemoryItem(
                text=sentence,
                score=fact.score,
                node_ids=fact.node_ids,
                edge_ids=[fact.edge_id] if fact.edge_id is not None else [],
                reason={"components": fact.components, **fact.reason},
            )
        )

    return RecallResponse(
        context="\n".join(lines),
        items=items,
        tokens_used=used,
        token_budget=token_budget,
        trace_id=trace_id,
    )
