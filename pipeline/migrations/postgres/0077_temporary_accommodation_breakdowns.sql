-- BETA-064: the bed-and-breakfast breakdown of Table TA1.
--
-- PostgreSQL dialect of ../0077_temporary_accommodation_breakdowns.sql. See
-- README.md in this directory for the conversion rules.
--
-- One narrow row per (authority, quarter, measure). `measure` is a closed
-- set (see `_BB_MEASURES` in pipeline/modules/m31_temporary_accommodation.py);
-- an unrecognised B&B column is a review-queue row, never a guessed measure.
-- `households` is NULL for MHCLG's [x]/[z]/[n]/[c] placeholders and
-- `households_text` keeps the cell verbatim. TEXT/INTEGER -> text/bigint only.
CREATE TABLE IF NOT EXISTS temporary_accommodation_breakdowns (
    ons_code        text NOT NULL,
    quarter_start   text NOT NULL,   -- 'YYYY-MM-01'
    quarter_label   text NOT NULL,   -- e.g. 'January to March 2026'
    measure         text NOT NULL,   -- a code from _BB_MEASURES
    unit            text NOT NULL,   -- 'households'
    households      bigint,
    households_text text,
    source_url      text NOT NULL,
    retrieved_at    text NOT NULL,
    http_status     bigint NOT NULL,
    source_system   text NOT NULL,
    payload_sha256  text NOT NULL,
    PRIMARY KEY (ons_code, quarter_start, measure)
);

CREATE INDEX IF NOT EXISTS idx_temporary_accommodation_breakdowns_quarter
    ON temporary_accommodation_breakdowns (quarter_start);
CREATE INDEX IF NOT EXISTS idx_temporary_accommodation_breakdowns_measure
    ON temporary_accommodation_breakdowns (measure);
