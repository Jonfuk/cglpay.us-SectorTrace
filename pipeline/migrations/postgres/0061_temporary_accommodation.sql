-- Module 31: Temporary accommodation (H-CLIC), Table TA1.
--
-- One row per (authority, quarter): households in temporary accommodation
-- as at the last day of the quarter, and the with-children/children
-- breakdown. Reads the same evergreen quarterly attachment Module 30
-- reads Table A1 from -- see that module's docstring on why the discovery
-- and file-reading code is shared, not duplicated. Every numeric column
-- has a paired `_text` column holding the cell verbatim, because MHCLG's
-- own [x]/[z]/[n]/[c] placeholders are common and none of them means zero
-- -- see docs/CAVEATS.md.
--
-- PostgreSQL dialect of ../0061_temporary_accommodation.sql. See README.md
-- in this directory for the conversion rules.

CREATE TABLE IF NOT EXISTS temporary_accommodation_snapshot (
    ons_code                            text NOT NULL,
    quarter_start                       text NOT NULL,  -- 'YYYY-MM-01'
    quarter_label                       text NOT NULL,  -- e.g. 'January to March 2026'
    total_households_ta                 bigint,
    total_households_ta_text            text,
    households_ta_with_children         bigint,
    households_ta_with_children_text    text,
    children_in_ta                      bigint,
    children_in_ta_text                 text,
    households_in_area_thousands        double precision,
    households_in_area_thousands_text   text,
    source_url      text NOT NULL,
    retrieved_at    text NOT NULL,
    http_status     bigint NOT NULL,
    source_system   text NOT NULL,
    payload_sha256  text NOT NULL,
    PRIMARY KEY (ons_code, quarter_start)
);

CREATE INDEX IF NOT EXISTS idx_temporary_accommodation_quarter
    ON temporary_accommodation_snapshot (quarter_start);
