CREATE TABLE IF NOT EXISTS entity_link_suggestions (
    suggestion_id text PRIMARY KEY,
    signal_id text,
    raw_name text NOT NULL,
    raw_span text,
    proposed_entity_type text,
    proposed_canonical_id text,
    identifier_evidence_json text NOT NULL DEFAULT '[]',
    model_outputs_json text NOT NULL DEFAULT '[]',
    source_passage text,
    rejection_reasons_json text NOT NULL DEFAULT '[]',
    status text NOT NULL DEFAULT 'unresolved',
    created_at text NOT NULL,
    decided_at text
);

CREATE TABLE IF NOT EXISTS relationship_signal_candidates (
    candidate_id text PRIMARY KEY,
    release_id text,
    left_signal_id text,
    right_signal_id text,
    proposed_relationship_type text,
    deterministic_evidence_json text NOT NULL DEFAULT '[]',
    model_outputs_json text NOT NULL DEFAULT '[]',
    source_passage text,
    rejection_reasons_json text NOT NULL DEFAULT '[]',
    status text NOT NULL DEFAULT 'unresolved',
    created_at text NOT NULL,
    decided_at text
);

CREATE TABLE IF NOT EXISTS signal_graph_projection_queue (
    queue_id text PRIMARY KEY,
    release_id text NOT NULL REFERENCES analysis_releases(release_id),
    object_type text NOT NULL,
    object_id text NOT NULL,
    operation text NOT NULL,
    created_at text NOT NULL,
    processed_at text,
    attempt_count bigint NOT NULL DEFAULT 0,
    last_error text
);

CREATE TABLE IF NOT EXISTS signal_graph_projection_runs (
    run_id text PRIMARY KEY,
    release_id text,
    started_at text NOT NULL,
    completed_at text,
    status text NOT NULL,
    signal_count bigint NOT NULL DEFAULT 0,
    theme_count bigint NOT NULL DEFAULT 0,
    error_detail text
);

CREATE INDEX IF NOT EXISTS ix_entity_link_suggestions_status ON entity_link_suggestions(status, created_at);
CREATE INDEX IF NOT EXISTS ix_relationship_signal_candidates_status ON relationship_signal_candidates(status, created_at);
CREATE INDEX IF NOT EXISTS ix_signal_graph_queue_pending ON signal_graph_projection_queue(processed_at, created_at);
