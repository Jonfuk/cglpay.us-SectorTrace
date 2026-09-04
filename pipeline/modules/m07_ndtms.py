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

# The other direction: a handful of ONS names carry a trailing qualifier that
# NDTMS simply drops ("Bristol, City of" is NDTMS's "Bristol"). Stripping it
# gives that authority a second lookup key. The pattern is anchored to the
# trailing *comma* form deliberately -- "City of London" (E09000001) is a
# different authority, and stripping a leading "City of" would reduce it to
# "london", which is also a region name in these sheets. That would not fail
# loudly; it would file a London borough's figures under a region.
_ONS_TRAILING_QUALIFIER_RE = re.compile(r",\s*(?:city|county|borough)\s+of\s*$",
                                          re.IGNORECASE)

# And three areas where the two names simply differ, which is not a rule and
# must not be turned into one. Each is written out with the code it resolves
# to, so a reader can check it rather than trust it, and each maps one-to-one
# onto a single live authority.
#
# What is deliberately NOT here, because every one would attach a figure to a
# body that did not produce it:
#   "Cornwall and Isles of Scilly" is two authorities (E06000052, E06000053);
#   "Poole" and "Bournemouth" are pre-2019 authorities that no longer exist,
#   and resolving either to Bournemouth, Christchurch and Poole (E06000058)
#   would date a figure to a council that had not been created yet;
#   "ENGLAND", "National" and the nine region names are aggregates, not areas.
# Those stay NULL and go to review, which is the correct answer, not a gap.
NDTMS_AREA_ALIASES = {
    "durham": "E06000047",    # ONS "County Durham"
    "stockton": "E06000004",  # ONS "Stockton-on-Tees"
    "southend": "E06000033",  # ONS "Southend-on-Sea"
}

# NDTMS puts a reporting entity's lifecycle in the name itself: "Barnsley
# (discontinued)" and "Barnsley (from April 2026)" are the same borough
# either side of an April 2026 renumbering, and "North Yorkshire (pre April
# 2023)" is the county before it became a unitary. Both halves are real and
# both carry figures -- the discontinued entity holds the periods ending
# before the cutover, the new one the periods after -- so leaving them
# unmatched loses whole authorities from the data.
#
# The date in the suffix is NOT parsed to decide which code applies. Which
# code a half belongs to is read from `authority_successors`, the
# geometry-derived predecessor/successor edges m00 already records, so this
# follows the spine rather than a second opinion about English local
# government reorganisation.
_LIFECYCLE_SUFFIX_RE = re.compile(r"^(?P<base>.+?)\s*\((?P<marker>[^()]+)\)\s*$")

# A pair counts as one authority renumbered only when predecessor and
# successor cover effectively the same ground. Lower-overlap edges are real
# reorganisations that moved boundaries -- Northamptonshire splitting into two
# unitaries is 0.45/0.55 -- and carrying a figure across one of those would
# make it a figure for a different place.
_SAME_TERRITORY_OVERLAP = 0.99


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
    """Normalised area name -> ONS code.

    Built in three passes, and the order is the point: every authority's own
    name is claimed first, then the shortened forms, then the written-out
    aliases. A name that some authority actually has can therefore never be
    taken by another authority's abbreviation of it, because `setdefault` on
    an already-claimed key does nothing. Run the passes the other way round
    and a shortening could quietly outrank a real name.
    """
    lookup: dict[str, str] = {}
    shortened: dict[str, str] = {}
    for row in conn.execute("SELECT ons_code, name FROM authorities ORDER BY ons_code"):
        canonical = normalise_area_name(row["name"])
        lookup.setdefault(canonical, row["ons_code"])
        without_qualifier = normalise_area_name(
            _ONS_TRAILING_QUALIFIER_RE.sub("", row["name"]))
        if without_qualifier and without_qualifier != canonical:
            shortened.setdefault(without_qualifier, row["ons_code"])

    for key, code in shortened.items():
        lookup.setdefault(key, code)
    for name, code in NDTMS_AREA_ALIASES.items():
        lookup.setdefault(normalise_area_name(name), code)
    return lookup


def build_transition_lookup(conn) -> dict[str, tuple[str, str]]:
    """Normalised authority name -> (predecessor code, successor code).

    Only the handful of authorities the spine holds under two codes because
    ONS renumbered them: Barnsley and Sheffield at the April 2026 change,
    North Yorkshire and Somerset at the 2023 unitarisation.

    A name is only included when exactly one successor edge links two of the
    codes sharing that name. Two conditions matter and both are about
    refusing to guess. Ambiguity is dropped rather than resolved: if a name's
    codes are linked by several edges there is no single answer, and one
    invented here would be invisible downstream. And a successor may have
    other predecessors that are not part of this -- three Somerset districts
    also merge into E06000066 -- which is fine, because those districts do
    not share the name and so never enter the pairing.
    """
    by_name: dict[str, list[str]] = {}
    for row in conn.execute("SELECT ons_code, name FROM authorities ORDER BY ons_code"):
        by_name.setdefault(normalise_area_name(row["name"]), []).append(row["ons_code"])

    candidates = {name: codes for name, codes in by_name.items() if len(codes) > 1}
    if not candidates:
        return {}

    edges: set[tuple[str, str]] = set()
    for row in conn.execute(
            "SELECT predecessor_code, successor_code, overlap_fraction "
            "FROM authority_successors"):
        overlap = row["overlap_fraction"]
        if overlap is not None and overlap >= _SAME_TERRITORY_OVERLAP:
            edges.add((row["predecessor_code"], row["successor_code"]))

    transitions: dict[str, tuple[str, str]] = {}
    for name, codes in candidates.items():
        pairs = [(p, s) for p in codes for s in codes if p != s and (p, s) in edges]
        if len(pairs) == 1:
            transitions[name] = pairs[0]
    return transitions


