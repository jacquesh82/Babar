-- ===========================================================================
-- Ajoute le suivi temporel du decay d'importance.
-- Permet à consolidation/decay.py d'appliquer une décroissance IDEMPOTENTE
-- (élapsé = now - importance_updated_at) au lieu de recalculer depuis
-- recorded_at à chaque passage (ce qui sur-décroîtrait).
-- ===========================================================================
ALTER TABLE memory_edges
    ADD COLUMN IF NOT EXISTS importance_updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

ALTER TABLE memory_nodes
    ADD COLUMN IF NOT EXISTS importance_updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
