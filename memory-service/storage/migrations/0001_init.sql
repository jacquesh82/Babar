-- ===========================================================================
-- memory-service — migration initiale.
-- Graphe bi-temporel + index vectoriel + isolation multi-tenant.
--
-- Contraintes non négociables reflétées ici :
--   * bi-temporalité obligatoire sur les arêtes (valid_from / valid_until / recorded_at)
--   * tenant_id NOT NULL sur nœuds ET arêtes (isolation au niveau BASE, pas applicatif)
--   * flag `permanent` + `decay_rate` explicites (pas de decay uniforme)
-- ===========================================================================

-- Extensions -----------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;   -- pgvector

-- ===========================================================================
-- memory_nodes : entités / concepts du graphe de connaissances.
-- ===========================================================================
CREATE TABLE IF NOT EXISTS memory_nodes (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Isolation multi-tenant : OBLIGATOIRE, contrainte au niveau base.
    tenant_id     UUID NOT NULL,

    -- Identité de l'entité.
    node_type     TEXT NOT NULL,              -- ex: 'person', 'place', 'concept', 'event'
    canonical_key TEXT NOT NULL,              -- clé normalisée pour dédup / désambiguïsation
    label         TEXT NOT NULL,              -- libellé lisible

    -- Attributs libres (non structurés).
    attributes    JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Métadonnées de mémoire.
    importance    REAL NOT NULL DEFAULT 0.5,  -- [0,1], modulé par decay
    permanent     BOOLEAN NOT NULL DEFAULT FALSE,  -- fait "permanent déclaré" -> jamais decay
    decay_rate    REAL NOT NULL DEFAULT 0.0,  -- taux de décroissance explicite (0 = pas de decay)

    -- Bi-temporalité.
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Un même (tenant, entité canonique) n'existe qu'une fois.
    CONSTRAINT uq_node_tenant_key UNIQUE (tenant_id, canonical_key)
);

CREATE INDEX IF NOT EXISTS ix_nodes_tenant       ON memory_nodes (tenant_id);
CREATE INDEX IF NOT EXISTS ix_nodes_tenant_type  ON memory_nodes (tenant_id, node_type);
CREATE INDEX IF NOT EXISTS ix_nodes_attributes   ON memory_nodes USING gin (attributes);

-- ===========================================================================
-- memory_edges : relations (triples sujet-prédicat-objet) BI-TEMPORELLES.
--   valid_from / valid_until : temps de VALIDITÉ du fait dans le monde réel.
--   recorded_at              : temps de TRANSACTION (quand on l'a appris).
-- Une contradiction se traduit par la fermeture (valid_until) de l'ancienne
-- arête et l'ouverture d'une nouvelle — jamais un UPDATE destructif.
-- ===========================================================================
CREATE TABLE IF NOT EXISTS memory_edges (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Isolation multi-tenant : OBLIGATOIRE.
    tenant_id     UUID NOT NULL,

    -- Triple.
    subject_id    UUID NOT NULL REFERENCES memory_nodes (id) ON DELETE CASCADE,
    predicate     TEXT NOT NULL,
    object_id     UUID NOT NULL REFERENCES memory_nodes (id) ON DELETE CASCADE,

    -- Poids relationnel (utilisé par graph_walker top-K et le scorer).
    weight        REAL NOT NULL DEFAULT 1.0,

    -- Métadonnées de mémoire (par-arête).
    importance    REAL NOT NULL DEFAULT 0.5,
    permanent     BOOLEAN NOT NULL DEFAULT FALSE,
    decay_rate    REAL NOT NULL DEFAULT 0.0,

    -- Provenance / traçabilité.
    source        TEXT,                        -- d'où vient le fait (conversation id, import, …)
    confidence    REAL NOT NULL DEFAULT 1.0,

    -- Bi-temporalité (OBLIGATOIRE).
    valid_from    TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_until   TIMESTAMPTZ,                 -- NULL = encore valide
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_edge_validity CHECK (valid_until IS NULL OR valid_until >= valid_from),
    -- Le sujet et l'objet doivent appartenir au même tenant que l'arête :
    -- garanti applicativement + à renforcer par trigger si besoin (voir TODO).
    CONSTRAINT ck_edge_not_self CHECK (subject_id <> object_id OR predicate IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS ix_edges_tenant        ON memory_edges (tenant_id);
CREATE INDEX IF NOT EXISTS ix_edges_subject       ON memory_edges (tenant_id, subject_id);
CREATE INDEX IF NOT EXISTS ix_edges_object        ON memory_edges (tenant_id, object_id);
CREATE INDEX IF NOT EXISTS ix_edges_predicate     ON memory_edges (tenant_id, predicate);
-- Arêtes actuellement valides (requête la plus fréquente).
CREATE INDEX IF NOT EXISTS ix_edges_current       ON memory_edges (tenant_id, subject_id)
    WHERE valid_until IS NULL;

-- TODO: trigger de cohérence tenant (subject.tenant_id = edge.tenant_id = object.tenant_id).

-- ===========================================================================
-- memory_embeddings : vecteurs pgvector associés aux nœuds (recherche ANN).
-- Séparé de memory_nodes pour rester agnostique de la dimension/modèle.
-- ===========================================================================
CREATE TABLE IF NOT EXISTS memory_embeddings (
    node_id     UUID PRIMARY KEY REFERENCES memory_nodes (id) ON DELETE CASCADE,
    tenant_id   UUID NOT NULL,
    model       TEXT NOT NULL,                 -- modèle d'embedding utilisé
    -- La dimension (1536) DOIT correspondre à EMBEDDING_DIM ; ajuster si besoin.
    embedding   vector(1536) NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_embeddings_tenant ON memory_embeddings (tenant_id);
-- Index ANN (cosine). ivfflat nécessite ANALYZE + des données ; hnsw possible aussi.
CREATE INDEX IF NOT EXISTS ix_embeddings_ann
    ON memory_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ===========================================================================
-- contradiction_log : trace de TOUTE contradiction (contrainte non négociable #4).
-- Alimenté par consolidation/merger.py, consommé par observability/tracing.py.
-- ===========================================================================
CREATE TABLE IF NOT EXISTS contradiction_log (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id      UUID NOT NULL,
    kept_edge_id   UUID,                        -- arête retenue
    dropped_edge_id UUID,                       -- arête fermée / écartée
    strategy       TEXT NOT NULL,               -- 'lww' | 'llm_arbitration' | ...
    detail         JSONB NOT NULL DEFAULT '{}'::jsonb,
    recorded_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_contradiction_tenant ON contradiction_log (tenant_id);
