CREATE TABLE IF NOT EXISTS analysis_releases (
    release_id text PRIMARY KEY,
    status text NOT NULL DEFAULT 'draft',
    manifest_json text NOT NULL,
    manifest_sha256 text NOT NULL UNIQUE,
    code_commit text,
    created_at text NOT NULL,
    activated_at text,
    rolled_back_at text,
    rollback_reason text
);

CREATE TABLE IF NOT EXISTS analysis_domain_runs (
    domain_run_id text PRIMARY KEY,
    release_id text NOT NULL REFERENCES analysis_releases(release_id),
    domain_id text NOT NULL,
    status text NOT NULL,
    prerequisite_status text NOT NULL DEFAULT 'ready',
    missing_tables_json text NOT NULL DEFAULT '[]',
    rows_processed bigint NOT NULL DEFAULT 0,
    rows_written bigint NOT NULL DEFAULT 0,
    started_at text NOT NULL,
    completed_at text,
    error_detail text,
    UNIQUE(release_id, domain_id)
);

CREATE TABLE IF NOT EXISTS analysis_windows (
    window_id text PRIMARY KEY,
    domain_run_id text NOT NULL REFERENCES analysis_domain_runs(domain_run_id),
    domain_id text NOT NULL,
    source_table text NOT NULL,
    source_record_id text NOT NULL,
    subject_type text,
    subject_id text,
    period_start text,
    period_end text,
    text_sha256 text,
    feature_json text NOT NULL DEFAULT '{}',
    status text NOT NULL DEFAULT 'pending',
    UNIQUE(domain_run_id, source_table, source_record_id)
);

CREATE TABLE IF NOT EXISTS analysis_program_versions (
    program_version_id text PRIMARY KEY,
    release_id text NOT NULL REFERENCES analysis_releases(release_id),
    domain_id text NOT NULL,
    model_id text NOT NULL,
    program_kind text NOT NULL,
    status text NOT NULL DEFAULT 'challenger',
    proxy_score double precision,
    quote_recoverability double precision,
    mutation_failure_count bigint NOT NULL DEFAULT 0,
    agreement_score double precision,
    config_json text NOT NULL DEFAULT '{}',
    created_at text NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_analysis_domain_runs_release ON analysis_domain_runs(release_id);
CREATE INDEX IF NOT EXISTS ix_analysis_windows_subject ON analysis_windows(domain_id, subject_id);
