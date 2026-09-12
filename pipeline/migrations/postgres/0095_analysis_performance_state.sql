-- Compact, resumable analysis state and content-addressed model reuse.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM analysis_runs
        WHERE status IN ('queued', 'running', 'paused', 'cancelling')
    ) THEN
        RAISE EXCEPTION
            'migration 0095 requires active analysis work to finish or be stopped at a committed checkpoint';
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS analysis_input_manifests (
    input_manifest_id text PRIMARY KEY,
    domain_run_id text NOT NULL UNIQUE REFERENCES analysis_domain_runs(domain_run_id),
    run_id text NOT NULL,
    release_id text NOT NULL REFERENCES analysis_releases(release_id),
    domain_id text NOT NULL,
    source_tables_json text NOT NULL,
    input_count bigint NOT NULL DEFAULT 0,
    ordered_input_sha256 text NOT NULL,
    configuration_sha256 text NOT NULL,
    prefilter_version text NOT NULL,
    prefilter_result_sha256 text,
    suppression_enabled bigint NOT NULL DEFAULT 0 CHECK (suppression_enabled IN (0, 1)),
    candidate_count bigint NOT NULL DEFAULT 0,
    checkpoint_document_id text,
    checkpoint_sequence bigint,
    checkpoint_element_id text,
    accumulator_json text NOT NULL DEFAULT '{}',
    output_sha256 text,
    status text NOT NULL DEFAULT 'active',
    detail_purged_at text,
    created_at text NOT NULL,
    updated_at text NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_candidates (
    candidate_id text PRIMARY KEY,
    input_manifest_id text NOT NULL REFERENCES analysis_input_manifests(input_manifest_id),
    ordinal bigint NOT NULL,
    document_element_id text NOT NULL,
    prefilter_matched bigint NOT NULL,
    critical_categories_json text NOT NULL DEFAULT '[]',
    status text NOT NULL DEFAULT 'pending',
    error_detail text,
    created_at text NOT NULL,
    UNIQUE (input_manifest_id, document_element_id),
    UNIQUE (input_manifest_id, ordinal)
);

CREATE TABLE IF NOT EXISTS analysis_theme_counts (
    input_manifest_id text NOT NULL REFERENCES analysis_input_manifests(input_manifest_id),
    theme_key text NOT NULL,
    first_ordinal bigint NOT NULL,
    passage_count bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (input_manifest_id, theme_key)
);
CREATE TABLE IF NOT EXISTS analysis_theme_documents (
    input_manifest_id text NOT NULL REFERENCES analysis_input_manifests(input_manifest_id),
    theme_key text NOT NULL,
    document_id text NOT NULL,
    PRIMARY KEY (input_manifest_id, theme_key, document_id)
);
CREATE TABLE IF NOT EXISTS analysis_theme_subjects (
    input_manifest_id text NOT NULL REFERENCES analysis_input_manifests(input_manifest_id),
    theme_key text NOT NULL,
    subject_id text NOT NULL,
    PRIMARY KEY (input_manifest_id, theme_key, subject_id)
);
CREATE TABLE IF NOT EXISTS analysis_theme_evidence (
    input_manifest_id text NOT NULL REFERENCES analysis_input_manifests(input_manifest_id),
    theme_key text NOT NULL,
    ordinal bigint NOT NULL,
    passage_json text NOT NULL,
    PRIMARY KEY (input_manifest_id, theme_key, ordinal)
);

CREATE INDEX IF NOT EXISTS ix_analysis_candidates_pending
    ON analysis_candidates (input_manifest_id, status, ordinal, candidate_id);
CREATE INDEX IF NOT EXISTS ix_automated_signals_link_candidates
    ON automated_signals
    (release_id, subject_type, subject_id, domain_id, period_end, signal_id);

CREATE TABLE IF NOT EXISTS analysis_prefilter_results (
    result_id text PRIMARY KEY,
    corpus_version text NOT NULL UNIQUE,
    corpus_sha256 text NOT NULL,
    rules_version text NOT NULL,
    rules_sha256 text NOT NULL,
    thresholds_json text NOT NULL,
    result_sha256 text NOT NULL UNIQUE,
    positives bigint NOT NULL,
    accepted_positives bigint NOT NULL,
    critical_positives bigint NOT NULL,
    accepted_critical bigint NOT NULL,
    critical_categories_json text NOT NULL,
    overall_recall double precision NOT NULL,
    critical_recall double precision NOT NULL,
    gate_passed bigint NOT NULL,
    adjudicated_by text NOT NULL,
    evaluated_at text NOT NULL,
    CHECK (positives > 0),
    CHECK (critical_positives > 0),
    CHECK (accepted_positives <= positives),
    CHECK (accepted_critical <= critical_positives),
    CHECK (gate_passed IN (0, 1))
);

CREATE INDEX IF NOT EXISTS ix_analysis_prefilter_gate
    ON analysis_prefilter_results (rules_version, gate_passed, evaluated_at DESC);

ALTER TABLE analysis_input_manifests
    ADD CONSTRAINT fk_analysis_input_prefilter_result
    FOREIGN KEY (prefilter_result_sha256)
    REFERENCES analysis_prefilter_results(result_sha256);

CREATE TABLE IF NOT EXISTS analysis_model_response_cache (
    request_sha256 text PRIMARY KEY,
    response_sha256 text NOT NULL,
    response_json text NOT NULL,
    requested_model text NOT NULL,
    actual_model text NOT NULL,
    provider_id text,
    created_at text NOT NULL
);

ALTER TABLE analysis_model_calls ADD COLUMN request_sha256 text;
ALTER TABLE analysis_model_calls ADD COLUMN response_cache_key text;
ALTER TABLE analysis_model_calls
    ADD CONSTRAINT fk_analysis_model_calls_cache
    FOREIGN KEY (response_cache_key)
    REFERENCES analysis_model_response_cache(request_sha256);
CREATE INDEX IF NOT EXISTS ix_analysis_model_calls_request
    ON analysis_model_calls (request_sha256, created_at);

-- A release/table has one health observation. A source shared by several
-- domains must not be counted and stored repeatedly.
DELETE FROM analysis_health_snapshots a
USING analysis_health_snapshots b
WHERE a.release_id IS NOT NULL
  AND a.release_id = b.release_id
  AND a.source_table = b.source_table
  AND (a.collected_at, a.health_snapshot_id) < (b.collected_at, b.health_snapshot_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_analysis_health_release_source
    ON analysis_health_snapshots (release_id, source_table)
    WHERE release_id IS NOT NULL;

-- Existing terminal detail is no longer a permanent passage ledger. Active
-- and failed work is deliberately retained for safe resume/inspection.
DELETE FROM analysis_windows aw
USING analysis_domain_runs dr
WHERE aw.domain_run_id = dr.domain_run_id
  AND dr.status IN ('complete', 'unavailable', 'cancelled');
DROP INDEX IF EXISTS ix_analysis_windows_subject;
CREATE INDEX IF NOT EXISTS ix_analysis_windows_active
    ON analysis_windows (domain_run_id, status, source_record_id);

CREATE OR REPLACE FUNCTION reject_model_cache_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'analysis model cache and audit rows are append-only'
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$;
DROP TRIGGER IF EXISTS analysis_model_cache_no_update ON analysis_model_response_cache;
CREATE TRIGGER analysis_model_cache_no_update
BEFORE UPDATE OR DELETE ON analysis_model_response_cache
FOR EACH ROW EXECUTE FUNCTION reject_model_cache_mutation();

DROP TRIGGER IF EXISTS analysis_model_calls_no_update ON analysis_model_calls;
CREATE TRIGGER analysis_model_calls_no_update
BEFORE UPDATE OR DELETE ON analysis_model_calls
FOR EACH ROW EXECUTE FUNCTION reject_model_cache_mutation();

DROP TRIGGER IF EXISTS analysis_prefilter_results_no_update ON analysis_prefilter_results;
CREATE TRIGGER analysis_prefilter_results_no_update
BEFORE UPDATE OR DELETE ON analysis_prefilter_results
FOR EACH ROW EXECUTE FUNCTION reject_model_cache_mutation();

CREATE OR REPLACE FUNCTION reject_sealed_input_manifest_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' OR OLD.status = 'complete' OR OLD.detail_purged_at IS NOT NULL THEN
        RAISE EXCEPTION 'sealed analysis input manifests are immutable'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS analysis_input_manifests_sealed ON analysis_input_manifests;
CREATE TRIGGER analysis_input_manifests_sealed
BEFORE UPDATE OR DELETE ON analysis_input_manifests
FOR EACH ROW EXECUTE FUNCTION reject_sealed_input_manifest_mutation();
