-- PostgreSQL dialect of ../0052_archive_extractions.sql.
CREATE TABLE IF NOT EXISTS archive_extraction_runs (
    run_id            text PRIMARY KEY,
    started_at        text NOT NULL,
    completed_at      text,
    status            text NOT NULL,
    extractor_name    text NOT NULL,
    extractor_version text NOT NULL,
    object_count      bigint NOT NULL DEFAULT 0,
    processed_count   bigint NOT NULL DEFAULT 0,
    skipped_count     bigint NOT NULL DEFAULT 0,
    failed_count      bigint NOT NULL DEFAULT 0,
    error_detail      text
);

CREATE TABLE IF NOT EXISTS archive_objects (
    object_id       text PRIMARY KEY,
    source_system   text NOT NULL,
    payload_sha256  text NOT NULL,
    logical_path    text NOT NULL UNIQUE,
    mime_type       text,
    size_bytes      bigint NOT NULL,
    first_seen_at   text NOT NULL,
    last_seen_at    text NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_archive_objects_source
    ON archive_objects (source_system, payload_sha256);

CREATE TABLE IF NOT EXISTS archive_extractions (
    extraction_id     text PRIMARY KEY,
    run_id            text NOT NULL REFERENCES archive_extraction_runs(run_id),
    object_id         text NOT NULL REFERENCES archive_objects(object_id),
    evidence_id       text REFERENCES evidence_records(evidence_id),
    extractor_name    text NOT NULL,
    extractor_version text NOT NULL,
    parser_name       text NOT NULL,
    parser_version    text NOT NULL,
    status            text NOT NULL,
    text_storage_path text,
    text_sha256       text,
    character_count   bigint NOT NULL DEFAULT 0,
    metadata_json     text NOT NULL,
    error_detail      text,
    created_at        text NOT NULL,
    UNIQUE (object_id, extractor_name, extractor_version)
);

CREATE INDEX IF NOT EXISTS idx_archive_extractions_evidence
    ON archive_extractions (evidence_id);
