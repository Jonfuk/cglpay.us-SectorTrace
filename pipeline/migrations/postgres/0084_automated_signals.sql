CREATE TABLE IF NOT EXISTS analysis_model_calls (
    model_call_id text PRIMARY KEY,
    release_id text NOT NULL REFERENCES analysis_releases(release_id),
    domain_id text NOT NULL,
    window_id text,
    model_id text NOT NULL,
    prompt_sha256 text NOT NULL,
    response_json text,
    cached bigint NOT NULL DEFAULT 0,
    cost_micros bigint,
    latency_ms bigint,
    status text NOT NULL,
    created_at text NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_verifier_results (
    verifier_result_id text PRIMARY KEY,
    signal_id text,
    verifier_name text NOT NULL,
    passed bigint NOT NULL,
    score double precision,
    reasons_json text NOT NULL DEFAULT '[]',
    created_at text NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_topics (
    topic_id text PRIMARY KEY,
    release_id text NOT NULL REFERENCES analysis_releases(release_id),
    domain_id text,
    topic_number bigint NOT NULL,
    label text,
    novelty_similarity double precision,
    outlier bigint NOT NULL DEFAULT 0,
    representative_json text NOT NULL DEFAULT '[]',
    created_at text NOT NULL
);

CREATE TABLE IF NOT EXISTS emerging_themes (
    theme_id text PRIMARY KEY,
    release_id text NOT NULL REFERENCES analysis_releases(release_id),
    domain_id text NOT NULL,
    theme_key text NOT NULL,
    status text NOT NULL DEFAULT 'shadow',
    passage_count bigint NOT NULL DEFAULT 0,
    document_count bigint NOT NULL DEFAULT 0,
    subject_count bigint NOT NULL DEFAULT 0,
    novelty_similarity double precision,
    evidence_json text NOT NULL DEFAULT '[]',
    promotion_reason text,
    created_at text NOT NULL,
    promoted_at text
);

CREATE TABLE IF NOT EXISTS automated_signals (
    signal_id text PRIMARY KEY,
    release_id text NOT NULL REFERENCES analysis_releases(release_id),
    domain_id text NOT NULL,
    taxonomy_namespace text NOT NULL,
    signal_type text NOT NULL,
    subject_type text NOT NULL,
    subject_id text NOT NULL,
    direction text NOT NULL,
    assertion_status text NOT NULL,
    period_start text,
    period_end text,
    evidence_refs_json text NOT NULL,
    derivation_method text NOT NULL,
    confidence_contract_json text NOT NULL,
    human_verified bigint NOT NULL DEFAULT 0,
    created_at text NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_automated_signals_subject ON automated_signals(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS ix_automated_signals_release_domain ON automated_signals(release_id, domain_id);
CREATE INDEX IF NOT EXISTS ix_emerging_themes_status ON emerging_themes(status, domain_id);
