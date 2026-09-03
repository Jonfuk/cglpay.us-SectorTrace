-- Latest successful operational calculations reused by health and diagnostics.
CREATE TABLE IF NOT EXISTS operational_snapshots (
    snapshot_key text PRIMARY KEY,
    payload_json text NOT NULL,
    captured_at text NOT NULL,
    duration_ms double precision,
    source_version text,
    stale bigint NOT NULL DEFAULT 0,
    refresh_error text
);
