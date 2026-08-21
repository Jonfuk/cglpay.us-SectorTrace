-- Module 27: NDTMS monthly provisional statistics
-- (https://www.ndtms.net/Monthly/Adults, .../YoungPeople -- the classic
-- server-rendered report, not the Power BI "Monthly provisional statistics"
-- front door those pages link to).
--
-- SEPARATE EVIDENCE LAYER, same reasoning as ndtms_la_statistics
-- (migrations/0012_ndtms.sql): service-demand context, not workforce data,
-- never merged with workforce_census_metrics.
--
-- This is a live report with no discrete document to point at, so
-- provenance is the fetched HTML page itself rather than a publication:
-- report_version_id is NDTMS's own report-date sequence number (its
-- ReportVersionId form field), and report_month is that same value resolved
-- to a calendar month. Only the site's current default (latest) month is
-- fetched -- ReportVersionId also addresses months back to April 2014, but
-- walking that whole history multiplies every area by every month, and
-- nothing so far has asked for it.
--
-- area_name_raw/dat_code are NDTMS's own area code (e.g. 'B18B' for
-- Manchester), not an ONS code, so ons_code is resolved by name against
-- `authorities` the same way m07_ndtms does; an unmatched name goes to
-- review_queue rather than being guessed.
CREATE TABLE IF NOT EXISTS ndtms_monthly_statistics (
    report_version_id    INTEGER NOT NULL,
    report_month          TEXT NOT NULL,   -- ISO date of the 1st, e.g. '2026-06-01'
    cohort                  TEXT NOT NULL, -- 'adults' | 'young_people'
    area_name_raw            TEXT NOT NULL,
    dat_code                   TEXT NOT NULL,
    ons_code                     TEXT,
    region_code                    TEXT NOT NULL,  -- ONS region code, e.g. 'E12000002'
    section                          TEXT NOT NULL, -- report section, e.g. 'number_in_treatment'
    substance_category                 TEXT NOT NULL, -- row label, e.g. 'Opioids'
    time_period_raw                      TEXT NOT NULL, -- column label, e.g. 'Jun24 - May25'
    value                                   REAL,
    value_text                               TEXT NOT NULL, -- verbatim cell, kept when unparseable
    source_url                                 TEXT NOT NULL,
    retrieved_at                                 TEXT NOT NULL,
    http_status                                    INTEGER NOT NULL,
    source_system                                    TEXT NOT NULL,
    payload_sha256                                     TEXT NOT NULL,
    PRIMARY KEY (report_version_id, cohort, dat_code, section, substance_category, time_period_raw)
);

CREATE INDEX IF NOT EXISTS idx_ndtms_monthly_ons ON ndtms_monthly_statistics (ons_code);
CREATE INDEX IF NOT EXISTS idx_ndtms_monthly_section ON ndtms_monthly_statistics (section);
