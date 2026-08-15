-- Module 17: statutory pay rates (National Minimum Wage / National Living
-- Wage), from the GOV.UK rates page -- deliberately NOT an API, because the
-- government publishes no machine-readable rates endpoint; the page is the
-- publication. One row per (period, band), the period and band labels kept
-- verbatim because the band set itself changes between eras (the living wage
-- column was "25 and over" until 2021, "23 and over" to 2024, "21 and over"
-- since).
--
-- The gate in the phase plan applies to whatever is built on this: a floor
-- comparison is side-by-side, and any ratio ("X% above the NLW") is a
-- CAVEATS decision, not the module's.
--
-- PostgreSQL dialect of ../0035_statutory_pay_rates.sql. See README.md in this directory for
-- the conversion rules; the porting decisions specific to this file are
-- commented where they occur.

CREATE TABLE IF NOT EXISTS statutory_pay_rates (
    period_label     text NOT NULL,  -- verbatim: "April 2026", "April 2025 to March 2026"
    effective_from   text,           -- ISO date when the period label parses; NULL otherwise
    band_label       text NOT NULL,  -- verbatim header: "21 and over", "Apprentice", ...
    band_role        text NOT NULL,  -- 'national_living_wage' for the first data column of
                                     -- each table (the page's own layout), else
                                     -- 'national_minimum_wage'
    amount           double precision, -- pounds per hour; NULL where the cell did not parse
    value_text       text NOT NULL,  -- the cell verbatim, so an unparseable figure is
                                     -- still citable
    source_url       text NOT NULL,
    retrieved_at     text NOT NULL,
    http_status      bigint NOT NULL,
    source_system    text NOT NULL,
    payload_sha256   text NOT NULL,
    PRIMARY KEY (period_label, band_label)
);
