"""Module 30 — Statutory homelessness (H-CLIC), Table A1.

BETA-014's own flagged follow-up: MHCLG's other local-authority-level
homelessness collection, alongside Module 29's rough sleeping snapshot.
Where Module 29 is an annual single-night estimate, this is the quarterly
statutory count — every household a council formally assessed under the
Housing Act's homelessness duties, and what it decided. Same comparator
role as Module 29 (see `docs/CAVEATS.md`): never combined with the sector's
own evidence, side by side only.

The source page (`live-tables-on-homelessness`) is evergreen, but unlike
Module 29's single ever-replaced attachment, MHCLG publishes one file per
quarter here and keeps the whole run of past quarters attached — closer to
this module's own per-quarter shape than to Module 13's per-publication
search, but everything still comes from one content-API fetch.

Only Table A1 is read: "Number of households by initial assessment of
homelessness circumstances and needs" — the flagship count (how many
households were assessed, and whether a prevention or relief duty was
owed). The workbook carries 40+ other tables (temporary accommodation,
prevention/relief outcomes, multiple-disadvantage breakdowns); reading one
table properly this cycle beats reading many badly, the same discipline
Module 29 applied by reading two of MHCLG's rough-sleeping tables rather
than all of them.

Two real complications, both confirmed against actually-downloaded
workbooks before a line of the parser was written, not assumed from
documentation:

1. **The sheet layout is not stable across the series.** Older files
   (2017–2025, in both .xlsx and .ods) use a multi-row merged-header block;
   very recent files use a flat single header row. `locate_a1_columns`
   below resolves either shape by keyword, not by fixed position — see its
   own docstring for how collisions between a total and its own
   sub-breakdown are avoided.
2. **`sheet_rows()` here is not the same function m13/m29 use.** Those
   modules' own copies only walk `<table%(table)s-cell>` elements. That is
   invisible in their own sources, which do not have genuine
   multi-column-spanning merged cells — but H-CLIC's older-era files do
   (the merged group-header cells in the multi-row shape), and ODF
   represents the columns a merge covers as separate
   `<table:covered-table-cell>` elements. Skipping them silently shifts
   every later column in that row left by however many columns the merge
   spanned. Confirmed this by hand against a real 2019 file: without
   accounting for covered cells, column 6 in the data rows reads as if it
   were column 7's label. Not fixed in m13/m29 — their own inputs never hit
   it, and there is no benefit to changing code that already works for a
   file shape it was never wrong about.

Only .ods and .xlsx are read. The pre-2017 quarters are plain `.xls`
(binary Excel), which this pipeline has no reader for and will not add a
dependency for two years of history — a bounded, documented gap (see
`docs/CAVEATS.md`), not a silent one. `pipeline.xlsx.read_sheet` already
reads cells by explicit position (`r="E7"` etc.), so it does not share
`sheet_rows()`'s covered-cell problem — both readers feed the same
shape-agnostic column locator below.
"""
from __future__ import annotations

import io
import json
import re

import structlog
from odf.opendocument import load as load_ods
from odf.table import Table, TableRow
from odf.text import P

from pipeline import db
from pipeline import xlsx as pipeline_xlsx
from pipeline.http import PipelineHTTPClient
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "mhclg_statutory_homelessness"
CONTENT_URL = (
    "https://www.gov.uk/api/content/government/statistical-data-sets/"
    "live-tables-on-homelessness"
)
ODS_MIME = "application/vnd.oasis.opendocument.spreadsheet"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SUPPORTED_MIMES = {ODS_MIME, XLSX_MIME}

A1_SHEET = "A1"

# Local-authority prefixes only (E06/E07/E08/E09/E10 -- the same set m13's
# own classify_body_type treats as "local_authority"). Deliberately
# narrower than m29's `^E\d{8}$`: this source's region and England
# aggregate rows carry genuine ONS codes in the authority-code column
# (E12xxxxxx, E92000001), not a "[z]" placeholder the way m29's source
# marks them -- a plain 8-digit pattern would misfile a region as a local
# authority instead of correctly excluding it.
ONS_CODE_RE = re.compile(r"^E(?:0[6-9]|10)\d{6}$")

# Matches the two title conventions MHCLG has used for the quarterly
# LA-level file across the series ("...tables:" from 2019, "...figures:"
# 2017-2018), quarter only (month-to-month plus one year), with an
# optional "(revised)" suffix. Deliberately does not match: year-range
# titles with no month names ("2014 to 2015", the pre-2017 annual files),
# "financial year" annual summaries (would double-count quarters already
# read individually), or a trailing "- Accessible" duplicate-format
# version (same data, different formatting; the primary version is read).
_MONTH = (r"January|February|March|April|May|June|July|August|September|"
          r"October|November|December")
