-- Optional, isolated projection metadata. These tables are not graph_claims.
CREATE TABLE IF NOT EXISTS entity_link_suggestions (
    suggestion_id TEXT PRIMARY KEY,
    signal_id TEXT,
    raw_name TEXT NOT NULL,
    raw_span TEXT,
    proposed_entity_type TEXT,
    proposed_canonical_id TEXT,
    identifier_evidence_json TEXT NOT NULL DEFAULT '[]',
    model_outputs_json TEXT NOT NULL DEFAULT '[]',
    source_passage TEXT,
    rejection_reasons_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'unresolved',
    created_at TEXT NOT NULL,
    decided_at TEXT
);

CREATE TABLE IF NOT EXISTS relationship_signal_candidates (
    candidate_id TEXT PRIMARY KEY,
    release_id TEXT,
    left_signal_id TEXT,
    right_signal_id TEXT,
    proposed_relationship_type TEXT,
    deterministic_evidence_json TEXT NOT NULL DEFAULT '[]',
    model_outputs_json TEXT NOT NULL DEFAULT '[]',
    source_passage TEXT,
    rejection_reasons_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'unresolved',
    created_at TEXT NOT NULL,
    decided_at TEXT
);

CREATE TABLE IF NOT EXISTS signal_graph_projection_queue (
    queue_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL REFERENCES analysis_releases(release_id),
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    created_at TEXT NOT NULL,
    processed_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT
);

CREATE TABLE IF NOT EXISTS signal_graph_projection_runs (
    run_id TEXT PRIMARY KEY,
    release_id TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    signal_count INTEGER NOT NULL DEFAULT 0,
    theme_count INTEGER NOT NULL DEFAULT 0,
    error_detail TEXT
);

CREATE INDEX IF NOT EXISTS ix_entity_link_suggestions_status ON entity_link_suggestions(status, created_at);
CREATE INDEX IF NOT EXISTS ix_relationship_signal_candidates_status ON relationship_signal_candidates(status, created_at);
CREATE INDEX IF NOT EXISTS ix_signal_graph_queue_pending ON signal_graph_projection_queue(processed_at, created_at);
