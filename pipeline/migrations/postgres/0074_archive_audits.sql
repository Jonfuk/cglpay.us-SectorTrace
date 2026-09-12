-- BETA-060: append-only raw-archive audit snapshots.
--
-- PostgreSQL dialect of ../0074_archive_audits.sql. See README.md in this
-- directory for the conversion rules.
--
-- One immutable row per `archive-audit` run: counts, by-source distribution,
-- unarchived evidence references, duplicated hashes, a deterministic sample.
-- Measurement only — nothing that writes here deletes, compacts, or chooses
-- retention.

CREATE TABLE IF NOT EXISTS archive_audits (
    audit_id          text NOT NULL,
    run_at            text NOT NULL,
    object_count      bigint NOT NULL,
    total_bytes       bigint NOT NULL,
    by_source_json    text NOT NULL,
    missing_refs      bigint NOT NULL,
    duplicate_hashes  bigint NOT NULL,
    sample_json       text NOT NULL,
    git_revision      text,
    PRIMARY KEY (audit_id)
);

CREATE INDEX IF NOT EXISTS idx_archive_audits_run
    ON archive_audits (run_at);
