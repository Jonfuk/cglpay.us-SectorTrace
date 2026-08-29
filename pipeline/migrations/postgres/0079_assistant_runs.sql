-- BETA-108: one immutable row per single-turn assistant run.
--
-- PostgreSQL dialect of ../0079_assistant_runs.sql. See README.md in this
-- directory for the conversion rules.
--
-- A model name is not a reproducible identity: this table records the request
-- and filters, the Needle/LFM identities and quant, each frozen prompt
-- template's SHA-256, the routing confidence and validated arguments, the
-- retrieved chunk ids, the answer and its result-local citation ids, timings,
-- outcome and error class. Append-only by the same discipline as
-- `alias_decisions` (0075) — a re-run is a new row, nothing is updated or
-- deleted. No secrets, keys or model file paths are stored, only identities
-- and hashes.

CREATE TABLE IF NOT EXISTS assistant_runs (
    run_id              text PRIMARY KEY,
    created_at          text NOT NULL,
    code_commit         text,

    question            text NOT NULL,
    filters_json        text NOT NULL,

    needle_model        text,
    needle_endpoint     text,
    lfm_model           text,
    lfm_quant           text,
    lfm_endpoint        text,
    router_prompt_sha256 text,
    answer_prompt_sha256 text,

    selected_tool       text,
    routing_confidence  double precision,
    tool_args_json      text,

    retrieved_chunk_ids text,
    answer              text,
    citation_ids_json   text,

    timings_json        text,
    outcome             text NOT NULL,
    error_class         text
);

CREATE INDEX IF NOT EXISTS idx_assistant_runs_created
    ON assistant_runs (created_at);
