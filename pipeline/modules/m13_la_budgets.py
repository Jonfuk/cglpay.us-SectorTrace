"""Module 13 — Local authority revenue budgets (MHCLG).

The structured national release, so 150+ council websites do not have to be
scraped for the same numbers. MHCLG publishes each authority's budgeted
revenue expenditure by service line, with the ONS code in the sheet — so this
joins to `authorities` with no name matching, unlike almost every other
council-level source in this pipeline.

The sheets describe their own structure in marker rows ("This row contains
the data base Asset ID", "This row contains section headings for..."), which
is what the parser keys on rather than fixed row offsets: the number of
columns changes year to year (213 in 2026-27) and offsets would drift.

Units come from the sheet's own "Data are reported in £ thousand" line. Where
that cannot be read, amounts are stored NULL rather than assumed — the same
rule as the charity accounts, and for the same reason.

What this module does NOT do is compare the budget to the public health
grant. Module 11 records what an authority was ALLOCATED; this records what
it BUDGETED. They come from different departments by different processes, and
the gap between them is a question to investigate, not a figure to publish
unexamined.
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

SOURCE_SYSTEM = "mhclg_la_revenue_budgets"
GOVUK_SEARCH_URL = "https://www.gov.uk/api/search.json"
GOVUK_CONTENT_BASE = "https://www.gov.uk/api/content"
ODS_MIME = "application/vnd.oasis.opendocument.spreadsheet"

TITLE_RE = re.compile(
    r"^Local authority revenue expenditure and financing England:\s*"
    r"(\d{4})\s*to\s*(\d{4})\s*budget individual local authority data\s*$",
    re.IGNORECASE)

# The sheets label their own structural rows; keyed on these rather than on
# fixed offsets, because the shape shifts between years.
ASSET_ID_MARKER = "data base asset"
SECTION_MARKER = "section headings"
LINE_NUMBER_MARKER = "line number"

ONS_CODE_RE = re.compile(r"^E\d{8}$")

# ONS entity-code prefixes seen in MHCLG's release, confirmed against the
# authority names the sheet itself publishes rather than assumed:
#   E23 Avon & Somerset Police and Crime Commissioner
#   E31 Avon Combined Fire and Rescue Authority
#   E47 Cambridgeshire and Peterborough Combined Authority
#   E26 Dartmoor National Park Authority
#   E50 East London Waste Authority
#   E68 Lee Valley Regional Park Authority
#   E12 Greater London Authority
#   E92 ENGLAND
# Only the local-authority prefixes have rows in `authorities`; the rest are
# other precepting bodies whose absence is correct, not a failed join.
_BODY_TYPE_BY_PREFIX = {
    "E06": "local_authority", "E07": "local_authority", "E08": "local_authority",
    "E09": "local_authority", "E10": "local_authority",
    "E23": "police", "E31": "fire", "E47": "combined_authority",
    "E26": "national_park", "E68": "regional_park", "E50": "waste_authority",
    "E12": "greater_london_authority", "E92": "england_total",
}


def classify_body_type(ons_code: str) -> str:
    return _BODY_TYPE_BY_PREFIX.get((ons_code or "")[:3], "other_precepting_body")


_MULTIPLIER_RE = re.compile(
    r"(?:reported|presented|shown|expressed)\s+in\s*£?\s*(thousands?|millions?)\b",
    re.IGNORECASE,
)
_APOS = r"[’‘'`´]?"
_THOUSAND_RE = re.compile(
    rf"£\s*{_APOS}\s*000s?|\bin thousands?\b|£\s*thousands?\b",
    re.IGNORECASE,
)
_MILLION_RE = re.compile(
    r"£\s*(?:m|millions?)\b|\bin millions?\b",
    re.IGNORECASE,
)


class BudgetParseError(RuntimeError):
    """The expected MHCLG sheet shape could not be found."""


def _cell_text(cell) -> str:
    return "".join(str(p) for p in cell.getElementsByType(P))


def sheet_rows(table) -> list[list[str]]:
    return [[_cell_text(c).strip() for c in row.getElementsByType(TableCell)]
             for row in table.getElementsByType(TableRow)]


def detect_multiplier(rows: list[list[str]]) -> int | None:
    """Denomination from the sheet's own preamble. None when absent — never
    a default, since being wrong here is a 1,000x error.
    """
    # The preamble has moved between sheets and years.  Restrict the search
    # to text before the data header so a budget-line description containing
    # "million" cannot manufacture a denomination, but do not assume a fixed
    # number of preamble rows or a fixed number of populated cells.
    header = find_header_row(rows)
    preamble = rows[:header] if header is not None else rows[:12]
    for row in preamble:
        for cell in row:
            m = _MULTIPLIER_RE.search(cell or "")
            if m:
                return 1000 if m.group(1).lower().startswith("thousand") else 1_000_000
            if _THOUSAND_RE.search(cell or ""):
                return 1000
            if _MILLION_RE.search(cell or ""):
                return 1_000_000
    return None


def find_marker_row(rows: list[list[str]], marker: str, limit: int = 15) -> int | None:
    for i, row in enumerate(rows[:limit]):
        if row and marker.lower() in (row[0] or "").lower():
            return i
    return None


def find_header_row(rows: list[list[str]], limit: int = 15) -> int | None:
    """The row naming the identifier columns (E-code / ONS Code / authority)."""
    for i, row in enumerate(rows[:limit]):
        lowered = [c.strip().lower() for c in row[:8]]
        if any(c == "ons code" for c in lowered):
            return i
    return None


def forward_fill(values: list[str], width: int) -> list[str]:
    """Section headings appear once at the start of the columns they cover;
    carry each forward so every data column knows its section.
    """
    filled: list[str] = []
    current = ""
    for i in range(width):
        value = values[i].strip() if i < len(values) else ""
        if value:
            current = value
        filled.append(current)
    return filled


def _to_number(raw: str) -> float | None:
    text = (raw or "").strip().replace(",", "").replace("£", "")
    if text in {"", "-", "–", "—", ":", "..", "n/a", "N/A"}:
        return None
    if text.startswith("(") and text.endswith(")"):   # accounting negative
        text = "-" + text[1:-1]
    try:
        return float(text)
    except ValueError:
        return None


def parse_budget_sheet(rows: list[list[str]]) -> dict:
    """Structure of one RA data sheet.

    Returns the header index, the per-column asset ids / sections / line
    numbers, and the identifier column positions.
    """
    header_index = find_header_row(rows)
    if header_index is None:
        raise BudgetParseError("no header row with an 'ONS Code' column")

    header = rows[header_index]
    lowered = [c.strip().lower() for c in header]
    ons_idx = lowered.index("ons code")
    name_idx = next((i for i, c in enumerate(lowered) if c == "local authority"), None)
    class_idx = next((i for i, c in enumerate(lowered) if c == "class"), None)

    width = max(len(r) for r in rows[:header_index + 1]) if header_index else len(header)

    asset_row = find_marker_row(rows, ASSET_ID_MARKER)
    section_row = find_marker_row(rows, SECTION_MARKER)
    line_row = find_marker_row(rows, LINE_NUMBER_MARKER)

    asset_ids = rows[asset_row] if asset_row is not None else []
    sections = forward_fill(rows[section_row], width) if section_row is not None else [""] * width
    line_numbers = rows[line_row] if line_row is not None else []

    return {
        "header_index": header_index,
        "ons_idx": ons_idx,
        "name_idx": name_idx,
        "class_idx": class_idx,
        "asset_ids": asset_ids,
        "sections": sections,
        "line_numbers": line_numbers,
        "width": width,
    }


def extract_budget_rows(rows: list[list[str]], structure: dict, multiplier: int | None) -> list[dict]:
    """One record per (authority, budget line)."""
    ons_idx = structure["ons_idx"]
    asset_ids = structure["asset_ids"]
    sections = structure["sections"]
    line_numbers = structure["line_numbers"]
    identifier_columns = {ons_idx, structure["name_idx"], structure["class_idx"]}

    out: list[dict] = []
    for row in rows[structure["header_index"] + 1:]:
        if ons_idx >= len(row):
            continue
        ons_code = row[ons_idx].strip()
        if not ONS_CODE_RE.match(ons_code):
            continue  # England totals, blank rows, footnotes

        authority_class = (row[structure["class_idx"]].strip()
                            if structure["class_idx"] is not None
                            and structure["class_idx"] < len(row) else None)

        for column in range(len(row)):
            if column in identifier_columns or column >= len(asset_ids):
                continue
            line_code = (asset_ids[column] or "").strip()
            if not line_code or line_code.lower().startswith("this row"):
                continue
            raw = row[column].strip()
            if not raw:
                continue
            value = _to_number(raw)
            out.append({
                "ons_code": ons_code,
                "line_code": line_code,
                "section": (sections[column] if column < len(sections) else "") or None,
                "line_number": (line_numbers[column].strip()
                                 if column < len(line_numbers) else None) or None,
                "column_label": None,
                "amounts_multiplier": multiplier,
                "amount": value * multiplier if (value is not None and multiplier) else None,
                "value_text": raw,
                "body_type": classify_body_type(ons_code),
                "authority_class": authority_class,
            })
    return out


def parse_publication_title(title: str) -> str | None:
    """Financial year from a publication title, else None."""
    m = TITLE_RE.match((title or "").strip())
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)[-2:]}"


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


def _discover_publications(client: PipelineHTTPClient) -> list[dict]:
    result = client.get(GOVUK_SEARCH_URL, params={
        "q": "local authority revenue expenditure and financing budget individual local authority data",
        "count": 100, "fields": "title,link"})
    if not result.ok:
        raise BudgetParseError(f"GOV.UK search failed ({result.status_code})")

    found: dict[str, dict] = {}
    for row in json.loads(result.body).get("results", []):
        financial_year = parse_publication_title(row.get("title", ""))
        if not financial_year:
            continue
        found.setdefault(row["link"], {
            "publication_slug": row["link"], "financial_year": financial_year,
            "title": row.get("title")})
    return sorted(found.values(), key=lambda p: p["financial_year"])


@register_module(
    "m13_la_budgets", supports_since=True,
    depends_on=("m00_geography",),
    depends_note="the public health budget view joins to authorities",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m13_la_budgets"
    conn = ctx.conn
    since_year = ctx.since_year()

    budget_rows = 0
    documents = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        publications = _discover_publications(client)
        if not publications:
            raise BudgetParseError(
                "No MHCLG revenue budget publications found — the GOV.UK title pattern "
                "may have changed. Check TITLE_RE in m13_la_budgets.")
        log.info("budgets.publications_discovered", count=len(publications))

        if ctx.limit:
            publications = publications[-ctx.limit:]

        for pub in ctx.track(publications, "budget publications"):
            if since_year and int(pub["financial_year"][:4]) < since_year:
                continue

            content = client.get(f"{GOVUK_CONTENT_BASE}{pub['publication_slug']}")
            if not content.ok:
                db.record_review_item(conn, module_name, "budget_publication_unavailable",
                                       pub["publication_slug"],
                                       json.dumps({"status": content.status_code}))
                continue

            attachments = json.loads(content.body).get("details", {}).get("attachments", [])
            # Revenue Account (RA) files only. The specific/special grants (SG)
            # file is a different measurement and is not merged in here.
            ra_files = [a for a in attachments
                         if a.get("content_type") == ODS_MIME
                         and (a.get("url") or "").startswith("http")
                         and re.search(r"\bRA\b|revenue account", a.get("title") or "", re.I)]
            if not ra_files:
                db.record_review_item(conn, module_name, "budget_no_ra_attachment",
                                       pub["publication_slug"],
                                       json.dumps({"title": pub["title"]}))
                continue

            for attachment in ra_files:
                file_result = client.get(attachment["url"])
                if not file_result.ok:
                    db.record_review_item(conn, module_name, "budget_file_unavailable",
                                           attachment["url"],
                                           json.dumps({"status": file_result.status_code}))
                    continue

                try:
                    doc = load_ods(io.BytesIO(file_result.body))
                    tables = doc.spreadsheet.getElementsByType(Table)
                except Exception as exc:
                    db.record_review_item(conn, module_name, "budget_file_unreadable",
                                           attachment["url"],
                                           json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
                    continue

                provenance = _provenance(file_result)
                for table in tables:
                    rows = sheet_rows(table)
                    if find_header_row(rows) is None:
                        continue  # front page, notes, dropdown helper sheets

                    multiplier = detect_multiplier(rows)
                    if multiplier is None:
                        db.record_parse_failure(
                            conn, module_name, "amounts_multiplier", attachment["url"],
                            "could not read the sheet's denomination; amounts left NULL",
                            source_url=attachment["url"])

                    try:
                        structure = parse_budget_sheet(rows)
                    except BudgetParseError as exc:
                        db.record_review_item(conn, module_name, "budget_sheet_unparsed",
                                               attachment["url"],
                                               json.dumps({"sheet": table.getAttribute("name"),
                                                            "reason": str(exc)}))
                        continue

                    extracted = extract_budget_rows(rows, structure, multiplier)
                    for entry in extracted:
                        db.upsert(conn, "la_revenue_budgets", {
                            **entry,
                            "financial_year": pub["financial_year"],
                            "source_document": attachment["url"],
                            **provenance,
                        }, natural_key=["ons_code", "financial_year", "line_code"])
                        budget_rows += 1

                    db.upsert(conn, "la_budget_publications", {
                        "publication_slug": pub["publication_slug"],
                        "document_url": attachment["url"],
                        "financial_year": pub["financial_year"],
                        "document_label": attachment.get("title"),
                        "amounts_multiplier": multiplier,
                        "sheet_name": table.getAttribute("name"),
                        "data_rows": len(extracted),
                        **provenance,
                    }, natural_key=["publication_slug", "document_url"])
                    documents += 1

                    log.info("budgets.sheet_processed", year=pub["financial_year"],
                              sheet=table.getAttribute("name"), rows=len(extracted),
                              multiplier=multiplier)

                if not ctx.dry_run:
                    conn.commit()

    log.info("budgets.run_complete", documents=documents, rows=budget_rows)
