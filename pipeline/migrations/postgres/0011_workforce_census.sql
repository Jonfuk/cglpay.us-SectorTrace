-- Module 6: National Drug and Alcohol Treatment and Recovery Services
-- Workforce Census (NHS England / NHS Benchmarking Network).
--
-- TWO HARD LIMITS, both enforced by this schema rather than left to
-- convention:
--
-- 1. NO PROVIDER ATTRIBUTION. The census publishes sector-level aggregates
--    only; there is no provider-level breakdown. There is deliberately no
--    provider_key column here, because attributing a census figure to CGL or
--    any named provider would be inference presented as measurement.
--
-- 2. NOT LIKE-FOR-LIKE ACROSS YEARS. Provider participation varies between
--    census rounds — the 2023 report says in terms that its data "should not
--    be used to infer that the workforce size overall" changed. Rows carry
--    the year they came from and must not be differenced without reading the
--    participation caveat for both years. See docs/CAVEATS.md.
--
-- Every extracted figure keeps the verbatim source line next to it, and
-- nothing is treated as publishable until a human has ticked it off against
-- docs/verification/census_{year}_tables.md.

--
-- PostgreSQL dialect of ../0011_workforce_census.sql. See README.md in this directory for
-- the conversion rules.
--
CREATE TABLE IF NOT EXISTS workforce_census_reports (
    census_year          bigint PRIMARY KEY,
    report_title          text,
    document_url           text NOT NULL,
    archived_path           text,
    page_count               bigint,
    publisher                 text,
    source_url                 text NOT NULL,
    retrieved_at                text NOT NULL,
    http_status                  bigint NOT NULL,
    source_system                 text NOT NULL,
    payload_sha256                 text NOT NULL
);

-- Tidy/long form: one row per (year, metric, workforce segment). A wide
-- table is impossible here because each year's report presents a different
-- set of cuts, and forcing them into fixed columns would silently drop
-- whatever that year happened to publish differently.
CREATE TABLE IF NOT EXISTS workforce_census_metrics (
    census_year            bigint NOT NULL,
    metric                  text NOT NULL,   -- 'wte_total' | 'vacancy_rate' | 'turnover_rate' | ...
    workforce_segment        text NOT NULL,  -- 'delivery' | 'treatment_provider' | 'commissioning' | 'unspecified'
    value                     double precision,
    unit                       text,         -- 'wte' | 'percent'
    source_page                 bigint,
    raw_text                     text NOT NULL, -- verbatim line the value was read from
    -- 0 until a human confirms it against the generated verification
    -- markdown. Exports should filter on this rather than assume.
    verified                      bigint NOT NULL DEFAULT 0,
    source_url                     text NOT NULL,
    retrieved_at                    text NOT NULL,
    http_status                      bigint NOT NULL,
    source_system                     text NOT NULL,
    payload_sha256                     text NOT NULL,
    PRIMARY KEY (census_year, metric, workforce_segment, raw_text)
);

CREATE INDEX IF NOT EXISTS idx_census_metrics_year ON workforce_census_metrics (census_year, metric);

-- Full text of every page an extractor read, kept so a figure can be checked
-- against its page without re-downloading, and so a later parser revision can
-- be re-run over the same text.
CREATE TABLE IF NOT EXISTS workforce_census_page_text (
    census_year      bigint NOT NULL,
    page_number       bigint NOT NULL,
    page_text          text NOT NULL,
    source_url          text NOT NULL,
    retrieved_at         text NOT NULL,
    http_status           bigint NOT NULL,
    source_system          text NOT NULL,
    payload_sha256          text NOT NULL,
    PRIMARY KEY (census_year, page_number)
);
