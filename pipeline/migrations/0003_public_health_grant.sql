-- Module 11: Public Health Grant allocations (DHSC).
--
-- Stored in tidy/long form — one row per (authority, financial year, grant
-- line item) — rather than a wide fixed-column table, because DHSC's
-- published spreadsheet structure changes shape most years (different
-- sheet name, different header row position, different set of grant
-- breakdowns). grant_type is a normalised slug of the actual source column
-- header, with the raw header preserved in source_column_header for audit.
CREATE TABLE IF NOT EXISTS public_health_grants (
    ons_code               TEXT NOT NULL,
    financial_year          TEXT NOT NULL, -- e.g. '2026-27'
    grant_type               TEXT NOT NULL, -- e.g. 'total_consolidated_public_health_grant', 'drug_alcohol_ring-fenced_funding_total'
    allocation_status         TEXT NOT NULL, -- 'confirmed' | 'indicative'
    unit                       TEXT NOT NULL, -- 'gbp' | 'gbp_per_head'
    amount                      REAL NOT NULL,
    source_column_header          TEXT NOT NULL,
    source_document                TEXT NOT NULL, -- URL of the ODS file this row came from
    source_url                      TEXT NOT NULL,
    retrieved_at                     TEXT NOT NULL,
    http_status                       INTEGER NOT NULL,
    source_system                      TEXT NOT NULL,
    payload_sha256                       TEXT NOT NULL,
    PRIMARY KEY (ons_code, financial_year, grant_type)
);

CREATE INDEX IF NOT EXISTS idx_phg_authority ON public_health_grants (ons_code);
