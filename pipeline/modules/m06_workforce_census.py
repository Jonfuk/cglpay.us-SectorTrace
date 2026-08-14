"""Module 6 — National workforce census.

The Drug and Alcohol Treatment and Recovery Services Workforce Census is
published as a PDF report per year by the NHS Benchmarking Network for NHS
England (2022's edition sits on the HEE site). Report URLs are discovered
from the census landing page and the national reports archive rather than
hardcoded, because they move between hosts between years.

Extraction is deliberately cautious. The three published years phrase the
same statistic completely differently —

    2022: "Vacancy, sickness absence and turnover rates for all staff were
           11%, 4% and 19% respectively"
    2023: "An overall vacancy rate of 10% was reported"
    2024: "8% vacancy rate in the delivery workforce"

— and 2023's report is laid out in two columns, which pdfplumber
interleaves. So rather than pretend a single parser can read these reliably,
every metric is stored with the verbatim line it came from, every page's
full text is retained, and nothing is marked verified automatically.

Where the checking happens: the Census tab of the operator UI, over
`workforce_census_page_text` — which is why this module keeps every page it
reads even though nothing else queries the table. Each figure is shown beside
its own parsed line and beside the whole page that line sits on, and a
decision is recorded against a named person (`pipeline/census_verify.py`,
migration 0033). This module used to write a markdown worklist per year
instead, pairing each value with its line and printing an `UPDATE ... WHERE
census_year = ?` at the top; that route is gone and the database now refuses
that statement. It set twenty flags on one statement, attributed them to
nobody, and could not tell you afterwards whether a page had been read.

Two things this module will not do:

  * Attribute any figure to a named provider. The census publishes
    sector-level aggregates only, and there is no provider-level breakdown
    to attribute from.
  * Compute year-on-year changes. Provider participation varies between
    rounds and the reports say so themselves, so differencing two years
    here would manufacture a trend the source does not support.
"""
from __future__ import annotations

import io
import json
import re

import pdfplumber
import structlog

from pipeline import db
from pipeline.http import PipelineHTTPClient
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "nhs_workforce_census"
LANDING_PAGES = [
    "https://www.wfbenchmarking.nhs.uk/drug-and-alcohol-treatment-and-recovery",
    "https://www.wfbenchmarking.nhs.uk/national-reports-archive",
]
SITE_ROOT = "https://www.wfbenchmarking.nhs.uk"

# A census report PDF: must mention drug/alcohol AND workforce AND a year.
REPORT_LINK_RE = re.compile(r'href="([^"]+\.pdf[^"]*)"', re.IGNORECASE)
YEAR_RE = re.compile(r"(20\d{2})")

# "delivery" is the census's own term for treatment providers and LEROs
# combined, so a line using it is unambiguous even though it also mentions
# those components. Checked before the individual segments for that reason.
_COMPOUND_SEGMENT_RE = re.compile(
    r"delivery workforce|treatment provider and lero", re.IGNORECASE)

_SEGMENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("commissioning", re.compile(r"commission", re.IGNORECASE)),
    ("treatment_provider", re.compile(r"treatment provider", re.IGNORECASE)),
    ("lero", re.compile(r"\blero\b", re.IGNORECASE)),
    ("all_staff", re.compile(r"all staff|all sectors|overall", re.IGNORECASE)),
]

# Percentage-bearing metrics. Each pattern must capture the number in group 1.
# Both orderings are needed: "8% vacancy rate" (2024) and "vacancy rate of
# 10%" (2023) both occur in real reports.
_PERCENT_METRICS: list[tuple[str, list[re.Pattern]]] = [
    ("vacancy_rate", [
        re.compile(r"(\d{1,3})%\s+vacancy rate", re.IGNORECASE),
        re.compile(r"vacancy rate[^.%\d]{0,30}?(\d{1,3})%", re.IGNORECASE),
    ]),
    ("turnover_rate", [
        re.compile(r"(\d{1,3})%\s+turnover rate", re.IGNORECASE),
        re.compile(r"turnover rate[^.%\d]{0,30}?(\d{1,3})%", re.IGNORECASE),
    ]),
    ("volunteer_share", [
        re.compile(r"(\d{1,3})%\s+of the [^.]{0,60}workforce were unpaid or volunteers", re.IGNORECASE),
    ]),
    ("full_time_share", [
        re.compile(r"(\d{1,3})%\s+of the [^.]{0,60}workforce was contracted to work full time", re.IGNORECASE),
    ]),
    ("voluntary_sector_share", [
        re.compile(r"(\d{1,3})%\s+of the treatment provider workforce was in the voluntary sector", re.IGNORECASE),
    ]),
]

