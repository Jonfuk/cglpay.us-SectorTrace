"""Module 31 — Temporary accommodation (H-CLIC), Table TA1.

BETA-015's own flagged follow-up: the same evergreen H-CLIC quarterly
workbook Module 30 reads Table A1 from also carries Table TA1 — households
placed in temporary accommodation by a council, as at the last day of the
quarter. Same comparator role as Modules 29/30 (see `docs/CAVEATS.md`):
never combined with the sector's own evidence, side by side only.

This module deliberately shares its discovery and file-reading with
Module 30 rather than duplicating it: `discover_publications`,
`read_workbook_sheet`, `sheet_rows` and `find_anchor_row` are imported
directly from `m30_statutory_homelessness`. Both modules read the same
evergreen page, the same per-quarter attachment list, and the same
revision-preference rule — this is one source shared by two modules, not
two similar-looking sources that happen to both be spreadsheets. That is a
different situation from m13/m29's own `sheet_rows` copies, which are
genuinely independent (different sources, coincidentally similar code), and
is why this one is imported rather than copied — see Module 30's own
docstring on `read_workbook_sheet`.

TA1's layout is simpler than A1's — one level of "of which" nesting (a
household total, then a breakdown by bed-and-breakfast use) rather than
A1's two. **v1 reads only the top-level totals** (households in TA,
households with children, children in TA) and deliberately drops the B&B
breakdown — the same smallest-coherent-slice discipline already applied to
Module 30 (which drops the Section 21 subset) and Module 29 (which drops
demographic breakdowns). The B&B figures are a plausible follow-up, not
built here.
"""
from __future__ import annotations

import json
import re

import structlog

from pipeline import db
from pipeline.http import PipelineHTTPClient
from pipeline.modules.m30_statutory_homelessness import (
    ONS_CODE_RE,
    SUPPORTED_MIMES,
    StatutoryHomelessnessParseError,
    discover_publications,
    find_anchor_row,
    read_workbook_sheet,
    to_float,
    to_int,
)
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "mhclg_temporary_accommodation"
TA1_SHEET = "TA1"

# Same ordering discipline as m30's locate_a1_columns: claim the more
# specific fields first so a total's own "of which" prefix (repeated on
# every sub-column in the newer flat-header shape) cannot steal its claim.
# No trailing \b after "ta": the real source appends footnote digits
# directly with no space ("...in TA1,2,3,4"), and \b does not fire between
# two word characters (a letter and a digit both count) -- an earlier
# version of this regex silently failed to match that column and let the
# per-1,000 rate column (whose text also contains "households in ta", just
# further right) win the claim instead. Caught by checking the resolved
# value against the real published England total, not by the regex looking
# wrong on its own.
_CHILDREN_RE = re.compile(r"children in ta", re.IGNORECASE)
_WITH_CHILDREN_RE = re.compile(r"households? in ta with children", re.IGNORECASE)
_TOTAL_TA_RE = re.compile(r"households? in ta", re.IGNORECASE)
_IN_AREA_RE = re.compile(r"in area", re.IGNORECASE)

_REQUIRED_FIELDS = {
    "total_households_ta", "households_ta_with_children", "children_in_ta",
}


def locate_ta1_columns(rows: list[list[str]], anchor: int) -> dict[str, int]:
    """Resolve Table TA1's field columns by keyword. See
    `m30_statutory_homelessness.locate_a1_columns` for the approach this
    mirrors (verified separately against TA1's own real header text in
    both source-file eras, which is a different shape from A1's)."""
    header_rows = [r for r in rows[:anchor] if sum(1 for c in r if c) >= 2]
    width = max([len(r) for r in header_rows] + [len(rows[anchor]) if anchor < len(rows) else 0])

    def signature(column: int) -> str:
        return " ".join(r[column] for r in header_rows
                         if column < len(r) and r[column])

    claimed: dict[str, int] = {}

    def claim(field: str, pattern: re.Pattern) -> None:
        if field in claimed:
            return
        taken = set(claimed.values())
        for column in range(width):
            if column in taken:
                continue
            if pattern.search(signature(column)):
                claimed[field] = column
                return

    claim("children_in_ta", _CHILDREN_RE)
    claim("households_ta_with_children", _WITH_CHILDREN_RE)
    claim("total_households_ta", _TOTAL_TA_RE)
    claim("households_in_area_thousands", _IN_AREA_RE)

    missing = _REQUIRED_FIELDS - claimed.keys()
    if missing:
        raise StatutoryHomelessnessParseError(
            f"could not locate required TA1 columns: {sorted(missing)}")
    return claimed


