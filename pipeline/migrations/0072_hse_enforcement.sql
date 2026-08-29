-- Module 33: HSE enforcement notices (Health and Safety Executive).
--
-- The public HSE Notices register (resources.hse.gov.uk/notices) lists
-- improvement and prohibition notices served on organisations and on
-- individuals. This pipeline keeps only the organisation-level notices --
-- individuals are excluded at parse time, before anything is written -- and
-- publishes only the ones that exactly match a tracked provider name
-- (provider_key IS NOT NULL). Every field is stored verbatim as the register
-- published it: this pipeline never infers a compliance outcome, and a notice
-- can be appealed, affirmed, modified, cancelled or withdrawn after issue.
--
-- One row per notice number. A notice number is HSE's own unique id for the
-- served notice; a re-fetch upserts on it.

CREATE TABLE IF NOT EXISTS hse_enforcement_notices (
    notice_number         TEXT NOT NULL,
    recipient_name        TEXT NOT NULL,     -- the organisation served, verbatim
    provider_key          TEXT,             -- set only on an exact tracked-name match
    notice_type           TEXT NOT NULL,    -- Improvement / Prohibition / ... verbatim
    issuing_body          TEXT,             -- 'HSE' or a local authority, verbatim
    issue_date            TEXT,             -- ISO date where the register gave one
    compliance_date       TEXT,             -- the original compliance-by date, verbatim
    revised_compliance_date TEXT,           -- where the register shows a revision
    result                TEXT,             -- 'Complied' / 'Withdrawn' / 'Under appeal' / ...
    industry              TEXT,             -- HSE's main-activity/industry label, verbatim
    legislation           TEXT,             -- the regulation(s) cited, verbatim
    contravention_text    TEXT,             -- the notice's own description, verbatim
    local_authority       TEXT,             -- where the register attributes one
    source_url            TEXT NOT NULL,
    retrieved_at          TEXT NOT NULL,
    http_status           INTEGER NOT NULL,
    source_system         TEXT NOT NULL,
    payload_sha256        TEXT NOT NULL,
    PRIMARY KEY (notice_number)
);

CREATE INDEX IF NOT EXISTS idx_hse_notices_provider
    ON hse_enforcement_notices (provider_key);