TITLE_RE = re.compile(
    rf"^Detailed local authority level (?:tables|homelessness figures):\s*"
    rf"({_MONTH})\s+to\s+({_MONTH})\s+(\d{{4}})\s*(?:\(revised\))?\s*$",
    re.IGNORECASE)
_MONTH_NUMBER = {name: i for i, name in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}

_PLACEHOLDER_TEXT = {"[x]", "[z]", "[n]", "[c]", "", "-", "–", "—"}

# Column-locating keywords, applied in this order so a total column's own
# "of which" sub-breakdowns (which repeat the total's group-label text as
# a prefix in the newer flat-header shape) cannot be claimed instead of
# the total itself — see `locate_a1_columns`.
_RELIEF_RE = re.compile(r"relief duty owed", re.IGNORECASE)
_PREVENTION_RE = re.compile(r"prevention duty owed", re.IGNORECASE)
_TOTAL_OWED_RE = re.compile(r"owed a (?:prevention or relief )?duty", re.IGNORECASE)
_INITIAL_RE = re.compile(r"initial assessment", re.IGNORECASE)
_NOT_THREATENED_RE = re.compile(
    r"not (?:homeless nor )?threatened with homelessness", re.IGNORECASE)
_WITHDREW_RE = re.compile(r"withdrew", re.IGNORECASE)
_NOT_ELIGIBLE_RE = re.compile(r"not eligible", re.IGNORECASE)
_IN_AREA_RE = re.compile(r"in area", re.IGNORECASE)

_REQUIRED_FIELDS = {
    "total_initial_assessments", "total_owed_duty",
    "prevention_duty_owed", "relief_duty_owed",
}


class StatutoryHomelessnessParseError(RuntimeError):
    """The expected H-CLIC workbook shape could not be found."""


def _cell_text(cell) -> str:
    return "".join(str(p) for p in cell.getElementsByType(P))


def sheet_rows(table) -> list[list[str]]:
    """Every row of an ODS sheet, `covered-table-cell` aware.

    Unlike a plain `getElementsByType(TableCell)` walk (what m13/m29 use),
    this also counts `<table:covered-table-cell>` elements — the cells a
    column-spanning merge covers — as blank placeholders in their true
    column position. Skipping them (the simpler walk's behaviour) silently
    shifts every column after a merge left by however many columns it
    spanned; H-CLIC's older-era sheets have genuine multi-column merged
    header cells and hit this, where m13/m29's own sources do not. See the
    module docstring.
    """
    rows: list[list[str]] = []
    for row in table.getElementsByType(TableRow):
        values: list[str] = []
        for child in row.childNodes:
            qname = getattr(child, "qname", None)
            tag = qname[1] if qname else None
            repeat = int(child.getAttribute("numbercolumnsrepeated") or 1)
            repeat = min(repeat, 64)
            if tag == "table-cell":
                values.extend([_cell_text(child).strip()] * repeat)
            elif tag == "covered-table-cell":
                values.extend([""] * repeat)
        rows.append(values)
    return rows


def find_anchor_row(rows: list[list[str]], limit: int = 20) -> int | None:
    """The first England-level data row (`E92000001` / "ENGLAND").

    Everything above it is header content — title, notes, and (in the
    older shape) two or three rows of merged group headers — regardless of
    how many rows that takes, which is why this locates by content rather
    than a fixed offset.
    """
    for i, row in enumerate(rows[:limit]):
        if not row:
            continue
        code = row[0].strip() if row else ""
        name = row[1].strip().upper() if len(row) > 1 else ""
        if code == "E92000001" or name == "ENGLAND":
            return i
    return None


