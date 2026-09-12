-- The durable queue behind the Phase 5 worker cutover (CLAUDE.md settled
-- decision 10): a module run started from the admin UI is enqueued here and
-- executed by a separate `pipeline worker` process, not by the web server
-- that took the request. The web process only ever reads and writes this
-- table's rows; it never runs a module directly once this lands.
--
-- These three tables were first sketched in pipeline/worker.py as
-- `CREATE TABLE IF NOT EXISTS` run from `WorkerQueue.__init__`, before
-- anything enqueued into them. Formalised here for the same reason every
-- other table in this warehouse is a migration and not a runtime
-- side-effect: `schema_migrations` should be the one place that answers "is
-- this object supposed to exist", and a table a class happens to create on
-- first use is invisible to that ledger.
CREATE TABLE IF NOT EXISTS worker_jobs (
    -- Text, not the `job_runs.id` bigint identity column, even though every
    -- value written here today is `str(job_runs.id)`. That equivalence is an
    -- application convention (pipeline/web/jobs.py: JobRegistry allocates one
    -- id and uses its string form here) rather than a database one, and a
    -- foreign key would make this table unable to hold a row job_runs.load()
    -- cannot yet explain, which is exactly the row a crash-and-resume needs
    -- to find.
    job_id            text PRIMARY KEY,
    kind              text NOT NULL,
    arguments_json    text NOT NULL,
    -- 'queued' -> 'running' -> ('finished' | 'failed'). A worker restarting
    -- mid-run re-enters at 'running' with lease_until in the past, which is
    -- what makes it claimable again rather than stuck.
    state             text NOT NULL CHECK (state IN ('queued', 'running', 'finished', 'failed')),
    -- What the run has completed so far, in whatever shape the caller chose
    -- (pipeline/worker.py checkpoints module names and partial summary rows
    -- after each module `runner.run_waves` finishes). Read back on claim so
    -- a resumed job can skip what it already did rather than re-running it.
    checkpoint_json   text NOT NULL DEFAULT '{}',
    -- Set by `finish()`, read by the admin poll bridge (pipeline/web/jobs.py)
    -- so a failed job's reason survives a web-process restart the same way
    -- job_runs.error already does for the in-process ThreadStrategy path.
    error             text,
    summary_json      text,
    -- NULL while queued; set to now()+lease on claim. A worker that dies
    -- mid-run leaves this in the past, which is what lets `claim()` treat a
    -- 'running' row as claimable again instead of leaving it stuck forever.
    lease_until       text,
    attempt_count     bigint NOT NULL DEFAULT 0,
    created_at        text NOT NULL,
    updated_at        text NOT NULL
);

-- `claim()` orders by (state, created_at) and needs the queued/expired-lease
-- rows fast; `active()` (the admin route's cross-process "is anything using
-- the one pipeline slot" check) is the same shape with no lease condition.
CREATE INDEX IF NOT EXISTS idx_worker_jobs_state_created
    ON worker_jobs (state, created_at);

-- The log a poller reads instead of Job.lines once execution has left the
-- web process — see pipeline/web/jobs.py's Job._refresh_from_queue(). Rows
-- age out from the front (event()'s own trim, mirroring jobs.py's MAX_LINES)
-- but `sequence_no` is never reused, so the gap between the highest number
-- ever issued and how many rows survive is exactly how many were trimmed —
-- the same accounting `Job.dropped` already gave a reader for the in-memory
-- buffer, done here without keeping the trimmed rows around to count.
CREATE TABLE IF NOT EXISTS worker_job_events (
    job_id        text NOT NULL,
    sequence_no   bigint NOT NULL,
    level         text NOT NULL,
    message       text NOT NULL,
    created_at    text NOT NULL,
    PRIMARY KEY (job_id, sequence_no)
);

-- One row, bumped whenever a worker-executed run finishes successfully — the
-- cross-process equivalent of the read cache's own `bump_version()` callback
-- that a same-process ThreadStrategy job could call directly. A future
-- reader (the web process's cache, polling this) invalidates on a change
-- instead of on a callback it cannot receive from another process.
CREATE TABLE IF NOT EXISTS warehouse_data_version (
    version       bigint NOT NULL,
    updated_at    text NOT NULL
);
