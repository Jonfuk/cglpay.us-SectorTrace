-- PostgreSQL dialect of ../0056_ndtms_monthly.sql. See README.md in this
-- directory for the conversion rules.
CREATE TABLE IF NOT EXISTS ndtms_monthly_statistics (
    report_version_id    bigint NOT NULL,
    report_month          text NOT NULL,
    cohort                  text NOT NULL,
    area_name_raw            text NOT NULL,
    dat_code                   text NOT NULL,
    ons_code                     text,
    region_code                    text NOT NULL,
    section                          text NOT NULL,
    substance_category                 text NOT NULL,
    time_period_raw                      text NOT NULL,
    value                                   double precision,
    value_text                               text NOT NULL,
    source_url                                 text NOT NULL,
    retrieved_at                                 text NOT NULL,
    http_status                                    bigint NOT NULL,
    source_system                                    text NOT NULL,
    payload_sha256                                     text NOT NULL,
    PRIMARY KEY (report_version_id, cohort, dat_code, section, substance_category, time_period_raw)
);

CREATE INDEX IF NOT EXISTS idx_ndtms_monthly_ons ON ndtms_monthly_statistics (ons_code);
CREATE INDEX IF NOT EXISTS idx_ndtms_monthly_section ON ndtms_monthly_statistics (section);
