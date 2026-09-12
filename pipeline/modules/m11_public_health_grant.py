"""Module 11 — Public Health Grant allocations.

DHSC publishes an annual "Public health grants to local authorities: YYYY
to YYYY" release on GOV.UK, each with an attached ODS spreadsheet of
authority-level allocations. There is no stable slug or attachment title
across years (2026-27's file is "Annex E: public health grant
allocations..."; 2024-25's is "Public health local authority allocations
..."; sheet names, header row position, and the set of grant-type columns
all differ too), so this module discovers publications via the GOV.UK
Search API, resolves each one's spreadsheet attachment via the GOV.UK
Content API, and parses the sheet generically: find the header row by
locating the 'Ecode' / ONS-code columns, then classify every other column
that contains a "YYYY to YYYY" financial year span as a grant line item.

Stored in tidy/long form (one row per authority/year/grant_type) rather
than forcing DHSC's shifting column set into a fixed wide schema — see the
migration file for why.
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

SOURCE_SYSTEM = "dhsc_public_health_grant"
GOVUK_SEARCH_URL = "https://www.gov.uk/api/search.json"
GOVUK_CONTENT_BASE = "https://www.gov.uk/api/content"
ODS_MIME = "application/vnd.oasis.opendocument.spreadsheet"

TITLE_RE = re.compile(r"^Public health grants to local authorities:\s*(\d{4})\s*to\s*(\d{4})\s*$", re.IGNORECASE)
YEAR_SPAN_RE = re.compile(r"(\d{4})\s*to\s*(\d{4})")
ONS_CODE_RE = re.compile(r"^E\d{8}$")
_HEADER_NOISE_RE = re.compile(r"financial year|\bfy\b|indicative|[():*£]", re.IGNORECASE)


class DiscoveryError(RuntimeError):
    """Raised when the expected GOV.UK/ODS shape can't be found."""


def _cell_text(cell) -> str:
    return "".join(str(p) for p in cell.getElementsByType(P))


def _sheet_rows(ods_bytes: bytes) -> list[list[str]]:
    doc = load_ods(io.BytesIO(ods_bytes))
    tables = doc.spreadsheet.getElementsByType(Table)
    if not tables:
        raise DiscoveryError("ODS file has no sheets")
    rows = []
    for row in tables[0].getElementsByType(TableRow):
        rows.append([_cell_text(c) for c in row.getElementsByType(TableCell)])
    return rows


def _find_header_row(rows: list[list[str]]) -> int:
    for i, row in enumerate(rows[:15]):
        lowered = [c.strip().lower() for c in row]
        if "ecode" in lowered and any("ons" in c and "local authority code" in c for c in lowered):
            return i
    raise DiscoveryError("Could not locate header row (no 'Ecode' + ONS local authority code columns in first 15 rows)")


def _slugify_grant_type(header_text: str, y1: str, y2: str) -> str:
    text = header_text.lower().replace(f"{y1} to {y2}", "")
    text = _HEADER_NOISE_RE.sub("", text)
    text = re.sub(r"[,:]", " ", text)
    text = re.sub(r"\s+", "_", text.strip())
    return text.strip("_") or "allocation"


def _classify_columns(header_row: list[str]) -> tuple[int, int, list[dict]]:
    """DHSC's "Of which is drug & alcohol ring-fenced..." sub-columns don't
    repeat the "YYYY to YYYY" year span themselves — they inherit it from
    the most recent "Financial year YYYY to YYYY: Total..." column to their
    left. So the year context carries forward until a new one is found;
    only columns before any year context is established (Ecode, and
    ons_idx/name_idx themselves) are excluded.
    """
    ons_idx = None
    name_idx = None
    year_columns = []
    current_year: dict | None = None
    for idx, raw in enumerate(header_row):
        text = raw.strip()
        if not text:
            continue
        lowered = text.lower()
        if "ons" in lowered and "local authority code" in lowered:
            ons_idx = idx
            continue
        if lowered == "local authority name":
            name_idx = idx
            continue

        m = YEAR_SPAN_RE.search(text)
        if m:
            y1, y2 = m.group(1), m.group(2)
            current_year = {
                "financial_year": f"{y1}-{y2[-2:]}",
                "allocation_status": "indicative" if "indicative" in lowered else "confirmed",
                "y1": y1, "y2": y2,
            }
        if current_year is None:
            continue

        year_columns.append({
            "index": idx,
            "header": text,
            "financial_year": current_year["financial_year"],
            "allocation_status": current_year["allocation_status"],
            "unit": "gbp_per_head" if ("per head" in lowered or "per capita" in lowered) else "gbp",
            "grant_type": _slugify_grant_type(text, current_year["y1"], current_year["y2"]),
        })
    if ons_idx is None or name_idx is None:
        raise DiscoveryError(f"Could not find ONS code / name columns in header row: {header_row}")
    return ons_idx, name_idx, year_columns


def _parse_amount(raw: str) -> float:
    cleaned = raw.strip().replace(",", "").replace("£", "")
    return float(cleaned)


