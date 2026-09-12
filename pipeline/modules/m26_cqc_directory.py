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

It does not add rows to `cqc_locations`, and it never touches `overall_rating`
/ `overall_rating_date` — those stay exactly what the API said, including
staying NULL, which is the API's own honest answer. Mixing a daily
per-location API record and a weekly/monthly bulk export into the same
columns is exactly the cross-source conflation docs/CAVEATS.md rules out.
It flags two things to review_queue for a person to act on:

  * `cqc_directory_location_missing` — the directory lists a location for a
    matched provider that has no row at all in `cqc_locations`. Re-run
    m05_cqc.
  * `cqc_directory_rating_stale` — a location's ratings-export publication
    date is newer than what m05_cqc last recorded for it, *and the API did
    supply a rating* (just an older-looking one). Re-run m05_cqc; the two
    sources plausibly just haven't caught up with each other yet.

One exception to "does not add or correct rows", confirmed for real
(location `1-12790083928`, "Aspire Havering"): a same-day fetch of
`GET /locations/{id}` can return `currentRatings.overall` as null while the
bulk ratings export -- CQC's own file, not a third party -- carries a real
published rating for the same location. Re-running m05_cqc does not fix
this; the API is not behind, it is structurally silent for that location.
For exactly that case -- `overall_rating IS NULL` and the bulk export has a
value -- this module writes `bulk_overall_rating` / `bulk_overall_rating_date`
(migration 0055), separate columns from the API's own, so a reader can
always tell which source a location's displayed rating came from. It never
writes these when the API *did* supply a rating: the bulk export being more
current in the null case is not evidence it is also more current when the
two sources actively disagree rather than one of them staying silent.

The same "the API has nothing" case also leaves `cqc_location_reports`
empty for that location -- confirmed for real, 53 of 157 CGL locations at
time of writing. There is no bulk-export equivalent of that table (the
ratings ODS carries a publication date but no report link), so this module
reads the one place CQC does publish the link: the location's own page at
`cqc.org.uk/location/{id}`, plain server-rendered HTML (`_extract_report_info`
-- confirmed against two real, differently-shaped pages, no JavaScript
execution needed). One synthetic row per location, keyed on
`BULK_REPORT_LINK_ID` so re-runs update it rather than accumulate rows, and
cleared alongside the rating fallback once the API supplies its own.

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

import httpx
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

# --- report backfill: a location's own CQC page ------------------------------
#
# cqc_location_reports has no bulk-export equivalent -- the ratings ODS
# carries a publication date but no report link, and report_uri's own rule
# has always been never to guess one. A location's own page at this URL is
# the one place CQC publishes the actual link, and it is plain
# server-rendered HTML: confirmed against two real, differently-shaped pages
# (a location the API has stopped serving reports for, on CQC's newer
# /location/{id}/reports/{planId}/overall path, and one it still serves, on
# the older api.cqc.org.uk/public/v1/reports/{uuid} path) that the link and
# its publish date are both sitting in the plain HTTP response -- no
# JavaScript execution, no headless browser, needed to read either.
LOCATION_PAGE_TEMPLATE = "https://www.cqc.org.uk/location/{location_id}"
LOCATION_PAGE_SOURCE_SYSTEM = "cqc_location_page"
BULK_REPORT_LINK_ID = "bulk_export"

_REPORT_LINK_TAG_RE = re.compile(
    r'<a\b[^>]*\bclass="download-report__link"[^>]*>', re.IGNORECASE)
_HREF_ATTR_RE = re.compile(r'\bhref="([^"]*)"', re.IGNORECASE)
_PUBLISH_DATE_BLOCK_RE = re.compile(
    r'class="download-report__publish-info-date"[^>]*>(.*?)</p>', re.IGNORECASE | re.DOTALL)
_PUBLISH_DATE_TEXT_RE = re.compile(r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})")
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
    placeholders = ",".join("%s" for _ in provider_keys)
    rows = conn.execute(
        f"SELECT location_id FROM cqc_locations WHERE provider_key IN ({placeholders})",
        tuple(provider_keys)).fetchall()
    return {r["location_id"] for r in rows}


def _existing_ratings(conn, provider_keys: set[str]) -> dict[str, tuple[str | None, str | None, str | None]]:
    """location_id -> (overall_rating, overall_rating_date, bulk_overall_rating).
    The third value is whatever a previous run may already have backfilled
    into the fallback columns -- needed to know whether it now needs
    clearing, not just whether it needs setting.
    """
    if not provider_keys:
        return {}
    placeholders = ",".join("%s" for _ in provider_keys)
    rows = conn.execute(
        f"SELECT location_id, overall_rating, overall_rating_date, bulk_overall_rating "
        f"FROM cqc_locations WHERE provider_key IN ({placeholders})", tuple(provider_keys)).fetchall()
    return {r["location_id"]: (r["overall_rating"], r["overall_rating_date"], r["bulk_overall_rating"])
            for r in rows}


