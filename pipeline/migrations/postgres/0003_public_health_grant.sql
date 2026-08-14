-- Module 11: Public Health Grant allocations (DHSC).
--
-- Stored in tidy/long form — one row per (authority, financial year, grant
-- line item) — rather than a wide fixed-column table, because DHSC's
-- published spreadsheet structure changes shape most years (different
-- sheet name, different header row position, different set of grant
-- breakdowns). grant_type is a normalised slug of the actual source column
-- header, with the raw header preserved in source_column_header for audit.
--
-- PostgreSQL dialect of ../0003_public_health_grant.sql. See README.md in this directory for
-- the conversion rules.
--
CREATE TABLE IF NOT EXISTS public_health_grants (
    ons_code               text NOT NULL,
    financial_year          text NOT NULL, -- e.g. '2026-27'
    grant_type               text NOT NULL, -- e.g. 'total_consolidated_public_health_grant', 'drug_alcohol_ring-fenced_funding_total'
    allocation_status         text NOT NULL, -- 'confirmed' | 'indicative'
    unit                       text NOT NULL, -- 'gbp' | 'gbp_per_head'
    amount                      double precision NOT NULL,
    source_column_header          text NOT NULL,
    source_document                text NOT NULL, -- URL of the ODS file this row came from
    source_url                      text NOT NULL,
    retrieved_at                     text NOT NULL,
    http_status                       bigint NOT NULL,
    source_system                      text NOT NULL,
    payload_sha256                       text NOT NULL,
    PRIMARY KEY (ons_code, financial_year, grant_type)
);

CREATE INDEX IF NOT EXISTS idx_phg_authority ON public_health_grants (ons_code);
