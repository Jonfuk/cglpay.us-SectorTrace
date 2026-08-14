-- Module 12: OHID Fingertips local-authority indicators.
--
-- Exists to fill the gap Module 7 exposed: the GOV.UK NDTMS data tables
-- publish numbers in treatment, waiting times and successful completions
-- nationally, with only one local-authority sheet. Fingertips carries the
-- same measures per authority, keyed by ONS area code.
--
-- SAME SEPARATION RULE AS MODULE 7. This is service-demand and outcome
-- context, not workforce data, and it is never merged into the workforce
-- census tables.
--
-- NO DERIVED UNMET NEED. Prevalence (indicator 91117) and numbers in
-- treatment (92454, 91182) are stored exactly as published. Unmet need is
-- conventionally the gap between them, but the two use different estimation
-- methods, populations and confidence intervals, so this pipeline does not
-- subtract one from the other — that is a downstream decision to document.

--
-- PostgreSQL dialect of ../0013_fingertips.sql. See README.md in this directory for
-- the conversion rules.
--
CREATE TABLE IF NOT EXISTS fingertips_indicators (
    indicator_id        bigint PRIMARY KEY,
    indicator_name       text NOT NULL,
    slug                  text,
    topic                  text,   -- numbers_in_treatment | successful_completions | waiting_times | prevalence | ...
    substance               text,  -- drug | alcohol | substance_misuse
    definition               text,
    unit                      text,
    source_url                 text NOT NULL,
    retrieved_at                text NOT NULL,
    http_status                  bigint NOT NULL,
    source_system                 text NOT NULL,
    payload_sha256                 text NOT NULL
);

-- One row per published data point. area_code is Fingertips' ONS code, so
-- this joins to `authorities` directly with no name matching — unlike the
-- NDTMS spreadsheets, which publish area names only.
--
-- ons_code is set only when the code actually resolves against `authorities`;
-- national (E92…) and regional (E12…) rows are retained with ons_code NULL
-- because they are the published comparators for the LA figures, and dropping
-- them would leave the LA values without the context they are read against.
CREATE TABLE IF NOT EXISTS fingertips_la_values (
    indicator_id          bigint NOT NULL,
    area_code              text NOT NULL,
    area_type_id            bigint NOT NULL,
    sex                      text NOT NULL DEFAULT '',
    age                       text NOT NULL DEFAULT '',
    category_type              text NOT NULL DEFAULT '',
    category                    text NOT NULL DEFAULT '',
    time_period                  text NOT NULL,
    area_name                     text,
    ons_code                       text,   -- NULL for England/region rows
    area_level                      text,  -- 'local_authority' | 'region' | 'england' | 'other'
    value                            double precision,
    lower_ci_95                       double precision,
    upper_ci_95                        double precision,
    count_numerator                     double precision,
    denominator                          double precision,
    value_note                            text,
    time_period_sortable                   text,
    source_url                              text NOT NULL,
    retrieved_at                             text NOT NULL,
    http_status                               bigint NOT NULL,
    source_system                              text NOT NULL,
    payload_sha256                              text NOT NULL,
    PRIMARY KEY (indicator_id, area_code, area_type_id, sex, age,
                  category_type, category, time_period),
    FOREIGN KEY (indicator_id) REFERENCES fingertips_indicators (indicator_id)
);

CREATE INDEX IF NOT EXISTS idx_fingertips_ons ON fingertips_la_values (ons_code);
CREATE INDEX IF NOT EXISTS idx_fingertips_indicator_period
    ON fingertips_la_values (indicator_id, time_period);

-- Convenience view: local-authority rows only, joined to the authority name,
-- with the indicator's topic so a consumer can pick a measure without
-- memorising indicator IDs. Deliberately no cross-indicator arithmetic.
DROP VIEW IF EXISTS v_fingertips_la_latest;
CREATE VIEW v_fingertips_la_latest AS
SELECT
    v.indicator_id,
    i.slug,
    i.topic,
    i.substance,
    i.indicator_name,
    v.ons_code,
    a.name          AS authority_name,
    v.time_period,
    v.value,
    v.lower_ci_95,
    v.upper_ci_95,
    v.count_numerator,
    v.denominator,
    v.value_note
FROM fingertips_la_values v
JOIN fingertips_indicators i ON i.indicator_id = v.indicator_id
JOIN authorities a          ON a.ons_code = v.ons_code
WHERE v.area_level = 'local_authority'
  AND v.ons_code IS NOT NULL;
