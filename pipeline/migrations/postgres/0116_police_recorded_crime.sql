-- Module 36: Police recorded crime, drug offences (Home Office, CSP level).
--
-- One row per (authority, financial-year quarter, drug-offence subgroup) --
-- e.g. "Possession of drugs" and "Trafficking of drugs" stay separate rows
-- rather than being summed into one "drug offences" total, because this
-- pipeline computes no such total itself (see docs/CAVEATS.md). `csp_name`
-- keeps the source's own Community Safety Partnership label alongside the
-- matched `ons_code`, so a reader can check the name match this pipeline
-- made rather than trust it blindly -- most current CSPs are named
-- identically to their local authority, but not all are, and an
-- unmatched name is never stored here at all (see the module docstring).

CREATE TABLE IF NOT EXISTS police_recorded_drug_offences (
    ons_code            text NOT NULL,
    csp_name            text NOT NULL,   -- the source's own CSP label, verbatim
    financial_year      text NOT NULL,   -- e.g. '2025/26', verbatim
    financial_quarter   bigint NOT NULL, -- 1-4; Home Office financial-year quarter
    quarter_start       text NOT NULL,   -- 'YYYY-MM-01', computed -- see the module
    offence_subgroup    text NOT NULL,   -- e.g. 'Possession of drugs', verbatim
    offence_count       bigint,          -- NULL only if the source cell were unparseable
    offence_count_text  text NOT NULL,   -- the cell verbatim, always kept
    source_url      text NOT NULL,
    retrieved_at    text NOT NULL,
    http_status     bigint NOT NULL,
    source_system   text NOT NULL,
    payload_sha256  text NOT NULL,
    PRIMARY KEY (ons_code, quarter_start, offence_subgroup)
);

CREATE INDEX IF NOT EXISTS idx_police_recorded_drug_offences_quarter
    ON police_recorded_drug_offences (quarter_start);
