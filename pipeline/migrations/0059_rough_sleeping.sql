-- Module 29: Rough sleeping snapshot (MHCLG).
--
-- One evergreen GOV.UK page republishes the whole 2010-current time series
-- on every edition -- one column per year, not one file per year -- so a
-- single fetch captures the full history rather than needing per-edition
-- discovery. Count and the source's own published rate per 100,000
-- population (calculated by MHCLG from ONS population estimates, never by
-- this pipeline) are kept in the same row, one per (authority, year).

CREATE TABLE IF NOT EXISTS rough_sleeping_snapshot (
    ons_code        TEXT NOT NULL,
    snapshot_year   INTEGER NOT NULL,
    count           INTEGER,           -- NULL where the cell is [x]/[z]/[n]
    count_text      TEXT NOT NULL,     -- the cell verbatim, always kept
    rate_per_100k   REAL,              -- MHCLG's own figure; see the module
                                        -- docstring on why this pipeline never
                                        -- computes one itself
    rate_text       TEXT,              -- verbatim; NULL if Table 5 had no
                                        -- matching row for this authority/year
    source_url      TEXT NOT NULL,
    retrieved_at    TEXT NOT NULL,
    http_status     INTEGER NOT NULL,
    source_system   TEXT NOT NULL,
    payload_sha256  TEXT NOT NULL,
    PRIMARY KEY (ons_code, snapshot_year)
);

CREATE INDEX IF NOT EXISTS idx_rough_sleeping_year
    ON rough_sleeping_snapshot (snapshot_year);
