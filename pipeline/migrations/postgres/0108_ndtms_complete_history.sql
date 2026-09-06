-- The monthly provisional reports are a third evidence layer. Keep them
-- distinct from annual ViewIt vintages and current Power BI cells while
-- exposing one read-only shape for downstream coverage/export tooling.
CREATE OR REPLACE VIEW v_ndtms_complete_history AS
SELECT * FROM v_ndtms_viewit_current_history
UNION ALL
SELECT
    'monthly_provisional'::text AS source_variant,
    'monthly_provisional'::text AS dashboard_key,
    m.cohort,
    m.payload_sha256,
    m.area_name_raw,
    m.ons_code,
    m.time_period_raw AS reporting_period,
    m.section AS metric_raw,
    m.value,
    m.value_text,
    jsonb_build_object(
        'substance_category', m.substance_category,
        'report_month', m.report_month,
        'report_version_id', m.report_version_id,
        'dat_code', m.dat_code,
        'region_code', m.region_code
    ) AS dimensions_json,
    m.source_url,
    m.retrieved_at,
    m.source_system
FROM ndtms_monthly_statistics m;
