-- Document-level prevalence diagnostics for narrative analysis.
CREATE TABLE IF NOT EXISTS analysis_prevalence_diagnostics (
    prevalence_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL REFERENCES analysis_releases(release_id),
    domain_id TEXT NOT NULL,
    positives INTEGER NOT NULL,
    negatives INTEGER NOT NULL,
    subjects INTEGER NOT NULL,
    pacc REAL,
    emq REAL,
    continue_exploration INTEGER NOT NULL,
    suppressed INTEGER NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_analysis_prevalence_release ON analysis_prevalence_diagnostics(release_id, domain_id, created_at);
