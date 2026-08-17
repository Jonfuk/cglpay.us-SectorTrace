"""Module 25 — Skills for Care workforce intelligence (G2).

Adult social care pay and headcount benchmarks from the ASC-WDS workforce
estimates, which Skills for Care publishes as Excel data downloads. The
sector this corpus tracks sits between health and social care, and its
workforce market is largely the care workforce — so these figures are the
contextual pay and turnover comparators the campaign's claims need, on the
same side-by-side footing G1 (ASHE) already established: a comparator is
read beside the sector's own evidence, never turned into a ratio by this
pipeline.

ACCESS SHAPE (the review Phase 19 opened with). The Data downloads page
lists five workbooks, all .xlsx, at predictable URLs under
.../resources/Our-data/: the current-year regional, local-area and ICB
downloads (same 313-column data sheet shape, keyed by the ONS area code the
workbook itself carries), the statistical appendix (51 report sheets, no
data sheet), and the trended download (a slimmer long-format sheet). The
site serves no robots.txt directives for these paths, and data.gov.uk
catalogues the ASC-WDS data under OGL v3.0 — both verified by request on
2026-08-16, and both recorded in docs/SOURCES.md.

WHAT IS PARSED, AND WHY ONLY THAT. The three current-year downloads share
the data-sheet shape, so the parser is written to the shape rather than to
the sheet name (which carries the year): find the sheet whose header row
names the standard columns, then read the pay and turnover columns beside
the workbook's own identifiers. The appendix and the trended file are
fetched, archived and recorded per file, but their shapes are not parsed —
the appendix is report tables, and the trended file is the change-over-time
series that F-05 declined history for. A file whose shape this module does
not read is `parse_status = 'unreadable'` with a `parse_failures` row and a
review item, never silently skipped.

THE COLUMN RULE. Estimates are stored as the workbook published them:
`fte_annual_pay`, `hourly_pay`, `turnover_rate` and `vacancy_rate` are the
workbook's own figures, NULL where a cell could not be read, and never
derived from one another (an annual figure annualised from an hourly one is
a number the source never stated). The ~300 other columns (demographics,
qualifications, nationality) are deliberately not copied: they are not the
claim's material, and the workbook is archived in full.

THE GEOGRAPHY RULE. `area_code` is the workbook's own ONS code, and rows are
joined to the authorities table only by that code — never by name, which is
m07/m12's matching labour and not this module's. Rows whose area code this
warehouse does not recognise are stored with the code verbatim; the join is
the caller's to make, exactly as the workbook published it.

The licence test names this module under the `skills_for_care` entry: OGL
v3.0 for the ASC-WDS data per the data.gov.uk catalogue entry, with the
publisher's own site-wide copyright line stated beside it (a permission is
only asserted where the catalogue grants it). The figures are official
statistics under the Office for Statistics Regulation's Code of Practice.
"""
from __future__ import annotations

import json
import re
import zipfile

import structlog

from pipeline import db
from pipeline.http import PipelineHTTPClient
from pipeline.registry import ModuleContext, register_module
from pipeline.xlsx import XlsxError, iter_sheet, sheet_names

log = structlog.get_logger()

SOURCE_SYSTEM = "skills_for_care"
DOWNLOADS_PAGE = ("https://www.skillsforcare.org.uk/Adult-Social-Care-Workforce-Data/"
                  "workforceintelligence/About-our-data/Data-downloads.aspx")

# The data sheets' header vocabulary. The parser keys on these column names
# rather than on sheet names or offsets: the sheet name carries the year
# ('Region area 2024-25'), and the workbook's own labels are the only stable
# part of its shape.
DATA_HEADER_NAMES = {
    "year": "Year",
    "area_code": "Area code",
    "area_level": "Area Level",
    "region": "Region",
    "area": "Area",
    "sector": "Sector",
    "service": "Service",
    "job_role_group": "Job role group",
    "job_role": "Job role",
    "fte_annual_pay": "FTE Annual Pay",
    "hourly_pay": "Hourly Pay",
    "turnover_rate": "Turnover rate",
    "vacancy_rate": "Vacancy rate",
}

# The link to a current-year data download. The five files share a directory
# and a prefix, and the three current-year ones share the data-sheet shape;
# the appendix and trended files are fetched but not parsed (see docstring).
_CURRENT_YEAR_LINK_RE = re.compile(
    r'([^"]*)resources/Our-data/Current-year-data-download-[^"]*\.xlsx',
    re.IGNORECASE)
