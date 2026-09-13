-- Module 42: Nomis ASHE labour-market context.
--
-- Resident and workplace ASHE headline observations are kept separately from
-- m21_ons_ashe. Nomis geography codes/labels and exact source provenance travel
-- with every row; NULL value means the source did not publish a numeric value.

CREATE TABLE IF NOT EXISTS nomis_labour_market_observations (
    dataset_id                 text NOT NULL, -- ASHER (resident) | ASHE (workplace)
    analysis                   text NOT NULL, -- resident | workplace
    dataset_title              text NOT NULL,
    geography_selector         text NOT NULL, -- Nomis TYPE424 (LA district/unitary, Apr 2023)
    geography_code             text NOT NULL, -- ONS/Nomis geography code
    geography_name             text,
    sex                        text NOT NULL,
    sex_name                   text,
    item                       text NOT NULL,
    item_name                  text,
    pay                        text NOT NULL, -- 6 hourly pay excluding overtime | 9 total hours
    pay_name                  text,
    time                       text NOT NULL,
    value                      double precision,
    value_text                 text,
    observation_status         text,
    observation_confidence     text,
    source_url                 text NOT NULL,
    retrieved_at               text NOT NULL,
    http_status                bigint NOT NULL,
    source_system              text NOT NULL,
    payload_sha256             text NOT NULL,
    PRIMARY KEY (dataset_id, geography_code, sex, item, pay, time)
);

CREATE INDEX IF NOT EXISTS idx_nomis_labour_market_geo_time
    ON nomis_labour_market_observations (geography_code, time);

CREATE INDEX IF NOT EXISTS idx_nomis_labour_market_analysis_pay
    ON nomis_labour_market_observations (analysis, pay, time);
