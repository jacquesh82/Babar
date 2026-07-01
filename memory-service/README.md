# memory-service

Service de **mémoire persistante, structurée en graphe**, conçu pour être
**agnostique du LLM consommateur** (Claude, GPT, Gemini, Mistral, …).

L'objectif est de reproduire des capacités proches de la mémoire humaine :
stockage à très grande échelle, activation rapide sur un sujet précis, et
génération d'un **contexte optimisé** injecté dans le prompt du LLM cible —
sans jamais dépendre d'un provider particulier ni consommer une API payante.
L'intégration se fait via des **connecteurs côté abonnement** (MCP pour Claude,
Actions/OpenAPI pour ChatGPT, REST en fallback).

> État actuel : squelette d'architecture (stubs + TODOs) avec plusieurs couches
> **implémentées et testées** :
> - **Fondations** : `config.py`, pool Postgres (`storage/db.py`), isolation
>   multi-tenant (`auth/tenant_isolation.py`), CRUD bi-temporel du graphe
>   (`storage/graph_store.py`).
> - **Read path** : liaison d'entités (`retrieval/entity_linker.py`), traversée
>   N-sauts (`retrieval/graph_walker.py`), fusion+scoring (`retrieval/scorer.py`),
>   linéarisation budgétée (`context_builder/linearizer.py`), tracing
>   (`observability/tracing.py`). L'endpoint `/v1/recall` est **fonctionnel**
>   bout-en-bout (activation par graphe ; le fallback vectoriel reste en TODO).
>
> Restent en stub : ingestion LLM, `consolidation/{merger,decay}`,
> `storage/{vector_store,buffer_store}`, adaptateurs MCP/Action.
>
> Tests : `pytest` → 21 unitaires (purs) verts ; les tests d'intégration
> DB (`graph_store`, `graph_walker`, recall) se *skippent* automatiquement sans
> Postgres joignable (les lancer via `docker compose up -d postgres`).

---

## 1. Architecture en 3 couches

La mémoire est organisée comme un système cognitif à trois niveaux :

| Couche | Rôle | Support technique | Durée de vie |
|--------|------|-------------------|--------------|
| **Working memory** | Contexte de la requête courante : entités actives, sous-graphe pertinent, budget de tokens. Reconstruit à chaque requête. | En mémoire (process FastAPI) | Le temps d'une requête |
| **Short-term memory** | Buffer des faits récents extraits tour par tour, en attente de validation/consolidation. | **Redis** | Minutes → heures, jusqu'à promotion |
| **Long-term memory** | Graphe de connaissances bi-temporel + index vectoriel. Source de vérité. | **PostgreSQL** (`memory_nodes` / `memory_edges`) + **pgvector** | Persistant (avec decay contrôlé) |

Le passage short-term → long-term est **explicite** (voir
`storage/buffer_store.py`, critère de promotion) et non automatique.

```
                +-------------------+
   requête ---> |  Working memory   |  (activation, scoring, linéarisation)
                +---------+---------+
                          |
              +-----------+-----------+
              |                       |
      +-------v-------+      +--------v--------+
      | Short-term    |      |   Long-term     |
      | (Redis)       |      | (Postgres +     |
      | buffer tour   | ---> |  pgvector)      |
      | par tour      | prom.|  graphe bitemp. |
      +---------------+      +-----------------+
                                     ^
                                     |
                          +----------+----------+
                          | Worker consolidation |
                          | (merge / decay, cron)|
                          +---------------------+
```

## 2. Flux d'une requête (question → injection)

```
question
   │
   ▼
[retrieval/entity_linker]   question → entités candidates (+ cache requêtes fréquentes)
   │
   ├─► [retrieval/graph_walker]    traversée N-sauts, top-K arêtes par nœud (par poids)
   │
   └─► [retrieval/vector_search]   similarité sémantique (ANN via pgvector)
   │
   ▼
[retrieval/scorer]          fusion + scoring (pertinence / récence / importance / poids relationnel)
   │
   ▼
[context_builder/linearizer] sélection gloutonne budgétée (budget de tokens strict) → texte naturel
   │
   ▼
[interface/*]               injection dans le prompt du LLM cible (MCP / Action / REST)
```

