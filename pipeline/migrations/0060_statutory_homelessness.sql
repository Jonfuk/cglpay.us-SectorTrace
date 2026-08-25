-- Module 30: Statutory homelessness (H-CLIC), Table A1.
--
-- One row per (authority, quarter): how many households were assessed
-- under the Housing Act's homelessness duties, and what was decided --
-- owed a prevention or relief duty, or one of three no-duty outcomes.
-- Every numeric column has a paired `_text` column holding the cell
-- verbatim, because MHCLG's own [x]/[z]/[n]/[c] placeholders are common
-- and none of them means zero -- see docs/CAVEATS.md.

CREATE TABLE IF NOT EXISTS statutory_homelessness_snapshot (
    ons_code                            TEXT NOT NULL,
    quarter_start                       TEXT NOT NULL,  -- 'YYYY-MM-01'
    quarter_label                       TEXT NOT NULL,  -- e.g. 'January to March 2026'
    total_initial_assessments           INTEGER,
    total_initial_assessments_text      TEXT,
    total_owed_duty                     INTEGER,
    total_owed_duty_text                TEXT,
    prevention_duty_owed                INTEGER,
    prevention_duty_owed_text           TEXT,
    relief_duty_owed                    INTEGER,
    relief_duty_owed_text               TEXT,
    not_threatened_no_duty              INTEGER,
    not_threatened_no_duty_text         TEXT,
    withdrew_no_duty                    INTEGER,
    withdrew_no_duty_text               TEXT,
    not_eligible_no_duty                INTEGER,
    not_eligible_no_duty_text           TEXT,
    households_in_area_thousands        REAL,
    households_in_area_thousands_text   TEXT,
    source_url      TEXT NOT NULL,
    retrieved_at    TEXT NOT NULL,
    http_status     INTEGER NOT NULL,
    source_system   TEXT NOT NULL,
    payload_sha256  TEXT NOT NULL,
    PRIMARY KEY (ons_code, quarter_start)
);

CREATE INDEX IF NOT EXISTS idx_statutory_homelessness_quarter
    ON statutory_homelessness_snapshot (quarter_start);
