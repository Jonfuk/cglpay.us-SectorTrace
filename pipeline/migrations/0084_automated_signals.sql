-- Model-call provenance, verification, topics and the isolated signal envelope.
CREATE TABLE IF NOT EXISTS analysis_model_calls (
    model_call_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL REFERENCES analysis_releases(release_id),
    domain_id TEXT NOT NULL,
    window_id TEXT,
    model_id TEXT NOT NULL,
    prompt_sha256 TEXT NOT NULL,
    response_json TEXT,
    cached INTEGER NOT NULL DEFAULT 0,
    cost_micros INTEGER,
    latency_ms INTEGER,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_verifier_results (
    verifier_result_id TEXT PRIMARY KEY,
    signal_id TEXT,
    verifier_name TEXT NOT NULL,
    passed INTEGER NOT NULL,
    score REAL,
    reasons_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_topics (
    topic_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL REFERENCES analysis_releases(release_id),
    domain_id TEXT,
    topic_number INTEGER NOT NULL,
    label TEXT,
    novelty_similarity REAL,
    outlier INTEGER NOT NULL DEFAULT 0,
    representative_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS emerging_themes (
    theme_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL REFERENCES analysis_releases(release_id),
    domain_id TEXT NOT NULL,
    theme_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'shadow',
    passage_count INTEGER NOT NULL DEFAULT 0,
    document_count INTEGER NOT NULL DEFAULT 0,
    subject_count INTEGER NOT NULL DEFAULT 0,
    novelty_similarity REAL,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    promotion_reason TEXT,
    created_at TEXT NOT NULL,
    promoted_at TEXT
);

CREATE TABLE IF NOT EXISTS automated_signals (
    signal_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL REFERENCES analysis_releases(release_id),
    domain_id TEXT NOT NULL,
    taxonomy_namespace TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    assertion_status TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    evidence_refs_json TEXT NOT NULL,
    derivation_method TEXT NOT NULL,
    confidence_contract_json TEXT NOT NULL,
    human_verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_automated_signals_subject ON automated_signals(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS ix_automated_signals_release_domain ON automated_signals(release_id, domain_id);
CREATE INDEX IF NOT EXISTS ix_emerging_themes_status ON emerging_themes(status, domain_id);
