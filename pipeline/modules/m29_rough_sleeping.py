"""Module 29 — Rough sleeping snapshot (MHCLG).

An annual, England-wide, local-authority-level comparator for the sector's
own evidence: how many people were estimated to be sleeping rough in each
authority on a single night each autumn since 2010, and MHCLG's own rate per
100,000 population for the same figure. Rough sleeping and substance misuse
are widely and separately documented as overlapping populations, which is
exactly why this belongs beside the sector's own evidence as a side-by-side
comparator — never combined with it. See `docs/CAVEATS.md`: this module
adds no new arithmetic, and none is permitted across it either.

The source page (`tables-on-rough-sleeping`) is evergreen — MHCLG replaces
its attachment each edition rather than publishing one page per year — but
each edition's single ODS file republishes the *whole* 2010-to-current time
series as one column per year, not one file per year. So unlike most of this
pipeline's "discover the current publication" modules (Module 13's GOV.UK
search, for instance), a single fetch of the current page captures the full
history in one pass; there is no per-edition backlog to discover.

Two tables in the workbook are read. `Table_1_Total` is the estimated count.
`Table_5_Rates` is MHCLG's own rate per 100,000 population, calculated from
the corresponding year's ONS population estimate (the workbook's own Note 5)
— this pipeline stores it exactly as published and never derives a rate
itself, the same discipline as every other officially-published rate here
(ONS ASHE, NDTMS). Demographic breakdowns (gender, nationality, age) and the
methodology/consultation tables are not read by this first version; a
`snapshot_year`-and-`ons_code` count and rate is the smallest coherent slice
worth having.

Methodology is not standardised between authorities and the workbook says so
plainly (Note 3): each authority chooses its own approach — a count, an
evidence-based estimate, or an evidence-based estimate with a spotlight
count — and its own date within the October-November window. A comparison
between two authorities' snapshots is a comparison between two different
measurement methods, not just two different places, and the caveat travels
with every figure this module writes.
"""
from __future__ import annotations

import io
import json
import re

import structlog
from odf.opendocument import load as load_ods
from odf.table import Table, TableCell, TableRow
from odf.text import P

from pipeline import db
from pipeline.http import PipelineHTTPClient
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "mhclg_rough_sleeping"
CONTENT_URL = (
    "https://www.gov.uk/api/content/government/statistical-data-sets/"
    "tables-on-rough-sleeping"
)
ODS_MIME = "application/vnd.oasis.opendocument.spreadsheet"

# Distinguishes the annual snapshot from the newer, differently-shaped
# quarterly "Rough Sleeping Data Framework" management-information
# collection published on the same evergreen page — a separate source with
# its own metrics, not read by this module.
SNAPSHOT_ATTACHMENT_RE = re.compile(r"rough sleeping snapshot", re.IGNORECASE)

ONS_CODE_RE = re.compile(r"^E\d{8}$")
YEAR_HEADER_RE = re.compile(r"^(19|20)\d{2}$")

_PLACEHOLDER_TEXT = {"[x]", "[z]", "[n]", "", "-", "–", "—"}


class RoughSleepingParseError(RuntimeError):
    """The expected MHCLG workbook shape could not be found."""


def _cell_text(cell) -> str:
    return "".join(str(p) for p in cell.getElementsByType(P))


def sheet_rows(table) -> list[list[str]]:
    """Every row, with `table:number-columns-repeated` expanded.

    Unlike a simple `getElementsByType(TableCell)` walk, this keeps column
    position meaningful even where the sheet compresses a run of identical
    or empty trailing cells into one element — which this workbook's header
    row does (46 empty cells after 2025, one element). Capped per row so a
    sheet-wide "repeat to the end of the row" convention some ODS writers
    use cannot manufacture a row of unbounded width.
    """
    rows = []
    for row in table.getElementsByType(TableRow):
        values: list[str] = []
        for cell in row.getElementsByType(TableCell):
            repeat = int(cell.getAttribute("numbercolumnsrepeated") or 1)
            text = _cell_text(cell).strip()
            values.extend([text] * min(repeat, 64))
        rows.append(values)
    return rows


def find_header_row(rows: list[list[str]], limit: int = 10) -> int | None:
    for i, row in enumerate(rows[:limit]):
        if row and row[0].strip().lower() == "local authority code":
            return i
    return None


def _to_int(raw: str) -> int | None:
    text = raw.replace(",", "").strip()
    if text in _PLACEHOLDER_TEXT:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _to_float(raw: str) -> float | None:
    text = raw.replace(",", "").strip()
    if text in _PLACEHOLDER_TEXT:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def extract_year_series(rows: list[list[str]]) -> dict[tuple[str, int], str]:
    """(ons_code, year) -> the cell's raw text, for every real local
    authority row (region and England aggregate rows carry `[z]` as their
    authority code and are excluded, the same filter Module 13 uses).
    """
    header_index = find_header_row(rows)
    if header_index is None:
        raise RoughSleepingParseError("no header row with a 'Local Authority Code' column")

    header = rows[header_index]
    year_columns = [(i, int(cell)) for i, cell in enumerate(header)
                     if YEAR_HEADER_RE.match(cell)]
    if not year_columns:
        raise RoughSleepingParseError("no year columns found in the header row")

    out: dict[tuple[str, int], str] = {}
    for row in rows[header_index + 1:]:
        if not row or not row[0]:
            continue
        ons_code = row[0].strip()
        if not ONS_CODE_RE.match(ons_code):
            continue  # region/England aggregate rows, or a blank trailer
        for column, year in year_columns:
            if column < len(row):
                out[(ons_code, year)] = row[column]
    return out


