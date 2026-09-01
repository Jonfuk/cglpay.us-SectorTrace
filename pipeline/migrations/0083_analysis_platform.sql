-- SectorTrace analysis platform: immutable release manifests and domain runs.
CREATE TABLE IF NOT EXISTS analysis_releases (
    release_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'draft',
    manifest_json TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL UNIQUE,
    code_commit TEXT,
    created_at TEXT NOT NULL,
    activated_at TEXT,
    rolled_back_at TEXT,
    rollback_reason TEXT
);

CREATE TABLE IF NOT EXISTS analysis_domain_runs (
    domain_run_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL REFERENCES analysis_releases(release_id),
    domain_id TEXT NOT NULL,
    status TEXT NOT NULL,
    prerequisite_status TEXT NOT NULL DEFAULT 'ready',
    missing_tables_json TEXT NOT NULL DEFAULT '[]',
    rows_processed INTEGER NOT NULL DEFAULT 0,
    rows_written INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    error_detail TEXT,
    UNIQUE(release_id, domain_id)
);

CREATE TABLE IF NOT EXISTS analysis_windows (
    window_id TEXT PRIMARY KEY,
    domain_run_id TEXT NOT NULL REFERENCES analysis_domain_runs(domain_run_id),
    domain_id TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    subject_type TEXT,
    subject_id TEXT,
    period_start TEXT,
    period_end TEXT,
    text_sha256 TEXT,
    feature_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    UNIQUE(domain_run_id, source_table, source_record_id)
);

CREATE TABLE IF NOT EXISTS analysis_program_versions (
    program_version_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL REFERENCES analysis_releases(release_id),
    domain_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    program_kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'challenger',
    proxy_score REAL,
    quote_recoverability REAL,
    mutation_failure_count INTEGER NOT NULL DEFAULT 0,
    agreement_score REAL,
    config_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_analysis_domain_runs_release ON analysis_domain_runs(release_id);
CREATE INDEX IF NOT EXISTS ix_analysis_windows_subject ON analysis_windows(domain_id, subject_id);
