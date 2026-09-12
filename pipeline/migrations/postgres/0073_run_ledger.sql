-- BETA-058: one durable row per module-run, whatever started it.
--
-- PostgreSQL dialect of ../0073_run_ledger.sql. See README.md in this
-- directory for the conversion rules.
--
-- Written by `pipeline/runner.py::run_waves`, the single choke point every
-- entry point goes through. It does not replace `job_runs` (the web UI keeps
-- using that for live log streaming); it is the durable, entry-point-agnostic
-- ledger beside it. Full module logs stay where they are.

CREATE TABLE IF NOT EXISTS run_ledger (
    run_id          text NOT NULL,
    origin          text NOT NULL,
    revision        text,
    environment     text,
    parent_run_id   text,
    module_selector text,
    dry_run         bigint NOT NULL DEFAULT 0,
    started_at      text NOT NULL,
    finished_at     text,
    status          text NOT NULL,
    modules_total   bigint,
    modules_ok      bigint,
    modules_failed  bigint,
    results_json    text,
    PRIMARY KEY (run_id)
);

CREATE INDEX IF NOT EXISTS idx_run_ledger_started
    ON run_ledger (started_at);
