-- Public NDTMS Power BI querydata captures.
--
-- The exact response is archived and the observations retain the response
-- hash. These tables deliberately do not merge with the annual ODS or legacy
-- monthly tables: Power BI report versions and query envelopes can change
-- independently of those releases.
CREATE TABLE IF NOT EXISTS ndtms_powerbi_payloads (
    dashboard_key           text NOT NULL,
    payload_sha256          text NOT NULL,
    cohort                  text NOT NULL,
    dashboard_url           text NOT NULL,
    response_url            text NOT NULL,
    request_body_sha256     text NOT NULL,
    sequence                bigint NOT NULL,
    http_status             bigint NOT NULL,
    content_type            text,
    archived_path           text NOT NULL,
    source_url              text NOT NULL,
    retrieved_at            text NOT NULL,
    source_system           text NOT NULL,
    PRIMARY KEY (dashboard_key, payload_sha256)
);

CREATE INDEX IF NOT EXISTS idx_ndtms_powerbi_dashboard
    ON ndtms_powerbi_payloads (dashboard_key, cohort);

CREATE TABLE IF NOT EXISTS ndtms_powerbi_observations (
    dashboard_key           text NOT NULL,
    payload_sha256          text NOT NULL,
    row_index               bigint NOT NULL,
    cell_path               text NOT NULL,
    column_index            bigint NOT NULL,
    metric_raw              text NOT NULL,
    value                   double precision,
    value_text              text NOT NULL,
    dimensions_json         text NOT NULL,
    area_name_raw           text,
    ons_code                text,
    time_period_raw         text,
    source_url              text NOT NULL,
    retrieved_at            text NOT NULL,
    http_status              bigint NOT NULL,
    source_system           text NOT NULL,
    PRIMARY KEY (dashboard_key, payload_sha256, row_index)
);

CREATE INDEX IF NOT EXISTS idx_ndtms_powerbi_observations_ons
    ON ndtms_powerbi_observations (ons_code);
CREATE INDEX IF NOT EXISTS idx_ndtms_powerbi_observations_metric
    ON ndtms_powerbi_observations (metric_raw);