def _set_bulk_rating(conn, location_id: str, rating: str | None, rating_date: str | None,
                      source_url: str | None, retrieved_at: str | None) -> None:
    """A plain UPDATE, not db.upsert: the row is already known to exist (see
    the `location_id not in existing` guard at every call site), and
    db.upsert always attempts an INSERT first -- which SQLite validates
    against cqc_locations' NOT NULL columns (provider_id, location_name, ...)
    even when the row will end up conflicting, so a sparse row naming only
    these four columns fails that INSERT before it ever reaches ON CONFLICT.
    """
    conn.execute(
        "UPDATE cqc_locations SET bulk_overall_rating = %s, bulk_overall_rating_date = %s, "
        "bulk_rating_source_url = %s, bulk_rating_retrieved_at = %s WHERE location_id = %s",
        (rating, rating_date, source_url, retrieved_at, location_id))


def _parse_date(raw: str, fmt: str) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, fmt).date().isoformat()
    except ValueError:
        return None


def _extract_report_info(html: str) -> tuple[str | None, str | None]:
    """(report_uri, report_date) read from a location's own CQC page.
    (None, None) if the page has nothing published yet -- a location that
    genuinely has not been inspected carries no such block, and that is a
    fact about the location, not a parse failure.
    """
    uri = None
    tag_match = _REPORT_LINK_TAG_RE.search(html)
    if tag_match:
        href_match = _HREF_ATTR_RE.search(tag_match.group(0))
        if href_match and href_match.group(1):
            uri = href_match.group(1)
            if uri.startswith("/"):
                uri = f"https://www.cqc.org.uk{uri}"

    report_date = None
    date_block = _PUBLISH_DATE_BLOCK_RE.search(html)
    if date_block:
        date_text = _PUBLISH_DATE_TEXT_RE.search(date_block.group(1))
        if date_text:
            try:
                report_date = datetime.strptime(date_text.group(1), "%d %B %Y").date().isoformat()
            except ValueError:
                report_date = None
    return uri, report_date


def _backfill_report(client: PipelineHTTPClient, conn, module_name: str, location_id: str,
                      fallback_date: str | None) -> None:
    """The one fetch in this module that reads a location's own webpage
    rather than a bulk file, and the natural-key marker (BULK_REPORT_LINK_ID)
    keeps it to at most one row per location, idempotent across runs. A
    failure here does not undo the rating backfill that triggered it -- it
    just means this location's badge stays linked to the page rather than a
    specific report, which is what providers.js already falls back to when
    there is no row here at all.
    """
    url = LOCATION_PAGE_TEMPLATE.format(location_id=location_id)
    try:
        result = client.get(url)
    except (httpx.HTTPStatusError, httpx.TransportError) as exc:
        db.record_review_item(conn, module_name, "cqc_location_page_unavailable", location_id,
                               json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        return
    if not result.ok:
        db.record_review_item(conn, module_name, "cqc_location_page_unavailable", location_id,
                               json.dumps({"status": result.status_code}))
        return

    report_uri, report_date = _extract_report_info(result.body.decode("utf-8", errors="replace"))
    if report_uri is None and report_date is None:
        return  # nothing published on the page either -- the rating backfill alone stands

    db.upsert(conn, "cqc_location_reports", {
        "location_id": location_id,
        "report_link_id": BULK_REPORT_LINK_ID,
        "report_date": report_date or fallback_date,
        "first_visit_date": None,
        "report_uri": report_uri,
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": LOCATION_PAGE_SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }, natural_key=["location_id", "report_link_id"])


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
    retrieved_at = result.retrieved_at.isoformat()
    stale = 0
    backfilled = 0
    for entry in ctx.track(entries, "ratings entries"):
        if entry["location_id"] not in existing:
            continue  # no row to compare against -- the completeness check owns this gap
        stored_rating, stored_date, existing_bulk_rating = existing[entry["location_id"]]

        if stored_rating is None:
            # The API has nothing at all for this location -- not "older
            # than the bulk export", nothing. Re-running m05_cqc will not
            # change that (confirmed for real: see the module docstring), so
            # a review-only flag would just repeat forever. Any rating the
            # bulk export does have is strictly more informative than null.
            if entry["rating"]:
                _set_bulk_rating(conn, entry["location_id"], entry["rating"],
                                  entry["publication_date"], ods_url, retrieved_at)
                _backfill_report(client, conn, module_name, entry["location_id"],
                                  entry["publication_date"])
                db.record_review_item(
                    conn, module_name, "cqc_directory_rating_backfilled", entry["location_id"],
                    json.dumps({
                        "provider_key": entry["provider_key"],
                        "bulk_overall_rating": entry["rating"],
                        "bulk_overall_rating_date": entry["publication_date"],
                        "ratings_source_url": ods_url,
                        "note": "the CQC API returned no rating for this location; the portal "
                                 "shows this bulk-export value instead of the API's until the "
                                 "API supplies its own -- re-running m05_cqc will not change that",
                    }))
                backfilled += 1
            continue

        # The API does have a rating now. A fallback value left over from
        # when it did not would sit beside it with nothing marking it stale
        # -- clear it rather than let a reader mistake it for current, and
        # the same for a report row this module scraped in its absence.
        if existing_bulk_rating is not None:
            _set_bulk_rating(conn, entry["location_id"], None, None, None, None)
            conn.execute(
                "DELETE FROM cqc_location_reports WHERE location_id = %s AND report_link_id = %s",
                (entry["location_id"], BULK_REPORT_LINK_ID))

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
                         "record for this location, which did supply a rating -- re-run "
                         "m05_cqc, the two sources plausibly just haven't caught up yet",
            }))
        stale += 1
    log.info("cqc_directory.ratings_checked", matched=len(entries), stale=stale, backfilled=backfilled)
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
