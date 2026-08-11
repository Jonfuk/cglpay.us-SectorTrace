"""Module 7 — NDTMS published treatment statistics.

OHID publishes annual adult and young people's substance misuse treatment
statistics on GOV.UK, each with a data-tables spreadsheet. Publications are
discovered via the GOV.UK Search API and their spreadsheet resolved via the
Content API, then every sheet is inspected: those with an "Area name" or
"Area code" header are extracted as local-authority rows, and the rest are
recorded in an inventory so the national-only share of the publication is
visible rather than looking like an extraction failure.

Worth knowing before relying on this module: the LA-level content of these
spreadsheets is much thinner than it might appear. In the 2024-25 adult
publication, exactly one of 44 sheets is local-authority level (deaths in
drug treatment); numbers in treatment, waiting times and successful
completions are published nationally there. The richer LA-level treatment
indicators live in OHID's Fingertips platform, which is a different source
and is not fetched here. `ndtms_sheet_inventory` makes the split explicit.

Area names are matched to ONS codes with the same deterministic
normalisation used for procurement buyers; anything unmatched goes to
review_queue rather than being guessed.

This is service-demand context, not workforce data, and is kept in its own
tables — see the migration for why it is never merged with the census.
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

SOURCE_SYSTEM = "ohid_ndtms"
GOVUK_SEARCH_URL = "https://www.gov.uk/api/search.json"
GOVUK_CONTENT_BASE = "https://www.gov.uk/api/content"

SPREADSHEET_MIMES = {
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

TITLE_RE = re.compile(
    r"^Substance misuse treatment for (adults|young people):\s*statistics\s*"
    r"(\d{4})\s*to\s*(\d{4})\s*$",
    re.IGNORECASE,
)

AREA_NAME_HEADERS = {"area name", "local authority", "la name", "area"}
AREA_CODE_HEADERS = {"area code", "ons code", "la code"}
# Columns that qualify a row rather than being measured values.
DIMENSION_HEADERS = {"age", "age group", "time period", "period", "sex", "gender"}

# NDTMS writes some authorities with a trailing status word that ONS omits
# ("Bedford Borough" -> ONS "Bedford", "Cheshire East UA" -> "Cheshire East").
# Stripping those is mechanical, not fuzzy. Genuinely combined areas such as
# "Cornwall & Isles of Scilly" have no single ONS code and are deliberately
# left unmatched for review rather than forced onto one of their components.
_COUNCIL_SUFFIX_RE = re.compile(
    r"\b(metropolitan borough council|county council|city council|borough council|"
    r"district council|unitary authority|royal borough of|london borough of|council)\b",
    re.IGNORECASE,
)
_TRAILING_STATUS_RE = re.compile(r"\s+(borough|ua|ua\b|unitary)$", re.IGNORECASE)


def _cell_text(cell) -> str:
    return "".join(str(p) for p in cell.getElementsByType(P))


def _sheet_rows(table) -> list[list[str]]:
    rows = []
    for row in table.getElementsByType(TableRow):
        rows.append([_cell_text(c).strip() for c in row.getElementsByType(TableCell)])
    return rows


def normalise_area_name(name: str) -> str:
    text = (name or "").lower().replace("&", "and")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = _COUNCIL_SUFFIX_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return _TRAILING_STATUS_RE.sub("", text).strip()


def build_authority_lookup(conn) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for row in conn.execute("SELECT ons_code, name FROM authorities ORDER BY ons_code"):
        lookup.setdefault(normalise_area_name(row["name"]), row["ons_code"])
    return lookup


def find_header_row(rows: list[list[str]], max_scan: int = 12) -> int | None:
    """Index of the header row, identified by an area-name/code column.
    None when the sheet is not local-authority level.
    """
    for i, row in enumerate(rows[:max_scan]):
        lowered = {c.strip().lower() for c in row if c.strip()}
        if lowered & AREA_NAME_HEADERS or lowered & AREA_CODE_HEADERS:
            return i
    return None


def _to_number(raw: str) -> float | None:
    text = (raw or "").strip().replace(",", "").replace("%", "")
    if text in {"", "-", "–", "—", "*", "c", "z", "x", ":"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def extract_la_rows(rows: list[list[str]], header_index: int) -> list[dict]:
    """Long-form rows from one LA-level sheet: one per (area, indicator)."""
    header = rows[header_index]
    lowered = [h.strip().lower() for h in header]

    area_name_idx = next((i for i, h in enumerate(lowered) if h in AREA_NAME_HEADERS), None)
    area_code_idx = next((i for i, h in enumerate(lowered) if h in AREA_CODE_HEADERS), None)
    if area_name_idx is None and area_code_idx is None:
        return []

    dimension_idx = {i: header[i] for i, h in enumerate(lowered) if h in DIMENSION_HEADERS}
    value_idx = [
        i for i, h in enumerate(lowered)
        if h and i != area_name_idx and i != area_code_idx and i not in dimension_idx
    ]

    extracted: list[dict] = []
    for row in rows[header_index + 1:]:
        if not any(c.strip() for c in row):
            continue
        area_name = row[area_name_idx].strip() if area_name_idx is not None and area_name_idx < len(row) else ""
        area_code = row[area_code_idx].strip() if area_code_idx is not None and area_code_idx < len(row) else ""
        if not area_name and not area_code:
            continue
        # Footnote lines below the table body have text in the first column
        # but nothing in the value columns.
        if not any(i < len(row) and row[i].strip() for i in value_idx):
            continue

        age_group = ""
        time_period = ""
        for i, label in dimension_idx.items():
            if i >= len(row):
                continue
            if "age" in label.lower():
                age_group = row[i].strip()
            elif "period" in label.lower():
                time_period = row[i].strip()

        for i in value_idx:
            if i >= len(row):
                continue
            raw = row[i].strip()
            if not raw:
                continue
            extracted.append({
                "area_name_raw": area_name or area_code,
                "published_area_code": area_code or None,
                "age_group": age_group,
                "time_period": time_period,
                "indicator": header[i].strip(),
                "value": _to_number(raw),
                "value_text": raw,
            })
    return extracted


def parse_publication_title(title: str) -> tuple[str, str] | None:
    """(cohort, financial_year) from a publication title, else None."""
    m = TITLE_RE.match((title or "").strip())
    if not m:
        return None
    cohort = "adults" if m.group(1).lower() == "adults" else "young_people"
    return cohort, f"{m.group(2)}-{m.group(3)[-2:]}"


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


def _discover_publications(client: PipelineHTTPClient) -> list[dict]:
    found: dict[str, dict] = {}
    for query in ("substance misuse treatment for adults statistics",
                   "substance misuse treatment for young people statistics"):
        result = client.get(GOVUK_SEARCH_URL, params={
            "q": query, "count": 100, "fields": "title,link,public_timestamp"})
        if not result.ok:
            continue
        for r in json.loads(result.body).get("results", []):
            parsed = parse_publication_title(r.get("title", ""))
            if not parsed:
                continue
            cohort, financial_year = parsed
            link = r.get("link") or ""
            found.setdefault(link, {
                "publication_slug": link, "cohort": cohort,
                "financial_year": financial_year, "title": r.get("title"),
            })
    return sorted(found.values(), key=lambda p: (p["cohort"], p["financial_year"]))


@register_module("m07_ndtms", supports_since=True)
def run(ctx: ModuleContext) -> None:
    module_name = "m07_ndtms"
    conn = ctx.conn
    authority_lookup = build_authority_lookup(conn)
    if not authority_lookup:
        log.info("ndtms.no_authorities",
                  note="run m00_geography first or every area will go to review_queue")

    stats_written = 0
    publications_done = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        publications = _discover_publications(client)
        if not publications:
            raise RuntimeError(
                "No NDTMS statistics publications found — the GOV.UK title pattern may "
                "have changed. Check TITLE_RE in m07_ndtms.")
        log.info("ndtms.publications_discovered", count=len(publications))

        if ctx.limit:
            publications = publications[-ctx.limit:]

        since_year = ctx.since_year()
        for pub in publications:
            if since_year and int(pub["financial_year"][:4]) < since_year:
                continue
            content = client.get(f"{GOVUK_CONTENT_BASE}{pub['publication_slug']}")
            if not content.ok:
                db.record_review_item(conn, module_name, "ndtms_publication_unavailable",
                                       pub["publication_slug"],
                                       json.dumps({"status": content.status_code}))
                continue

            attachments = json.loads(content.body).get("details", {}).get("attachments", [])
            sheets = [a for a in attachments
                       if a.get("content_type") in SPREADSHEET_MIMES
                       and (a.get("url") or "").startswith("http")]
            if not sheets:
                db.record_review_item(conn, module_name, "ndtms_no_data_tables",
                                       pub["publication_slug"],
                                       json.dumps({"title": pub["title"]}))
                continue

            attachment = sheets[0]
            if not attachment["url"].lower().endswith(".ods"):
                # XLSX editions exist in older years; odfpy cannot read them and
                # this pipeline does not carry an xlsx reader.
                db.record_review_item(conn, module_name, "ndtms_unsupported_format",
                                       attachment["url"],
                                       json.dumps({"publication": pub["publication_slug"],
                                                    "note": "not an .ods file"}))
                continue

            file_result = client.get(attachment["url"])
            if not file_result.ok:
                db.record_review_item(conn, module_name, "ndtms_data_tables_unavailable",
                                       attachment["url"],
                                       json.dumps({"status": file_result.status_code}))
                continue

            try:
                doc = load_ods(io.BytesIO(file_result.body))
                tables = doc.spreadsheet.getElementsByType(Table)
            except Exception as exc:
                db.record_review_item(conn, module_name, "ndtms_spreadsheet_unreadable",
                                       attachment["url"],
                                       json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
                continue

            provenance = _provenance(file_result)
            la_sheets = 0

            for table in tables:
                table_ref = table.getAttribute("name") or ""
                rows = _sheet_rows(table)
                header_index = find_header_row(rows)
                sheet_title = rows[0][0] if rows and rows[0] else None

                db.upsert(conn, "ndtms_sheet_inventory", {
                    "publication_slug": pub["publication_slug"],
                    "table_ref": table_ref,
                    "sheet_title": sheet_title,
                    "is_local_authority": 1 if header_index is not None else 0,
                    "row_count": len(rows),
                }, natural_key=["publication_slug", "table_ref"])

                if header_index is None:
                    continue
                la_sheets += 1

                for entry in extract_la_rows(rows, header_index):
                    ons_code = authority_lookup.get(normalise_area_name(entry["area_name_raw"]))
                    if ons_code is None and entry.get("published_area_code"):
                        ons_code = entry["published_area_code"]
                    if ons_code is None:
                        db.record_review_item(
                            conn, module_name, "unmatched_ndtms_area", entry["area_name_raw"],
                            json.dumps({"publication": pub["publication_slug"],
                                         "table": table_ref}))

                    db.upsert(conn, "ndtms_la_statistics", {
                        "publication_slug": pub["publication_slug"],
                        "table_ref": table_ref,
                        "area_name_raw": entry["area_name_raw"],
                        "ons_code": ons_code,
                        "age_group": entry["age_group"],
                        "time_period": entry["time_period"],
                        "indicator": entry["indicator"],
                        "value": entry["value"],
                        "value_text": entry["value_text"],
                        "cohort": pub["cohort"],
                        "financial_year": pub["financial_year"],
                        **provenance,
                    }, natural_key=["publication_slug", "table_ref", "area_name_raw",
                                     "age_group", "time_period", "indicator"])
                    stats_written += 1

            db.upsert(conn, "ndtms_publications", {
                "publication_slug": pub["publication_slug"],
                "cohort": pub["cohort"],
                "financial_year": pub["financial_year"],
                "title": pub["title"],
                "document_url": attachment["url"],
                "archived_path": str(file_result.archived_path) if file_result.archived_path else None,
                "sheets_total": len(tables),
                "sheets_local_authority": la_sheets,
                **provenance,
            }, natural_key=["publication_slug"])
            publications_done += 1

            log.info("ndtms.publication_processed", slug=pub["publication_slug"],
                      cohort=pub["cohort"], year=pub["financial_year"],
                      sheets=len(tables), la_sheets=la_sheets)

            if not ctx.dry_run:
                conn.commit()

    log.info("ndtms.run_complete", publications=publications_done, la_rows=stats_written)
