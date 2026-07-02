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
> - **Write path** : extraction incrémentale (`ingestion/extractor.py`,
>   heuristique provider-agnostic), coréférence (`ingestion/coref_resolver.py`),
>   validation/dédup (`ingestion/validator.py`), buffer short-term Redis avec
>   critère de promotion explicite (`storage/buffer_store.py`). L'endpoint
>   `/v1/ingest` est **fonctionnel** (bufférise ; la promotion long-term relève
>   du worker de consolidation).
> - **Consolidation** : worker orchestrateur (`consolidation/worker.py`) qui
>   referme la boucle short-term → long-term (promotion), fusion de doublons +
>   résolution de contradictions **LWW avec fermeture temporelle et log
>   obligatoire** (`consolidation/merger.py`), et decay **différencié** permanent
>   vs situationnel (`consolidation/decay.py`).
> - **Feedback** : `/v1/correct` **fonctionnel** (`feedback/corrections.py`) —
>   `forget` (fermeture temporelle, audit préservé), `hard_delete` (RGPD),
>   `update` (ferme l'ancien + ouvre le nouveau) ; cible par ids ou langage naturel.
> - **Adaptateurs** : les 3 connecteurs (`api_rest`, `openai_action`,
>   `mcp_server`) délèguent tous au **service commun** (`interface/common/service.py`)
>   → aucune divergence. Le router Action et la **surface MCP JSON-RPC** (`/mcp`,
>   `initialize`/`tools/list`/`tools/call`) sont montés sur l'app REST.
> - **Vector search** : embeddings pgvector (`storage/vector_store.py`) avec un
>   backend d'embedding **local déterministe** (provider-agnostic) ; recherche ANN
>   cosinus scopée tenant ; **fallback sémantique** dans `entity_linker` et le
>   scoring de `recall`. *Best-effort* : sans pgvector, mode graphe seul.
> - **Auth** : isolation par `X-Tenant-Id`, **JWT HS256** (`auth/jwt_utils.py`,
>   sans dépendance) ou `single` (dev). Voir §7.
> - **Cache** : requêtes fréquentes en Redis (`entity_linker`) avec invalidation
>   sur toute écriture (corrections, consolidation).
> - **Worker** : **ordonnanceur cron intégré** (`consolidation/cron.py`, stdlib)
>   piloté par `CONSOLIDATION_CRON`.
> - **Observabilité** : logs **structlog** + audit persistant des rappels
>   (`recall_log`) et contradictions (`contradiction_log`).
> - **Qualité** : lint/format **ruff**, **CI GitHub Actions** (lint + tests avec
>   Postgres/pgvector + Redis, migrations appliquées).
>
> Seams prêts pour un modèle local (sans changer le reste) : `EXTRACTION_BACKEND`,
> `COREF_BACKEND`, `EMBEDDING_BACKEND` (défauts déterministes, sans API payante).
>
> Tests : `pytest` → **~70 unitaires (purs) verts** ; les tests d'intégration
> DB/Redis se *skippent* automatiquement sans backend, et passent (**104/105**,
> le dernier requérant pgvector) avec Postgres + Redis
> (`docker compose up -d postgres redis`).

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

Commandes utiles via `make` : `make up` / `down` / `test` / `lint` / `fmt` /
`migrate` / `worker`.

## 6. Authentification & isolation multi-tenant

Le mode est choisi par `TENANT_MODE` ; chaque requête doit porter un tenant, sans
quoi elle est rejetée en **401** avant d'atteindre le domaine.

| `TENANT_MODE` | Comment fournir le tenant | Usage |
|---------------|---------------------------|-------|
| `header` (défaut) | En-tête `X-Tenant-Id: <uuid>` | Intégrations simples / gateway de confiance |
| `jwt` | `Authorization: Bearer <JWT HS256>` signé avec `JWT_SECRET` ; claims `JWT_TENANT_CLAIM`/`JWT_USER_CLAIM` | SaaS |
| `single` | — (tenant de dev fixe) | Développement local uniquement |

L'isolation est aussi garantie **au niveau base** (`tenant_id NOT NULL` + index
et filtres scopés) : le mode d'auth est la 1ʳᵉ ligne, la base le filet de sécurité.

```bash
# header
curl -H "X-Tenant-Id: 11111111-1111-1111-1111-111111111111" \
     -H "Content-Type: application/json" \
     -d '{"tenant":{"tenant_id":"11111111-1111-1111-1111-111111111111"},"query":"where do I live?"}' \
     http://localhost:8000/v1/recall
```

## 7. Arborescence

```
memory-service/
├── ingestion/        extractor (backend pluggable), coref_resolver, validator
├── storage/          graph_store (bitemp.), vector_store (pgvector), buffer_store,
│                     db (pool), redis_client, migrations/
├── retrieval/        entity_linker (+ cache), graph_walker, vector_search, scorer
├── consolidation/    worker (+ cron), merger (contradictions LWW), decay
├── context_builder/  linearizer (sélection budgétée → texte)
├── feedback/         corrections explicites ("forget that I…")
├── interface/        common/{schemas,service} + mcp_server + openai_action + api_rest
├── auth/             tenant_isolation (header/jwt/single), jwt_utils
├── observability/    tracing (structlog + audit recall_log)
├── tests/            unitaires purs + intégration + memory_regression
├── .github/workflows/ci.yml   lint + tests (Postgres/pgvector + Redis)
├── config.py · pyproject.toml · Makefile · Dockerfile · docker-compose.yml
├── .env.example
└── README.md
```
