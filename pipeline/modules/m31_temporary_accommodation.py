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
A1's two. v1 read only the top-level totals (households in TA, households
with children, children in TA). BETA-064 adds the bed-and-breakfast "of
which" block into `temporary_accommodation_breakdowns` — a narrow table
(one row per authority/quarter/measure) because the B&B sub-columns are not
stable across the series: the older multi-row-header era splits households
and households-with-children, the flat-header era publishes only the
households total. `_BB_MEASURES` is a closed set; a B&B column matching none
of them is a `temporary_accommodation_breakdown_unknown_column` review item,
never a guessed measure. The block is optional — a quarter with no
recognisable B&B column writes no breakdown rows and is not an error.
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

# The bed-and-breakfast "of which" block (BETA-064). A B&B column is one
# whose concatenated header text names bed-and-breakfast accommodation; the
# newer flat-header era has one such column, the older multi-row era has a
# merged group header followed by "of which" sub-columns whose own text does
# NOT repeat "bed and breakfast" -- so the block is bounded from its first
# B&B-anchored column up to the next snapshot column, and every column in
# that span is classified by its own sub-header.
_BB_BLOCK_RE = re.compile(r"b\s*&\s*b|bed[\s-]*and[\s-]*breakfast", re.IGNORECASE)
_BB_WITH_CHILDREN_RE = re.compile(
    r"with (children|dependent|pregnan)|pregnan", re.IGNORECASE)

# code -> the classifier applied to a column's header signature. Order is the
# claim order: the more specific measure first, so the plain households
# total cannot swallow the with-children column. Each code is claimed at
# most once; a second column that would match an already-claimed code is
# reported as unknown rather than overwriting it.
_BB_MEASURES = (
    ("bb_households_with_children", _BB_WITH_CHILDREN_RE),
    ("bb_households", re.compile(r"household|total", re.IGNORECASE)),
)


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


_BB_SUBHEADER_RE = re.compile(r"^\s*(total|of which|number)\b", re.IGNORECASE)


def locate_ta1_breakdown_columns(
    rows: list[list[str]], anchor: int, snapshot_columns: dict[str, int]
) -> tuple[dict[str, int], list[str]]:
    """Resolve the bed-and-breakfast "of which" columns (BETA-064).

    Returns `(measures, unknown)` — `measures` maps a `_BB_MEASURES` code to
    its column, `unknown` is the header text of every B&B-block column that
    matched no measure (or a measure already claimed). Both may be empty:
    a quarter with no B&B column is not an error, it just writes no
    breakdown rows.

    The block runs from the first column whose header names bed-and-breakfast
    accommodation up to the next snapshot column. A trailing column joins the
    block only when its own header reads as an "of which" sub-header
    (`Total with children`, `Total number of households`) — so a separate
    non-B&B group that happens to sit to the right is not pulled in.
    """
    header_rows = [r for r in rows[:anchor] if sum(1 for c in r if c) >= 2]
    width = max([len(r) for r in header_rows]
                + [len(rows[anchor]) if anchor < len(rows) else 0])

    def signature(column: int) -> str:
        return " ".join(r[column] for r in header_rows
                        if column < len(r) and r[column])

    anchored = [c for c in range(width) if _BB_BLOCK_RE.search(signature(c))]
    if not anchored:
        return {}, []

    snapshot_cols = set(snapshot_columns.values())
    start = min(anchored)
    block = [start]
    for column in range(start + 1, width):
        if column in snapshot_cols:
            break
        sig = signature(column)
        if column in anchored or (sig and _BB_SUBHEADER_RE.match(sig)):
            block.append(column)
        elif sig:
            break

    measures: dict[str, int] = {}
    unknown: list[str] = []
    for column in block:
        sig = signature(column)
        if not sig:
            continue
        for code, pattern in _BB_MEASURES:
            if pattern.search(sig):
                if code in measures:
                    unknown.append(sig)
                else:
                    measures[code] = column
                break
        else:
            unknown.append(sig)
    return measures, unknown


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
    breakdown_written = 0
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

            # BETA-064: the bed-and-breakfast "of which" block. Optional per
            # vintage; a B&B column that matches no known measure is a review
            # item for this quarter, not a guessed row.
            bb_columns, bb_unknown = locate_ta1_breakdown_columns(
                rows, anchor, columns)
            if bb_unknown:
                db.record_review_item(
                    conn, module_name,
                    "temporary_accommodation_breakdown_unknown_column",
                    attachment["url"], json.dumps({
                        "quarter": pub["quarter_label"],
                        "columns": sorted(set(bb_unknown)),
                        "note": "a bed-and-breakfast column in TA1 matched no "
                                "code in _BB_MEASURES; add it there or confirm "
                                "it is genuinely a new measure",
                    }))
            bb_by_code = {e["ons_code"]: e
                          for e in extract_ta1_rows(rows, anchor, bb_columns)}

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

                bb_entry = bb_by_code.get(ons_code)
                for measure, _column in bb_columns.items():
                    raw = (bb_entry or {}).get(measure, "")
                    db.upsert(conn, "temporary_accommodation_breakdowns", {
                        "ons_code": ons_code,
                        "quarter_start": pub["quarter_start"],
                        "quarter_label": pub["quarter_label"],
                        "measure": measure,
                        "unit": "households",
                        "households": to_int(raw),
                        "households_text": raw or None,
                        **provenance,
                    }, natural_key=["ons_code", "quarter_start", "measure"])
                    breakdown_written += 1

            quarters_processed += 1
            if not ctx.dry_run:
                conn.commit()

    log.info("temporary_accommodation.run_complete",
              quarters=quarters_processed, rows=written,
              breakdown_rows=breakdown_written)