Le flux d'écriture (ingestion) est symétrique et **incrémental** (par tour de
conversation, pas en fin de session) :

```
tour de conversation
   │
   ▼
[ingestion/extractor]        extraction incrémentale de triples
   │
   ▼
[ingestion/coref_resolver]   résolution de coréférence + désambiguïsation d'entités
   │
   ▼
[ingestion/validator]        dédoublonnage + cohérence
   │
   ▼
[storage/buffer_store]       écriture short-term (Redis)  ──promotion──►  [storage/graph_store] + [storage/vector_store]
```

## 3. Contraintes de conception non négociables

1. **Découplage strict LLM** — aucun module hors de `interface/` ne connaît le
   LLM consommateur. Le contrat `context_builder → interface` est **du texte +
   métadonnées légères (JSON simple)**, jamais une structure propriétaire.
2. **Bi-temporalité** sur les arêtes (`valid_from`, `valid_until`,
   `recorded_at`) → audit ("que savais-tu de moi à telle date ?") et RGPD.
3. **Pas de decay uniforme** — chaque fait porte `permanent: bool` ou un
   `decay_rate` explicite à l'écriture.
4. **Toute contradiction** détectée par `consolidation/merger.py` est **loguée**
   (voir `observability/tracing.py`), jamais résolue silencieusement.
5. **Isolation multi-tenant dès le schéma** — chaque nœud/arête porte un
   `tenant_id` obligatoire, avec contrainte **au niveau base de données**.
6. **Budget de tokens strict et configurable** dans le linearizer, sélection
   gloutonne par score décroissant.

## 4. Décisions d'architecture à trancher (documentées, non figées)

- **Résolution de contradiction** (`merger.py`) : deux stratégies possibles —
  *dernière-écriture-gagne* (LWW, simple, déterministe) ou *arbitrage LLM*
  (plus riche mais coûteux/non déterministe). Choix par défaut proposé :
  **LWW avec fermeture temporelle** (l'ancienne arête reçoit un `valid_until`,
  la nouvelle un `valid_from`), l'arbitrage LLM restant optionnel et loggué.
  → à trancher avant implémentation de `merger.py`.
- **Worker de consolidation** : Celery vs arq. Le `docker-compose.yml` prévoit
  un service `worker` générique + `redis` comme broker ; le choix final est
  isolé dans `consolidation/` et n'impacte pas le reste.

## 5. Lancement local

Prérequis : Docker + Docker Compose.

```bash
cp .env.example .env         # ajuster les secrets / mots de passe
docker compose up --build    # api + postgres(pgvector) + redis + worker
```

Services exposés :

| Service | Port | Description |
|---------|------|-------------|
| `api` | `8000` | FastAPI (REST + monte les routers MCP / Action) |
| `postgres` | `5432` | PostgreSQL 16 + extension `vector` (pgvector) |
| `redis` | `6379` | Buffer short-term / broker worker |
| `worker` | — | Consolidation périodique (merge + decay) |

La migration SQL initiale se trouve dans
[`storage/migrations/0001_init.sql`](storage/migrations/0001_init.sql).

Documentation OpenAPI auto-générée : http://localhost:8000/docs

## 6. Arborescence

```
memory-service/
├── ingestion/        extraction incrémentale de triples, coréférence, validation
├── storage/          graph_store (bitemp.), vector_store (pgvector), buffer_store (Redis)
├── retrieval/        entity_linker, graph_walker, vector_search, scorer
├── consolidation/    merger (contradictions), decay (importance)
├── context_builder/  linearizer (sélection budgétée → texte)
├── feedback/         corrections explicites ("forget that I…")
├── interface/        common/schemas + mcp_server + openai_action + api_rest
├── auth/             tenant_isolation (multi-tenant strict)
├── observability/    tracing ("pourquoi ce contexte a été injecté ?")
├── tests/            memory_regression (survie des faits stables)
├── docker-compose.yml
├── .env.example
└── README.md
```
