-- PostgreSQL maintenance telemetry (performance.md "PostgreSQL maintenance",
-- Phase 5). Observation-only: these tables exist to accumulate the evidence
-- that phase explicitly requires *before* any autovacuum/analyze threshold,
-- index, or planner change is made — "after telemetry establishes update
-- rates" / "after the telemetry observation period". Nothing reads these
-- tables to change server configuration yet; pipeline/pg_telemetry.py only
-- captures into them.
--
-- Each capture (pipeline pg-telemetry-snapshot) writes one `captured_at` batch
-- across the three tables below, so update rates and index usage can be
-- compared across snapshots rather than only read as the single live
-- point-in-time answer pg_stat_user_tables/pg_stat_user_indexes/
-- pg_stat_statements would otherwise give.

-- One row per application table per snapshot: the autovacuum/analyze
-- telemetry a table-specific threshold decision would need.
CREATE TABLE IF NOT EXISTS pg_telemetry_table_stats (
    captured_at             text NOT NULL,
    schema_name             text NOT NULL,
    table_name              text NOT NULL,
    n_live_tup              bigint,
    n_dead_tup              bigint,
    n_mod_since_analyze     bigint,
    last_autovacuum         text,
    last_analyze            text,
    autovacuum_count        bigint,
    analyze_count           bigint,
    PRIMARY KEY (captured_at, schema_name, table_name)
);

CREATE INDEX IF NOT EXISTS idx_pg_telemetry_table_stats_table
    ON pg_telemetry_table_stats (schema_name, table_name, captured_at);

-- One row per index per snapshot: the usage evidence an eventual index
-- review (performance.md: "based on execution counts, total time, I/O,
-- plans, constraint roles") would need. `idx_tup_read`/`idx_tup_fetch` alone
-- already answered the one index question Phase 4 asked (docs/benchmarks) —
-- this is what lets that answer be asked again without a live server.
CREATE TABLE IF NOT EXISTS pg_telemetry_index_stats (
    captured_at             text NOT NULL,
    schema_name             text NOT NULL,
    table_name              text NOT NULL,
    index_name              text NOT NULL,
    idx_scan                bigint,
    idx_tup_read            bigint,
    idx_tup_fetch           bigint,
    PRIMARY KEY (captured_at, schema_name, table_name, index_name)
);

CREATE INDEX IF NOT EXISTS idx_pg_telemetry_index_stats_index
    ON pg_telemetry_index_stats (schema_name, index_name, captured_at);

-- One row per query fingerprint per snapshot, only when pg_stat_statements is
-- installed (it needs shared_preload_libraries at server start, which
-- `pipeline pg-telemetry-snapshot` cannot arrange itself — see
-- pipeline/pg_telemetry.py and deploy/ansible/README.md for the operator
-- step). Absent the extension this table simply accumulates no rows; the
-- capture never fails for that reason.
CREATE TABLE IF NOT EXISTS pg_telemetry_statement_stats (
    captured_at             text NOT NULL,
    queryid                 bigint NOT NULL,
    query_text              text,
    calls                   bigint,
    total_exec_time_ms      double precision,
    rows                    bigint,
    shared_blks_hit         bigint,
    shared_blks_read        bigint,
    PRIMARY KEY (captured_at, queryid)
);

CREATE INDEX IF NOT EXISTS idx_pg_telemetry_statement_stats_queryid
    ON pg_telemetry_statement_stats (queryid, captured_at);
