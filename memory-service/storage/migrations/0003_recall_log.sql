-- ===========================================================================
-- Journal d'audit des rappels : *pourquoi* ce contexte a été injecté.
-- Alimenté par observability/tracing.persist_recall (best-effort).
-- ===========================================================================
CREATE TABLE IF NOT EXISTS recall_log (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id    UUID NOT NULL,
    trace_id     TEXT NOT NULL,
    query        TEXT,
    selected     JSONB NOT NULL DEFAULT '[]'::jsonb,   -- faits retenus (edge ids)
    rejected     JSONB NOT NULL DEFAULT '[]'::jsonb,   -- faits écartés (edge ids)
    tokens_used  INTEGER NOT NULL DEFAULT 0,
    token_budget INTEGER NOT NULL DEFAULT 0,
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_recall_log_tenant ON recall_log (tenant_id);
CREATE INDEX IF NOT EXISTS ix_recall_log_trace  ON recall_log (trace_id);
