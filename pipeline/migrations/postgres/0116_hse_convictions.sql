-- Module 33: HSE convictions, sibling to hse_enforcement_notices (0072).
--
-- The public HSE register of convictions lists prosecution breaches at
-- breach level, not case level: a case can carry several breaches, each
-- with its own hearing date, result and fine. This pipeline keeps only the
-- organisation-level breaches -- individuals are excluded at parse time,
-- same as notices -- and publishes only the ones that exactly match a
-- tracked provider name. Every field is stored verbatim.

CREATE TABLE IF NOT EXISTS hse_enforcement_convictions (
    breach_id       text NOT NULL,
    case_number     text NOT NULL,
    breach_sequence text,
    defendant_name  text NOT NULL,
    provider_key    text,
    hearing_date    text,
    result          text,
    fine_text       text,
    legislation     text,
    source_url      text NOT NULL,
    retrieved_at    text NOT NULL,
    http_status     bigint NOT NULL,
    source_system   text NOT NULL,
    payload_sha256  text NOT NULL,
    PRIMARY KEY (breach_id)
);

CREATE INDEX IF NOT EXISTS idx_hse_convictions_provider
    ON hse_enforcement_convictions (provider_key);

CREATE INDEX IF NOT EXISTS idx_hse_convictions_case
    ON hse_enforcement_convictions (case_number);
