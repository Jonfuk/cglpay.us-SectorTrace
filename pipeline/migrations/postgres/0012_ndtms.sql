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

--
-- PostgreSQL dialect of ../0012_ndtms.sql. See README.md in this directory for
-- the conversion rules.
--
CREATE TABLE IF NOT EXISTS ndtms_publications (
    publication_slug        text PRIMARY KEY,
    cohort                   text NOT NULL,   -- 'adults' | 'young_people'
    financial_year            text NOT NULL,  -- e.g. '2024-25'
    title                      text,
    document_url                text,
    archived_path                text,
    sheets_total                  bigint,
    sheets_local_authority         bigint,   -- how many were LA-level
    source_url                      text NOT NULL,
    retrieved_at                     text NOT NULL,
    http_status                       bigint NOT NULL,
    source_system                      text NOT NULL,
    payload_sha256                      text NOT NULL
);

-- One row per (publication, table, area, indicator, value type). ons_code is
-- resolved from the published area name against `authorities`; it stays NULL
-- and the name goes to review_queue when it cannot be matched deterministically,
-- rather than being guessed.
CREATE TABLE IF NOT EXISTS ndtms_la_statistics (
    publication_slug      text NOT NULL,
    table_ref              text NOT NULL,   -- source sheet name, e.g. 'Table_9_2'
    area_name_raw           text NOT NULL,
    ons_code                 text,
    age_group                 text,
    time_period                text,
    indicator                   text NOT NULL, -- source column header, normalised
    value                        double precision,
    value_text                    text,       -- verbatim cell, kept when unparseable
    cohort                         text NOT NULL,
    financial_year                  text NOT NULL,
    source_url                       text NOT NULL,
    retrieved_at                      text NOT NULL,
    http_status                        bigint NOT NULL,
    source_system                       text NOT NULL,
    payload_sha256                       text NOT NULL,
    PRIMARY KEY (publication_slug, table_ref, area_name_raw, age_group, time_period, indicator)
);

CREATE INDEX IF NOT EXISTS idx_ndtms_ons ON ndtms_la_statistics (ons_code);
CREATE INDEX IF NOT EXISTS idx_ndtms_indicator ON ndtms_la_statistics (indicator);

-- Records every sheet seen and whether it was LA-level, so the (large) share
-- of this publication that is national-only is visible rather than looking
-- like a extraction failure.
CREATE TABLE IF NOT EXISTS ndtms_sheet_inventory (
    publication_slug   text NOT NULL,
    table_ref           text NOT NULL,
    sheet_title          text,
    is_local_authority    bigint NOT NULL DEFAULT 0,
    row_count              bigint,
    PRIMARY KEY (publication_slug, table_ref)
);
