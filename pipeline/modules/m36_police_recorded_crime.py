"""Module 36 -- Police recorded crime, drug offences (Home Office, CSP level).

JON-34's feasibility document (`docs/crime-data-area-level-context-feasibility.md`)
found that `data.police.uk` -- the site originally proposed as a crime
comparator -- publishes no geography coarser than LSOA, which would need a
new LSOA-to-local-authority crosswalk this pipeline does not have. A separate
GOV.UK/Home Office publication, "Police recorded crime and outcomes open data
tables" (not on `data.police.uk` at all), turned out to already be at
Community Safety Partnership (CSP) geography -- which the Home Office's own
user guide states "generally corresponds to single or combined Local
Authority boundaries" -- and carries a dedicated "Drug offences" breakdown.
This module reads that CSP-level table, "Drug offences" group only, the
same "one clean coherent slice worth having" scope discipline Module 29
applied (reading two of MHCLG's rough-sleeping tables, not all of them).

Same comparator role as Modules 29-31 (see `docs/CAVEATS.md`): never combined
with the sector's own evidence, side by side only, and -- specific to this
source -- never read as a measure of drug use or unmet treatment need. ONS's
own *User Guide to Crime Statistics* states plainly that recorded drug
possession offences are "heavily influenced by police activities and
priorities" rather than by how much drug use is actually happening; a change
or a difference between two authorities can be a change in enforcement
activity, not in the underlying population this pipeline's sector evidence is
about.

**Geography is resolved by name match against `authorities`, not the official
ONS CSP-to-LAD lookup the feasibility document also found.** This mirrors the
exact-normalised-name-then-`review_queue` discipline `m07_ndtms` and `m29`
already use for their own area names, rather than adding a second reference
table and crosswalk mechanism for a first version. CSP names are, in the
large majority of current English rows, spelled identically to their local
authority ("Bath and North East Somerset", "Barnsley", "Wolverhampton" --
confirmed against the publication's own geographical reference table during
JON-34's research). A CSP name with no exact match -- a combined CSP
covering more than one authority, a historic pre-reorganisation sub-district
CSP, or (this source covers England and Wales) a Welsh CSP, since this
pipeline's `authorities` table holds only English authorities -- is never
guessed onto a single component authority; it is logged once per run to
`review_queue` and the figure is not stored. Coverage of this table is
therefore a subset of England's CSPs, not all of them, and that subset is
whatever cleanly names one live authority.

**Streamed, not loaded as one document.** The current CSP-level file is a
~50 MB `.ods` whose `content.xml` decompresses to well over a gigabyte --
six sheets (one per financial year), each many hundreds of thousands of rows
across every offence code, because this pipeline only wants the "Drug
offences" group out of roughly a dozen. `odfpy`'s `load_ods` (what
Modules 29/30 use for their much smaller workbooks) builds one in-memory
document for the whole file; doing that here risks a multi-gigabyte parse for
a module that keeps a few thousand rows out of several million. Rows are
streamed with `xml.etree.ElementTree.iterparse` instead, clearing each row
element as it is read -- the same discipline `pipeline/xlsx.py`'s
`iter_sheet_stream` already uses for Skills for Care's own oversized import.

Only the current, rolling-window CSP file is read (discovered by content, see
`find_current_csp_attachment`) -- not the four further, closed historical
windows (2003-2007, 2008-2011, 2012-2015, 2016-2020) the same GOV.UK page
also lists. Reading the full 2003-to-date series is a real further step, not
attempted in this first version, mirroring Module 29's own "one source read
properly this cycle" discipline.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from collections.abc import Iterator
from xml.etree import ElementTree as ET

import structlog

from pipeline import db
from pipeline.http import PipelineHTTPClient
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "home_office_recorded_crime_csp"
CONTENT_URL = (
    "https://www.gov.uk/api/content/government/statistical-data-sets/"
    "police-recorded-crime-and-outcomes-open-data-tables"
)
ODS_MIME = "application/vnd.oasis.opendocument.spreadsheet"

# Every attachment on the page titled this way is a CSP-level table -- the
# current rolling-window file and the four closed historical windows alike.
# Matched on content, not spelling: the current file's own title has drifted
# between "open data" and "open data tables" across editions, and the point
# is the geography, not the exact wording.
CSP_TITLE_RE = re.compile(r"Community Safety Partnership", re.IGNORECASE)
_YEAR_ENDING_MARCH_RE = re.compile(r"year ending March (\d{4})", re.IGNORECASE)

# ODS namespaces. Written out rather than imported from odfpy, because the
# streaming reader below deliberately does not use odfpy at all -- see the
# module docstring.
_TABLE_NS = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
_TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
_OFFICE_NS = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
_TABLE_TAG = f"{{{_TABLE_NS}}}table"
_ROW_TAG = f"{{{_TABLE_NS}}}table-row"
_CELL_TAG = f"{{{_TABLE_NS}}}table-cell"
_COVERED_CELL_TAG = f"{{{_TABLE_NS}}}covered-table-cell"
_P_TAG = f"{{{_TEXT_NS}}}p"
_NAME_ATTR = f"{{{_TABLE_NS}}}name"
_REPEAT_ATTR = f"{{{_TABLE_NS}}}number-columns-repeated"
_VALUE_TYPE_ATTR = f"{{{_OFFICE_NS}}}value-type"
_VALUE_ATTR = f"{{{_OFFICE_NS}}}value"

# One data sheet per financial year ("2020_21", ..., "2025_26" in the edition
# read while building this module) -- matched by shape, not a fixed list, so
# a future edition dropping the oldest year and adding a new one needs no
# code change here. "Cover_sheet" and "Notes" never match and are skipped.
_DATA_SHEET_RE = re.compile(r"^\d{4}_\d{2}$")
_FINANCIAL_YEAR_RE = re.compile(r"^(\d{4})/\d{2}$")

# Verified against a live download of the current edition (see the feasibility
# document, §3.2): the CSP-level file's own header row, in this exact order.
# A workbook whose header does not match this exactly is a shape change this
# module has not seen and refuses to guess column positions for.
EXPECTED_HEADER = (
    "Financial Year", "Financial Quarter", "Police Force", "CSP Name",
    "Offence Description", "Offence Group", "Offence Subgroup",
    "Offence Code", "Offence Count",
)
_FIELDS = (
    "financial_year", "financial_quarter", "police_force", "csp_name",
    "offence_description", "offence_group", "offence_subgroup",
    "offence_code", "offence_count",
)

# The exact string this file uses for the group this module reads. Verified
# live to be "Drug offences" (lower-case "o") in this table -- a separate
# Home Office file (the force-level drug-offence subcode breakdown) uses
# "Drug Offences" (title case) for the same concept, a real inconsistency
# within the same publication family, not a typo in this module. Matched
# case-insensitively here so a future edition correcting -- or reproducing --
# that inconsistency does not silently stop matching.
DRUG_OFFENCES_GROUP = "drug offences"

_QUARTER_START_MONTH = {1: 4, 2: 7, 3: 10, 4: 1}


class PoliceRecordedCrimeParseError(RuntimeError):
    """The expected Home Office CSP workbook shape could not be found."""


def find_current_csp_attachment(attachments: list[dict]) -> dict | None:
    """The current, still-extending CSP-level file, or None.

    The page lists five CSP-titled ODS attachments: the current rolling
    window and four closed historical windows that stopped being extended
    years ago. Every title states its own "year ending March YYYY" start and
    end; the current file's end year is always the largest, because it is
    the one edition still being republished forward. Chosen by that content,
    not by a hardcoded filename or URL -- the same discovery-over-fixed-URL
    discipline `m00_geography`, `m13` and `m30` already use for their own
    versioned sources.
    """
    best: tuple[int, dict] | None = None
    for attachment in attachments:
        if attachment.get("content_type") != ODS_MIME:
            continue
        title = attachment.get("title") or ""
        if not CSP_TITLE_RE.search(title):
            continue
        years = [int(y) for y in _YEAR_ENDING_MARCH_RE.findall(title)]
        if len(years) < 2:
            continue
        end_year = max(years)
        if best is None or end_year > best[0]:
            best = (end_year, attachment)
    return best[1] if best else None


def _cell_text(cell: ET.Element) -> str:
    return "".join(node.text or "" for node in cell.iter(_P_TAG))


def _cell_numeric(cell: ET.Element) -> float | None:
    if cell.get(_VALUE_TYPE_ATTR) != "float":
        return None
    raw = cell.get(_VALUE_ATTR)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def iter_csp_sheet_rows(body: bytes) -> Iterator[tuple[str, list[tuple[str, float | None]]]]:
    """(sheet_name, cells) for every row of every financial-year data sheet.

    `cells` holds exactly `len(EXPECTED_HEADER)` `(text, numeric)` pairs --
    `numeric` is the ODS-computed `office:value` where the source cell is
    typed as a number (avoiding this module's own comma-stripping guess where
    the source already states the value unambiguously), `None` otherwise. A
    sheet's own trailing "number-columns-repeated" filler cell (tens of
    thousands of columns wide, covering the rest of the sheet's declared
    width) is never expanded -- once the expected column count is reached,
    later cells in the row are ignored.

    Streamed with `ElementTree.iterparse`, not `odfpy.load_ods` -- see the
    module docstring for why. Only rows belonging to a table whose name
    matches `_DATA_SHEET_RE` are yielded; `Cover_sheet` and `Notes` are read
    (there is no way to skip bytes mid-stream in one XML document) but
    discarded without building row dictionaries for them.
    """
    header_width = len(EXPECTED_HEADER)
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        with archive.open("content.xml") as stream:
            current_sheet: str | None = None
            row_cells: list[tuple[str, float | None]] = []
            for event, elem in ET.iterparse(stream, events=("start", "end")):
                tag = elem.tag
                if event == "start":
                    if tag == _TABLE_TAG:
                        name = elem.get(_NAME_ATTR) or ""
                        current_sheet = name if _DATA_SHEET_RE.match(name) else None
                    continue

                # event == "end" from here on.
                if tag == _TABLE_TAG:
                    current_sheet = None
                    elem.clear()
                    continue
                if current_sheet is None:
                    elem.clear()
                    continue
                if tag in (_CELL_TAG, _COVERED_CELL_TAG):
                    repeat = min(int(elem.get(_REPEAT_ATTR) or 1),
                                 header_width - len(row_cells))
                    if repeat > 0:
                        pair = ((_cell_text(elem), _cell_numeric(elem))
                                if tag == _CELL_TAG else ("", None))
                        row_cells.extend([pair] * repeat)
                    elem.clear()
                elif tag == _ROW_TAG:
                    if row_cells:
                        yield current_sheet, row_cells
                    row_cells = []
                    elem.clear()


def _to_int_cell(pair: tuple[str, float | None]) -> int | None:
    text, numeric = pair
    if numeric is not None:
        return int(numeric)
    stripped = (text or "").replace(",", "").strip()
    if not stripped:
        return None
    try:
        return int(float(stripped))
    except ValueError:
        return None


def financial_quarter_start(financial_year: str, quarter: int | None) -> str | None:
    """'YYYY-MM-01' for a Home Office financial-year quarter.

    Home Office financial years run April to March: Q1 is April-June, Q4 is
    January-March of the *second* calendar year in the label. `('2025/26',
    1)` -> `'2025-04-01'`; `('2025/26', 4)` -> `'2026-01-01'`. This is a fixed
    calendar mapping, not a statistic -- the same class of harmless date
    arithmetic `m30` already does turning "January to March 2026" into a
    `quarter_start` for sorting, never a claim about anything the source
    itself did not state at quarter granularity.
    """
    match = _FINANCIAL_YEAR_RE.match((financial_year or "").strip())
    if not match or quarter not in _QUARTER_START_MONTH:
        return None
    start_year = int(match.group(1))
    year = start_year + 1 if quarter == 4 else start_year
    return f"{year:04d}-{_QUARTER_START_MONTH[quarter]:02d}-01"


def _normalise_csp_name(name: str) -> str:
    text = (name or "").lower().replace("&", "and")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def build_drug_offence_row(
    cells: list[tuple[str, float | None]],
    authority_lookup: dict[str, str],
    provenance: dict,
) -> tuple[dict | None, str | None]:
    """One already-known-to-be-a-data-row (never the header) -> (record,
    rejection_reason). Exactly one of the pair is not None.

    `rejection_reason` is one of `"not_drug_offence"` (a different Offence
    Group -- the overwhelming majority of rows, silently skipped, no
    review_queue entry: this is normal filtering, not a data problem),
    `"unmatched_csp"` (the caller logs the CSP name once per run, see the
    module docstring on why this is expected, not a gap) or
    `"unresolvable_quarter"` (a `parse_failures` row). Separated from the
    streaming loop so it can be tested directly against hand-built cell
    tuples rather than a constructed `.ods` file.
    """
    entry = dict(zip(_FIELDS, cells))
    if entry["offence_group"][0].strip().lower() != DRUG_OFFENCES_GROUP:
        return None, "not_drug_offence"

    csp_name = entry["csp_name"][0].strip()
    ons_code = authority_lookup.get(_normalise_csp_name(csp_name))
    if ons_code is None:
        return None, "unmatched_csp"

    quarter = _to_int_cell(entry["financial_quarter"])
    quarter_start = financial_quarter_start(entry["financial_year"][0], quarter)
    if quarter_start is None:
        return None, "unresolvable_quarter"

    record = {
        "ons_code": ons_code,
        "csp_name": csp_name,
        "financial_year": entry["financial_year"][0].strip(),
        "financial_quarter": quarter,
        "quarter_start": quarter_start,
        "offence_subgroup": entry["offence_subgroup"][0].strip(),
        "offence_count": _to_int_cell(entry["offence_count"]),
        "offence_count_text": entry["offence_count"][0].strip(),
        **provenance,
    }
    return record, None


def build_authority_lookup(conn) -> dict[str, str]:
    """Normalised authority name -> ons_code.

    Deliberately simpler than `m07_ndtms.build_authority_lookup`: this
    source's CSP names are, in the large majority of current rows, spelled
    identically to the authority's own name (see the module docstring), so
    there is no council-suffix stripping or alias table to carry over from a
    different source's own naming quirks. A name that does not match this
    lookup goes to `review_queue`, which is correct for this source's genuine
    combined/historic/Welsh cases -- not a gap to widen the matching for.
    """
    lookup: dict[str, str] = {}
    for row in conn.execute("SELECT ons_code, name FROM authorities ORDER BY ons_code"):
        lookup.setdefault(_normalise_csp_name(row["name"]), row["ons_code"])
    return lookup


@register_module(
    "m36_police_recorded_crime", supports_since=True,
    since_note="filters which financial years are written; the fetch itself "
               "always reads the whole current CSP-level file",
    depends_on=("m00_geography",),
    depends_note="authority names come from the authorities table",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m36_police_recorded_crime"
    conn = ctx.conn
    since_year = ctx.since_year()

    authority_lookup = build_authority_lookup(conn)
    unmatched_logged: set[str] = set()

    written = 0
    sheets_processed = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        content = client.get(CONTENT_URL)
        if not content.ok:
            raise PoliceRecordedCrimeParseError(
                f"GOV.UK content API failed for {CONTENT_URL} ({content.status_code})")

        attachments = json.loads(content.body).get("details", {}).get("attachments", [])
        attachment = find_current_csp_attachment(attachments)
        if attachment is None:
            db.record_review_item(
                conn, module_name, "police_recorded_crime_no_csp_attachment",
                CONTENT_URL, json.dumps({
                    "titles_seen": [a.get("title") for a in attachments],
                    "note": "no Community Safety Partnership open data attachment "
                            "found; the page's shape may have changed, see "
                            "CSP_TITLE_RE in m36_police_recorded_crime",
                }))
            log.info("police_recorded_crime.run_complete", rows=0)
            return

        ctx.phase(f"fetching {attachment.get('title')!r}")
        file_result = client.get(attachment["url"])
        if not file_result.ok:
            db.record_review_item(
                conn, module_name, "police_recorded_crime_file_unavailable",
                attachment["url"], json.dumps({"status": file_result.status_code}))
            log.info("police_recorded_crime.run_complete", rows=0)
            return

        provenance = {
            "source_url": file_result.url,
            "retrieved_at": file_result.retrieved_at.isoformat(),
            "http_status": file_result.status_code,
            "source_system": SOURCE_SYSTEM,
            "payload_sha256": file_result.payload_sha256,
        }

        ctx.phase("streaming the CSP-level workbook (drug offences only)")
        # `raw_sheet` is the sheet name last seen in the stream, always kept
        # in step with it. `tracked_sheet` is that same name only while this
        # sheet's rows are actually wanted (its year clears `since_year` and
        # its header matched) -- otherwise None. Keeping the two separate is
        # what stops a skipped sheet's rows from re-triggering "entered a new
        # sheet" handling (and an unwanted `conn.commit()`) on every single
        # row: the outer transition check compares against `raw_sheet`, which
        # only changes once per sheet regardless of whether it is tracked.
        raw_sheet: str | None = None
        tracked_sheet: str | None = None
        sheet_header_ok = False
        sheet_rows: list[dict] = []

        def flush() -> None:
            nonlocal written, sheets_processed
            if sheet_rows:
                written += db.upsert_many(
                    conn, "police_recorded_drug_offences", sheet_rows,
                    natural_key=["ons_code", "quarter_start", "offence_subgroup"],
                )
            if tracked_sheet is not None and sheet_header_ok:
                sheets_processed += 1
            if not ctx.dry_run:
                conn.commit()

        try:
            for sheet_name, cells in iter_csp_sheet_rows(file_result.body):
                if sheet_name != raw_sheet:
                    flush()
                    raw_sheet = sheet_name
                    sheet_header_ok = False
                    sheet_rows = []

                    match = _FINANCIAL_YEAR_RE.match(sheet_name.replace("_", "/", 1))
                    start_year = int(match.group(1)) if match else None
                    skip_for_since = bool(
                        since_year and start_year is not None and start_year < since_year)
                    tracked_sheet = None if skip_for_since else sheet_name

                if tracked_sheet is None:
                    continue

                if not sheet_header_ok:
                    header_text = tuple(text for text, _numeric in cells)
                    if header_text != EXPECTED_HEADER:
                        db.record_review_item(
                            conn, module_name, "police_recorded_crime_header_unexpected",
                            attachment["url"], json.dumps({
                                "sheet": sheet_name, "header_seen": list(header_text),
                                "expected": list(EXPECTED_HEADER),
                            }))
                        tracked_sheet = None  # skip the rest of this sheet
                        continue
                    sheet_header_ok = True
                    continue  # the header row itself is never a data row

                record, reason = build_drug_offence_row(cells, authority_lookup, provenance)
                if reason == "unmatched_csp":
                    csp_name = cells[_FIELDS.index("csp_name")][0].strip()
                    if csp_name not in unmatched_logged:
                        db.record_review_item(
                            conn, module_name, "police_recorded_crime_unmatched_csp",
                            csp_name, json.dumps({
                                "note": "no exact-matching English authority name -- "
                                        "a combined CSP, a historic sub-district CSP, "
                                        "or (this source covers England and Wales) a "
                                        "Welsh CSP are all expected, not a data error",
                            }))
                        unmatched_logged.add(csp_name)
                    continue
                if reason == "unresolvable_quarter":
                    entry = dict(zip(_FIELDS, cells))
                    db.record_parse_failure(
                        conn, module_name, "quarter_start", attachment["url"],
                        f"unresolvable financial year/quarter: "
                        f"{entry['financial_year'][0]!r} / {entry['financial_quarter'][0]!r}")
                    continue
                if record is None:  # reason == "not_drug_offence"
                    continue

                sheet_rows.append(record)
            flush()
        except zipfile.BadZipFile as exc:
            db.record_review_item(
                conn, module_name, "police_recorded_crime_file_unreadable",
                attachment["url"], json.dumps({"error": f"{type(exc).__name__}: {exc}"}))

    log.info("police_recorded_crime.run_complete",
              sheets=sheets_processed, rows=written)
