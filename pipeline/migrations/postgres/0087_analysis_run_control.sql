-- Durable control-plane state for admin-started analysis runs.
CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id text PRIMARY KEY,
    release_id text NOT NULL REFERENCES analysis_releases(release_id),
    run_kind text NOT NULL DEFAULT 'complete',
    status text NOT NULL DEFAULT 'queued',
    requested_domains_json text NOT NULL DEFAULT '[]',
    total_domains bigint NOT NULL DEFAULT 0,
    completed_domains bigint NOT NULL DEFAULT 0,
    current_domain text,
    current_stage text NOT NULL DEFAULT 'queued',
    estimated_calls bigint,
    estimated_cost_micros bigint,
    cost_micros bigint NOT NULL DEFAULT 0,
    cost_ceiling_micros bigint NOT NULL DEFAULT 0,
    started_at text NOT NULL,
    updated_at text NOT NULL,
    completed_at text,
    cancelled_at text,
    error_detail text
);

ALTER TABLE analysis_domain_runs ADD COLUMN run_id text;

CREATE INDEX IF NOT EXISTS ix_analysis_runs_status ON analysis_runs(status, updated_at);
CREATE INDEX IF NOT EXISTS ix_analysis_domain_runs_run ON analysis_domain_runs(run_id, status);
