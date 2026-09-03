"""Google Sheets export — ten tabs, defined in exports/schema.py.

Always writes CSV to exports/output/sheets/ so the export is reproducible and
diffable without credentials. If GOOGLE_SERVICE_ACCOUNT_JSON and
GOOGLE_SHEETS_SPREADSHEET_ID are configured and gspread is installed, the same
tabs are pushed to the spreadsheet.

Every tab is guarded before it is written: a restricted_ table or a
personal-data column in a tab's output raises rather than exporting.
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import structlog

from pipeline.exports import assert_no_restricted_tables, guard_columns
from pipeline.exports.provenance import write_export
from pipeline.exports.schema import TABS, TabSpec

log = structlog.get_logger()

# Tables each tab reads from, for the provenance file.
TAB_TABLES: dict[str, list[str]] = {
    "01_Authorities": ["authorities", "authority_successors"],
    "02_Public_Health_Grant": ["public_health_grants"],
    "03_Contracts": ["contracts"],
    "04_Providers": ["providers", "companies", "company_previous_names",
                      "restricted_company_officers"],
    "05_Charity_Finance": ["charity_financials", "charity_accounts_extracts"],
    "06_CQC_Locations": ["cqc_locations"],
    "07_Tribunal_Cases": ["tribunal_cases"],
    "08_PFD_Reports": ["pfd_reports", "pfd_concern_terms", "pfd_provider_mentions"],
    "09_Workforce_Census": ["workforce_census_metrics"],
    "10_Sector_Universe": ["sector_universe"],
}


def run_tab_query(conn: sqlite3.Connection, tab: TabSpec) -> tuple[list[str], list[tuple]]:
    cursor = conn.execute(tab.sql)
    columns = [d[0] for d in cursor.description]
    guard_columns(tab.name, columns)
    return columns, [tuple(row[column] for column in columns) for row in cursor.fetchall()]


def _write_csv(path: Path, columns: list[str], rows: list[tuple], tab: TabSpec) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        # Caveats travel with the data, not in a separate document nobody opens.
        for caveat in tab.caveats:
            writer.writerow([f"# CAVEAT: {caveat}"])
        if tab.caveats:
            writer.writerow([])
        writer.writerow(columns)
        writer.writerows(rows)


def export_sheets(conn: sqlite3.Connection, output_dir: Path,
                   push_to_google: bool = False, settings=None) -> list[Path]:
    """Write every tab as CSV (plus provenance). Returns the CSV paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for tab in TABS:
        tables = TAB_TABLES.get(tab.name, [])
        # A restricted table must never even be listed as a contributor.
        assert_no_restricted_tables(conn, [t for t in tables if not t.startswith("restricted_")])

        columns, rows = run_tab_query(conn, tab)
        path = output_dir / f"{tab.name}.csv"
        write_export(
            path=path,
            payload_writer=lambda p, c=columns, r=rows, t=tab: _write_csv(p, c, r, t),
            conn=conn,
            tables=tables,
            export_type="google_sheets_tab_csv",
            row_count=len(rows),
            caveats=tab.caveats,
            extra={"tab": tab.name, "description": tab.description, "columns": columns},
        )
        written.append(path)
        log.info("sheets.tab_written", tab=tab.name, rows=len(rows), path=str(path))

    if push_to_google:
        _push_to_google(conn, settings)
    return written


def _push_to_google(conn: sqlite3.Connection, settings) -> None:
    """Push the same tabs to the configured spreadsheet. Optional: the CSVs
    are the canonical output and are produced with or without credentials.
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        log.info("sheets.google_push_skipped",
                  reason="gspread/google-auth not installed (install the 'sheets' extra)")
        return

    spreadsheet_id = settings.google_sheets_spreadsheet_id
    if not spreadsheet_id:
        log.info("sheets.google_push_skipped", reason="GOOGLE_SHEETS_SPREADSHEET_ID not set")
        return

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    if settings.google_service_account_json_b64:
        import base64
        import json

        try:
            raw = base64.b64decode(settings.google_service_account_json_b64, validate=True)
            service_account_info = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "GOOGLE_SERVICE_ACCOUNT_JSON_B64 is not valid base64-encoded "
                "service-account JSON.") from exc
        credentials = Credentials.from_service_account_info(
            service_account_info, scopes=scopes)
    else:
        credential_path = settings.require_google_service_account()
        credentials = Credentials.from_service_account_file(
            str(credential_path), scopes=scopes)
    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(spreadsheet_id)

    for tab in TABS:
        columns, rows = run_tab_query(conn, tab)
        values = [[f"# CAVEAT: {c}"] for c in tab.caveats]
        if tab.caveats:
            values.append([])
        values.append(columns)
        values.extend([["" if v is None else v for v in row] for row in rows])

        try:
            worksheet = spreadsheet.worksheet(tab.name)
            worksheet.clear()
        except Exception:
            worksheet = spreadsheet.add_worksheet(
                title=tab.name, rows=max(len(values) + 10, 100), cols=max(len(columns) + 2, 10))
        worksheet.update(values, "A1")
        log.info("sheets.google_tab_pushed", tab=tab.name, rows=len(rows))
