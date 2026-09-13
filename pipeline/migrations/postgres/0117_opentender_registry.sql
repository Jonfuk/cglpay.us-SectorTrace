-- Module 40: OpenTender/OCP Registry historical mirror and reconciliation.
--
-- This is deliberately not an extension of `contracts`. The Registry entry is
-- a compiled/latest-value snapshot and its licence is CC BY-NC-SA 4.0, unlike
-- the direct OGL procurement channels. It is operator-only until a person
-- decides whether any particular reuse is permitted.

CREATE TABLE IF NOT EXISTS procurement_mirror_packages (
    package_id          text PRIMARY KEY,
    source_system       text NOT NULL,
    source_url          text NOT NULL,
    retrieved_at        text NOT NULL,
    payload_sha256      text NOT NULL,
    raw_object_path     text NOT NULL,
    byte_size           bigint NOT NULL CHECK (byte_size >= 0),
    content_type        text,
    package_format      text NOT NULL,
    ocid_prefix         text NOT NULL,
    period_start        text,
    period_end          text,
    licence_id          text NOT NULL,
    export_disposition  text NOT NULL DEFAULT 'operator_only',
    status              text NOT NULL,
    row_count           bigint NOT NULL DEFAULT 0 CHECK (row_count >= 0),
    metadata_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          text NOT NULL,
    UNIQUE (source_url, payload_sha256),
    CHECK (source_system = 'opentender_uk_registry'),
    CHECK (licence_id = 'opentender_cc_by_nc_sa'),
    CHECK (export_disposition = 'operator_only'),
    CHECK (status IN ('captured', 'rejected', 'failed'))
);

CREATE TABLE IF NOT EXISTS procurement_mirror_observations (
    observation_id      text PRIMARY KEY,
    package_id          text NOT NULL REFERENCES procurement_mirror_packages(package_id),
    source_record_id    text NOT NULL,
    ocid                text NOT NULL,
    buyer_name          text,
    title               text,
    cpv_codes           text,
    value_amount       double precision,
    value_currency      text,
    date_published     text,
    record_sha256       text NOT NULL,
    parser_version      text NOT NULL,
    match_status        text NOT NULL,
    matched_ocid        text,
    match_basis         text,
    candidate_count     bigint NOT NULL DEFAULT 0 CHECK (candidate_count >= 0),
    metadata_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          text NOT NULL,
    UNIQUE (package_id, source_record_id, record_sha256),
    CHECK (match_status IN ('exact_ocid', 'candidate_match', 'ambiguous_match', 'unmatched'))
);

CREATE INDEX IF NOT EXISTS idx_procurement_mirror_observations_ocid
    ON procurement_mirror_observations (ocid);
CREATE INDEX IF NOT EXISTS idx_procurement_mirror_observations_match
    ON procurement_mirror_observations (match_status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_procurement_mirror_packages_retrieved
    ON procurement_mirror_packages (retrieved_at DESC);

-- Source observations are immutable; the only mutable columns are the
-- reconciliation result, which may become more precise after direct primary
-- evidence is collected. A delete or source-field rewrite would destroy the
-- audit trail needed to explain a later reconciliation.
CREATE OR REPLACE FUNCTION reject_opentender_source_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'OpenTender observations are append-only';
    END IF;
    IF NEW.package_id IS DISTINCT FROM OLD.package_id
       OR NEW.source_record_id IS DISTINCT FROM OLD.source_record_id
       OR NEW.ocid IS DISTINCT FROM OLD.ocid
       OR NEW.buyer_name IS DISTINCT FROM OLD.buyer_name
       OR NEW.title IS DISTINCT FROM OLD.title
       OR NEW.cpv_codes IS DISTINCT FROM OLD.cpv_codes
       OR NEW.value_amount IS DISTINCT FROM OLD.value_amount
       OR NEW.value_currency IS DISTINCT FROM OLD.value_currency
       OR NEW.date_published IS DISTINCT FROM OLD.date_published
       OR NEW.record_sha256 IS DISTINCT FROM OLD.record_sha256
       OR NEW.parser_version IS DISTINCT FROM OLD.parser_version THEN
        RAISE EXCEPTION 'OpenTender source fields are immutable';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS procurement_mirror_observations_source_guard
    ON procurement_mirror_observations;
CREATE TRIGGER procurement_mirror_observations_source_guard
BEFORE UPDATE OR DELETE ON procurement_mirror_observations
FOR EACH ROW EXECUTE FUNCTION reject_opentender_source_mutation();
