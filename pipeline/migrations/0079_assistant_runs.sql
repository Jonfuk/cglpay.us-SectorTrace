-- BETA-108: one immutable row per single-turn assistant run.
--
-- The optional local analyst assistant (BETA-107) answers one question by
-- routing it to one read-only tool (BETA-110) and summarising that tool's
-- result with a local model (BETA-111). A model name is not a reproducible
-- identity, so this table records what an analyst needs to reconstruct an
-- answer WITHOUT keeping unrestricted hidden model state: the request and its
-- filters, the Needle/LFM identities and quant, the SHA-256 of each frozen
-- prompt template, the routing confidence and the validated tool arguments,
-- the retrieved chunk ids, the answer and its result-local citation ids,
-- timings, the outcome and an error class.
--
-- Append-only by the same discipline as `alias_decisions` (0075) and
-- `qc_sample_findings` (0078): the write path in `pipeline/assistant/ledger.py`
-- only ever INSERTs. A re-run is a NEW row. Nothing here is evidence, a
-- review decision or a claim; a row records that a person asked the assistant
-- a question and what it did.
--
-- No secrets, API keys or model file paths are stored — only identities and
-- hashes. Successful, abstained, clarified, timed-out, failed and unavailable
-- runs are all recorded so the ledger is a true account of what the feature
-- did, not only of when it worked.

CREATE TABLE IF NOT EXISTS assistant_runs (
    run_id              TEXT PRIMARY KEY,      -- uuid4 hex
    created_at          TEXT NOT NULL,
    code_commit         TEXT,                  -- git revision at run time, or NULL

    question            TEXT NOT NULL,
    filters_json        TEXT NOT NULL,         -- {source_system, date_from, date_to, limit}

    needle_model        TEXT,                  -- e.g. 'needle-2'
    needle_endpoint     TEXT,                  -- base URL, no credentials
    lfm_model           TEXT,                  -- 'LiquidAI/LFM2.5-1.2B-Instruct'
    lfm_quant           TEXT,                  -- 'Q4_K_M'
    lfm_endpoint        TEXT,
    router_prompt_sha256 TEXT,                 -- SHA-256 of the frozen routing template
    answer_prompt_sha256 TEXT,                 -- SHA-256 of the frozen answer template

    selected_tool       TEXT,                  -- one of the five, or NULL when unrouted
    routing_confidence  REAL,                  -- Needle's calibrated confidence, or NULL
    tool_args_json      TEXT,                  -- the validated, bounded arguments actually run

    retrieved_chunk_ids TEXT,                  -- JSON array of document_chunk_id, in result order
    answer              TEXT,                  -- the displayed answer, or NULL when suppressed
    citation_ids_json   TEXT,                  -- JSON array of result-local identifiers cited

    timings_json        TEXT,                  -- {route_ms, tool_ms, answer_ms, total_ms}
    outcome             TEXT NOT NULL,         -- 'ok'|'abstained'|'clarified'|'timeout'|'failed'|'unavailable'
    error_class         TEXT                   -- exception class name on a failure, else NULL
);

CREATE INDEX IF NOT EXISTS idx_assistant_runs_created
    ON assistant_runs (created_at);
