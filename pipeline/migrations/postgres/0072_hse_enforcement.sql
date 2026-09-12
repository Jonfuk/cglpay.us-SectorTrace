-- Module 33: HSE enforcement notices (Health and Safety Executive).
--
-- PostgreSQL dialect of ../0072_hse_enforcement.sql. See README.md in this
-- directory for the conversion rules.
--
-- The public HSE Notices register lists improvement and prohibition notices
-- served on organisations and on individuals. This pipeline keeps only the
-- organisation-level notices -- individuals are excluded at parse time -- and
-- publishes only the ones that exactly match a tracked provider name. Every
-- field is stored verbatim; this pipeline never infers a compliance outcome,
-- and a notice can be appealed, affirmed, modified, cancelled or withdrawn.

CREATE TABLE IF NOT EXISTS hse_enforcement_notices (
    notice_number         text NOT NULL,
    recipient_name        text NOT NULL,
    provider_key          text,
    notice_type           text NOT NULL,
    issuing_body          text,
    issue_date            text,
    compliance_date       text,
    revised_compliance_date text,
    result                text,
    industry              text,
    legislation           text,
    contravention_text    text,
    local_authority       text,
    source_url            text NOT NULL,
    retrieved_at          text NOT NULL,
    http_status           bigint NOT NULL,
    source_system         text NOT NULL,
    payload_sha256        text NOT NULL,
    PRIMARY KEY (notice_number)
);

CREATE INDEX IF NOT EXISTS idx_hse_notices_provider
    ON hse_enforcement_notices (provider_key);
