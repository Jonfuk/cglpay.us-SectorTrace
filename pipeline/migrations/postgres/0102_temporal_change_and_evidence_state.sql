-- Centrally reserved migration 0102, reconciled against beta before use.
-- Generic temporal/change records supplement source-specific verbatim fields;
-- they do not invent dates and never turn absence into non-existence.

CREATE TABLE IF NOT EXISTS evidence_temporal_state (
    temporal_state_id   text PRIMARY KEY,
    layer               text NOT NULL,
    evidence_identity   text NOT NULL,
    evidence_hash       text NOT NULL,
    source_valid_from   date,
    source_valid_to     date,
    observed_at         timestamptz,
    effective_at        timestamptz,
    retrieved_at        timestamptz,
    state               text NOT NULL,
    is_current          boolean NOT NULL,
    supersedes_id       text REFERENCES evidence_temporal_state(temporal_state_id),
    source_url          text,
    payload_sha256      text,
    provenance_json     jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL,
    CHECK (state IN ('new','unchanged','modified','removed','redirected','superseded','historical')),
    CHECK (source_valid_to IS NULL OR source_valid_from IS NULL OR source_valid_to >= source_valid_from)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_temporal_one_current
    ON evidence_temporal_state (layer, evidence_identity) WHERE is_current;
CREATE INDEX IF NOT EXISTS idx_evidence_temporal_history
    ON evidence_temporal_state (layer, evidence_identity, retrieved_at DESC);

CREATE TABLE IF NOT EXISTS evidence_change_events (
    change_event_id       text PRIMARY KEY,
    layer                 text NOT NULL,
    evidence_identity     text NOT NULL,
    prior_hash            text,
    current_hash          text,
    change_state          text NOT NULL,
    prior_state_id        text REFERENCES evidence_temporal_state(temporal_state_id),
    current_state_id      text REFERENCES evidence_temporal_state(temporal_state_id),
    source_url_before     text,
    source_url_after      text,
    observed_at           timestamptz NOT NULL,
    provenance_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (change_state IN ('new','unchanged','modified','removed','redirected','superseded'))
);

CREATE INDEX IF NOT EXISTS idx_evidence_change_identity
    ON evidence_change_events (layer, evidence_identity, observed_at DESC);

CREATE TABLE IF NOT EXISTS evidence_quality_assertions (
    assertion_id       text PRIMARY KEY,
    layer              text NOT NULL,
    evidence_identity  text NOT NULL,
    assertion_type     text NOT NULL,
    assertion_value    text,
    assertion_status   text NOT NULL,
    method             text NOT NULL,
    rationale          text,
    asserted_by        text,
    asserted_at        timestamptz NOT NULL,
    source_url         text,
    payload_sha256     text,
    provenance_json    jsonb NOT NULL DEFAULT '{}'::jsonb,
    supersedes_id      text REFERENCES evidence_quality_assertions(assertion_id),
    is_current         boolean NOT NULL DEFAULT true,
    CHECK (assertion_type IN ('authority','extraction_quality','corroboration','temporal_completeness','review_state')),
    CHECK (assertion_status IN ('asserted','unknown','not_applicable','needs_review'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_quality_current
    ON evidence_quality_assertions (layer, evidence_identity, assertion_type)
    WHERE is_current;
