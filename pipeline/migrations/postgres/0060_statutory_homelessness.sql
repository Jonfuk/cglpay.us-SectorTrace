-- Module 30: Statutory homelessness (H-CLIC), Table A1.
--
-- One row per (authority, quarter): how many households were assessed
-- under the Housing Act's homelessness duties, and what was decided --
-- owed a prevention or relief duty, or one of three no-duty outcomes.
-- Every numeric column has a paired `_text` column holding the cell
-- verbatim, because MHCLG's own [x]/[z]/[n]/[c] placeholders are common
-- and none of them means zero -- see docs/CAVEATS.md.
--
-- PostgreSQL dialect of ../0060_statutory_homelessness.sql. See README.md
-- in this directory for the conversion rules.

CREATE TABLE IF NOT EXISTS statutory_homelessness_snapshot (
    ons_code                            text NOT NULL,
    quarter_start                       text NOT NULL,  -- 'YYYY-MM-01'
    quarter_label                       text NOT NULL,  -- e.g. 'January to March 2026'
    total_initial_assessments           bigint,
    total_initial_assessments_text      text,
    total_owed_duty                     bigint,
    total_owed_duty_text                text,
    prevention_duty_owed                bigint,
    prevention_duty_owed_text           text,
    relief_duty_owed                    bigint,
    relief_duty_owed_text               text,
    not_threatened_no_duty              bigint,
    not_threatened_no_duty_text         text,
    withdrew_no_duty                    bigint,
    withdrew_no_duty_text               text,
    not_eligible_no_duty                bigint,
    not_eligible_no_duty_text           text,
    households_in_area_thousands        double precision,
    households_in_area_thousands_text   text,
    source_url      text NOT NULL,
    retrieved_at    text NOT NULL,
    http_status     bigint NOT NULL,
    source_system   text NOT NULL,
    payload_sha256  text NOT NULL,
    PRIMARY KEY (ons_code, quarter_start)
);

CREATE INDEX IF NOT EXISTS idx_statutory_homelessness_quarter
    ON statutory_homelessness_snapshot (quarter_start);
