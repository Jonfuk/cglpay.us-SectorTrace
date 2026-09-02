-- Durable recovery state for unattended analysis workers.
ALTER TABLE analysis_runs ADD COLUMN automatic_retry_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE analysis_runs ADD COLUMN next_retry_at TEXT;
ALTER TABLE analysis_domain_runs ADD COLUMN next_retry_at TEXT;
