-- Semantic-analysis layer (pipeline/nlp), tranche 034A: the foundation.
--
-- PostgreSQL dialect of ../0065_semantic_analysis.sql. See README.md in this
-- directory for the conversion rules. TEXT -> text, INTEGER -> bigint,
-- BLOB -> bytea; everything else is identical.
--
-- The embedding is a dialect-neutral little-endian float32 `bytea` in BOTH
-- trees for 034A — exact cosine is computed in Python. A pgvector `vector`
-- column and an ANN index are a later, Postgres-only migration, added only
-- if the 034A retrieval benchmark shows exact search is too slow. That keeps
-- `migrate` runnable on a PostgreSQL server without the `vector` extension
-- installed, and keeps the two trees comparable by
-- tests/test_migration_equivalence.py. See docs/semantic-analysis.md.

CREATE TABLE IF NOT EXISTS nlp_runs (
    run_id           text PRIMARY KEY,
    stage            text NOT NULL,
    status           text NOT NULL,
    started_at       text NOT NULL,
    completed_at     text,
    code_commit      text,
    chunker_version  text,
    model_key        text,
    model_revision   text,
    ontology_version text,
    config_sha256    text NOT NULL,
    input_scope_json text NOT NULL DEFAULT '{}',
    rows_processed   bigint NOT NULL DEFAULT 0,
    rows_written     bigint NOT NULL DEFAULT 0,
    error            text
);

CREATE INDEX IF NOT EXISTS idx_nlp_runs_stage ON nlp_runs (stage, started_at);

CREATE TABLE IF NOT EXISTS nlp_model_registry (
    model_key          text PRIMARY KEY,
    model_provider     text NOT NULL,
    model_id           text NOT NULL,
    revision_sha       text,
    framework          text,
    framework_version  text,
    tokenizer_revision text,
    dimension          bigint,
    distance_metric    text NOT NULL DEFAULT 'cosine',
    normalised         bigint NOT NULL DEFAULT 1,
    first_seen_at      text NOT NULL
);

CREATE TABLE IF NOT EXISTS document_chunks (
    document_chunk_id            text PRIMARY KEY,
    document_version_id          text NOT NULL REFERENCES document_versions(document_version_id),
    chunker_name                 text NOT NULL,
    chunker_version              text NOT NULL,
    chunk_index                  bigint NOT NULL,
    text                         text NOT NULL,
    text_sha256                  text NOT NULL,
    token_estimate               bigint NOT NULL,
    page_start                   bigint,
    page_end                     bigint,
    element_start_id             text REFERENCES document_elements(document_element_id),
    element_end_id               text REFERENCES document_elements(document_element_id),
    preceding_heading_element_id text REFERENCES document_elements(document_element_id),
    char_start                   bigint NOT NULL,
    char_end                     bigint NOT NULL,
    superseded                   bigint NOT NULL DEFAULT 0,
    nlp_run_id                   text REFERENCES nlp_runs(run_id),
    created_at                   text NOT NULL,
    UNIQUE (document_version_id, chunker_name, chunker_version, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_version
    ON document_chunks (document_version_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_document_chunks_live
    ON document_chunks (document_version_id) WHERE superseded = 0;

CREATE TABLE IF NOT EXISTS document_embeddings (
    document_chunk_id text NOT NULL REFERENCES document_chunks(document_chunk_id),
    model_key         text NOT NULL REFERENCES nlp_model_registry(model_key),
    dimension         bigint NOT NULL,
    embedding         bytea NOT NULL,
    nlp_run_id        text REFERENCES nlp_runs(run_id),
    created_at        text NOT NULL,
    PRIMARY KEY (document_chunk_id, model_key)
);

CREATE INDEX IF NOT EXISTS idx_document_embeddings_model
    ON document_embeddings (model_key);