_ALL_FILES_RE = re.compile(
    r'<a[^>]*href="([^"]*resources/Our-data/[^"]*\.xlsx)"[^>]*>'
    r'(?:<[^>]*>)*([^<]{1,120})', re.IGNORECASE | re.DOTALL)

# '*' is the publisher's own suppression marker in the data sheets (ASC-WDS
# rounds and suppresses small-cell estimates). It is a deliberate absence, not
# a parse failure: the workbook is saying "no figure is published here", and
# NULL is the honest storage for that.
SUPPRESSION_MARKER = "*"

_NUMBER_RE = re.compile(r"^[£]?([0-9][0-9,]*)(\.\d+)?([eE][+-]?\d+)?$")


def _as_number(raw: str) -> float | None:
    """A workbook cell as a number. Blank or the suppression marker is NULL;
    anything else unreadable is NULL too — the caller records the parse
    failure — and a number is never assumed."""
    text = (raw or "").strip()
    if not text or text == SUPPRESSION_MARKER:
        return None
    match = _NUMBER_RE.match(text)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "") + (match.group(2) or "")
                     + (match.group(3) or ""))
    except ValueError:
        return None


def _find_data_sheet(rows_by_name: dict[str, list[dict[str, str]]]) -> tuple[str, list[dict[str, str]]] | None:
    """The sheet whose header row names the standard columns.

    Returns (sheet_name, rows) or None. A sheet is only the data sheet when
    its first row names the workbook's own identifiers AND the pay column —
    either alone could be a glossary table that happens to share a word.
    """
    for name, rows in rows_by_name.items():
        if not rows:
            continue
        header = {k: str(v).strip().lower() for k, v in rows[0].items()}
        lowered = set(header.values())
        if {"area code", "job role", "hourly pay"} <= lowered:
            return name, rows
    return None


def parse_estimates(rows: list[dict[str, str]]) -> tuple[list[dict], list[tuple[str, str]]]:
    """The data sheet as estimate rows, plus parse failures.

    Rows come from `iter_sheet` as {column letter: value}; the first row is
    the header, which maps column letters to the workbook's column names.
    Reads by column name from the header; a row missing the identifiers is
    skipped (total rows, blank rows, footnotes). `area_code` is kept
    verbatim — the workbook's own ONS code, never matched here.

    A numeric cell that is neither blank nor the suppression marker and
    cannot be parsed is returned as a parse failure: the figure was
    published in an unreadable form, which is a fact about the workbook, not
    a missing value.
    """
    if not rows:
        return [], []
    header = {str(v).strip().lower(): k for k, v in rows[0].items()}
    names = {name: header[label.lower()] for name, label
             in DATA_HEADER_NAMES.items() if label.lower() in header}
    required = ("area_code", "area_level", "area", "sector", "service")
    if any(name not in names for name in required):
        return [], []

    out: list[dict] = []
    failures: list[tuple[str, str]] = []
    for row in rows[1:]:
        def cell(name: str) -> str:
            letter = names.get(name)
            if letter is None:
                return ""
            return (row.get(letter) or "").strip()

        area_code = cell("area_code")
        area_level = cell("area_level")
        area = cell("area")
        if not (area_code and area_level and area):
            continue

        def number(name: str) -> float | None:
            raw = cell(name)
            value = _as_number(raw)
            if value is None and raw and raw != SUPPRESSION_MARKER:
                failures.append((name, raw))
            return value

        out.append({
            "year": cell("year") or None,
            "area_code": area_code,
            "area_level": area_level,
            "region": cell("region") or None,
            "area": area,
            "sector": cell("sector"),
            "service": cell("service"),
            "job_role_group": cell("job_role_group") or None,
            "job_role": cell("job_role") or None,
            "fte_annual_pay": number("fte_annual_pay"),
            "hourly_pay": number("hourly_pay"),
            "turnover_rate": number("turnover_rate"),
            "vacancy_rate": number("vacancy_rate"),
        })
    return out, failures


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


