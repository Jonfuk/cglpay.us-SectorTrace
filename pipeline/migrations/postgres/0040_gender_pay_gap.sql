-- Module 20: gender pay gap reports, from the Gender Pay Gap service's own
-- bulk download (`/viewing/download-data/{year}`).
--
-- One row per MATCHED filing: a provider whose legal entity appears in the
-- bulk file for a year gets a row with the figures as submitted. Absence is
-- deliberately NOT a row: a provider not in the file may be out of scope
-- (fewer than 250 staff, outside the law's reach) or may not have filed, and
-- the module cannot tell which. The absence is a review item
-- (`gender_pay_gap_absence`), which is the one place the distinction can be
-- decided -- never a zero gap.
--
-- `ResponsiblePerson` from the source CSV is deliberately NOT collected: it
-- is the name of the person who confirmed the figures, personal data this
-- pipeline has no reason to hold.
--
-- PostgreSQL dialect of ../0040_gender_pay_gap.sql. See README.md in this directory for
-- the conversion rules; the porting decisions specific to this file are
-- commented where they occur.

CREATE TABLE IF NOT EXISTS gender_pay_gap_reports (
    provider_key               text NOT NULL,  -- the tracked provider the filing matched
    reporting_year             text NOT NULL,  -- the year the reporting year starts ("2025")
    reporting_year_label       text NOT NULL,  -- verbatim: "2025 to 2026"
    employer_id                text NOT NULL,  -- the service's own employer id
    match_basis                text NOT NULL,  -- 'company_number' | 'name_exact'
    employer_name              text,           -- the name as reported, verbatim
    company_number             text,           -- as the file publishes it, verbatim
    sic_codes                  text,           -- as published (comma-joined list)
    diff_mean_hourly_percent   double precision, -- NULL where the filing left the cell blank
    diff_median_hourly_percent double precision,
    diff_mean_bonus_percent    double precision,
    diff_median_bonus_percent  double precision,
    male_bonus_percent         double precision,
    female_bonus_percent       double precision,
    male_lower_quartile        double precision,
    female_lower_quartile      double precision,
    male_lower_middle_quartile double precision,
    female_lower_middle_quartile double precision,
    male_upper_middle_quartile double precision,
    female_upper_middle_quartile double precision,
    male_top_quartile          double precision,
    female_top_quartile        double precision,
    written_statement_url      text,           -- CompanyLinkToGPGInfo: the employer's own page
    employer_size              text,           -- the service's band, verbatim
    current_name               text,           -- the employer's current name, verbatim
    submitted_after_deadline   bigint,         -- 0/1 as the file says
    due_date                   text,           -- verbatim; "dd/mm/yyyy hh:mm"
    date_submitted             text,
    source_url                 text NOT NULL,
    retrieved_at               text NOT NULL,
    http_status                bigint NOT NULL,
    source_system              text NOT NULL,
    payload_sha256             text NOT NULL,
    PRIMARY KEY (provider_key, reporting_year, employer_id)
);

CREATE INDEX IF NOT EXISTS idx_gender_pay_gap_year
    ON gender_pay_gap_reports (reporting_year);
