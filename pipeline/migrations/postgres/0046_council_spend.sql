-- Phase 19 (G5): council spend-transparency files.
--
-- PostgreSQL dialect of ../0046_council_spend.sql. See README.md in this
-- directory for the conversion rules; the porting decisions specific to this
-- file are commented where they occur.
--
-- The argument for the schema lives in the SQLite original: line items are
-- stored verbatim (`payee`, `amount_text`) with `amount` parsed beside them
-- (NULL where unreadable, never a zero), and `provider_key` is set only by
-- an exact-normalised match against the tracked providers' own variants.

CREATE TABLE IF NOT EXISTS council_spend_files (
    authority_ons_code text NOT NULL,
    file_url           text NOT NULL,
    discovered_from    text,
    file_format        text,
    parse_status       text NOT NULL,
    row_count          bigint,
    source_url         text NOT NULL,
    retrieved_at       text NOT NULL,
    http_status        bigint NOT NULL,
    source_system      text NOT NULL,
    payload_sha256     text NOT NULL,
    PRIMARY KEY (authority_ons_code, file_url)
);

CREATE TABLE IF NOT EXISTS council_spend (
    authority_ons_code text NOT NULL,
    file_url           text NOT NULL,
    row_index          bigint NOT NULL,
    period             text,
    payee              text NOT NULL,
    amount             double precision,
    amount_text        text,
    description        text,
    provider_key       text,
    source_url         text NOT NULL,
    retrieved_at       text NOT NULL,
    http_status        bigint NOT NULL,
    source_system      text NOT NULL,
    payload_sha256     text NOT NULL,
    PRIMARY KEY (authority_ons_code, file_url, row_index)
);

CREATE INDEX IF NOT EXISTS idx_council_spend_authority
    ON council_spend (authority_ons_code);
CREATE INDEX IF NOT EXISTS idx_council_spend_provider
    ON council_spend (provider_key);
