-- What the server has been asked to run, kept where a restart cannot lose it.
--
-- The job registry (pipeline/web/jobs.py) is in memory, and that was the right
-- call for the thing it was built for: a job is something you *watch*, and a
-- server restart is the end of watching. But it also made the registry the
-- only record that a run had happened at all. Close the server and the fact
-- that a four-hour crawl ran last night, with what arguments, and whether it
-- finished, is gone -- the evidence it collected is in the warehouse and the
-- lines it printed are in logs/, but nothing joins the two.
--
-- So the *fact* of a job is persisted here and its log is not. The log lines
-- already have a home, and copying thousands of them into the warehouse would
-- put the chattiest table in the database next to the evidence it is not.
--
-- `dry_run` is a column rather than something to dig out of args_json,
-- because "did this run write anything?" is the first question anyone asks of
-- a job list and it should not require parsing JSON to answer.
CREATE TABLE IF NOT EXISTS job_runs (
    -- Not AUTOINCREMENT: ids are allocated by the registry, which continues
    -- from the highest persisted id on startup so that a job id means one job
    -- for the life of the warehouse rather than for the life of a process.
    id            INTEGER PRIMARY KEY,
    kind          TEXT NOT NULL,
    label         TEXT NOT NULL,
    args_json     TEXT NOT NULL,
    -- 'interrupted' is what a process that died mid-run leaves behind. It is
    -- written on startup, not by the job: a job that could still update its
    -- own row would not have been interrupted.
    state         TEXT NOT NULL CHECK (state IN ('running', 'finished', 'failed', 'interrupted')),
    dry_run       INTEGER NOT NULL DEFAULT 0,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    error         TEXT,
    summary_json  TEXT
);

-- The job list is "newest first, a page of them", and nothing else.
CREATE INDEX IF NOT EXISTS idx_job_runs_started_at
    ON job_runs (started_at DESC);
