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

CREATE TABLE IF NOT EXISTS temporary_accommodation_snapshot (
    ons_code                            TEXT NOT NULL,
    quarter_start                       TEXT NOT NULL,  -- 'YYYY-MM-01'
    quarter_label                       TEXT NOT NULL,  -- e.g. 'January to March 2026'
    total_households_ta                 INTEGER,
    total_households_ta_text            TEXT,
    households_ta_with_children         INTEGER,
    households_ta_with_children_text    TEXT,
    children_in_ta                      INTEGER,
    children_in_ta_text                 TEXT,
    households_in_area_thousands        REAL,
    households_in_area_thousands_text   TEXT,
    source_url      TEXT NOT NULL,
    retrieved_at    TEXT NOT NULL,
    http_status     INTEGER NOT NULL,
    source_system   TEXT NOT NULL,
    payload_sha256  TEXT NOT NULL,
    PRIMARY KEY (ons_code, quarter_start)
);

CREATE INDEX IF NOT EXISTS idx_temporary_accommodation_quarter
    ON temporary_accommodation_snapshot (quarter_start);
