-- Durable control-plane state for admin-started analysis runs.
CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL REFERENCES analysis_releases(release_id),
    run_kind TEXT NOT NULL DEFAULT 'complete',
    status TEXT NOT NULL DEFAULT 'queued',
    requested_domains_json TEXT NOT NULL DEFAULT '[]',
    total_domains INTEGER NOT NULL DEFAULT 0,
    completed_domains INTEGER NOT NULL DEFAULT 0,
    current_domain TEXT,
    current_stage TEXT NOT NULL DEFAULT 'queued',
    estimated_calls INTEGER,
    estimated_cost_micros INTEGER,
    cost_micros INTEGER NOT NULL DEFAULT 0,
    cost_ceiling_micros INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    cancelled_at TEXT,
    error_detail TEXT
);

ALTER TABLE analysis_domain_runs ADD COLUMN run_id TEXT;

CREATE INDEX IF NOT EXISTS ix_analysis_runs_status ON analysis_runs(status, updated_at);
CREATE INDEX IF NOT EXISTS ix_analysis_domain_runs_run ON analysis_domain_runs(run_id, status);