def locate_a1_columns(rows: list[list[str]], anchor: int) -> dict[str, int]:
    """Resolve Table A1's field columns by keyword, not fixed position.

    Works for both the older multi-row merged-header shape and the newer
    flat single-header-row shape: every real data column carries its own
    direct label text in at least one header row in both shapes, so no
    forward-fill is needed — concatenating each column's own text across
    all header rows is enough to match against.

    Fields are claimed in a specific order (relief and prevention before
    the total, which is claimed before its own "of which" sub-breakdowns
    can be): in the newer shape, a duty-outcome sub-column repeats its
    parent group's label text as a prefix ("Assessed as owed a duty..."),
    so a naive single-pass match risks a sub-breakdown column stealing the
    total's claim. Claiming the more specific fields first, then treating
    already-claimed columns as unavailable, avoids it. Verified by hand
    against three real downloaded quarters spanning both shapes before
    this was written.
    """
    # A prose row (the table's title, "Return to contents", the [x]/[z]
    # shorthand note) carries exactly one populated cell in column 0 and
    # would otherwise leak into keyword matching -- the title literally
    # contains the phrase "initial assessment" for this table. A genuine
    # structural header row always populates two or more columns.
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

    claim("relief_duty_owed", _RELIEF_RE)
    claim("prevention_duty_owed", _PREVENTION_RE)
    claim("total_owed_duty", _TOTAL_OWED_RE)
    claim("total_initial_assessments", _INITIAL_RE)
    # In older editions this is the sole "no duty owed" total (there is no
    # separate withdrew/not-eligible breakdown yet, so those two stay
    # unclaimed and NULL for that quarter); in newer editions it is only the
    # "not threatened" reason, one of three additive columns. Confirmed by
    # hand against real published totals from both eras — see
    # docs/CAVEATS.md's Module 30 entry, which is the only place this
    # distinction is recorded.
    claim("not_threatened_no_duty", _NOT_THREATENED_RE)
    claim("withdrew_no_duty", _WITHDREW_RE)
    claim("not_eligible_no_duty", _NOT_ELIGIBLE_RE)
    claim("households_in_area_thousands", _IN_AREA_RE)

    missing = _REQUIRED_FIELDS - claimed.keys()
    if missing:
        raise StatutoryHomelessnessParseError(
            f"could not locate required A1 columns: {sorted(missing)}")
    return claimed


def extract_a1_rows(rows: list[list[str]], anchor: int,
                     columns: dict[str, int]) -> list[dict[str, str]]:
    """One dict per real local-authority row (raw cell text, uncoerced).

    Region/nation aggregate rows (`E92000001`, `E12xxxxxxx`) and the
    "Rest of England" row (no ONS code, `-` or `[z]`) are excluded by the
    same `ONS_CODE_RE` local-authority-code filter every other module in
    this pipeline uses.
    """
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


def to_int(raw: str) -> int | None:
    text = (raw or "").replace(",", "").strip()
    if text in _PLACEHOLDER_TEXT:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def to_float(raw: str) -> float | None:
    text = (raw or "").replace(",", "").strip()
    if text in _PLACEHOLDER_TEXT:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_quarter_title(title: str) -> tuple[str, int, str] | None:
    """(quarter_start 'YYYY-MM-01', year, quarter_label) from a matching
    attachment title, or None if the title is not a quarterly LA-level
    file this module reads (financial-year summaries, Multiple
    Disadvantage tables, and "- Accessible" duplicates all correctly
    return None — see `TITLE_RE`).
    """
    m = TITLE_RE.match((title or "").strip())
    if not m:
        return None
    start_month, _end_month, year = m.group(1), m.group(2), int(m.group(3))
    month_number = _MONTH_NUMBER[start_month.title()]
    quarter_start = f"{year:04d}-{month_number:02d}-01"
    quarter_label = f"{start_month} to {m.group(2)} {year}"
    return quarter_start, year, quarter_label


def discover_publications(client: PipelineHTTPClient) -> list[dict]:
    """Every quarterly LA-level attachment on the one evergreen page,
    deduplicated to one file per quarter (a "(revised)" edition wins over
    the original where both exist)."""
    content = client.get(CONTENT_URL)
    if not content.ok:
        raise StatutoryHomelessnessParseError(
            f"GOV.UK content API failed for {CONTENT_URL} ({content.status_code})")

    attachments = json.loads(content.body).get("details", {}).get("attachments", [])
    by_quarter: dict[str, dict] = {}
    for attachment in attachments:
        parsed = parse_quarter_title(attachment.get("title") or "")
        if parsed is None:
            continue
        quarter_start, year, quarter_label = parsed
        existing = by_quarter.get(quarter_start)
        is_revised = "revised" in (attachment.get("title") or "").lower()
        if existing is not None and not is_revised:
            continue  # keep the revised edition already chosen
        by_quarter[quarter_start] = {
            "attachment": attachment,
            "quarter_start": quarter_start,
            "year": year,
            "quarter_label": quarter_label,
        }
    return sorted(by_quarter.values(), key=lambda p: p["quarter_start"])


