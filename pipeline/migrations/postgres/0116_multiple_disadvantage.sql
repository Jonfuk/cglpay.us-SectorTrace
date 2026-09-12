-- Module 36: Multiple Disadvantage Detailed Local Authority Data.
--
-- One row per (authority, quarter): MHCLG's own published percentage of
-- duties owed where homelessness was prevented or relieved for households
-- experiencing multiple disadvantage, plus the qualifying total and its
-- five-category breakdown (domestic abuse, mental health, substance
-- dependency, homelessness/rough sleeping, criminal justice) at each of
-- three duty stages: assessed, prevention-secured, relief-secured.
--
-- The five category columns within one stage are NOT mutually exclusive
-- and sum to several times the stage's own qualifying total -- see
-- docs/CAVEATS.md's Module 36 entry. Every numeric column has a paired
-- `_text` column holding the cell verbatim, because MHCLG's own [x]/[z]
-- placeholders are common and neither means zero.
--
-- This is housing-assessment administrative data (H-CLIC), not clinical or
-- treatment data -- comparator layer only, same as Modules 29-31, never
-- combined with this pipeline's own NDTMS/Fingertips substance-misuse
-- figures despite one column reading "substance dependency".

CREATE TABLE IF NOT EXISTS multiple_disadvantage_snapshot (
    ons_code        text NOT NULL,
    quarter_start   text NOT NULL,  -- 'YYYY-MM-01'
    quarter_label   text NOT NULL,  -- e.g. 'January to March 2026'

    -- Table 1 (Multiple_Disadvantage_values): MHCLG's own published
    -- metric, never recomputed here -- it can legitimately exceed 100%.
    md_pct                                              double precision,
    md_pct_text                                         text,

    -- Table 2 (A_Multiple_Disadvantage): assessed as owed a duty.
    assessed_md_total                                   bigint,
    assessed_md_total_text                              text,
    assessed_domestic_abuse_total                       bigint,
    assessed_domestic_abuse_total_text                  text,
    assessed_mental_health_total                        bigint,
    assessed_mental_health_total_text                   text,
    assessed_substance_dependency_total                 bigint,
    assessed_substance_dependency_total_text            text,
    assessed_homelessness_rough_sleeping_total           bigint,
    assessed_homelessness_rough_sleeping_total_text      text,
    assessed_criminal_justice_total                     bigint,
    assessed_criminal_justice_total_text                text,

    -- Table 3 (P_Multiple_Disadvantage): accommodation secured 6+ months
    -- after a prevention duty ended.
    prevention_secured_md_total                         bigint,
    prevention_secured_md_total_text                    text,
    prevention_secured_domestic_abuse_total              bigint,
    prevention_secured_domestic_abuse_total_text         text,
    prevention_secured_mental_health_total               bigint,
    prevention_secured_mental_health_total_text          text,
    prevention_secured_substance_dependency_total        bigint,
    prevention_secured_substance_dependency_total_text   text,
    prevention_secured_homelessness_rough_sleeping_total          bigint,
    prevention_secured_homelessness_rough_sleeping_total_text     text,
    prevention_secured_criminal_justice_total            bigint,
    prevention_secured_criminal_justice_total_text       text,

    -- Table 4 (R_Multiple_Disadvantage): accommodation secured 6+ months
    -- after a relief duty ended.
    relief_secured_md_total                             bigint,
    relief_secured_md_total_text                        text,
    relief_secured_domestic_abuse_total                  bigint,
    relief_secured_domestic_abuse_total_text             text,
    relief_secured_mental_health_total                   bigint,
    relief_secured_mental_health_total_text              text,
    relief_secured_substance_dependency_total            bigint,
    relief_secured_substance_dependency_total_text       text,
    relief_secured_homelessness_rough_sleeping_total              bigint,
    relief_secured_homelessness_rough_sleeping_total_text         text,
    relief_secured_criminal_justice_total                bigint,
    relief_secured_criminal_justice_total_text           text,

    source_url      text NOT NULL,
    retrieved_at    text NOT NULL,
    http_status     bigint NOT NULL,
    source_system   text NOT NULL,
    payload_sha256  text NOT NULL,
    PRIMARY KEY (ons_code, quarter_start)
);

CREATE INDEX IF NOT EXISTS idx_multiple_disadvantage_quarter
    ON multiple_disadvantage_snapshot (quarter_start);
