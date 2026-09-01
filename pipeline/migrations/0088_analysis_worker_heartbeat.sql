-- Liveness for the analysis worker that consumes admin-started runs.
CREATE TABLE IF NOT EXISTS analysis_worker_heartbeats (
    worker_id TEXT PRIMARY KEY,
    last_seen_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'idle',
    version TEXT
);

CREATE INDEX IF NOT EXISTS ix_analysis_worker_heartbeats_seen
    ON analysis_worker_heartbeats(last_seen_at);
