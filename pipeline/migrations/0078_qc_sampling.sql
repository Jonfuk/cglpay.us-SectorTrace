-- BETA-106: reproducible quality-control samples of previously decided
-- records, and append-only second-look findings against them.
--
-- Review audit history records what happened; it gives no focused surface
-- for checking a defensible sample after the fact. A QC sample is a
-- deterministic draw: the same seed + population filter + method always
-- yields the same record ids, so the sample can be re-derived and defended
-- a year later. `qc_samples` is the manifest of exactly how it was drawn.
--
-- `qc_sample_findings` is append-only by the same discipline as
-- `alias_decisions` (0075): one row per record inspected, a revised opinion
-- is a NEW row, nothing is updated or deleted. The write path in
-- `pipeline/web/qc_sampling.py` only ever INSERTs.

CREATE TABLE IF NOT EXISTS qc_samples (
    sample_id         TEXT PRIMARY KEY,      -- deterministic hash of the draw parameters
    seed              TEXT NOT NULL,         -- the caller's seed string
    source            TEXT NOT NULL,         -- 'review_queue' | 'alias_decisions'
    method            TEXT NOT NULL,         -- 'random' | 'stratified'
    stratify_by       TEXT,                  -- column name when method = 'stratified'
    population_filter TEXT NOT NULL,         -- JSON of the applied filter ({} = all eligible)
    population_size   INTEGER NOT NULL,
    sample_size       INTEGER NOT NULL,
    record_ids        TEXT NOT NULL,         -- JSON array of the drawn record ids, in draw order
    created_by        TEXT,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS qc_sample_findings (
    finding_id        TEXT PRIMARY KEY,
    sample_id         TEXT NOT NULL REFERENCES qc_samples (sample_id),
    record_ref        TEXT NOT NULL,         -- one id from qc_samples.record_ids
    verdict           TEXT NOT NULL,         -- 'agree' | 'disagree' | 'unclear'
    note              TEXT,
    created_by        TEXT,
    created_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_qc_findings_sample
    ON qc_sample_findings (sample_id);
