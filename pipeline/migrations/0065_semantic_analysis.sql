-- Semantic-analysis layer (pipeline/nlp), tranche 034A: the foundation.
--
-- This is a DOWNSTREAM, non-collecting stage. It reads document_elements
-- (the parser-neutral output of pipeline/documents, migrations 0052-0054)
-- and produces retrieval- and analysis-ready records. It fetches nothing,
-- calls no paid AI service, and — like every layer above the raw archive —
-- produces finding aids and machine candidates, never evidence. Nothing
-- here is attributed to a provider or promoted to a claim without a person;
-- that path is the existing review queue -> graph_claims (0050).
--
-- Four tables ship here:
--
--   nlp_runs            one row per invocation of an nlp stage, carrying the
--                       full software/model/config state, so "why does this
--                       annotation exist?" is answerable the same way it is
--                       for a collected row. Every derived row below points
--                       back to a run.
--   nlp_model_registry  the resolved identity of every model used — provider,
--                       id, and the pinned revision SHA (a model *name* is
--                       not a stable identity; the resolved commit is).
--   document_chunks     paragraph-level units merged from document_elements,
--                       with a CONTENT-DERIVED id so a chunker change cannot
--                       silently repoint an id at different text. The
--                       provenance trail is by element id, not offsets alone:
--                       chunk -> element_start/end -> document_version ->
--                       archived payload.
--   document_embeddings one vector per (chunk, model). Stored as a
--                       dialect-neutral little-endian float32 blob in BOTH
--                       trees for 034A; exact cosine is computed in Python.
--                       A pgvector `vector` column and an ANN index are a
--                       later, Postgres-only migration, added only if the
--                       034A retrieval benchmark shows exact search is too
--                       slow — see docs/semantic-analysis.md.

CREATE TABLE IF NOT EXISTS nlp_runs (
    run_id           TEXT PRIMARY KEY,
    stage            TEXT NOT NULL,          -- 'chunk' | 'embed' | 'spans' | 'context' | 'relations' | 'clusters'
    status           TEXT NOT NULL,          -- 'running' | 'ok' | 'failed'
    started_at       TEXT NOT NULL,
    completed_at     TEXT,
    code_commit      TEXT,
    chunker_version  TEXT,
    model_key        TEXT,
    model_revision   TEXT,
    ontology_version TEXT,
    config_sha256    TEXT NOT NULL,
    input_scope_json TEXT NOT NULL DEFAULT '{}',
    rows_processed   INTEGER NOT NULL DEFAULT 0,
    rows_written     INTEGER NOT NULL DEFAULT 0,
    error            TEXT
);

CREATE INDEX IF NOT EXISTS idx_nlp_runs_stage ON nlp_runs (stage, started_at);

CREATE TABLE IF NOT EXISTS nlp_model_registry (
    model_key          TEXT PRIMARY KEY,     -- our stable handle, e.g. 'embed:minilm-l6-v2'
    model_provider     TEXT NOT NULL,        -- 'sentence-transformers' | 'hash-stub' | 'gliner' | 'spacy' | ...
    model_id           TEXT NOT NULL,        -- the provider's id, e.g. 'sentence-transformers/all-MiniLM-L6-v2'
    revision_sha       TEXT,                 -- resolved commit/revision; NULL for a deterministic stub
    framework          TEXT,
    framework_version  TEXT,
    tokenizer_revision TEXT,
    dimension          INTEGER,
    distance_metric    TEXT NOT NULL DEFAULT 'cosine',
    normalised         INTEGER NOT NULL DEFAULT 1,
    first_seen_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_chunks (
    document_chunk_id            TEXT PRIMARY KEY,   -- sha256(version | chunker_name | chunker_version | chunk_index | text_sha256)
    document_version_id          TEXT NOT NULL REFERENCES document_versions(document_version_id),
    chunker_name                 TEXT NOT NULL,
    chunker_version              TEXT NOT NULL,
    chunk_index                  INTEGER NOT NULL,
    text                         TEXT NOT NULL,
    text_sha256                  TEXT NOT NULL,
    token_estimate               INTEGER NOT NULL,
    page_start                   INTEGER,
    page_end                     INTEGER,
    element_start_id             TEXT REFERENCES document_elements(document_element_id),
    element_end_id               TEXT REFERENCES document_elements(document_element_id),
    preceding_heading_element_id TEXT REFERENCES document_elements(document_element_id),
    char_start                   INTEGER NOT NULL,   -- offset into the version's concatenated element text
    char_end                     INTEGER NOT NULL,
    superseded                   INTEGER NOT NULL DEFAULT 0,
    nlp_run_id                   TEXT REFERENCES nlp_runs(run_id),
    created_at                   TEXT NOT NULL,
    UNIQUE (document_version_id, chunker_name, chunker_version, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_version
    ON document_chunks (document_version_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_document_chunks_live
    ON document_chunks (document_version_id) WHERE superseded = 0;

CREATE TABLE IF NOT EXISTS document_embeddings (
    document_chunk_id TEXT NOT NULL REFERENCES document_chunks(document_chunk_id),
    model_key         TEXT NOT NULL REFERENCES nlp_model_registry(model_key),
    dimension         INTEGER NOT NULL,
    embedding         BLOB NOT NULL,          -- little-endian float32, `dimension` values
    nlp_run_id        TEXT REFERENCES nlp_runs(run_id),
    created_at        TEXT NOT NULL,
    PRIMARY KEY (document_chunk_id, model_key)
);

CREATE INDEX IF NOT EXISTS idx_document_embeddings_model
    ON document_embeddings (model_key);
