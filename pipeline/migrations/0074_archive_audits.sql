-- BETA-060: append-only raw-archive audit snapshots.
--
-- `archive-verify` answers "is the archive intact right now?" and writes a
-- manifest file. It does not leave a trail, so integrity *drift* and storage
-- growth are invisible. This table is one immutable row per `archive-audit`
-- run: the counts, the by-source distribution, how many evidence references
-- have no archived object, how many hashes are stored more than once, and a
-- deterministic sample for a spot check over time.
--
-- Measurement only. Nothing that writes here deletes, compacts, or chooses a
-- retention policy — the row is a photograph, not an instruction.

CREATE TABLE IF NOT EXISTS archive_audits (
    audit_id          TEXT NOT NULL,        -- uuid4 hex
    run_at            TEXT NOT NULL,
    object_count      INTEGER NOT NULL,     -- rows in archive_objects
    total_bytes       INTEGER NOT NULL,     -- SUM(size_bytes)
    by_source_json    TEXT NOT NULL,        -- source_system -> {count, bytes}
    missing_refs      INTEGER NOT NULL,     -- evidence payload_sha256 with no object
    duplicate_hashes  INTEGER NOT NULL,     -- payload_sha256 stored under >1 object_id
    sample_json       TEXT NOT NULL,        -- deterministic object sample
    git_revision      TEXT,
    PRIMARY KEY (audit_id)
);

CREATE INDEX IF NOT EXISTS idx_archive_audits_run
    ON archive_audits (run_at);
