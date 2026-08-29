-- BETA-058: one durable row per module-run, whatever started it.
--
-- `job_runs` records runs started from the web UI's job registry. A run
-- started from the CLI or a cron wrapper leaves nothing behind but its log
-- file, so "which path collected this, and when" cannot always be answered.
--
-- This table is written by `pipeline/runner.py::run_waves`, the single choke
-- point every entry point already goes through. It does not replace
-- `job_runs` (the web UI keeps using that for its live log streaming); it is
-- the durable, entry-point-agnostic ledger beside it. Full module logs stay
-- where they are.

CREATE TABLE IF NOT EXISTS run_ledger (
    run_id          TEXT NOT NULL,          -- uuid4 hex
    origin          TEXT NOT NULL,          -- 'cli' | 'admin' | 'scheduled'
    revision        TEXT,                   -- git revision at run time, or NULL
    environment     TEXT,                   -- 'local' | 'production' | ...
    parent_run_id   TEXT,                   -- when one run was spawned by another
    module_selector TEXT,                   -- what was asked for ('all' or a list)
    dry_run         INTEGER NOT NULL DEFAULT 0,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,                   -- NULL while status = 'running'
    status          TEXT NOT NULL,          -- 'running' | 'ok' | 'partial' | 'failed'
    modules_total   INTEGER,
    modules_ok      INTEGER,
    modules_failed  INTEGER,
    results_json    TEXT,                   -- [{module,status,rows,review,failures,elapsed_ms}]
    PRIMARY KEY (run_id)
);

CREATE INDEX IF NOT EXISTS idx_run_ledger_started
    ON run_ledger (started_at);