def read_workbook_sheet(body: bytes, content_type: str, sheet_name: str) -> list[list[str]]:
    """One named sheet from an H-CLIC quarterly workbook, ODS or XLSX.

    Not module-private: Module 31 (temporary accommodation) reads the same
    quarterly attachments this module discovers, just a different sheet
    (`TA1` rather than `A1`), and imports this directly rather than
    duplicating it — the two modules share one source, one attachment list
    and one dedup rule, which is a different situation from m13/m29's
    deliberately-separate `sheet_rows` copies (unrelated sources that just
    happen to both be ODS).

    A sheet name is looked up exactly first; if that fails, a single
    trailing underscore is tried too (`"TA1_"` as well as `"TA1"`) before
    giving up — confirmed against a real edition (January-March 2023) that
    published Table TA1 under exactly that misnamed sheet, alongside every
    other sheet in the same workbook named normally. Never resolved when
    more than one sheet would match after stripping, so a genuinely
    ambiguous workbook still fails rather than guessing.
    """
    if content_type == ODS_MIME:
        doc = load_ods(io.BytesIO(body))
        tables = {t.getAttribute("name"): t
                  for t in doc.spreadsheet.getElementsByType(Table)}
        if sheet_name not in tables:
            candidates = [name for name in tables
                          if name.rstrip("_") == sheet_name and name != sheet_name]
            if len(candidates) == 1:
                sheet_name = candidates[0]
            else:
                raise StatutoryHomelessnessParseError(
                    f"no {sheet_name!r} sheet in this workbook")
        return sheet_rows(tables[sheet_name])
    if content_type == XLSX_MIME:
        return pipeline_xlsx.read_sheet(body, sheet_name)
    raise StatutoryHomelessnessParseError(f"unsupported content type {content_type!r}")


@register_module(
    "m30_statutory_homelessness", supports_since=True,
    since_note="filters which quarters are written by the quarter's calendar "
               "year; the fetch itself always reads the whole attachment list",
    depends_on=("m00_geography",),
    depends_note="authority names come from the authorities table",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m30_statutory_homelessness"
    conn = ctx.conn
    since_year = ctx.since_year()

    known_authorities = {row["ons_code"] for row in conn.execute(
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
                "m30_statutory_homelessness.")
        log.info("statutory_homelessness.publications_discovered", count=len(publications))

        if ctx.limit:
            publications = publications[-ctx.limit:]

        for pub in ctx.track(publications, "statutory homelessness quarters"):
            if since_year and pub["year"] < since_year:
                continue

            attachment = pub["attachment"]
            content_type = attachment.get("content_type")
            if content_type not in SUPPORTED_MIMES:
                db.record_review_item(
                    conn, module_name, "statutory_homelessness_unsupported_format",
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
                    conn, module_name, "statutory_homelessness_file_unavailable",
                    attachment["url"], json.dumps({"status": file_result.status_code}))
                continue

            try:
                rows = read_workbook_sheet(file_result.body, content_type, A1_SHEET)
            except Exception as exc:
                db.record_review_item(
                    conn, module_name, "statutory_homelessness_file_unreadable",
                    attachment["url"], json.dumps({
                        "quarter": pub["quarter_label"],
                        "error": f"{type(exc).__name__}: {exc}"}))
                continue

            anchor = find_anchor_row(rows)
            if anchor is None:
                db.record_review_item(
                    conn, module_name, "statutory_homelessness_no_anchor_row",
                    attachment["url"], json.dumps({"quarter": pub["quarter_label"]}))
                continue

            try:
                columns = locate_a1_columns(rows, anchor)
            except StatutoryHomelessnessParseError as exc:
                db.record_review_item(
                    conn, module_name, "statutory_homelessness_columns_unresolved",
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

            for entry in extract_a1_rows(rows, anchor, columns):
                ons_code = entry["ons_code"]
                if ons_code not in known_authorities:
                    if ons_code not in unmatched_logged:
                        db.record_review_item(
                            conn, module_name, "statutory_homelessness_unmatched_authority",
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
                for field in ("total_initial_assessments", "total_owed_duty",
                              "prevention_duty_owed", "relief_duty_owed",
                              "not_threatened_no_duty", "withdrew_no_duty",
                              "not_eligible_no_duty"):
                    raw = entry.get(field, "")
                    record[field] = to_int(raw)
                    record[f"{field}_text"] = raw or None
                raw_area = entry.get("households_in_area_thousands", "")
                record["households_in_area_thousands"] = to_float(raw_area)
                record["households_in_area_thousands_text"] = raw_area or None

                db.upsert(conn, "statutory_homelessness_snapshot", record,
                          natural_key=["ons_code", "quarter_start"])
                written += 1

            quarters_processed += 1
            if not ctx.dry_run:
                conn.commit()

    log.info("statutory_homelessness.run_complete",
              quarters=quarters_processed, rows=written)
