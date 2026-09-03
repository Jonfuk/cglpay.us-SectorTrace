-- Phase 3 embedding cutover support.  `embedding_vec` is the only active
-- semantic value.  The maintenance command validates and drops the legacy
-- bytea column during the controlled table swap; this migration cannot do so
-- safely because production may still have an interrupted 0071 backfill.

CREATE TABLE IF NOT EXISTS embedding_migration_audits (
    migration_id             text PRIMARY KEY,
    status                   text NOT NULL,
    source_row_count         bigint NOT NULL,
    replacement_row_count    bigint,
    model_dimension_counts   jsonb NOT NULL,
    sampled_value_digest     text,
    semantic_parity_digest   text,
    backup_restore_verified  boolean NOT NULL DEFAULT false,
    backup_archive_sha256    text,
    restore_receipt_json     jsonb,
    started_at               timestamptz NOT NULL,
    completed_at             timestamptz,
    error_detail             text
);

-- All three retrieval candidate paths operate over live chunks.  Trigram
-- similarity is ranking only and never an entity-resolution or truth rule.
CREATE INDEX IF NOT EXISTS idx_document_chunks_text_trgm
    ON document_chunks USING gin (text public.gin_trgm_ops) WHERE superseded = 0;

CREATE INDEX IF NOT EXISTS idx_document_chunks_text_fts
    ON document_chunks USING gin (to_tsvector('simple', COALESCE(text, '')))
    WHERE superseded = 0;

-- Stop creating duplicate values immediately. The nullable legacy recovery
-- source remains until `nlp compact-embeddings` performs the measured,
-- maintenance-window compact-table swap.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'document_embeddings'
          AND column_name = 'embedding'
    ) THEN
        ALTER TABLE document_embeddings ALTER COLUMN embedding DROP NOT NULL;
        -- The maintenance command performs a validated compact-table copy,
        -- HNSW rebuild and short swap. Do not turn that operational gate into
        -- an unmeasured startup migration even when every row is backfilled.
    END IF;
END $$;