_WTE_TOTAL_PATTERNS = [
    re.compile(r"([\d,]{3,})\s+whole time equivalents?\s*\(WTEs?\)", re.IGNORECASE),
    re.compile(r"([\d,]{3,})\s+whole time equivalent\s*\(WTE\)\s*staff", re.IGNORECASE),
]


def _to_number(raw: str) -> float | None:
    try:
        return float(raw.replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def classify_segment(line: str) -> str:
    """Which part of the workforce a line is talking about.

    Returns 'ambiguous' when a line names more than one segment, rather than
    picking by priority order. A real 2022 line reads:

        "Across all sectors 11,851 whole time equivalent (WTE) staff were
         reported, 11,269 WTE (95%) for the treatment provider workforce,
         398 WTE (3%) commissioning staff"

    which names all three. Resolving that by an arbitrary rule attributed the
    all-sectors total of 11,851 to the commissioning workforce, which in fact
    has 398 — a 30x error that looks entirely plausible in a table. Ambiguous
    rows are still stored with their source line for human resolution.
    """
    text = line or ""
    if _COMPOUND_SEGMENT_RE.search(text):
        return "delivery"

    matched = [segment for segment, pattern in _SEGMENT_PATTERNS if pattern.search(text)]
    if not matched:
        return "unspecified"
    if len(matched) > 1:
        return "ambiguous"
    return matched[0]


def extract_metrics_from_text(page_text: str, page_number: int) -> list[dict]:
    """Candidate metrics from one page.

    Deliberately line-scoped: a value and the words that qualify it must
    appear on the same line, so a percentage cannot be attached to a metric
    mentioned in a different sentence. Every hit keeps its source line.
    """
    found: list[dict] = []
    seen: set[tuple] = set()

    for line in (page_text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        for metric, patterns in _PERCENT_METRICS:
            for pattern in patterns:
                m = pattern.search(stripped)
                if not m:
                    continue
                value = _to_number(m.group(1))
                if value is None or not (0 <= value <= 100):
                    continue
                key = (metric, classify_segment(stripped), stripped)
                if key in seen:
                    continue
                seen.add(key)
                found.append({
                    "metric": metric,
                    "workforce_segment": classify_segment(stripped),
                    "value": value,
                    "unit": "percent",
                    "source_page": page_number,
                    "raw_text": stripped,
                })
                break

        for pattern in _WTE_TOTAL_PATTERNS:
            m = pattern.search(stripped)
            if not m:
                continue
            value = _to_number(m.group(1))
            if value is None or value <= 0:
                continue
            key = ("wte_total", classify_segment(stripped), stripped)
            if key in seen:
                continue
            seen.add(key)
            found.append({
                "metric": "wte_total",
                "workforce_segment": classify_segment(stripped),
                "value": value,
                "unit": "wte",
                "source_page": page_number,
                "raw_text": stripped,
            })
            break

    return found


def discover_reports(html: str, base_url: str = SITE_ROOT) -> list[dict]:
    """Census report PDFs linked from a landing page, with their year."""
    reports: dict[int, dict] = {}
    for href in REPORT_LINK_RE.findall(html or ""):
        url = href.replace("&amp;", "&")
        decoded = url.replace("%20", " ")
        # Subject must be drug/alcohol, but the 2024 report is filed as
        # "DA-workforce-census-FINAL-report-2024.pdf" — requiring the word
        # "drug" silently dropped the most recent year. Requiring "workforce"
        # AND "census" alongside keeps the DA- abbreviation safe and still
        # rejects e.g. mental-health-workforce-census-2024.pdf and DA-FAQs.pdf.
        if not re.search(r"drug|alcohol|\bDA[-_ ]", decoded, re.IGNORECASE):
            continue
        if not re.search(r"workforce", decoded, re.IGNORECASE):
            continue
        if not re.search(r"census", decoded, re.IGNORECASE):
            continue
        years = [int(y) for y in YEAR_RE.findall(decoded)]
        # Report filenames can carry a publication date as well as the census
        # year (…Census 2022 Final Report 20230301.pdf); the census year is
        # the smallest plausible year present.
        plausible = [y for y in years if 2015 <= y <= 2100]
        if not plausible:
            continue
        year = min(plausible)
        if url.startswith("/"):
            url = f"{base_url}{url}"
        reports.setdefault(year, {"census_year": year, "document_url": url})
    return sorted(reports.values(), key=lambda r: r["census_year"])


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


@register_module("m06_workforce_census", supports_since=True)
def run(ctx: ModuleContext) -> None:
    module_name = "m06_workforce_census"
    conn = ctx.conn

    reports: dict[int, dict] = {}
    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        ctx.phase("finding reports")
        for landing in LANDING_PAGES:
            page = client.get(landing)
            if not page.ok:
                db.record_review_item(conn, module_name, "census_landing_page_unavailable", landing,
                                       json.dumps({"status": page.status_code}))
                continue
            for report in discover_reports(page.body.decode("utf-8", errors="ignore")):
                reports.setdefault(report["census_year"], report)

        if not reports:
            raise RuntimeError(
                "No workforce census reports discovered — the landing page layout or link "
                "naming may have changed. Check LANDING_PAGES in m06_workforce_census."
            )
        log.info("census.reports_discovered", years=sorted(reports))

        metrics_written = 0
        since_year = ctx.since_year()
        for year in ctx.track(sorted(reports), "census years"):
            if since_year and year < since_year:
                continue
            document_url = reports[year]["document_url"]
            pdf_result = client.get(document_url)
            if not pdf_result.ok:
                db.record_review_item(conn, module_name, "census_report_unavailable", document_url,
                                       json.dumps({"census_year": year,
                                                    "status": pdf_result.status_code}))
                continue

            try:
                with pdfplumber.open(io.BytesIO(pdf_result.body)) as pdf:
                    pages = [(i, page.extract_text() or "") for i, page in enumerate(pdf.pages)]
            except Exception as exc:
                db.record_review_item(conn, module_name, "census_report_unreadable", document_url,
                                       json.dumps({"census_year": year,
                                                    "error": f"{type(exc).__name__}: {exc}"}))
                continue

            provenance = _provenance(pdf_result)
            db.upsert(conn, "workforce_census_reports", {
                "census_year": year,
                "report_title": f"Drug and Alcohol Workforce Census {year}",
                "document_url": document_url,
                "archived_path": str(pdf_result.archived_path) if pdf_result.archived_path else None,
                "page_count": len(pages),
                "publisher": "NHS Benchmarking Network / NHS England",
                **provenance,
            }, natural_key=["census_year"])

            year_metrics: list[dict] = []
            for page_number, page_text in pages:
                if not page_text.strip():
                    continue
                db.upsert(conn, "workforce_census_page_text", {
                    "census_year": year,
                    "page_number": page_number,
                    "page_text": page_text,
                    **provenance,
                }, natural_key=["census_year", "page_number"])

                for metric in extract_metrics_from_text(page_text, page_number):
                    db.upsert(conn, "workforce_census_metrics", {
                        "census_year": year,
                        **metric,
                        # Preserved: a figure somebody has checked against its
                        # page must not go back to unchecked because the module
                        # re-read the same line. Migration 0033 gave this table
                        # the other two DECISION_COLUMNS, so `preserve` now
                        # covers all three rather than one by accident.
                        "verified": 0,
                        **provenance,
                    }, natural_key=["census_year", "metric", "workforce_segment", "raw_text"],
                        preserve=db.DECISION_COLUMNS)
                    year_metrics.append(metric)
                    metrics_written += 1

            if not year_metrics:
                db.record_parse_failure(
                    conn, module_name, "metrics", f"census {year}",
                    "no metrics matched any known phrasing in this report",
                    source_url=document_url)

            log.info("census.year_processed", year=year, pages=len(pages),
                      metrics=len(year_metrics))

            if not ctx.dry_run:
                conn.commit()

    log.info("census.run_complete", years=len(reports), metrics=metrics_written)