def extract_ta1_rows(rows: list[list[str]], anchor: int,
                      columns: dict[str, int]) -> list[dict[str, str]]:
    """One dict per real local-authority row. Same region/nation exclusion
    as Module 30's `extract_a1_rows` — this source's aggregate rows carry
    genuine ONS codes, not a placeholder, so `ONS_CODE_RE` (imported from
    Module 30, local-authority prefixes only) does the filtering."""
    out: list[dict[str, str]] = []
    for row in rows[anchor:]:
        if not row:
            continue
        code = row[0].strip()
        if not ONS_CODE_RE.match(code):
            continue
        entry = {"ons_code": code}
        for field, column in columns.items():
            entry[field] = row[column] if column < len(row) else ""
        out.append(entry)
    return out


@register_module(
    "m31_temporary_accommodation", supports_since=True,
    since_note="filters which quarters are written by the quarter's calendar "
               "year; the fetch itself always reads the whole attachment list",
    depends_on=("m00_geography",),
    depends_note="authority names come from the authorities table",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m31_temporary_accommodation"
    conn = ctx.conn
    since_year = ctx.since_year()

    known_authorities = {row[0] for row in conn.execute(
        "SELECT ons_code FROM authorities")}
    unmatched_logged: set[str] = set()

    written = 0
    quarters_processed = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        publications = discover_publications(client)
        if not publications:
            raise StatutoryHomelessnessParseError(
                "No quarterly local-authority-level H-CLIC files found — the "
                "GOV.UK title pattern may have changed. Check TITLE_RE in "
                "m30_statutory_homelessness (shared with this module).")
        log.info("temporary_accommodation.publications_discovered", count=len(publications))

        if ctx.limit:
            publications = publications[-ctx.limit:]

        for pub in ctx.track(publications, "temporary accommodation quarters"):
            if since_year and pub["year"] < since_year:
                continue

            attachment = pub["attachment"]
            content_type = attachment.get("content_type")
            if content_type not in SUPPORTED_MIMES:
                db.record_review_item(
                    conn, module_name, "temporary_accommodation_unsupported_format",
                    attachment.get("url", ""), json.dumps({
                        "quarter": pub["quarter_label"],
                        "content_type": content_type,
                        "note": "only ODS and XLSX are read; pre-2017 .xls "
                                "quarters are a documented gap, see docs/CAVEATS.md",
                    }))
                continue

            file_result = client.get(attachment["url"])
            if not file_result.ok:
                db.record_review_item(
                    conn, module_name, "temporary_accommodation_file_unavailable",
                    attachment["url"], json.dumps({"status": file_result.status_code}))
                continue

            try:
                rows = read_workbook_sheet(file_result.body, content_type, TA1_SHEET)
            except Exception as exc:
                db.record_review_item(
                    conn, module_name, "temporary_accommodation_file_unreadable",
                    attachment["url"], json.dumps({
                        "quarter": pub["quarter_label"],
                        "error": f"{type(exc).__name__}: {exc}"}))
                continue

            anchor = find_anchor_row(rows)
            if anchor is None:
                db.record_review_item(
                    conn, module_name, "temporary_accommodation_no_anchor_row",
                    attachment["url"], json.dumps({"quarter": pub["quarter_label"]}))
                continue

            try:
                columns = locate_ta1_columns(rows, anchor)
            except StatutoryHomelessnessParseError as exc:
                db.record_review_item(
                    conn, module_name, "temporary_accommodation_columns_unresolved",
                    attachment["url"], json.dumps({
                        "quarter": pub["quarter_label"], "reason": str(exc)}))
                continue

            provenance = {
                "source_url": file_result.url,
                "retrieved_at": file_result.retrieved_at.isoformat(),
                "http_status": file_result.status_code,
                "source_system": SOURCE_SYSTEM,
                "payload_sha256": file_result.payload_sha256,
            }

            for entry in extract_ta1_rows(rows, anchor, columns):
                ons_code = entry["ons_code"]
                if ons_code not in known_authorities:
                    if ons_code not in unmatched_logged:
                        db.record_review_item(
                            conn, module_name, "temporary_accommodation_unmatched_authority",
                            ons_code, json.dumps({
                                "note": "not in the authorities table — possibly a "
                                        "reorganisation predecessor/successor code "
                                        "this pipeline has not reconciled",
                            }))
                        unmatched_logged.add(ons_code)
                    continue

                record = {
                    "ons_code": ons_code,
                    "quarter_start": pub["quarter_start"],
                    "quarter_label": pub["quarter_label"],
                    **provenance,
                }
                for field in ("total_households_ta", "households_ta_with_children",
                              "children_in_ta"):
                    raw = entry.get(field, "")
                    record[field] = to_int(raw)
                    record[f"{field}_text"] = raw or None
                raw_area = entry.get("households_in_area_thousands", "")
                record["households_in_area_thousands"] = to_float(raw_area)
                record["households_in_area_thousands_text"] = raw_area or None

                db.upsert(conn, "temporary_accommodation_snapshot", record,
                          natural_key=["ons_code", "quarter_start"])
                written += 1

            quarters_processed += 1
            if not ctx.dry_run:
                conn.commit()

    log.info("temporary_accommodation.run_complete",
              quarters=quarters_processed, rows=written)
