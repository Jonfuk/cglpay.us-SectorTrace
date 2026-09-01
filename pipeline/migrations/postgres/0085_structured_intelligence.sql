CREATE TABLE IF NOT EXISTS structured_signals (
    structured_signal_id text PRIMARY KEY,
    signal_id text NOT NULL REFERENCES automated_signals(signal_id),
    source_table text NOT NULL,
    source_row_id text NOT NULL,
    comparison_source_table text,
    comparison_source_row_id text,
    metric text NOT NULL,
    unit text NOT NULL,
    value_before text,
    value_after text,
    absolute_change double precision,
    percentage_change double precision,
    comparable bigint NOT NULL,
    robust_z double precision,
    anomaly_status text,
    calculation_json text NOT NULL DEFAULT '{}',
    created_at text NOT NULL
);

CREATE TABLE IF NOT EXISTS cross_source_signal_links (
    link_id text PRIMARY KEY,
    release_id text NOT NULL REFERENCES analysis_releases(release_id),
    left_signal_id text NOT NULL REFERENCES automated_signals(signal_id),
    right_signal_id text NOT NULL REFERENCES automated_signals(signal_id),
    relationship_type text NOT NULL,
    subject_type text NOT NULL,
    subject_id text NOT NULL,
    period_start text,
    period_end text,
    join_reason_json text NOT NULL,
    explanation text,
    created_at text NOT NULL,
    UNIQUE(left_signal_id, right_signal_id, relationship_type)
);

CREATE TABLE IF NOT EXISTS analysis_health_snapshots (
    health_snapshot_id text PRIMARY KEY,
    release_id text,
    domain_id text,
    source_table text NOT NULL,
    collected_at text NOT NULL,
    collection_success bigint,
    freshness_at text,
    content_hash text,
    parse_success bigint,
    expected_schema_json text NOT NULL DEFAULT '{}',
    observed_schema_json text NOT NULL DEFAULT '{}',
    row_count bigint,
    document_count bigint,
    embedding_coverage double precision,
    outlier_rate double precision,
    extractor_agreement double precision,
    verifier_pass_rate double precision,
    cost_micros bigint,
    latency_ms bigint,
    cache_hits bigint NOT NULL DEFAULT 0,
    signal_yield double precision
);

CREATE TABLE IF NOT EXISTS adaptation_proposals (
    proposal_id text PRIMARY KEY,
    release_id text,
    domain_id text,
    proposal_type text NOT NULL,
    trigger_json text NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    automatic_action text,
    admin_reason text,
    created_at text NOT NULL,
    decided_at text
);

CREATE INDEX IF NOT EXISTS ix_structured_signals_metric ON structured_signals(metric, unit);
CREATE INDEX IF NOT EXISTS ix_cross_source_links_subject ON cross_source_signal_links(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS ix_analysis_health_source ON analysis_health_snapshots(source_table, collected_at);
CREATE INDEX IF NOT EXISTS ix_adaptation_proposals_status ON adaptation_proposals(status, created_at);