def _discover_publications(client: PipelineHTTPClient) -> list[dict]:
    result = client.get(GOVUK_SEARCH_URL, params={
        "q": "public health grants to local authorities",
        "filter_organisations": "department-of-health-and-social-care",
        "count": 100,
    })
    if not result.ok:
        raise DiscoveryError(f"GOV.UK search failed ({result.status_code})")
    publications = []
    for r in json.loads(result.body).get("results", []):
        m = TITLE_RE.match((r.get("title") or "").strip())
        if not m:
            continue
        publications.append({"title": r["title"], "link": r["link"], "year_start": int(m.group(1))})
    publications.sort(key=lambda p: p["year_start"])
    return publications


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


@register_module(
    "m11_public_health_grant", supports_since=True,
    depends_on=("m00_geography",),
    depends_note="allocations are keyed on ONS codes",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m11_public_health_grant"
    conn = ctx.conn

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        publications = _discover_publications(client)
        if not publications:
            raise DiscoveryError(
                "No 'Public health grants to local authorities' publications found via GOV.UK "
                "search — the query or title pattern may need updating."
            )
        log.info("phg.discovered_publications", years=[p["year_start"] for p in publications])

        total_rows = 0
        since_year = ctx.since_year()
        for pub in ctx.track(publications, "grant publications"):
            if since_year and pub["year_start"] < since_year:
                continue
            content_result = client.get(f"{GOVUK_CONTENT_BASE}{pub['link']}")
            if not content_result.ok:
                db.record_parse_failure(conn, module_name, "publication", pub["link"],
                                         f"content API returned {content_result.status_code}",
                                         source_url=content_result.url)
                continue

            attachments = json.loads(content_result.body).get("details", {}).get("attachments", [])
            ods_attachments = [a for a in attachments
                                if a.get("content_type") == ODS_MIME and (a.get("url") or "").startswith("http")]

            if not ods_attachments:
                db.record_review_item(conn, module_name, "missing_allocation_spreadsheet", pub["link"],
                                       json.dumps({"title": pub["title"]}))
                continue
            if len(ods_attachments) > 1:
                preferred = [a for a in ods_attachments if "alloc" in (a.get("title") or "").lower()]
                if len(preferred) != 1:
                    db.record_review_item(conn, module_name, "ambiguous_allocation_spreadsheet", pub["link"],
                                           json.dumps({"title": pub["title"],
                                                       "candidates": [a.get("title") for a in ods_attachments]}))
                    continue
                ods_attachments = preferred

            attachment = ods_attachments[0]
            file_result = client.get(attachment["url"])
            if not file_result.ok:
                db.record_parse_failure(conn, module_name, "spreadsheet", attachment["url"],
                                         f"download returned {file_result.status_code}", source_url=file_result.url)
                continue

            try:
                rows = _sheet_rows(file_result.body)
                header_idx = _find_header_row(rows)
                ons_idx, name_idx, year_columns = _classify_columns(rows[header_idx])
            except DiscoveryError as exc:
                db.record_review_item(conn, module_name, "unparseable_spreadsheet", attachment["url"],
                                       json.dumps({"title": pub["title"], "reason": str(exc)}))
                continue

            provenance = _provenance(file_result)
            year_row_count = 0
            grant_rows: list[dict] = []
            for row in rows[header_idx + 1:]:
                if ons_idx >= len(row):
                    continue
                ons_code = row[ons_idx].strip()
                if not ONS_CODE_RE.match(ons_code):
                    continue  # footer notes, blank rows, non-English rows

                for col in year_columns:
                    if col["index"] >= len(row):
                        continue
                    raw_value = row[col["index"]]
                    if not raw_value.strip():
                        continue
                    try:
                        amount = _parse_amount(raw_value)
                    except ValueError:
                        db.record_parse_failure(
                            conn, module_name, col["grant_type"], raw_value,
                            f"could not parse amount for {ons_code} {col['financial_year']}",
                            source_url=attachment["url"],
                        )
                        continue

                    grant_rows.append({
                        "ons_code": ons_code,
                        "financial_year": col["financial_year"],
                        "grant_type": col["grant_type"],
                        "allocation_status": col["allocation_status"],
                        "unit": col["unit"],
                        "amount": amount,
                        "source_column_header": col["header"],
                        "source_document": attachment["url"],
                        **provenance,
                    })
                    year_row_count += 1

            db.upsert_many(
                conn, "public_health_grants", grant_rows,
                natural_key=["ons_code", "financial_year", "grant_type"],
            )
            total_rows += year_row_count
            # Committed per publication, not once at the end. SQLite allows one
            # writer, and a transaction left open spans every fetch that
            # follows it — so a module that wrote its first row early and
            # committed only on the way out held the warehouse's only write
            # slot for its entire run. Serially that is invisible; under
            # `run all --jobs N` it is every other module in the wave failing
            # with "database is locked" after waiting out the busy timeout.
            if not ctx.dry_run:
                conn.commit()
            log.info("phg.publication_processed", year=pub["year_start"], rows=year_row_count)

        log.info("phg.run_complete", total_rows=total_rows)
