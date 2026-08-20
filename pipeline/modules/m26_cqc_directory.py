"""Module 26 — CQC bulk-export cross-check.

CQC publishes two bulk exports independently of the syndication API that
Module 5 (m05_cqc) walks provider-by-provider:
https://www.cqc.org.uk/about-us/transparency/using-cqc-data#directory

  * the **care directory** (CSV, refreshed weekly) — every location it
    currently regulates, one row each, with CQC's own location and provider
    IDs.
  * the **ratings export** (ODS, refreshed monthly) — one row per
    (location, service/population group, KLOE domain), including the
    location's own overall rating and when it was published.

m05_cqc fetches one HTTP request per location (roughly 150 for CGL alone),
and a persistent 5xx/429 on any single one of those still means that
location's row in `cqc_locations` is whatever the last *successful* fetch
produced — which can lag CQC's own records by however many runs it took to
recover (see the m05_cqc fix that stopped one bad location from aborting the
whole run). This module catches that lag by comparing against CQC's own
bulk snapshot rather than trusting m05_cqc's completeness.

It does not add or correct rows in `cqc_locations` — that would mix a daily
per-location API record and a weekly/monthly bulk export into one row,
exactly the cross-source conflation docs/CAVEATS.md rules out. Instead it
flags two things to review_queue for a person to act on (typically: re-run
m05_cqc):

  * `cqc_directory_location_missing` — the directory lists a location for a
    matched provider that has no row at all in `cqc_locations`.
  * `cqc_directory_rating_stale` — a location's ratings-export publication
    date is newer than what m05_cqc last recorded for it.

Provider matching reuses `m05_cqc.match_provider_name` exactly, so a name
that is only a substring candidate there is only a substring candidate
here too — one matching policy, not two.

### Reading the ratings export

Each location has many rows: one per (`Service / Population Group`, KLOE
`Domain`) pair — Safe/Effective/Caring/Responsive/Well-led/Overall, repeated
per registered service where a location has more than one. Only the row
where *both* fields read 'Overall' is the location's own single rating —
the one comparable to the API's `currentRatings.overall`. Every other row is
a service-level or domain-level breakdown and is not read by this module.

### Why this reads the ODS by hand

odfpy (already a dependency, used by m13_la_budgets) builds a full DOM of
the workbook. The ratings export's `content.xml` runs past a gigabyte
uncompressed; odfpy was observed still running past a gigabyte of resident
memory without finishing. Read via stdlib `zipfile` + `xml.etree.iterparse`
instead, clearing each row once read, a full pass over ~320k rows completes
in about a minute with flat memory use. `docs/SOURCES.md` records the
comparison; nothing about this trick is CQC-specific, but no other module
here reads an ODS anywhere near this size.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime
from xml.etree import ElementTree as ET

import structlog

from pipeline import db
from pipeline.cqc_bulk import (
    DIRECTORY_LINK_RE,
    LANDING_PAGE,
    SOURCE_SYSTEM,
    find_link,
    parse_directory_csv,
)
from pipeline.http import PipelineHTTPClient
from pipeline.modules.m05_cqc import match_provider_name
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

RATINGS_LINK_RE = re.compile(
    r'href="(https://www\.cqc\.org\.uk/system/files/[^"]+_Latest_ratings\.ods)"', re.IGNORECASE)

RATINGS_DATE_FORMAT = "%d/%m/%Y"
RATINGS_SHEET_NAME = "Locations"
OVERALL = "Overall"

# --- streaming ODS reader ---------------------------------------------------
#
# See the module docstring for why this exists instead of odfpy.
_TABLE_NS = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
_TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
_TABLE_TAG = f"{{{_TABLE_NS}}}table"
_ROW_TAG = f"{{{_TABLE_NS}}}table-row"
_CELL_TAG = f"{{{_TABLE_NS}}}table-cell"
_PARA_TAG = f"{{{_TEXT_NS}}}p"
_REPEAT_ATTR = f"{{{_TABLE_NS}}}number-columns-repeated"
_NAME_ATTR = f"{{{_TABLE_NS}}}name"

# ODS collapses a run of identical cells -- near-universally the empty ones
# padding a row out to the sheet's declared width -- into one <table-cell>
# carrying a repeat count, which can run into the thousands. A genuinely
# blank column in the *middle* of a row still needs its position held, so
# every repeat is expanded; this only bounds the pathological trailing case.
_MAX_CELL_REPEAT = 64


def _cell_text(cell) -> str:
    return " ".join(text for p in cell.iter(_PARA_TAG) if (text := "".join(p.itertext())))


def _expand_row(row_elem) -> list[str]:
    cells: list[str] = []
    for cell in row_elem.findall(_CELL_TAG):
        repeat = int(cell.get(_REPEAT_ATTR, "1"))
        cells.extend([_cell_text(cell)] * min(repeat, _MAX_CELL_REPEAT))
    return cells


def iter_ods_rows(body: bytes, sheet_name: str):
    """Yield each row (list of cell strings) of the named sheet, without
    ever holding the whole workbook in memory.
    """
    with zipfile.ZipFile(io.BytesIO(body)) as archive, archive.open("content.xml") as xml_file:
        in_target = False
        for event, elem in ET.iterparse(xml_file, events=("start", "end")):
            tag = elem.tag
            if event == "start" and tag == _TABLE_TAG:
                in_target = elem.get(_NAME_ATTR) == sheet_name
                continue
            if event == "end" and tag == _TABLE_TAG:
                elem.clear()
                if in_target:
                    return
                continue
            if not in_target:
                continue
            if event == "end" and tag == _ROW_TAG:
                yield _expand_row(elem)
                elem.clear()


# --- shared helpers ----------------------------------------------------------

def _existing_location_ids(conn, provider_keys: set[str]) -> set[str]:
    if not provider_keys:
        return set()
    placeholders = ",".join("?" for _ in provider_keys)
    rows = conn.execute(
        f"SELECT location_id FROM cqc_locations WHERE provider_key IN ({placeholders})",
        tuple(provider_keys)).fetchall()
    return {r["location_id"] for r in rows}


def _existing_ratings(conn, provider_keys: set[str]) -> dict[str, tuple[str | None, str | None]]:
    if not provider_keys:
        return {}
    placeholders = ",".join("?" for _ in provider_keys)
    rows = conn.execute(
        f"SELECT location_id, overall_rating, overall_rating_date FROM cqc_locations "
        f"WHERE provider_key IN ({placeholders})", tuple(provider_keys)).fetchall()
    return {r["location_id"]: (r["overall_rating"], r["overall_rating_date"]) for r in rows}


def _parse_date(raw: str, fmt: str) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, fmt).date().isoformat()
    except ValueError:
        return None


# --- the two checks ----------------------------------------------------------

def _check_directory_completeness(client: PipelineHTTPClient, conn, module_name: str,
                                   csv_url: str, ctx: ModuleContext) -> int:
    ctx.phase("checking directory completeness")
    directory_rows = parse_directory_csv(client, conn, module_name, csv_url)
    if directory_rows is None:
        return 0

    entries: list[dict] = []
    provider_keys: set[str] = set()
    for row in directory_rows:
        provider_key, basis = match_provider_name(row.provider_name)
        if basis != "exact":
            continue
        provider_keys.add(provider_key)
        entries.append({
            "location_id": row.location_id,
            "location_name": row.location_name,
            "provider_key": provider_key,
            "provider_name": row.provider_name,
        })

    existing = _existing_location_ids(conn, provider_keys)
    missing = 0
    for entry in entries:
        if entry["location_id"] in existing:
            continue
        db.record_review_item(
            conn, module_name, "cqc_directory_location_missing", entry["location_id"],
            json.dumps({
                "provider_key": entry["provider_key"],
                "provider_name": entry["provider_name"],
                "location_name": entry["location_name"],
                "directory_source_url": csv_url,
                "note": "in CQC's own care directory for this provider but absent from "
                         "cqc_locations -- re-run m05_cqc",
            }))
        missing += 1
    log.info("cqc_directory.completeness_checked", directory_rows=len(entries), missing=missing)
    return missing


def _check_ratings_currency(client: PipelineHTTPClient, conn, module_name: str, ods_url: str,
                             ctx: ModuleContext) -> int:
    result = client.get(ods_url)
    if not result.ok:
        db.record_review_item(conn, module_name, "cqc_bulk_export_fetch_failed", ods_url,
                               json.dumps({"status": result.status_code}))
        return 0

    ctx.phase("streaming the ratings export")
    rows_iter = iter_ods_rows(result.body, RATINGS_SHEET_NAME)
    header_row = next(rows_iter, None)
    if not header_row:
        db.record_review_item(conn, module_name, "cqc_bulk_export_unreadable", ods_url,
                               json.dumps({"note": f"'{RATINGS_SHEET_NAME}' sheet had no header row"}))
        return 0
    col = {name.strip(): i for i, name in enumerate(header_row) if name and name.strip()}
    required = ("Location ID", "Provider Name", "Service / Population Group", "Domain",
                "Latest Rating", "Publication Date")
    if not all(name in col for name in required):
        db.record_review_item(conn, module_name, "cqc_bulk_export_unreadable", ods_url,
                               json.dumps({"note": "expected columns missing", "header": list(col)}))
        return 0
    width = max(col[name] for name in required)

    entries: list[dict] = []
    provider_keys: set[str] = set()
    for cells in rows_iter:
        if len(cells) <= width:
            continue
        # The many per-service, per-domain rows are not this location's own
        # rating -- only the (Overall, Overall) row is.
        if cells[col["Service / Population Group"]] != OVERALL or cells[col["Domain"]] != OVERALL:
            continue
        provider_key, basis = match_provider_name(cells[col["Provider Name"]])
        if basis != "exact":
            continue
        location_id = cells[col["Location ID"]]
        if not location_id:
            continue
        provider_keys.add(provider_key)
        entries.append({
            "location_id": location_id,
            "provider_key": provider_key,
            "rating": cells[col["Latest Rating"]] or None,
            "publication_date": _parse_date(cells[col["Publication Date"]], RATINGS_DATE_FORMAT),
        })

    existing = _existing_ratings(conn, provider_keys)
    stale = 0
    for entry in ctx.track(entries, "ratings entries"):
        if entry["location_id"] not in existing:
            continue  # no row to compare against -- the completeness check owns this gap
        stored_rating, stored_date = existing[entry["location_id"]]
        if not entry["publication_date"]:
            continue
        if stored_date and entry["publication_date"] <= stored_date:
            continue
        db.record_review_item(
            conn, module_name, "cqc_directory_rating_stale", entry["location_id"],
            json.dumps({
                "provider_key": entry["provider_key"],
                "directory_rating": entry["rating"],
                "directory_publication_date": entry["publication_date"],
                "api_overall_rating": stored_rating,
                "api_overall_rating_date": stored_date,
                "ratings_source_url": ods_url,
                "note": "CQC's ratings export shows a newer publication date than the API "
                         "record for this location -- re-run m05_cqc",
            }))
        stale += 1
    log.info("cqc_directory.ratings_checked", matched=len(entries), stale=stale)
    return stale


@register_module(
    "m26_cqc_directory",
    supports_since=False,
    depends_on=("m05_cqc",),
    depends_note="cross-checks cqc_locations, which m05_cqc populates",
    since_note="CQC's bulk exports are current snapshots, not dated streams",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m26_cqc_directory"
    conn = ctx.conn

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        ctx.phase("finding current bulk export links")
        landing = client.get(LANDING_PAGE)
        if not landing.ok:
            db.record_review_item(conn, module_name, "cqc_bulk_export_fetch_failed", LANDING_PAGE,
                                   json.dumps({"status": landing.status_code}))
            return

        html = landing.body.decode("utf-8", errors="replace")
        checks = (
            ("directory completeness", find_link(DIRECTORY_LINK_RE, html),
             "no *_CQC_directory.csv link found; the page layout may have changed",
             _check_directory_completeness),
            ("ratings currency", find_link(RATINGS_LINK_RE, html),
             "no *_Latest_ratings.ods link found; the page layout may have changed",
             _check_ratings_currency),
        )

        counts = {"directory completeness": 0, "ratings currency": 0}
        for label, url, missing_link_note, checker in ctx.track(checks, "bulk export checks"):
            if not url:
                db.record_review_item(conn, module_name, "cqc_bulk_export_fetch_failed",
                                       LANDING_PAGE, json.dumps({"note": missing_link_note}))
                continue
            counts[label] = checker(client, conn, module_name, url, ctx)

        if not ctx.dry_run:
            conn.commit()
        missing, stale = counts["directory completeness"], counts["ratings currency"]

    log.info("cqc_directory.run_complete", missing=missing, stale=stale)