@register_module(
    "m29_rough_sleeping", supports_since=True,
    since_note="filters which snapshot years are written; the fetch itself "
               "always reads the whole published series",
    depends_on=("m00_geography",),
    depends_note="authority names come from the authorities table",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m29_rough_sleeping"
    conn = ctx.conn
    since_year = ctx.since_year()

    known_authorities = {row["ons_code"] for row in conn.execute(
        "SELECT ons_code FROM authorities")}
    unmatched_logged: set[str] = set()

    written = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        content = client.get(CONTENT_URL)
        if not content.ok:
            raise RoughSleepingParseError(
                f"GOV.UK content API failed for {CONTENT_URL} ({content.status_code})")

        attachments = json.loads(content.body).get("details", {}).get("attachments", [])
        snapshot_files = [a for a in attachments
                          if a.get("content_type") == ODS_MIME
                          and (a.get("url") or "").startswith("http")
                          and SNAPSHOT_ATTACHMENT_RE.search(a.get("title") or "")]
        if not snapshot_files:
            db.record_review_item(
                conn, module_name, "rough_sleeping_no_snapshot_attachment",
                CONTENT_URL, json.dumps({
                    "titles_seen": [a.get("title") for a in attachments],
                    "note": "the evergreen page's shape may have changed; "
                            "see SNAPSHOT_ATTACHMENT_RE in m29_rough_sleeping",
                }))
            log.info("rough_sleeping.run_complete", rows=0)
            return

        # Exactly one is expected; if MHCLG ever publishes more than one
        # snapshot-titled attachment at once, read all of them rather than
        # guess which is current — later rows win on the natural key.
        for attachment in ctx.track(snapshot_files, "rough sleeping snapshot files"):
            file_result = client.get(attachment["url"])
            if not file_result.ok:
                db.record_review_item(
                    conn, module_name, "rough_sleeping_file_unavailable",
                    attachment["url"], json.dumps({"status": file_result.status_code}))
                continue

            try:
                doc = load_ods(io.BytesIO(file_result.body))
                tables = {t.getAttribute("name"): t
                          for t in doc.spreadsheet.getElementsByType(Table)}
            except Exception as exc:
                db.record_review_item(
                    conn, module_name, "rough_sleeping_file_unreadable",
                    attachment["url"],
                    json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
                continue

            if "Table_1_Total" not in tables:
                db.record_review_item(
                    conn, module_name, "rough_sleeping_sheet_missing",
                    attachment["url"], json.dumps({
                        "expected": "Table_1_Total",
                        "sheets_found": list(tables.keys()),
                    }))
                continue

            try:
                counts = extract_year_series(sheet_rows(tables["Table_1_Total"]))
            except RoughSleepingParseError as exc:
                db.record_review_item(
                    conn, module_name, "rough_sleeping_sheet_unparsed",
                    attachment["url"], json.dumps({"sheet": "Table_1_Total", "reason": str(exc)}))
                continue

            rates: dict[tuple[str, int], str] = {}
            if "Table_5_Rates" in tables:
                try:
                    rates = extract_year_series(sheet_rows(tables["Table_5_Rates"]))
                except RoughSleepingParseError as exc:
                    db.record_parse_failure(
                        conn, module_name, "rate_per_100k", attachment["url"],
                        f"Table_5_Rates present but unparseable: {exc}")

            provenance = {
                "source_url": file_result.url,
                "retrieved_at": file_result.retrieved_at.isoformat(),
                "http_status": file_result.status_code,
                "source_system": SOURCE_SYSTEM,
                "payload_sha256": file_result.payload_sha256,
            }

            snapshot_rows: list[dict] = []
            for (ons_code, year), count_text in counts.items():
                if since_year and year < since_year:
                    continue
                if ons_code not in known_authorities:
                    if ons_code not in unmatched_logged:
                        db.record_review_item(
                            conn, module_name, "rough_sleeping_unmatched_authority",
                            ons_code, json.dumps({
                                "note": "not in the authorities table — possibly a "
                                        "reorganisation predecessor/successor code "
                                        "this pipeline has not reconciled",
                            }))
                        unmatched_logged.add(ons_code)
                    continue

                rate_text = rates.get((ons_code, year))
                snapshot_rows.append({
                    "ons_code": ons_code,
                    "snapshot_year": year,
                    "count": _to_int(count_text),
                    "count_text": count_text,
                    "rate_per_100k": _to_float(rate_text) if rate_text is not None else None,
                    "rate_text": rate_text,
                    **provenance,
                })
                written += 1

            db.upsert_many(
                conn, "rough_sleeping_snapshot", snapshot_rows,
                natural_key=["ons_code", "snapshot_year"],
            )
            if not ctx.dry_run:
                conn.commit()

    log.info("rough_sleeping.run_complete", rows=written)
