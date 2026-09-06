"""Streaming export for the current Power BI plus historical ViewIt layers."""
from __future__ import annotations

from pathlib import Path

import structlog

from pipeline.exports import assert_no_restricted_tables, guard_columns
from pipeline.exports.provenance import write_export

log = structlog.get_logger()

TABLES = [
    "ndtms_powerbi_observations", "ndtms_viewit_archive_rows",
    "ndtms_monthly_statistics",
]
COLUMNS = [
    "source_variant", "dashboard_key", "cohort", "payload_sha256",
    "area_name_raw", "ons_code", "reporting_period", "metric_raw", "value",
    "value_text", "dimensions_json", "source_url", "retrieved_at", "source_system",
]


def export_all(conn, output_dir: Path) -> list[Path]:
    """Write all three NDTMS evidence layers without materialising rows in Python."""
    assert_no_restricted_tables(conn, TABLES)
    guard_columns("v_ndtms_viewit_current_history", COLUMNS)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "ndtms_current_history.csv"
    row_count = int(conn.execute(
        "SELECT count(*) AS n FROM v_ndtms_complete_history"
    ).fetchone()["n"])

    def write_csv(target: Path) -> None:
        query = """
            COPY (
                SELECT source_variant, dashboard_key, cohort, payload_sha256,
                       area_name_raw, ons_code, reporting_period, metric_raw,
                       value, value_text, dimensions_json, source_url,
                       retrieved_at, source_system
                FROM v_ndtms_complete_history
            ) TO STDOUT WITH (FORMAT CSV, HEADER TRUE)
        """
        with target.open("wb") as handle:
            with conn.raw.cursor() as cursor:
                with cursor.copy(query) as copy:
                    for chunk in copy:
                        handle.write(chunk)

    write_export(
        path=path,
        payload_writer=write_csv,
        conn=conn,
        tables=TABLES,
        export_type="ndtms_current_history_csv",
        row_count=row_count,
        caveats=[
            "Power BI, ViewIt archive, and monthly provisional records remain separate evidence layers.",
            "Suppression markers are preserved as text; NULL geography means no deterministic ONS match.",
            "This export does not imply that indicators or periods are comparable across layers.",
        ],
        extra={"view": "v_ndtms_complete_history", "columns": COLUMNS},
    )
    log.info("ndtms.export_written", rows=row_count, path=str(path))
    return [path]
