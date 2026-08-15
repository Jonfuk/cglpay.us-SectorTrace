"""Module 20 — gender pay gap reports.

A mandatory annual public filing: employers with 250 or more staff on their
snapshot date must report their gender pay gap to the Gender Pay Gap service,
which publishes one bulk CSV per reporting year at `/viewing/download-data`.
This is the sector's own compulsory disclosure — every tracked provider that
is large enough to file is here, or its absence is a recorded fact.

WHAT THIS MODULE RECORDS, AND DELIBERATELY DOES NOT:

  * One row per MATCHED filing. A provider is matched to a CSV row by
    company number (the identifiers m04 discovered, normalised the same way)
    or, failing that, by exact normalised name against the provider's own
    name variants — the m18 discipline: a shared name is not a shared
    identity, and here the consequence of a wrong match is attributing a
    legal entity's statutory disclosure to the wrong employer.
  * **Absence is not a row.** A provider not in the file may be outside the
    law's reach (fewer than 250 staff) or may not have filed, and this
    module cannot tell which — so nothing is stored, and a
    `gender_pay_gap_absence` review item is raised per (provider, year)
    naming what was searched. The out-of-scope decision is the review
    queue's, and the claim shape the roadmap filed ("of the tracked
    providers that must file, X report a mean gender pay gap of Y%") is
    built from the decided set, never from a zero.
  * **`ResponsiblePerson` is not collected.** It is the name of the person
    who confirmed the figures — personal data this pipeline has no reason
    to hold. Every other column the file publishes is stored, verbatim,
    with blank cells as NULL (a blank is not a zero: a filing that left
    DiffMeanHourlyPercent blank is not a filing reporting 0%).
  * The figures are the employer's own submission, transcribed as
    published. The service does not audit them; neither does this module.

Which years: the download page lists every reporting year; a year "Y to
Y+1" is complete once the filing deadline (30 March / 4 April of Y+1) has
passed, and the module reads the newest YEARS_TO_FETCH completed years.
The partial-year file the service also lists (deadlines not yet passed) is
deliberately not read.

robots.txt: the service is a GOV.UK service under the standard GOV.UK
allow-all policy. Rate limit is the shared client's default.

Licence: OGL v3.0 (service content; the underlying data is statutory
disclosure).
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import date

import structlog

from pipeline import db, providers
from pipeline.http import PipelineHTTPClient
from pipeline.keywords import SUPPLIER_NAME_VARIANTS
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "gender_pay_gap_service"
DOWNLOAD_PAGE = "https://gender-pay-gap.service.gov.uk/viewing/download"
DATA_URL = "https://gender-pay-gap.service.gov.uk/viewing/download-data/{year}"

# How many completed reporting years each run reads. The newest is the one
# the campaign's claims will stand on; the older ones show the year-on-year
# record the source itself publishes. More years cost one 4 MB CSV each.
YEARS_TO_FETCH = 3

# The filing deadline is 30 March (public authorities) / 4 April (everyone
# else) of the year the reporting year ends in. A year is read once that
# has passed — the page's own sentence says the same thing, but a date rule
# is the same rule stated in a form a test can pin.
DEADLINE_MONTH_DAY = (4, 5)

# The CSV columns we store, in file order. ResponsiblePerson is deliberately
# absent — a person's name, personal data this pipeline does not hold.
_KEEP_COLUMNS = [
    "EmployerName", "EmployerId", "CompanyNumber", "SicCodes",
    "DiffMeanHourlyPercent", "DiffMedianHourlyPercent",
    "DiffMeanBonusPercent", "DiffMedianBonusPercent",
    "MaleBonusPercent", "FemaleBonusPercent",
    "MaleLowerQuartile", "FemaleLowerQuartile",
    "MaleLowerMiddleQuartile", "FemaleLowerMiddleQuartile",
    "MaleUpperMiddleQuartile", "FemaleUpperMiddleQuartile",
    "MaleTopQuartile", "FemaleTopQuartile",
    "CompanyLinkToGPGInfo", "EmployerSize", "CurrentName",
    "SubmittedAfterTheDeadline", "DueDate", "DateSubmitted",
]

_NUMERIC = {"DiffMeanHourlyPercent", "DiffMedianHourlyPercent",
            "DiffMeanBonusPercent", "DiffMedianBonusPercent",
            "MaleBonusPercent", "FemaleBonusPercent",
            "MaleLowerQuartile", "FemaleLowerQuartile",
            "MaleLowerMiddleQuartile", "FemaleLowerMiddleQuartile",
            "MaleUpperMiddleQuartile", "FemaleUpperMiddleQuartile",
            "MaleTopQuartile", "FemaleTopQuartile"}

_YEAR_LINK_RE = re.compile(
    r'href="[^"]*viewing/download-data/(\d{4})[^"]*"[^>]*>.*?'
    r"Reporting year\s+(\d{4}\s+to\s+\d{4})", re.IGNORECASE | re.DOTALL)

# Same whole-word normalisation family as m18: match on the words that
# distinguish an employer, drop the words that never do.
_STRIP_RE = re.compile(r"\b(limited|ltd|llp|plc|cic|trust|foundation|company|the)\b")


def _normalise_name(name: str) -> str:
    text = re.sub(r"[^\w\s]", " ", (name or "").lower())
    text = _STRIP_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _number(value: str) -> float | None:
    """A CSV cell as a number. Blank is NULL (not a zero); something that
    cannot be read is NULL too, and the verbatim row is kept in the table."""
    text = (value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def completed_years(years: list[int], today: date | None = None) -> list[int]:
    """The reporting years whose deadlines have passed, newest first."""
    today = today or date.today()
    return sorted(
        (y for y in years if (y + 1, *DEADLINE_MONTH_DAY) <= (today.year, today.month, today.day)),
        reverse=True)


def _year_rows(page_html: str) -> list[tuple[int, str]]:
    """(year, label) pairs from the download page, in page order."""
    out: list[tuple[int, str]] = []
    for match in _YEAR_LINK_RE.finditer(page_html or ""):
        try:
            out.append((int(match.group(1)), match.group(2)))
        except ValueError:
            continue
    return out


def parse_csv_rows(raw: bytes) -> list[dict]:
    """The bulk file as a list of dicts keyed by the service's column names.

    The file is real CSV: addresses contain commas and SIC lists span
    physical lines inside their quotes, so it goes through the csv module
    rather than being split on commas.
    """
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def _store_row(conn, module_name: str, row: dict, provider_key: str,
               match_basis: str, *, year: int, year_label: str, result) -> None:
    stored = {
        "provider_key": provider_key,
        "reporting_year": str(year),
        "reporting_year_label": year_label,
        "employer_id": row.get("EmployerId") or "",
        "match_basis": match_basis,
    }
    for column in _KEEP_COLUMNS:
        value = row.get(column)
        if column in _NUMERIC:
            stored[_column_to_field(column)] = _number(value)
        elif column == "SubmittedAfterTheDeadline":
            # The file writes TRUE/FALSE; the schema stores 0/1. Anything
            # else is NULL, never a guess at the deadline.
            stored[_column_to_field(column)] = (
                1 if (value or "").strip().lower() == "true"
                else 0 if (value or "").strip().lower() == "false" else None)
        else:
            stored[_column_to_field(column)] = (value or None) if value != "" else None
    stored.update({
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    })
    db.upsert(conn, "gender_pay_gap_reports", stored,
              natural_key=["provider_key", "reporting_year", "employer_id"])


def _column_to_field(column: str) -> str:
    """The CSV's PascalCase column names as the schema's snake_case.

    Two renames are deliberate. The schema calls CompanyLinkToGPGInfo
    `written_statement_url`, because that is what the column is — the
    address of the employer's own written statement — and
    SubmittedAfterTheDeadline is `submitted_after_deadline`, the schema
    dropping the article.
    """
    if column == "CompanyLinkToGPGInfo":
        return "written_statement_url"
    if column == "SubmittedAfterTheDeadline":
        return "submitted_after_deadline"
    words = re.findall(r"[A-Z]+[a-z]*|\d+", column)
    return "_".join(words).lower()


def _provider_lookups(conn) -> tuple[dict[str, str], dict[str, str]]:
    """(normalised company number -> provider_key, normalised name ->
    provider_key). Company numbers are authoritative when present; names are
    the fallback and carry the m18 exact-match discipline.
    """
    by_number: dict[str, str] = {}
    for row in conn.execute(
            "SELECT provider_key, identifier FROM provider_identifiers "
            "WHERE scheme = 'company_number'"):
        by_number[providers.normalise_identifier("company_number", row["identifier"])] = row["provider_key"]
    by_name: dict[str, str] = {}
    for provider_key, variants in SUPPLIER_NAME_VARIANTS.items():
        for variant in variants:
            normalised = _normalise_name(variant)
            if normalised:
                by_name.setdefault(normalised, provider_key)
    return by_number, by_name


def _match_row(row: dict, by_number: dict[str, str],
               by_name: dict[str, str]) -> tuple[str | None, str | None]:
    company_number = (row.get("CompanyNumber") or "").strip()
    if company_number:
        key = providers.normalise_identifier("company_number", company_number)
        provider_key = by_number.get(key)
        if provider_key:
            return provider_key, "company_number"
    name = _normalise_name(row.get("EmployerName"))
    if name:
        provider_key = by_name.get(name)
        if provider_key:
            return provider_key, "name_exact"
    return None, None


@register_module(
    "m20_gender_pay_gap",
    supports_since=False,
    depends_on=("m04_companies",),
    depends_note="company-number matching reads the identifiers m04 discovered",
    since_note="a filing is a statutory snapshot per reporting year, not a dated stream",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m20_gender_pay_gap"
    conn = ctx.conn
    providers.seed_providers(conn, commit=not ctx.dry_run)

    by_number, by_name = _provider_lookups(conn)

    written = 0
    absent = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        page_result = client.get(DOWNLOAD_PAGE)
        if not page_result.ok:
            db.record_review_item(
                conn, module_name, "gender_pay_gap_page_unavailable", DOWNLOAD_PAGE,
                json.dumps({"status": page_result.status_code,
                             "note": "the download page did not answer; no years were read"}))
            log.info("gender_pay_gap.run_complete", page="unavailable",
                      status=page_result.status_code)
            return

        page_html = page_result.body.decode("utf-8", "replace")
        years = [year for year, _label in _year_rows(page_html)]
        if not years:
            db.record_parse_failure(
                conn, module_name, "years_list", DOWNLOAD_PAGE,
                "no /viewing/download-data/{year} links parsed from the download page",
                source_url=page_result.url)
            log.info("gender_pay_gap.run_complete", page="no years parsed")
            return

        for year in ctx.track(completed_years(years)[:YEARS_TO_FETCH], "reporting years"):
            result = client.get(DATA_URL.format(year=year))
            if not result.ok:
                db.record_review_item(
                    conn, module_name, "gender_pay_gap_year_unavailable", str(year),
                    json.dumps({"status": result.status_code}))
                log.info("gender_pay_gap.year_unavailable", year=year,
                          status=result.status_code)
                continue

            matched_here: set[str] = set()
            try:
                rows = parse_csv_rows(result.body)
            except (UnicodeDecodeError, csv.Error) as exc:
                db.record_parse_failure(
                    conn, module_name, "year_csv", DATA_URL.format(year=year),
                    f"could not parse the year file as CSV: {exc}",
                    source_url=result.url)
                continue

            label = next((label for y, label in _year_rows(page_html) if y == year),
                         f"{year} to {year + 1}")
            for row in ctx.track(rows, f"{year} rows"):
                provider_key, match_basis = _match_row(row, by_number, by_name)
                if provider_key is None:
                    continue
                matched_here.add(provider_key)
                _store_row(conn, module_name, row, provider_key, match_basis,
                           year=year, year_label=label, result=result)
                written += 1

            # Absence is the review queue's, not a zero row. Every tracked
            # provider with no matched filing this year is named, with the
            # identifiers that were searched, so the out-of-scope decision
            # (fewer than 250 staff) is made against the actual record.
            for provider_key in sorted(SUPPLIER_NAME_VARIANTS):
                if provider_key in matched_here:
                    continue
                db.record_review_item(
                    conn, module_name, "gender_pay_gap_absence",
                    f"{provider_key} {year}",
                    json.dumps({
                        "reporting_year": str(year),
                        "searched_names": SUPPLIER_NAME_VARIANTS[provider_key][0],
                        "searched_company_numbers": sorted(
                            k for k, p in by_number.items() if p == provider_key),
                        "note": "no filing matched in the bulk file for this year: "
                                "either the provider is out of scope (fewer than 250 "
                                "staff on its snapshot date) or it did not file. "
                                "Decide which; never read the absence as a zero gap."}))
                absent += 1

            if not ctx.dry_run:
                conn.commit()

    log.info("gender_pay_gap.run_complete", filings=written,
              absent_provider_years=absent)
