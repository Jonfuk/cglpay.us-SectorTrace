-- Archive exports contain literal text markers such as NULL.  They remain in
-- value_text; only strings that are unambiguously numeric may become value.
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
        WHEN replace(replace(m.value_text, ',', ''), '%', '')
             ~ '^-?[0-9]+(\\.[0-9]+)?$'
        THEN replace(replace(m.value_text, ',', ''), '%', '')::double precision
        ELSE NULL
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
