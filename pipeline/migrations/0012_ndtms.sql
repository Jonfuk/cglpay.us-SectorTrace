-- Module 7: NDTMS published treatment statistics (OHID).
--
-- SEPARATE EVIDENCE LAYER. This is service-demand context — how many people
-- are in treatment, waiting times, treatment-related deaths — and it is NOT
-- workforce data. It deliberately lives in its own tables and is never
-- merged into the workforce census tables, because the two measure different
-- populations by different methods. Dividing one by the other (caseload per
-- worker, say) would combine sources the pipeline is not entitled to combine;
-- that is a downstream decision for whoever documents it.
--
-- Stored tidy/long because the published indicator set differs by year and
-- by cohort (adults vs young people), so any fixed wide schema would drop
-- whatever a given year happened to publish differently.

CREATE TABLE IF NOT EXISTS ndtms_publications (
    publication_slug        TEXT PRIMARY KEY,
    cohort                   TEXT NOT NULL,   -- 'adults' | 'young_people'
    financial_year            TEXT NOT NULL,  -- e.g. '2024-25'
    title                      TEXT,
    document_url                TEXT,
    archived_path                TEXT,
    sheets_total                  INTEGER,
    sheets_local_authority         INTEGER,   -- how many were LA-level
    source_url                      TEXT NOT NULL,
    retrieved_at                     TEXT NOT NULL,
    http_status                       INTEGER NOT NULL,
    source_system                      TEXT NOT NULL,
    payload_sha256                      TEXT NOT NULL
);

-- One row per (publication, table, area, indicator, value type). ons_code is
-- resolved from the published area name against `authorities`; it stays NULL
-- and the name goes to review_queue when it cannot be matched deterministically,
-- rather than being guessed.
CREATE TABLE IF NOT EXISTS ndtms_la_statistics (
    publication_slug      TEXT NOT NULL,
    table_ref              TEXT NOT NULL,   -- source sheet name, e.g. 'Table_9_2'
    area_name_raw           TEXT NOT NULL,
    ons_code                 TEXT,
    age_group                 TEXT,
    time_period                TEXT,
    indicator                   TEXT NOT NULL, -- source column header, normalised
    value                        REAL,
    value_text                    TEXT,       -- verbatim cell, kept when unparseable
    cohort                         TEXT NOT NULL,
    financial_year                  TEXT NOT NULL,
    source_url                       TEXT NOT NULL,
    retrieved_at                      TEXT NOT NULL,
    http_status                        INTEGER NOT NULL,
    source_system                       TEXT NOT NULL,
    payload_sha256                       TEXT NOT NULL,
    PRIMARY KEY (publication_slug, table_ref, area_name_raw, age_group, time_period, indicator)
);

CREATE INDEX IF NOT EXISTS idx_ndtms_ons ON ndtms_la_statistics (ons_code);
CREATE INDEX IF NOT EXISTS idx_ndtms_indicator ON ndtms_la_statistics (indicator);

-- Records every sheet seen and whether it was LA-level, so the (large) share
-- of this publication that is national-only is visible rather than looking
-- like a extraction failure.
CREATE TABLE IF NOT EXISTS ndtms_sheet_inventory (
    publication_slug   TEXT NOT NULL,
    table_ref           TEXT NOT NULL,
    sheet_title          TEXT,
    is_local_authority    INTEGER NOT NULL DEFAULT 0,
    row_count              INTEGER,
    PRIMARY KEY (publication_slug, table_ref)
);
