-- PostgreSQL dialect of ../0051_document_analysis.sql.

CREATE TABLE IF NOT EXISTS document_records (
    document_id             text PRIMARY KEY,
    evidence_id             text NOT NULL REFERENCES evidence_records(evidence_id),
    source_table            text,
    source_key              text,
    document_type           text NOT NULL DEFAULT 'UNKNOWN',
    classification_method   text,
    classification_confidence double precision,
    mime_type               text,
    title                   text,
    filename                text,
    published_at            text,
    language                text,
    page_count              bigint,
    created_at              text NOT NULL,
    updated_at              text NOT NULL,
    UNIQUE (evidence_id)
);

CREATE INDEX IF NOT EXISTS idx_document_records_type
    ON document_records (document_type, published_at);

CREATE TABLE IF NOT EXISTS derived_artifacts (
    artifact_id             text PRIMARY KEY,
    evidence_id             text NOT NULL REFERENCES evidence_records(evidence_id),
    artifact_type           text NOT NULL,
    storage_path            text NOT NULL,
    sha256                  text NOT NULL,
    tool_name               text NOT NULL,
    tool_version            text,
    parameters_json         text NOT NULL,
    created_at              text NOT NULL,
    UNIQUE (evidence_id, artifact_type, sha256)
);

CREATE INDEX IF NOT EXISTS idx_derived_artifacts_evidence
    ON derived_artifacts (evidence_id, artifact_type);

CREATE TABLE IF NOT EXISTS document_versions (
    document_version_id     text PRIMARY KEY,
    document_id             text NOT NULL REFERENCES document_records(document_id),
    parser_name             text NOT NULL,
    parser_version          text NOT NULL,
    parse_schema_version    text NOT NULL,
    source_artifact_id      text REFERENCES derived_artifacts(artifact_id),
    config_hash             text NOT NULL,
    text_sha256             text,
    status                  text NOT NULL,
    is_active               bigint NOT NULL DEFAULT 0,
    created_at              text NOT NULL,
    UNIQUE (document_id, parser_name, parser_version, config_hash)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_document_versions_one_active
    ON document_versions (document_id) WHERE is_active = 1;

CREATE TABLE IF NOT EXISTS document_elements (
    document_element_id     text PRIMARY KEY,
    document_version_id     text NOT NULL REFERENCES document_versions(document_version_id),
    parent_element_id       text REFERENCES document_elements(document_element_id),
    element_type            text NOT NULL,
    sequence                bigint NOT NULL,
    page_number             bigint,
    heading_level           bigint,
    text                    text,
    text_sha256             text,
    bbox_json               text,
    metadata_json           text NOT NULL DEFAULT '{}',
    UNIQUE (document_version_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_document_elements_version_page
    ON document_elements (document_version_id, page_number, sequence);
CREATE INDEX IF NOT EXISTS idx_document_elements_search
    ON document_elements USING gin (to_tsvector('simple', COALESCE(text, '')));

CREATE TABLE IF NOT EXISTS document_tables (
    document_table_id       text PRIMARY KEY,
    document_element_id     text NOT NULL REFERENCES document_elements(document_element_id),
    row_count               bigint,
    column_count            bigint,
    table_json              text NOT NULL,
    markdown                text
);

CREATE TABLE IF NOT EXISTS document_links (
    document_link_id        text PRIMARY KEY,
    document_element_id     text NOT NULL REFERENCES document_elements(document_element_id),
    href                    text NOT NULL,
    anchor_text             text
);

CREATE TABLE IF NOT EXISTS document_parse_runs (
    document_parse_run_id   text PRIMARY KEY,
    document_id             text NOT NULL REFERENCES document_records(document_id),
    parser_name             text NOT NULL,
    parser_version          text NOT NULL,
    config_hash             text NOT NULL,
    started_at              text NOT NULL,
    completed_at            text,
    status                  text NOT NULL,
    elapsed_ms              bigint,
    warning_count           bigint NOT NULL DEFAULT 0,
    error                   text
);

CREATE INDEX IF NOT EXISTS idx_document_parse_runs_document
    ON document_parse_runs (document_id, started_at DESC);

CREATE TABLE IF NOT EXISTS document_quality (
    document_version_id     text PRIMARY KEY REFERENCES document_versions(document_version_id),
    status                  text NOT NULL,
    metrics_json            text NOT NULL,
    warnings_json           text NOT NULL,
    created_at              text NOT NULL
);

CREATE TABLE IF NOT EXISTS document_processing_states (
    evidence_id             text PRIMARY KEY REFERENCES evidence_records(evidence_id),
    inspection_status       text NOT NULL DEFAULT 'PENDING',
    ocr_status              text NOT NULL DEFAULT 'OCR_NOT_REQUIRED',
    parse_status            text NOT NULL DEFAULT 'PENDING',
    classification_status   text NOT NULL DEFAULT 'PENDING',
    quality_status          text,
    active_document_version_id text REFERENCES document_versions(document_version_id),
    attempt_count           bigint NOT NULL DEFAULT 0,
    last_error              text,
    last_attempted_at       text,
    last_processed_at       text
);

CREATE TABLE IF NOT EXISTS document_topics (
    document_element_id     text NOT NULL REFERENCES document_elements(document_element_id),
    topic                   text NOT NULL,
    match_count             bigint NOT NULL,
    match_method            text NOT NULL,
    PRIMARY KEY (document_element_id, topic)
);

CREATE TABLE IF NOT EXISTS document_entity_mentions (
    document_entity_mention_id text PRIMARY KEY,
    document_element_id     text NOT NULL REFERENCES document_elements(document_element_id),
    entity_id               text REFERENCES entities(entity_id),
    matched_text            text NOT NULL,
    match_method            text NOT NULL,
    start_offset            bigint,
    end_offset              bigint
);

CREATE INDEX IF NOT EXISTS idx_document_entity_mentions_entity
    ON document_entity_mentions (entity_id, document_element_id);