def match_area_name(name: str, lookup: dict[str, str],
                     transitions: dict[str, tuple[str, str]]) -> str | None:
    """The published area name resolved to an ONS code, or None for review.

    The plain lookup is tried first and always wins, so adding lifecycle
    handling cannot change what an ordinary name already resolved to. Only a
    name that did not match at all is examined for a `(...)` lifecycle
    marker.

    An unrecognised marker returns None rather than falling back to the base
    name. "Barnsley (something new NDTMS started writing in 2028)" is a
    question for a person, and quietly answering it with whichever Barnsley
    sorted first is how a figure ends up under the wrong code.
    """
    code = lookup.get(normalise_area_name(name))
    if code is not None:
        return code

    matched = _LIFECYCLE_SUFFIX_RE.match((name or "").strip())
    if matched is None:
        return None
    pair = transitions.get(normalise_area_name(matched.group("base")))
    if pair is None:
        return None

    predecessor, successor = pair
    marker = matched.group("marker").strip().lower()
    if marker == "discontinued" or marker.startswith("pre "):
        return predecessor
    if marker.startswith("from "):
        return successor
    return None


def find_header_row(rows: list[list[str]], max_scan: int = 12) -> int | None:
    """Index of the header row, identified by an area-name/code column.
    None when the sheet is not local-authority level.
    """
    for i, row in enumerate(rows[:max_scan]):
        lowered = {c.strip().lower() for c in row if c.strip()}
        if lowered & AREA_NAME_HEADERS or lowered & AREA_CODE_HEADERS:
            return i
    return None


# The opiate/crack and alcohol prevalence sheets in the 2018-19 and 2019-20
# editions write their header as two rows: a row of measure-group labels
# ("Number of users", "Rate of use per thousand of the population") with the
# per-measure breakdown (OCU/Opiates/Crack cocaine x point/lower/upper) held
# in colspanned cells beneath each group, then a row spelling out those
# sub-labels. `_sheet_rows` does not expand colspans, so the group-label row
# has far fewer cells than the data rows it heads (6 against 21, for
# 2_1_Drug_prevalence) and no column index in it lines up with a real data
# column past the first couple. Later editions write one flat header row per
# measure instead ("Crack cocaine (number) lower bound 95% CI"), which this
# parser already handles correctly.
#
# There is no way to recover the true column mapping from the compressed
# group row, so guessing at it would silently attach a value to the wrong
# measure for every row in the sheet, not just the header -- confirmed
# against the real files: "Rate of use per thousand of the population" for
# Derby resolves to 1,672, which is actually the opiate lower-bound *count*
# from a different measure group entirely. That is the same kind of invented
# pairing docs/CAVEATS.md rules out for confidence intervals, so a sheet
# shaped like this is recorded as seen in ndtms_sheet_inventory and left
# unextracted rather than parsed positionally.
_SUB_HEADER_MARKERS = {"lower bound 95% ci", "upper bound 95% ci"}


def has_reliable_header(rows: list[list[str]], header_index: int) -> bool:
    """False when the header is a colspan-compressed group-label row rather
    than one flat row of column names -- signalled by the very next row
    being a row of CI sub-labels instead of area data.
    """
    if header_index + 1 >= len(rows):
        return True
    next_row = {c.strip().lower() for c in rows[header_index + 1] if c.strip()}
    return not (next_row & _SUB_HEADER_MARKERS)


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
    if not has_reliable_header(rows, header_index):
        return []
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


@register_module(
    "m07_ndtms", supports_since=True,
    depends_on=("m00_geography",),
    depends_note="matches published area names against the authorities table",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m07_ndtms"
    conn = ctx.conn
    authority_lookup = build_authority_lookup(conn)
    transitions = build_transition_lookup(conn)
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
        for pub in ctx.track(publications, "publications"):
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
            stats_rows: list[dict] = []

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

                if not has_reliable_header(rows, header_index):
                    db.record_review_item(
                        conn, module_name, "ndtms_two_row_header_sheet", table_ref,
                        json.dumps({
                            "publication": pub["publication_slug"],
                            "note": "colspan-compressed group-label header; column "
                                     "positions do not match the data columns, left "
                                     "unextracted rather than parsed positionally",
                        }))
                    continue

                for entry in extract_la_rows(rows, header_index):
                    ons_code = match_area_name(
                        entry["area_name_raw"], authority_lookup, transitions)
                    if ons_code is None and entry.get("published_area_code"):
                        ons_code = entry["published_area_code"]
                    if ons_code is None:
                        db.record_review_item(
                            conn, module_name, "unmatched_ndtms_area", entry["area_name_raw"],
                            json.dumps({"publication": pub["publication_slug"],
                                         "table": table_ref}))

                    stats_rows.append({
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
                    })
                    stats_written += 1

            db.upsert_many(
                conn, "ndtms_la_statistics", stats_rows,
                natural_key=["publication_slug", "table_ref", "area_name_raw",
                             "age_group", "time_period", "indicator"],
            )
            db.upsert(conn, "ndtms_publications", {
                "publication_slug": pub["publication_slug"],
                "cohort": pub["cohort"],
                "financial_year": pub["financial_year"],
                "title": pub["title"],
                "document_url": attachment["url"],
                "archived_path": file_result.archived_ref,
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
