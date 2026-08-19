-- The derived Evidence Graph's relational foundation.
--
-- PostgreSQL/SQLite remain the authority.  These records hold stable graph
-- identities, provenance and replay state; Neo4j stores only a projection of
-- them and can be discarded and rebuilt at any time.

CREATE TABLE IF NOT EXISTS entities (
    entity_id                 TEXT PRIMARY KEY,
    entity_type               TEXT NOT NULL,
    canonical_name            TEXT NOT NULL,
    canonical_name_normalized TEXT NOT NULL,
    status                    TEXT NOT NULL DEFAULT 'active',
    created_at                TEXT NOT NULL,
    updated_at                TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_type_name
    ON entities (entity_type, canonical_name_normalized);

CREATE TABLE IF NOT EXISTS entity_aliases (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id        TEXT NOT NULL REFERENCES entities(entity_id),
    alias            TEXT NOT NULL,
    alias_normalized TEXT NOT NULL,
    alias_type       TEXT NOT NULL DEFAULT 'known_as',
    source_evidence_id TEXT,
    confidence       REAL,
    valid_from       TEXT,
    valid_to         TEXT,
    created_at       TEXT NOT NULL,
    UNIQUE (entity_id, alias_normalized, alias_type)
);

CREATE INDEX IF NOT EXISTS idx_entity_aliases_normalized
    ON entity_aliases (alias_normalized);

CREATE TABLE IF NOT EXISTS entity_identifiers (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id         TEXT NOT NULL REFERENCES entities(entity_id),
    identifier_scheme TEXT NOT NULL,
    identifier_value  TEXT NOT NULL,
    valid_from        TEXT,
    valid_to          TEXT,
    source_evidence_id TEXT,
    created_at        TEXT NOT NULL,
    UNIQUE (identifier_scheme, identifier_value)
);

CREATE TABLE IF NOT EXISTS evidence_records (
    evidence_id     TEXT PRIMARY KEY,
    source_system   TEXT NOT NULL,
    source_url      TEXT,
    retrieved_at    TEXT NOT NULL,
    http_status     INTEGER,
    payload_sha256  TEXT NOT NULL,
    raw_object_path TEXT,
    mime_type       TEXT,
    content_length  INTEGER,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evidence_records_payload
    ON evidence_records (payload_sha256);

CREATE TABLE IF NOT EXISTS graph_claims (
    claim_id          TEXT PRIMARY KEY,
    source_claim_id   TEXT,
    subject_entity_id TEXT REFERENCES entities(entity_id),
    predicate         TEXT NOT NULL,
    object_entity_id  TEXT REFERENCES entities(entity_id),
    object_literal    TEXT,
    claim_text        TEXT,
    evidence_id       TEXT REFERENCES evidence_records(evidence_id),
    document_reference TEXT,
    page_number       INTEGER,
    section           TEXT,
    text_start        INTEGER,
    text_end          INTEGER,
    evidence_span     TEXT,
    extraction_method TEXT NOT NULL,
    extractor_name    TEXT,
    extractor_version TEXT,
    confidence        REAL,
    review_status     TEXT NOT NULL DEFAULT 'draft',
    created_at        TEXT NOT NULL,
    CHECK (object_entity_id IS NOT NULL OR object_literal IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_graph_claims_subject ON graph_claims (subject_entity_id);
CREATE INDEX IF NOT EXISTS idx_graph_claims_evidence ON graph_claims (evidence_id);

CREATE TABLE IF NOT EXISTS entity_relationships (
    relationship_id    TEXT PRIMARY KEY,
    subject_entity_id  TEXT NOT NULL REFERENCES entities(entity_id),
    predicate          TEXT NOT NULL,
    object_entity_id   TEXT NOT NULL REFERENCES entities(entity_id),
    relationship_type  TEXT NOT NULL,
    evidence_id        TEXT REFERENCES evidence_records(evidence_id),
    claim_id           TEXT REFERENCES graph_claims(claim_id),
    valid_from         TEXT,
    valid_to           TEXT,
    confidence         REAL,
    derivation_type    TEXT NOT NULL,
    derivation_version TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    CHECK (derivation_type IN ('SOURCE_FACT', 'EXTRACTED_CLAIM',
                               'DERIVED_RELATIONSHIP', 'ANALYTICAL_SIGNAL'))
);

CREATE INDEX IF NOT EXISTS idx_entity_relationships_subject
    ON entity_relationships (subject_entity_id, predicate);
CREATE INDEX IF NOT EXISTS idx_entity_relationships_object
    ON entity_relationships (object_entity_id, predicate);

CREATE TABLE IF NOT EXISTS graph_projection_queue (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    object_type   TEXT NOT NULL,
    object_id     TEXT NOT NULL,
    operation     TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    processed_at  TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error    TEXT,
    UNIQUE (object_type, object_id, operation, processed_at)
);

CREATE INDEX IF NOT EXISTS idx_graph_projection_queue_pending
    ON graph_projection_queue (processed_at, id);

CREATE TABLE IF NOT EXISTS graph_projection_runs (
    run_id             TEXT PRIMARY KEY,
    started_at         TEXT NOT NULL,
    completed_at       TEXT,
    status             TEXT NOT NULL,
    schema_version     TEXT NOT NULL,
    projector_version  TEXT NOT NULL,
    warehouse_snapshot TEXT,
    entity_count       INTEGER NOT NULL DEFAULT 0,
    relationship_count INTEGER NOT NULL DEFAULT 0,
    claim_count        INTEGER NOT NULL DEFAULT 0,
    error_count        INTEGER NOT NULL DEFAULT 0,
    error_detail       TEXT
);

CREATE TABLE IF NOT EXISTS graph_metrics (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id        TEXT REFERENCES entities(entity_id),
    metric_name      TEXT NOT NULL,
    metric_value     REAL NOT NULL,
    analysis_name    TEXT NOT NULL,
    analysis_version TEXT NOT NULL,
    graph_snapshot   TEXT NOT NULL,
    calculated_at    TEXT NOT NULL,
    parameters_json  TEXT NOT NULL,
    UNIQUE (entity_id, metric_name, analysis_name, analysis_version, graph_snapshot)
);
