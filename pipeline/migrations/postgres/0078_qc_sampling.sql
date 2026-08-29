-- BETA-106: reproducible quality-control samples and append-only findings.
--
-- PostgreSQL dialect of ../0078_qc_sampling.sql. See README.md in this
-- directory for the conversion rules.
--
-- A QC sample is a deterministic draw: the same seed + filter + method
-- yields the same record ids. `qc_samples` is the manifest. `qc_sample_findings`
-- is append-only by the same discipline as `alias_decisions` (0075) — a
-- revised opinion is a new row, nothing is updated or deleted.

CREATE TABLE IF NOT EXISTS qc_samples (
    sample_id         text PRIMARY KEY,
    seed              text NOT NULL,
    source            text NOT NULL,
    method            text NOT NULL,
    stratify_by       text,
    population_filter text NOT NULL,
    population_size   integer NOT NULL,
    sample_size       integer NOT NULL,
    record_ids        text NOT NULL,
    created_by        text,
    created_at        text NOT NULL
);

CREATE TABLE IF NOT EXISTS qc_sample_findings (
    finding_id        text PRIMARY KEY,
    sample_id         text NOT NULL REFERENCES qc_samples (sample_id),
    record_ref        text NOT NULL,
    verdict           text NOT NULL,
    note              text,
    created_by        text,
    created_at        text NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_qc_findings_sample
    ON qc_sample_findings (sample_id);
