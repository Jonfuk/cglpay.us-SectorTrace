-- Canonical structured comparisons, cross-source links and operational drift.
CREATE TABLE IF NOT EXISTS structured_signals (
    structured_signal_id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES automated_signals(signal_id),
    source_table TEXT NOT NULL,
    source_row_id TEXT NOT NULL,
    comparison_source_table TEXT,
    comparison_source_row_id TEXT,
    metric TEXT NOT NULL,
    unit TEXT NOT NULL,
    value_before TEXT,
    value_after TEXT,
    absolute_change REAL,
    percentage_change REAL,
    comparable INTEGER NOT NULL,
    robust_z REAL,
    anomaly_status TEXT,
    calculation_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cross_source_signal_links (
    link_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL REFERENCES analysis_releases(release_id),
    left_signal_id TEXT NOT NULL REFERENCES automated_signals(signal_id),
    right_signal_id TEXT NOT NULL REFERENCES automated_signals(signal_id),
    relationship_type TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    join_reason_json TEXT NOT NULL,
    explanation TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(left_signal_id, right_signal_id, relationship_type)
);

CREATE TABLE IF NOT EXISTS analysis_health_snapshots (
    health_snapshot_id TEXT PRIMARY KEY,
    release_id TEXT,
    domain_id TEXT,
    source_table TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    collection_success INTEGER,
    freshness_at TEXT,
    content_hash TEXT,
    parse_success INTEGER,
    expected_schema_json TEXT NOT NULL DEFAULT '{}',
    observed_schema_json TEXT NOT NULL DEFAULT '{}',
    row_count INTEGER,
    document_count INTEGER,
    embedding_coverage REAL,
    outlier_rate REAL,
    extractor_agreement REAL,
    verifier_pass_rate REAL,
    cost_micros INTEGER,
    latency_ms INTEGER,
    cache_hits INTEGER NOT NULL DEFAULT 0,
    signal_yield REAL
);

CREATE TABLE IF NOT EXISTS adaptation_proposals (
    proposal_id TEXT PRIMARY KEY,
    release_id TEXT,
    domain_id TEXT,
    proposal_type TEXT NOT NULL,
    trigger_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    automatic_action TEXT,
    admin_reason TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);

CREATE INDEX IF NOT EXISTS ix_structured_signals_metric ON structured_signals(metric, unit);
CREATE INDEX IF NOT EXISTS ix_cross_source_links_subject ON cross_source_signal_links(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS ix_analysis_health_source ON analysis_health_snapshots(source_table, collected_at);
CREATE INDEX IF NOT EXISTS ix_adaptation_proposals_status ON adaptation_proposals(status, created_at);
