"""Shared reader for CQC's weekly care-directory CSV.

Two callers need the same file for two different reasons:

  * m05_cqc discovers which providers to walk from it, replacing what used
    to be the longest silent stretch in this pipeline -- paging the CQC
    syndication API's ~64k-row `/providers` index one page at a time just
    to get id-and-name pairs to match locally. The directory names every
    provider once per location row; deduplicated, that is the same
    id-and-name list, in one ~18MB download instead of ~64 paginated calls.
  * m26_cqc_directory cross-checks it against `cqc_locations` a row at a
    time, since it is the more complete source for "does this location
    exist at all", independent of whatever m05_cqc's own per-location API
    walk managed to complete.

Not itself a registered module -- it has nothing to fetch on its own
account, only a fetch-and-parse routine for the two that do. Kept out of
pipeline/modules/ for that reason: that package is one module per source
(see CLAUDE.md), and this is not a source, it is a file format two of them
happen to share.
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass

from pipeline import db
from pipeline.http import PipelineHTTPClient

SOURCE_SYSTEM = "cqc_bulk_export"
LANDING_PAGE = "https://www.cqc.org.uk/about-us/transparency/using-cqc-data"

DIRECTORY_LINK_RE = re.compile(
    r'href="(https://www\.cqc\.org\.uk/system/files/[^"]+_CQC_directory\.csv)"', re.IGNORECASE)

LOCATION_ID_COLUMN = "CQC Location ID (for office use only)"
PROVIDER_ID_COLUMN = "CQC Provider ID (for office use only)"


@dataclass(frozen=True)
class DirectoryRow:
    location_id: str
    location_name: str
    provider_id: str
    provider_name: str


def find_link(pattern: re.Pattern, html: str) -> str | None:
    match = pattern.search(html)
    return match.group(1) if match else None


def _find_header(rows: list[list[str]], marker: str) -> tuple[int, dict[str, int]] | None:
    marker = marker.lower()
    for i, row in enumerate(rows):
        if any((cell or "").strip().lower() == marker for cell in row):
            return i, {name.strip(): idx for idx, name in enumerate(row) if name and name.strip()}
    return None


def find_directory_url(client: PipelineHTTPClient, conn, module_name: str) -> str | None:
    """The current dated `*_CQC_directory.csv` URL, scraped from the
    landing page (the filename changes on every weekly publish). None on
    any failure, with a review_queue item recorded under the caller's own
    module name -- so a failure here is attributable to whichever module
    needed it, not pooled under a third name nobody would think to check.
    """
    landing = client.get(LANDING_PAGE)
    if not landing.ok:
        db.record_review_item(conn, module_name, "cqc_bulk_export_fetch_failed", LANDING_PAGE,
                               json.dumps({"status": landing.status_code}))
        return None

    url = find_link(DIRECTORY_LINK_RE, landing.body.decode("utf-8", errors="replace"))
    if not url:
        db.record_review_item(
            conn, module_name, "cqc_bulk_export_fetch_failed", LANDING_PAGE,
            json.dumps({"note": "no *_CQC_directory.csv link found; the page layout may "
                                 "have changed"}))
    return url


def parse_directory_csv(client: PipelineHTTPClient, conn, module_name: str,
                         csv_url: str) -> list[DirectoryRow] | None:
    """Fetch and parse `csv_url` into one row per location. None on any
    failure (fetch, or the expected columns are not where they used to
    be), with a review_queue item recorded under the caller's module name.
    """
    result = client.get(csv_url)
    if not result.ok:
        db.record_review_item(conn, module_name, "cqc_bulk_export_fetch_failed", csv_url,
                               json.dumps({"status": result.status_code}))
        return None

    rows = list(csv.reader(io.StringIO(result.body.decode("utf-8", errors="replace"))))
    header = _find_header(rows[:10], LOCATION_ID_COLUMN)
    if header is None:
        db.record_review_item(
            conn, module_name, "cqc_bulk_export_unreadable", csv_url,
            json.dumps({"note": f"no header row containing {LOCATION_ID_COLUMN!r} found"}))
        return None
    header_idx, col = header
    required = ("Name", "Provider name", LOCATION_ID_COLUMN, PROVIDER_ID_COLUMN)
    if not all(name in col for name in required):
        db.record_review_item(conn, module_name, "cqc_bulk_export_unreadable", csv_url,
                               json.dumps({"note": "expected columns missing", "header": list(col)}))
        return None
    width = max(col[name] for name in required)

    out: list[DirectoryRow] = []
    for data_row in rows[header_idx + 1:]:
        if len(data_row) <= width:
            continue
        location_id = data_row[col[LOCATION_ID_COLUMN]]
        provider_id = data_row[col[PROVIDER_ID_COLUMN]]
        if not location_id or not provider_id:
            continue
        out.append(DirectoryRow(
            location_id=location_id,
            location_name=data_row[col["Name"]],
            provider_id=provider_id,
            provider_name=data_row[col["Provider name"]],
        ))
    return out


def fetch_directory_rows(client: PipelineHTTPClient, conn, module_name: str) -> list[DirectoryRow] | None:
    """find_directory_url + parse_directory_csv in one call, for a caller
    that only wants the rows and does not also need the ratings export
    link off the same landing page (m26_cqc_directory fetches the landing
    page itself for that reason, and calls parse_directory_csv directly).
    """
    csv_url = find_directory_url(client, conn, module_name)
    if csv_url is None:
        return None
    return parse_directory_csv(client, conn, module_name, csv_url)
