-- Deterministic, replayable processing of immutable raw archive objects.
--
-- Raw bytes remain authoritative. These tables record the derived parser
-- output and make a manual run resumable without creating graph claims.

CREATE TABLE IF NOT EXISTS archive_extraction_runs (
    run_id            TEXT PRIMARY KEY,
    started_at        TEXT NOT NULL,
    completed_at      TEXT,
    status            TEXT NOT NULL,
    extractor_name    TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    object_count      INTEGER NOT NULL DEFAULT 0,
    processed_count   INTEGER NOT NULL DEFAULT 0,
    skipped_count     INTEGER NOT NULL DEFAULT 0,
    failed_count      INTEGER NOT NULL DEFAULT 0,
    error_detail      TEXT
);

CREATE TABLE IF NOT EXISTS archive_objects (
    object_id       TEXT PRIMARY KEY,
    source_system   TEXT NOT NULL,
    payload_sha256  TEXT NOT NULL,
    logical_path    TEXT NOT NULL UNIQUE,
    mime_type       TEXT,
    size_bytes      INTEGER NOT NULL,
    first_seen_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_archive_objects_source
    ON archive_objects (source_system, payload_sha256);

CREATE TABLE IF NOT EXISTS archive_extractions (
    extraction_id    TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL REFERENCES archive_extraction_runs(run_id),
    object_id        TEXT NOT NULL REFERENCES archive_objects(object_id),
    evidence_id      TEXT REFERENCES evidence_records(evidence_id),
    extractor_name   TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    parser_name      TEXT NOT NULL,
    parser_version   TEXT NOT NULL,
    status           TEXT NOT NULL,
    text_storage_path TEXT,
    text_sha256      TEXT,
    character_count  INTEGER NOT NULL DEFAULT 0,
    metadata_json    TEXT NOT NULL,
    error_detail     TEXT,
    created_at       TEXT NOT NULL,
    UNIQUE (object_id, extractor_name, extractor_version)
);

CREATE INDEX IF NOT EXISTS idx_archive_extractions_evidence
    ON archive_extractions (evidence_id);
