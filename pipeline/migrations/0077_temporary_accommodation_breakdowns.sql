-- BETA-064: the bed-and-breakfast breakdown of Table TA1.
--
-- Module 31 reads TA1's top-level totals into
-- `temporary_accommodation_snapshot`. TA1 also carries a one-level "of
-- which" breakdown by bed-and-breakfast use, deliberately dropped from that
-- module's v1. This is the bounded follow-up: the same archived quarterly
-- workbook, the same authority spine, one narrow row per (authority,
-- quarter, measure).
--
-- Narrow rather than wide because the set of B&B sub-columns is not stable
-- across the series -- the older multi-row-header era splits households and
-- households-with-children, the flat-header era publishes only the
-- households total -- and a narrow table absorbs that without a migration
-- per vintage. `measure` is a closed set (see `_BB_MEASURES` in
-- pipeline/modules/m31_temporary_accommodation.py); a B&B column that
-- matches none of them is a `parse_failures` / `review_queue` row, never a
-- guessed measure.
--
-- `households` is NULL when the source cell is one of MHCLG's
-- [x]/[z]/[n]/[c] placeholders; `households_text` keeps the cell verbatim,
-- because none of those placeholders means zero -- see docs/CAVEATS.md.
-- `unit` is always 'households' today; it is a column so a future
-- people-count measure does not need a schema change.
CREATE TABLE IF NOT EXISTS temporary_accommodation_breakdowns (
    ons_code        TEXT NOT NULL,
    quarter_start   TEXT NOT NULL,   -- 'YYYY-MM-01'
    quarter_label   TEXT NOT NULL,   -- e.g. 'January to March 2026'
    measure         TEXT NOT NULL,   -- a code from _BB_MEASURES
    unit            TEXT NOT NULL,   -- 'households'
    households      INTEGER,
    households_text TEXT,
    source_url      TEXT NOT NULL,
    retrieved_at    TEXT NOT NULL,
    http_status     INTEGER NOT NULL,
    source_system   TEXT NOT NULL,
    payload_sha256  TEXT NOT NULL,
    PRIMARY KEY (ons_code, quarter_start, measure)
);

CREATE INDEX IF NOT EXISTS idx_temporary_accommodation_breakdowns_quarter
    ON temporary_accommodation_breakdowns (quarter_start);
CREATE INDEX IF NOT EXISTS idx_temporary_accommodation_breakdowns_measure
    ON temporary_accommodation_breakdowns (measure);
