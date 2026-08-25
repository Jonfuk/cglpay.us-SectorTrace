-- Module 29: Rough sleeping snapshot (MHCLG).
--
-- One evergreen GOV.UK page republishes the whole 2010-current time series
-- on every edition -- one column per year, not one file per year -- so a
-- single fetch captures the full history rather than needing per-edition
-- discovery. Count and the source's own published rate per 100,000
-- population (calculated by MHCLG from ONS population estimates, never by
-- this pipeline) are kept in the same row, one per (authority, year).
--
-- PostgreSQL dialect of ../0059_rough_sleeping.sql. See README.md in this
-- directory for the conversion rules.

CREATE TABLE IF NOT EXISTS rough_sleeping_snapshot (
    ons_code        text NOT NULL,
    snapshot_year   bigint NOT NULL,
    count           bigint,             -- NULL where the cell is [x]/[z]/[n]
    count_text      text NOT NULL,      -- the cell verbatim, always kept
    rate_per_100k   double precision,   -- MHCLG's own figure; see the module
                                         -- docstring on why this pipeline
                                         -- never computes one itself
    rate_text       text,               -- verbatim; NULL if Table 5 had no
                                         -- matching row for this authority/year
    source_url      text NOT NULL,
    retrieved_at    text NOT NULL,
    http_status     bigint NOT NULL,
    source_system   text NOT NULL,
    payload_sha256  text NOT NULL,
    PRIMARY KEY (ons_code, snapshot_year)
);

CREATE INDEX IF NOT EXISTS idx_rough_sleeping_year
    ON rough_sleeping_snapshot (snapshot_year);
