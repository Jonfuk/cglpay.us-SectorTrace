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

CREATE TABLE IF NOT EXISTS gender_pay_gap_reports (
    provider_key               TEXT NOT NULL,  -- the tracked provider the filing matched
    reporting_year             TEXT NOT NULL,  -- the year the reporting year starts ("2025")
    reporting_year_label       TEXT NOT NULL,  -- verbatim: "2025 to 2026"
    employer_id                TEXT NOT NULL,  -- the service's own employer id
    match_basis                TEXT NOT NULL,  -- 'company_number' | 'name_exact'
    employer_name              TEXT,           -- the name as reported, verbatim
    company_number             TEXT,           -- as the file publishes it, verbatim
    sic_codes                  TEXT,           -- as published (comma-joined list)
    diff_mean_hourly_percent   REAL,           -- NULL where the filing left the cell blank
    diff_median_hourly_percent REAL,
    diff_mean_bonus_percent    REAL,
    diff_median_bonus_percent  REAL,
    male_bonus_percent         REAL,
    female_bonus_percent       REAL,
    male_lower_quartile        REAL,
    female_lower_quartile      REAL,
    male_lower_middle_quartile REAL,
    female_lower_middle_quartile REAL,
    male_upper_middle_quartile REAL,
    female_upper_middle_quartile REAL,
    male_top_quartile          REAL,
    female_top_quartile        REAL,
    written_statement_url      TEXT,           -- CompanyLinkToGPGInfo: the employer's own page
    employer_size              TEXT,           -- the service's band, verbatim
    current_name               TEXT,           -- the employer's current name, verbatim
    submitted_after_deadline   INTEGER,        -- 0/1 as the file says
    due_date                   TEXT,           -- verbatim; "dd/mm/yyyy hh:mm"
    date_submitted             TEXT,
    source_url                 TEXT NOT NULL,
    retrieved_at               TEXT NOT NULL,
    http_status                INTEGER NOT NULL,
    source_system              TEXT NOT NULL,
    payload_sha256             TEXT NOT NULL,
    PRIMARY KEY (provider_key, reporting_year, employer_id)
);

CREATE INDEX IF NOT EXISTS idx_gender_pay_gap_year
    ON gender_pay_gap_reports (reporting_year);
