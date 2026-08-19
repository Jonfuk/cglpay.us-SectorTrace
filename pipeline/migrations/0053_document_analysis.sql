-- Parser-neutral document analysis.  Existing module tables remain the
-- source-specific facts; this side-by-side layer references their immutable
-- provenance through evidence_records rather than attempting to homogenise
-- their natural keys.

CREATE TABLE IF NOT EXISTS document_records (
    document_id             TEXT PRIMARY KEY,
    evidence_id             TEXT NOT NULL REFERENCES evidence_records(evidence_id),
    source_table            TEXT,
    source_key              TEXT,
    document_type           TEXT NOT NULL DEFAULT 'UNKNOWN',
    classification_method   TEXT,
    classification_confidence REAL,
    mime_type               TEXT,
    title                   TEXT,
    filename                TEXT,
    published_at            TEXT,
    language                TEXT,
    page_count              INTEGER,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    UNIQUE (evidence_id)
);

CREATE INDEX IF NOT EXISTS idx_document_records_type
    ON document_records (document_type, published_at);

CREATE TABLE IF NOT EXISTS derived_artifacts (
    artifact_id             TEXT PRIMARY KEY,
    evidence_id             TEXT NOT NULL REFERENCES evidence_records(evidence_id),
    artifact_type           TEXT NOT NULL,
    storage_path            TEXT NOT NULL,
    sha256                  TEXT NOT NULL,
    tool_name               TEXT NOT NULL,
    tool_version            TEXT,
    parameters_json         TEXT NOT NULL,
    created_at              TEXT NOT NULL,
    UNIQUE (evidence_id, artifact_type, sha256)
);

CREATE INDEX IF NOT EXISTS idx_derived_artifacts_evidence
    ON derived_artifacts (evidence_id, artifact_type);

CREATE TABLE IF NOT EXISTS document_versions (
    document_version_id     TEXT PRIMARY KEY,
    document_id             TEXT NOT NULL REFERENCES document_records(document_id),
    parser_name             TEXT NOT NULL,
    parser_version          TEXT NOT NULL,
    parse_schema_version    TEXT NOT NULL,
    source_artifact_id      TEXT REFERENCES derived_artifacts(artifact_id),
    config_hash             TEXT NOT NULL,
    text_sha256             TEXT,
    status                  TEXT NOT NULL,
    is_active               INTEGER NOT NULL DEFAULT 0,
    created_at              TEXT NOT NULL,
    UNIQUE (document_id, parser_name, parser_version, config_hash)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_document_versions_one_active
    ON document_versions (document_id) WHERE is_active = 1;

CREATE TABLE IF NOT EXISTS document_elements (
    document_element_id     TEXT PRIMARY KEY,
    document_version_id     TEXT NOT NULL REFERENCES document_versions(document_version_id),
    parent_element_id       TEXT REFERENCES document_elements(document_element_id),
    element_type            TEXT NOT NULL,
    sequence                INTEGER NOT NULL,
    page_number             INTEGER,
    heading_level           INTEGER,
    text                    TEXT,
    text_sha256             TEXT,
    bbox_json               TEXT,
    metadata_json           TEXT NOT NULL DEFAULT '{}',
    UNIQUE (document_version_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_document_elements_version_page
    ON document_elements (document_version_id, page_number, sequence);
CREATE INDEX IF NOT EXISTS idx_document_elements_search
    ON document_elements (text);

CREATE VIRTUAL TABLE IF NOT EXISTS document_element_search USING fts5(
    document_element_id UNINDEXED,
    document_id UNINDEXED,
    page_number UNINDEXED,
    element_type UNINDEXED,
    text
);

CREATE TABLE IF NOT EXISTS document_tables (
    document_table_id       TEXT PRIMARY KEY,
    document_element_id     TEXT NOT NULL REFERENCES document_elements(document_element_id),
    row_count               INTEGER,
    column_count            INTEGER,
    table_json              TEXT NOT NULL,
    markdown                TEXT
);

CREATE TABLE IF NOT EXISTS document_links (
    document_link_id        TEXT PRIMARY KEY,
    document_element_id     TEXT NOT NULL REFERENCES document_elements(document_element_id),
    href                    TEXT NOT NULL,
    anchor_text             TEXT
);

CREATE TABLE IF NOT EXISTS document_parse_runs (
    document_parse_run_id   TEXT PRIMARY KEY,
    document_id             TEXT NOT NULL REFERENCES document_records(document_id),
    parser_name             TEXT NOT NULL,
    parser_version          TEXT NOT NULL,
    config_hash             TEXT NOT NULL,
    started_at              TEXT NOT NULL,
    completed_at            TEXT,
    status                  TEXT NOT NULL,
    elapsed_ms              INTEGER,
    warning_count           INTEGER NOT NULL DEFAULT 0,
    error                   TEXT
);

CREATE INDEX IF NOT EXISTS idx_document_parse_runs_document
    ON document_parse_runs (document_id, started_at DESC);

CREATE TABLE IF NOT EXISTS document_quality (
    document_version_id     TEXT PRIMARY KEY REFERENCES document_versions(document_version_id),
    status                  TEXT NOT NULL,
    metrics_json            TEXT NOT NULL,
    warnings_json           TEXT NOT NULL,
    created_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_processing_states (
    evidence_id             TEXT PRIMARY KEY REFERENCES evidence_records(evidence_id),
    inspection_status       TEXT NOT NULL DEFAULT 'PENDING',
    ocr_status              TEXT NOT NULL DEFAULT 'OCR_NOT_REQUIRED',
    parse_status            TEXT NOT NULL DEFAULT 'PENDING',
    classification_status   TEXT NOT NULL DEFAULT 'PENDING',
    quality_status          TEXT,
    active_document_version_id TEXT REFERENCES document_versions(document_version_id),
    attempt_count           INTEGER NOT NULL DEFAULT 0,
    last_error              TEXT,
    last_attempted_at       TEXT,
    last_processed_at       TEXT
);

CREATE TABLE IF NOT EXISTS document_topics (
    document_element_id     TEXT NOT NULL REFERENCES document_elements(document_element_id),
    topic                   TEXT NOT NULL,
    match_count             INTEGER NOT NULL,
    match_method            TEXT NOT NULL,
    PRIMARY KEY (document_element_id, topic)
);

CREATE TABLE IF NOT EXISTS document_entity_mentions (
    document_entity_mention_id TEXT PRIMARY KEY,
    document_element_id     TEXT NOT NULL REFERENCES document_elements(document_element_id),
    entity_id               TEXT REFERENCES entities(entity_id),
    matched_text            TEXT NOT NULL,
    match_method            TEXT NOT NULL,
    start_offset            INTEGER,
    end_offset              INTEGER
);

CREATE INDEX IF NOT EXISTS idx_document_entity_mentions_entity
    ON document_entity_mentions (entity_id, document_element_id);
