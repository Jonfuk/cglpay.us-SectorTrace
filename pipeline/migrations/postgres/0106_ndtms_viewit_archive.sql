-- Historical ViewIt export rows.  This is a separate evidence layer from the
-- current Power BI querydata observations: the archive is a wide CSV with its
-- own field names, rounding rules and report vintage.
CREATE TABLE IF NOT EXISTS ndtms_viewit_archive_rows (
    row_key             text PRIMARY KEY,
    cohort              text NOT NULL,
    reporting_period    text NOT NULL,
    area_name_raw       text NOT NULL,
    ons_code            text,
    drug_group          text NOT NULL,
    gender              text NOT NULL,
    age_group           text NOT NULL,
    metrics_json        jsonb NOT NULL,
    source_url          text NOT NULL,
    retrieved_at        text NOT NULL,
    http_status         bigint NOT NULL,
    source_system       text NOT NULL,
    payload_sha256      text NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ndtms_viewit_archive_ons
    ON ndtms_viewit_archive_rows (ons_code);
CREATE INDEX IF NOT EXISTS idx_ndtms_viewit_archive_period
    ON ndtms_viewit_archive_rows (reporting_period);

-- The union is deliberately metric-level, but archive measures stay inside
-- JSON until queried.  That preserves every source field without silently
-- inventing a cross-vintage indicator mapping.
CREATE OR REPLACE VIEW v_ndtms_viewit_current_history AS
SELECT
    'current_powerbi'::text AS source_variant,
    o.dashboard_key,
    CASE
        WHEN o.dashboard_key ILIKE '%young%' THEN 'young_people'
        ELSE 'adults'
    END AS cohort,
    o.payload_sha256,
    o.area_name_raw,
    o.ons_code,
    o.time_period_raw AS reporting_period,
    o.metric_raw,
    o.value,
    o.value_text,
    o.dimensions_json::jsonb AS dimensions_json,
    o.source_url,
    o.retrieved_at,
    o.source_system
FROM ndtms_powerbi_observations o
UNION ALL
SELECT
    'archive_viewit'::text AS source_variant,
    'viewit_archive'::text AS dashboard_key,
    a.cohort,
    a.payload_sha256,
    a.area_name_raw,
    a.ons_code,
    a.reporting_period,
    m.metric_raw,
    CASE
        WHEN m.value_text IN ('', '-', '–', '—', '*', 'c', 'z', 'x', ':')
        THEN NULL
        ELSE replace(m.value_text, ',', '')::double precision
    END AS value,
    m.value_text,
    jsonb_build_object(
        'drug_group', a.drug_group,
        'gender', a.gender,
        'age_group', a.age_group,
        'archive_row_key', a.row_key
    ) AS dimensions_json,
    a.source_url,
    a.retrieved_at,
    a.source_system
FROM ndtms_viewit_archive_rows a
CROSS JOIN LATERAL jsonb_each_text(a.metrics_json) AS m(metric_raw, value_text);
