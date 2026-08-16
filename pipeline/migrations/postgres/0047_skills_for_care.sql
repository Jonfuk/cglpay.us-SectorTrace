-- Phase 19 (G2): Skills for Care workforce intelligence.
--
-- PostgreSQL dialect of ../0047_skills_for_care.sql. See README.md in this
-- directory for the conversion rules; the porting decisions specific to this
-- file are commented where they occur.
--
-- The argument for the schema lives in the SQLite original: per-file rows
-- with parse_status, and per-estimate rows carrying the pay and turnover
-- columns as published (NULL where unreadable, never derived), with the
-- workbook itself archived in full.

CREATE TABLE IF NOT EXISTS skills_for_care_files (
    file_url         text PRIMARY KEY,
    link_label       text,
    file_format      text,
    parse_status     text NOT NULL,
    row_count        bigint,
    source_url       text NOT NULL,
    retrieved_at     text NOT NULL,
    http_status      bigint NOT NULL,
    source_system    text NOT NULL,
    payload_sha256   text NOT NULL
);

CREATE TABLE IF NOT EXISTS skills_for_care_estimates (
    file_url       text NOT NULL,
    year           text,
    area_code      text,
    area_level     text,
    region         text,
    area           text,
    sector         text,
    service        text,
    job_role_group text,
    job_role       text,
    fte_annual_pay double precision,
    hourly_pay     double precision,
    turnover_rate  double precision,
    vacancy_rate   double precision,
    source_url     text NOT NULL,
    retrieved_at   text NOT NULL,
    http_status    bigint NOT NULL,
    source_system  text NOT NULL,
    payload_sha256 text NOT NULL,
    PRIMARY KEY (file_url, year, area_code, sector, service, job_role_group, job_role)
);

CREATE INDEX IF NOT EXISTS idx_skills_for_care_estimates_area
    ON skills_for_care_estimates (area_code);
CREATE INDEX IF NOT EXISTS idx_skills_for_care_estimates_role
    ON skills_for_care_estimates (job_role);
