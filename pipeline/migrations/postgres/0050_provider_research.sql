-- PostgreSQL counterpart of 0050_provider_research.sql. Keep its columns and
-- object names structurally identical to the SQLite migration.

CREATE TABLE IF NOT EXISTS provider_research_runs (
    run_id                    TEXT PRIMARY KEY,
    prompt_version            TEXT NOT NULL,
    actor_type                TEXT NOT NULL CHECK (actor_type IN ('human', 'ai')),
    actor_id                  TEXT,
    model_id                  TEXT,
    started_at                TEXT NOT NULL,
    completed_at              TEXT,
    manifest_sha256           TEXT NOT NULL,
    manifest_archive_path     TEXT NOT NULL,
    source_bundle_archive_prefix TEXT,
    status                    TEXT NOT NULL CHECK (status IN ('validated', 'ingested', 'rejected', 'superseded')),
    item_count                INTEGER NOT NULL DEFAULT 0,
    source_count              INTEGER NOT NULL DEFAULT 0,
    validation_errors         TEXT,
    created_at                TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_provider_research_runs_manifest
    ON provider_research_runs (manifest_sha256);

CREATE TABLE IF NOT EXISTS provider_research_items (
    id                         BIGSERIAL PRIMARY KEY,
    run_id                     TEXT NOT NULL REFERENCES provider_research_runs (run_id),
    candidate_key              TEXT NOT NULL UNIQUE,
    provider_key               TEXT NOT NULL REFERENCES providers (provider_key),
    entity_type                TEXT,
    entity_identifier          TEXT,
    category                   TEXT NOT NULL,
    fact_type                  TEXT NOT NULL,
    question                   TEXT NOT NULL,
    raw_finding                TEXT,
    interpretation             TEXT,
    source_url                 TEXT,
    publisher                  TEXT,
    published_date             TEXT,
    accessed_at                TEXT NOT NULL,
    citation                   TEXT,
    licence                    TEXT,
    identity_match_basis       TEXT NOT NULL,
    time_period                TEXT,
    confidence                 DOUBLE PRECISION,
    evidence_status            TEXT NOT NULL CHECK (evidence_status IN (
        'evidence_found', 'candidate', 'no_evidence', 'source_inaccessible',
        'not_applicable', 'existing_project_evidence')),
    destination                TEXT NOT NULL,
    content_sha256             TEXT,
    source_archive_path        TEXT,
    priority_score             DOUBLE PRECISION,
    priority_factors_json      TEXT,
    identity_review_state       TEXT NOT NULL DEFAULT 'pending' CHECK (identity_review_state IN ('pending', 'approved', 'rejected')),
    evidence_review_state       TEXT NOT NULL DEFAULT 'pending' CHECK (evidence_review_state IN ('pending', 'approved', 'rejected')),
    state                      TEXT NOT NULL DEFAULT 'candidate' CHECK (state IN ('candidate', 'approved', 'rejected', 'superseded')),
    identity_review_item_id    BIGINT REFERENCES review_queue (id),
    evidence_review_item_id    BIGINT REFERENCES review_queue (id),
    supersedes_item_id         BIGINT REFERENCES provider_research_items (id),
    created_at                 TEXT NOT NULL,
    updated_at                 TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_provider_research_items_provider
    ON provider_research_items (provider_key, category, state);
CREATE INDEX IF NOT EXISTS idx_provider_research_items_review
    ON provider_research_items (identity_review_state, evidence_review_state, state);
CREATE INDEX IF NOT EXISTS idx_provider_research_items_run
    ON provider_research_items (run_id, id);

CREATE TABLE IF NOT EXISTS provider_research_evidence (
    id                         BIGSERIAL PRIMARY KEY,
    source_item_id             BIGINT NOT NULL UNIQUE REFERENCES provider_research_items (id),
    provider_key               TEXT NOT NULL REFERENCES providers (provider_key),
    entity_type                TEXT,
    entity_identifier          TEXT,
    category                   TEXT NOT NULL,
    fact_type                  TEXT NOT NULL,
    question                   TEXT NOT NULL,
    raw_finding                TEXT,
    interpretation             TEXT,
    source_url                 TEXT NOT NULL,
    publisher                  TEXT,
    published_date             TEXT,
    accessed_at                TEXT NOT NULL,
    citation                   TEXT NOT NULL,
    licence                    TEXT,
    identity_match_basis       TEXT NOT NULL,
    time_period                TEXT,
    confidence                 DOUBLE PRECISION,
    destination                TEXT NOT NULL,
    content_sha256             TEXT NOT NULL,
    source_archive_path        TEXT NOT NULL,
    promoted_by                TEXT NOT NULL,
    promoted_at                TEXT NOT NULL,
    superseded_at              TEXT
);

CREATE INDEX IF NOT EXISTS idx_provider_research_evidence_provider
    ON provider_research_evidence (provider_key, category, promoted_at);
CREATE INDEX IF NOT EXISTS idx_provider_research_evidence_period
    ON provider_research_evidence (provider_key, time_period);
