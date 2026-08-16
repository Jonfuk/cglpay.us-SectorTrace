-- Phase 19 (G2): Skills for Care workforce intelligence.
--
-- Adult social care pay and headcount benchmarks, from the ASC-WDS
-- workforce estimates the publisher releases as Excel data downloads on its
-- Data downloads page (five files, updated annually in October). The sector
-- this corpus tracks sits between health and social care, and its workforce
-- market is largely the care workforce — so Skills for Care's pay and
-- turnover figures are the contextual comparators the campaign's claims
-- need.
--
-- `skills_for_care_files` is one row per downloaded workbook: which file,
-- when it was fetched, whether its data sheet parsed and how many estimate
-- rows it yielded. A workbook whose shape this module does not (yet) read is
-- recorded here with parse_status 'unreadable' plus a `parse_failures` row
-- and a review item — never silently skipped, and never read as "Skills for
-- Care published nothing".
--
-- `skills_for_care_estimates` is one row per (workbook, area, sector,
-- service, job role) carrying the comparator columns the claim needs — pay
-- and turnover — as published: `fte_annual_pay`, `hourly_pay`,
-- `turnover_rate` and `vacancy_rate` are the workbook's own figures,
-- parsed but never derived, NULL where the cell could not be read. The
-- other ~300 columns the data sheets carry (demographics, qualifications,
-- nationality) are deliberately not copied into the warehouse: they are not
-- the claim's material, and the workbook itself is archived in full with its
-- provenance, which is where anything not parsed still lives.
--
-- Two caveats the module docstring and SOURCES.md carry: these are
-- *estimates* (modelled from the ASC-WDS collection, rounded), and they are
-- the whole adult social care workforce — a pay figure here is a
-- comparator for the sector's labour market, not an attribution to any
-- provider this pipeline tracks. The F-05 gate applies: the trended
-- workbook is stored as one file, but no change-over-time arithmetic is
-- performed anywhere (that would be the history F-05 declined).

CREATE TABLE IF NOT EXISTS skills_for_care_files (
    file_url         TEXT PRIMARY KEY,
    link_label       TEXT,           -- the publisher's own label for the file
    file_format      TEXT,           -- 'xlsx'
    parse_status     TEXT NOT NULL,  -- 'parsed' | 'unreadable'
    row_count        INTEGER,
    source_url       TEXT NOT NULL,
    retrieved_at     TEXT NOT NULL,
    http_status      INTEGER NOT NULL,
    source_system    TEXT NOT NULL,
    payload_sha256   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skills_for_care_estimates (
    file_url       TEXT NOT NULL,
    year           TEXT,           -- the workbook's own year label, e.g. '2024/25'
    area_code      TEXT,           -- the ONS code the workbook itself carries
    area_level     TEXT,           -- 'National' | 'Region' | 'Local authority'
    region         TEXT,
    area           TEXT,           -- the workbook's own area name
    sector         TEXT,           -- verbatim sector label
    service        TEXT,           -- verbatim service label
    job_role_group TEXT,           -- verbatim job role group label
    job_role       TEXT,           -- verbatim job role label
    fte_annual_pay REAL,           -- NULL where unreadable; never derived
    hourly_pay     REAL,           -- NULL where unreadable; never derived
    turnover_rate  REAL,           -- NULL where unreadable; never derived
    vacancy_rate   REAL,           -- NULL where unreadable; never derived
    source_url     TEXT NOT NULL,
    retrieved_at   TEXT NOT NULL,
    http_status    INTEGER NOT NULL,
    source_system  TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    PRIMARY KEY (file_url, year, area_code, sector, service, job_role_group, job_role)
);

CREATE INDEX IF NOT EXISTS idx_skills_for_care_estimates_area
    ON skills_for_care_estimates (area_code);
CREATE INDEX IF NOT EXISTS idx_skills_for_care_estimates_role
    ON skills_for_care_estimates (job_role);