@register_module(
    "m25_skills_for_care",
    supports_since=False,
    since_note="the module reads every current-year workbook the publisher's page names",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m25_skills_for_care"
    conn = ctx.conn
    written = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        page_result = client.get(DOWNLOADS_PAGE)
        if not page_result.ok:
            db.record_review_item(
                conn, module_name, "skills_for_care_page_unavailable", DOWNLOADS_PAGE,
                json.dumps({"status": page_result.status_code,
                             "note": "the Data downloads page did not answer; "
                                     "no workbooks were read"}))
            log.info("skills_for_care.run_complete", page="unavailable",
                      status=page_result.status_code)
            return
        page_html = page_result.body.decode("utf-8", "replace")

        # The five workbooks, in page order, with their link labels. The
        # regex allows the label to be empty (an icon link); the file is
        # still fetched.
        files = [(url, label.strip()) for url, label
                 in _ALL_FILES_RE.findall(page_html)]
        if not files:
            db.record_parse_failure(
                conn, module_name, "downloads_page", DOWNLOADS_PAGE,
                "no .xlsx workbook links parsed from the Data downloads page",
                source_url=page_result.url)
            log.info("skills_for_care.run_complete", page="no files parsed")
            return

        for file_url, label in ctx.track(files, "workbooks"):
            result = client.get(file_url)
            if not result.ok:
                db.record_review_item(
                    conn, module_name, "skills_for_care_file_unavailable", file_url,
                    json.dumps({"status": result.status_code, "label": label}))
                log.info("skills_for_care.file_unavailable", url=file_url,
                          status=result.status_code)
                continue

            current_year = _CURRENT_YEAR_LINK_RE.search(file_url) is not None
            if not current_year:
                # The appendix and trended workbooks are fetched, archived and
                # recorded, but their shapes are not this module's to parse —
                # report tables, and the change-over-time series F-05 declined.
                db.upsert(conn, "skills_for_care_files", {
                    "file_url": file_url,
                    "link_label": label or None,
                    "file_format": "xlsx",
                    "parse_status": "unreadable",
                    "row_count": None,
                    **_provenance(result),
                }, natural_key=["file_url"])
                db.record_review_item(
                    conn, module_name, "skills_for_care_shape_unread",
                    file_url,
                    json.dumps({"label": label,
                                 "note": "this workbook's shape is not parsed by "
                                         "m25; it is fetched and archived only. "
                                         "The appendix is report tables; the "
                                         "trended file is the change-over-time "
                                         "series that F-05 declined history for."}))
                if not ctx.dry_run:
                    conn.commit()
                continue

            try:
                sheets = {name: iter_sheet(result.body, name)
                          for name in sheet_names(result.body)}
            except (XlsxError, OSError, zipfile.BadZipFile) as exc:
                db.record_parse_failure(
                    conn, module_name, "workbook", file_url,
                    f"could not read the workbook as xlsx: {exc}",
                    source_url=result.url)
                db.upsert(conn, "skills_for_care_files", {
                    "file_url": file_url,
                    "link_label": label or None,
                    "file_format": "xlsx",
                    "parse_status": "unreadable",
                    "row_count": None,
                    **_provenance(result),
                }, natural_key=["file_url"])
                if not ctx.dry_run:
                    conn.commit()
                continue

            data_sheet = _find_data_sheet(sheets)
            if data_sheet is None:
                db.record_parse_failure(
                    conn, module_name, "data_sheet", file_url,
                    "no sheet carries the standard data columns (Area code, "
                    "Job role, Hourly Pay)",
                    source_url=result.url)
                db.upsert(conn, "skills_for_care_files", {
                    "file_url": file_url,
                    "link_label": label or None,
                    "file_format": "xlsx",
                    "parse_status": "unreadable",
                    "row_count": None,
                    **_provenance(result),
                }, natural_key=["file_url"])
                if not ctx.dry_run:
                    conn.commit()
                continue

            sheet_name, _rows = data_sheet
            estimates, failures = parse_estimates(_rows)
            for field, raw in failures:
                db.record_parse_failure(
                    conn, module_name, field, raw,
                    f"unreadable {field} value in {sheet_name!r} of {file_url}",
                    source_url=result.url)
            for estimate in estimates:
                db.upsert(conn, "skills_for_care_estimates", {
                    **estimate,
                    "file_url": file_url,
                    **_provenance(result),
                }, natural_key=["file_url", "year", "area_code", "sector",
                                "service", "job_role_group", "job_role"])
                written += 1

            db.upsert(conn, "skills_for_care_files", {
                "file_url": file_url,
                "link_label": label or None,
                "file_format": "xlsx",
                "parse_status": "parsed",
                "row_count": len(estimates),
                **_provenance(result),
            }, natural_key=["file_url"])

            if not ctx.dry_run:
                conn.commit()
            log.info("skills_for_care.file_parsed", url=file_url,
                      sheet=sheet_name, estimates=len(estimates))

    log.info("skills_for_care.run_complete", estimates=written)
