"""Module 3 — Charity finance.

Two distinct sources, kept as separate evidence layers (see migration 0008):

  1. Charity Commission register API — the financial history series
     (income, expenditure, and the income_from_govt_contracts /
     income_from_govt_grants split, which is directly campaign-relevant).
     Requires a free key; absent, the module fails with a clear message.

  2. The filed PDF accounts — everything the API does not expose: staff
     costs, wages and salaries, agency spend, average employee numbers and
     senior pay bands. Located from the register's accounts page and
     extracted with pdfplumber against a per-charity profile.

Two things this module refuses to do:

  * It never assumes the units of a figure. Accounts are normally presented
    in £000, but that is detected explicitly from the page and a note whose
    denomination cannot be determined stores NULL amounts plus a
    parse_failures row. A silent 1000x error in a pay campaign would be
    catastrophic.

  * It never conflates a headcount average with an FTE average. CGL's 2025
    accounts publish both (5,715 vs 4,623) and they differ by ~19%, so they
    are stored in separate columns with employees_basis recording which is
    which.
"""
from __future__ import annotations

import io
import json
import re
from datetime import date

import pdfplumber
import structlog

from pipeline import db, pdftext, providers
from pipeline.charity_accounts_config import AccountsProfile, profile_for
from pipeline.http import PipelineHTTPClient
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_API = "charity_commission_register_api"
SOURCE_ACCOUNTS = "charity_commission_filed_accounts"

API_BASE = "https://api.charitycommission.gov.uk/register/api"
REGISTER_BASE = "https://register-of-charities.charitycommission.gov.uk"
ACCOUNTS_PAGE = REGISTER_BASE + "/en/charity-search/-/charity-details/{org_number}/accounts-and-annual-returns"

# <a aria-label="Download the accounts and TAR submitted on 31 March 2025, PDF" ... href="...">
ACCOUNTS_LINK_RE = re.compile(
    r'<a\s+aria-label="([^"]+)"[^>]*class="[^"]*accounts-download-link[^"]*"[^>]*href="([^"]+)"',
    re.IGNORECASE | re.DOTALL,
)
SUBMITTED_DATE_RE = re.compile(r"submitted on (\d{1,2} \w+ \d{4})", re.IGNORECASE)

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], start=1)}

# "£60,000 to £69,999   59   46"  -> band, current year count, prior year count
PAY_BAND_RE = re.compile(
    r"£\s?([\d,]+)\s*(?:to|-|–)\s*£?\s?([\d,]+)\s+(\d[\d,]*|[-–—])\s+(\d[\d,]*|[-–—])"
)

# Denomination markers as they appear in accounts tables. The apostrophe in
# "£'000" is typically a typographic right single quote (U+2019) rather than
# an ASCII apostrophe, and may be absent entirely, so all forms are accepted.
_APOS = r"[’‘'`´]?"
MULTIPLIER_PATTERNS: list[tuple[re.Pattern, int]] = [
    (re.compile(rf"£\s*{_APOS}\s*000|\bin thousands\b", re.IGNORECASE), 1000),
    (re.compile(rf"£\s*{_APOS}\s*m\b|\bin millions\b|£\s?million", re.IGNORECASE), 1_000_000),
]


class CharityFinanceError(RuntimeError):
    """Unrecoverable problem talking to the Charity Commission."""


def _to_number(raw: str) -> float | None:
    """Accounts use an en/em dash for nil. Returns None for anything that
    isn't a parseable number — callers log a failure rather than defaulting.
    """
    text = (raw or "").strip().replace(",", "").replace("£", "")
    if text in {"-", "–", "—", ""}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return None


def detect_amounts_multiplier(page_text: str) -> int | None:
    """Detect whether a note is denominated in units, £000 or £m.
    Returns None when it cannot be determined — never a default.
    """
    for pattern, multiplier in MULTIPLIER_PATTERNS:
        if pattern.search(page_text or ""):
            return multiplier
    return None


_NUMBER_TOKEN = r"(?:-|–|—|\d[\d,]*(?:\.\d+)?)"
_LEADING_NUMBERS_RE = re.compile(rf"^\s*({_NUMBER_TOKEN})(?:\s+({_NUMBER_TOKEN}))?")


def _match_labelled_numbers(page_text: str, labels: list[str], count: int = 2) -> list[float] | None:
    """Find `labels` followed by its figures, returning up to `count` of
    them (accounts tables give the current year first, then the comparative).

    Two passes, strictest first:

    1. Label at the start of a line — the normal table shape, unambiguous.
    2. Label mid-line, but only when immediately followed by at least two
       consecutive numbers. This is needed because accounts are typeset in
       columns and pdfplumber interleaves them, so a real table row can
       surface as "...disclosed in note 20. Average number of employees
       4,933 4,380". Requiring two adjacent numbers is what keeps this from
       matching prose like "wages and salaries rose 12 per cent", where the
       label is followed by a single number and then words.
    """
    text = page_text or ""
    lowered_labels = [(label, label.lower()) for label in labels]

    for line in text.splitlines():
        stripped = line.strip()
        low = stripped.lower()
        for _label, low_label in lowered_labels:
            if low.startswith(low_label):
                numbers = re.findall(_NUMBER_TOKEN, stripped[len(low_label):])
                parsed = [_to_number(n) for n in numbers[:count]]
                if parsed and parsed[0] is not None:
                    return parsed

    for line in text.splitlines():
        low = line.lower()
        for _label, low_label in lowered_labels:
            index = low.find(low_label)
            if index == -1:
                continue
            m = _LEADING_NUMBERS_RE.match(line[index + len(low_label):])
            if not m or m.group(2) is None:
                continue  # need two adjacent numbers to trust a mid-line hit
            parsed = [_to_number(g) for g in m.groups()[:count] if g is not None]
            if parsed and parsed[0] is not None:
                return parsed
    return None


def extract_pay_bands(page_text: str) -> tuple[list[dict], int | None]:
    """Senior pay bands and their total headcount. Returns ([], None) when
    the note has no band table.
    """
    bands = []
    for m in PAY_BAND_RE.finditer(page_text or ""):
        lower = _to_number(m.group(1))
        upper = _to_number(m.group(2))
        current = _to_number(m.group(3))
        if lower is None or current is None:
            continue
        bands.append({
            "band_lower": lower,
            "band_upper": upper,
            "employees": int(current),
        })
    total = int(sum(b["employees"] for b in bands)) if bands else None
    return bands, total


def find_staff_costs_pages(pages: list[str], profile: AccountsProfile) -> list[tuple[int, str]]:
    """Locate the staff-costs note in already-extracted page text.

    Returns EVERY matching page, not just the first: the note routinely runs
    across a spread (CGL's 2025 accounts put the staff-costs table on one
    page and the employee-numbers table on the next), and reading only the
    first page silently loses whichever figures live on the second.

    Takes text rather than a pdfplumber.PDF so the expensive extraction
    happens once, in pipeline/pdftext.py, and is shared with m14 — which was
    re-extracting the same archived files at 16–23 seconds each.
    """
    matches: list[tuple[int, str]] = []
    for i, text in enumerate(pages):
        low = (text or "").lower()
        for group in profile.locator_keywords:
            if all(k.lower() in low for k in group):
                matches.append((i, text or ""))
                break
    return matches


def extract_accounts_figures(pdf_bytes: bytes, profile: AccountsProfile,
                              settings=None, sha256: str | None = None) -> dict:
    """Pull staff-cost figures out of a filed accounts PDF.

    Thin wrapper: locates the note's pages and delegates to
    extract_figures_from_text, which holds all the parsing logic and is
    testable against a text fixture without shipping a multi-megabyte PDF.

    Pass `settings` and `sha256` to route extraction through the shared page
    cache; without them it extracts directly, which is what the unit tests do.
    """
    if settings is not None and sha256:
        pages = pdftext.page_texts(settings, SOURCE_ACCOUNTS, sha256, pdf_bytes)
    else:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]

    page_count = len(pages)
    located = find_staff_costs_pages(pages, profile)

    if not located:
        return {"page_count": page_count,
                "_problems": ["no page matching the staff-costs locator keywords"]}

    page_index = located[0][0]
    # Concatenate every page of the note so a field on the second page is
    # still found; raw_text_block keeps all of it for eyeball verification.
    page_text = "\n".join(text for _, text in located)

    result = extract_figures_from_text(page_text, profile)
    result["page_count"] = page_count
    result["extraction_page"] = page_index
    return result


def extract_figures_from_text(page_text: str, profile: AccountsProfile) -> dict:
    """Parse staff-cost figures from the text of a charity's staff-costs note.

    Returns a dict that always includes `_problems`: a list of
    human-readable reasons a field could not be extracted. Fields that
    could not be read are None — never approximated.
    """
    result: dict = {"_problems": []}
    result["raw_text_block"] = page_text

    multiplier = detect_amounts_multiplier(page_text)
    result["amounts_multiplier"] = multiplier
    if multiplier is None:
        result["_problems"].append(
            "could not determine whether amounts are in units, £000 or £m; "
            "monetary fields left NULL rather than assumed"
        )

    def money(labels: list[str], key: str) -> None:
        found = _match_labelled_numbers(page_text, labels)
        if found is None or found[0] is None:
            result[key] = None
            result["_problems"].append(f"{key}: no matching labelled line")
            return
        result[key] = found[0] * multiplier if multiplier else None

    money(profile.wages_and_salaries, "wages_and_salaries")
    money(profile.social_security_costs, "social_security_costs")
    money(profile.pension_costs, "pension_costs")
    money(profile.agency_and_third_party, "agency_and_third_party")
    money(profile.redundancy_costs, "redundancy_costs")

    # Employee counts are plain counts, never scaled by the money multiplier.
    headcount = _match_labelled_numbers(page_text, profile.average_employees)
    result["average_employees"] = headcount[0] if headcount else None
    result["employees_basis"] = profile.employees_basis if headcount else "unknown"
    if headcount is None:
        result["_problems"].append("average_employees: no matching labelled line")

    fte = _match_labelled_numbers(page_text, profile.average_employees_fte)
    result["average_employees_fte"] = fte[0] if fte else None

    bands, band_total = extract_pay_bands(page_text)
    result["senior_pay_bands_json"] = json.dumps(bands) if bands else None
    result["senior_pay_band_headcount"] = band_total

    # Staff costs total: only accepted if it is at least the wages figure,
    # since "TOTAL" appears more than once on a two-column page (the pay-band
    # table has its own). This is a validation, not an inference — a value
    # failing it is discarded and logged.
    total_candidates = []
    for line in page_text.splitlines():
        m = re.match(r"^\s*TOTAL\s+([\d,]+)", line, re.IGNORECASE)
        if m:
            value = _to_number(m.group(1))
            if value is not None:
                total_candidates.append(value)
    wages = result.get("wages_and_salaries")
    staff_total = None
    if multiplier and wages:
        for candidate in total_candidates:
            if candidate * multiplier >= wages:
                staff_total = candidate * multiplier
                break
    result["staff_costs_total"] = staff_total
    if staff_total is None:
        result["_problems"].append(
            "staff_costs_total: no TOTAL line at least as large as wages "
            "(page has multiple TOTAL rows); left NULL"
        )

    km = re.search(r"key management personnel[^.]*?comprises\s+(\d+)", page_text, re.IGNORECASE)
    result["key_management_headcount"] = int(km.group(1)) if km else None
    km_pay = re.search(
        r"key management personnel were\s*£\s?([\d,]+)", page_text, re.IGNORECASE)
    result["key_management_remuneration"] = _to_number(km_pay.group(1)) if km_pay else None

    return result


def parse_accounts_links(html: str) -> list[dict]:
    """Accounts PDF links from a charity's accounts-and-annual-returns page,
    with the financial period end date parsed from the link's aria-label.
    """
    documents = []
    for label, href in ACCOUNTS_LINK_RE.findall(html or ""):
        m = SUBMITTED_DATE_RE.search(label)
        if not m:
            continue
        day, month_name, year = m.group(1).split()
        month = MONTHS.get(month_name.lower())
        if month is None:
            continue
        url = href.replace("&amp;", "&")
        documents.append({
            "financial_year_end": date(int(year), month, int(day)).isoformat(),
            "document_url": url,
            "document_label": label,
        })
    return documents


def _provenance(result, source_system: str) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": source_system,
        "payload_sha256": result.payload_sha256,
    }


def _target_charities(conn) -> list[tuple[str, str]]:
    """(provider_key, charity_number) for every provider with a charity
    number on file. Unverified identifiers are included — Module 3 is one of
    the things that helps confirm them — but the status is logged.
    """
    rows = conn.execute(
        "SELECT provider_key, identifier, status FROM provider_identifiers "
        "WHERE scheme = 'charity_number' ORDER BY provider_key"
    ).fetchall()
    return [(r["provider_key"], r["identifier"]) for r in rows]


@register_module("m03_charity_finance", supports_since=True)
def run(ctx: ModuleContext) -> None:
    module_name = "m03_charity_finance"
    conn = ctx.conn
    api_key = ctx.settings.require_charity_commission_key()
    providers.seed_providers(conn, commit=not ctx.dry_run)

    targets = _target_charities(conn)
    if not targets:
        log.info("charity.no_targets",
                  note="no provider has a charity_number in provider_identifiers")
        return

    financial_rows = 0
    extract_rows = 0

    with PipelineHTTPClient(SOURCE_API, settings=ctx.settings, conn=conn) as api_client:
        headers = {"Ocp-Apim-Subscription-Key": api_key}

        ctx.phase("reading register")
        for provider_key, charity_number in ctx.track(targets, "charities"):
            details = api_client.get(f"{API_BASE}/allcharitydetailsV2/{charity_number}/0", headers=headers)
            if not details.ok:
                db.record_review_item(conn, module_name, "charity_details_unavailable", charity_number,
                                       json.dumps({"provider_key": provider_key,
                                                    "status": details.status_code}))
                continue
            detail_data = json.loads(details.body)
            org_number = detail_data.get("organisation_number")

            # The register publishes the charity's company number; record it
            # so Module 4 has a verified starting point instead of searching
            # Companies House by name.
            company_number = detail_data.get("charity_co_reg_number")
            if company_number:
                providers.record_discovered_identifier(
                    conn, provider_key, "company_number", str(company_number).strip(),
                    discovered_by=module_name, role="charity's registered company",
                )

            history = api_client.get(f"{API_BASE}/charityfinancialhistory/{charity_number}/0", headers=headers)
            if not history.ok:
                db.record_review_item(conn, module_name, "charity_financial_history_unavailable",
                                       charity_number, json.dumps({"status": history.status_code}))
            else:
                for row in json.loads(history.body):
                    period_end = (row.get("financial_period_end_date") or "")[:10]
                    if ctx.is_before_since(period_end):
                        continue
                    if not period_end:
                        db.record_parse_failure(conn, module_name, "financial_period_end_date",
                                                 json.dumps(row)[:300], "missing period end date",
                                                 source_url=history.url)
                        continue
                    db.upsert(conn, "charity_financials", {
                        "charity_number": charity_number,
                        "financial_year_end": period_end,
                        "ar_cycle_reference": row.get("ar_cycle_reference"),
                        "total_income": row.get("income"),
                        "total_expenditure": row.get("expenditure"),
                        "income_from_govt_contracts": row.get("income_from_govt_contracts"),
                        "income_from_govt_grants": row.get("income_from_govt_grants"),
                        "inc_charitable_activities": row.get("inc_charitable_activities"),
                        "exp_charitable_activities": row.get("exp_charitable_activities"),
                        "consolidated_account": 1 if row.get("consolidated_account") else 0,
                        **_provenance(history, SOURCE_API),
                    }, natural_key=["charity_number", "financial_year_end"])
                    financial_rows += 1

            if not ctx.dry_run:
                conn.commit()

            if org_number is None:
                db.record_review_item(conn, module_name, "no_organisation_number", charity_number,
                                       json.dumps({"note": "cannot locate accounts page without it"}))
                continue

            # --- filed accounts PDFs -------------------------------------
            with PipelineHTTPClient(SOURCE_ACCOUNTS, settings=ctx.settings, conn=conn) as doc_client:
                page = doc_client.get(ACCOUNTS_PAGE.format(org_number=org_number))
                if not page.ok:
                    db.record_review_item(conn, module_name, "accounts_page_unavailable", charity_number,
                                           json.dumps({"status": page.status_code}))
                    continue

                documents = parse_accounts_links(page.body.decode("utf-8", errors="ignore"))
                if not documents:
                    db.record_review_item(conn, module_name, "no_accounts_documents_found", charity_number,
                                           json.dumps({"org_number": org_number}))
                    continue

                if ctx.limit:
                    documents = documents[:ctx.limit]

                profile = profile_for(charity_number)
                for doc in documents:
                    pdf_result = doc_client.get(doc["document_url"])
                    if not pdf_result.ok:
                        db.record_review_item(conn, module_name, "accounts_pdf_unavailable",
                                               doc["document_url"],
                                               json.dumps({"charity_number": charity_number,
                                                            "status": pdf_result.status_code}))
                        continue

                    try:
                        figures = extract_accounts_figures(
                            pdf_result.body, profile, settings=ctx.settings,
                            sha256=pdf_result.payload_sha256)
                    except Exception as exc:  # a malformed PDF must not kill the run
                        db.record_review_item(conn, module_name, "accounts_pdf_unreadable",
                                               doc["document_url"],
                                               json.dumps({"charity_number": charity_number,
                                                            "error": f"{type(exc).__name__}: {exc}"}))
                        continue

                    db.upsert(conn, "charity_accounts_documents", {
                        "charity_number": charity_number,
                        "financial_year_end": doc["financial_year_end"],
                        "document_url": doc["document_url"],
                        "document_label": doc["document_label"],
                        "archived_path": str(pdf_result.archived_path) if pdf_result.archived_path else None,
                        "page_count": figures.get("page_count"),
                        **_provenance(pdf_result, SOURCE_ACCOUNTS),
                    }, natural_key=["charity_number", "financial_year_end"])

                    problems = figures.pop("_problems", [])
                    for problem in problems:
                        db.record_parse_failure(
                            conn, module_name, problem.split(":")[0],
                            f"{charity_number} {doc['financial_year_end']}", problem,
                            source_url=doc["document_url"],
                        )
                    if problems:
                        db.record_review_item(
                            conn, module_name, "accounts_partially_parsed", doc["document_url"],
                            json.dumps({"charity_number": charity_number,
                                         "financial_year_end": doc["financial_year_end"],
                                         "problems": problems}),
                        )

                    figures.pop("page_count", None)
                    db.upsert(conn, "charity_accounts_extracts", {
                        "charity_number": charity_number,
                        "financial_year_end": doc["financial_year_end"],
                        **{k: figures.get(k) for k in (
                            "amounts_multiplier", "staff_costs_total", "wages_and_salaries",
                            "social_security_costs", "pension_costs", "agency_and_third_party",
                            "redundancy_costs", "average_employees", "employees_basis",
                            "average_employees_fte", "senior_pay_bands_json",
                            "senior_pay_band_headcount", "key_management_remuneration",
                            "key_management_headcount", "extraction_page", "raw_text_block",
                        )},
                        **_provenance(pdf_result, SOURCE_ACCOUNTS),
                    }, natural_key=["charity_number", "financial_year_end"])
                    extract_rows += 1

                    if not ctx.dry_run:
                        conn.commit()

            log.info("charity.provider_complete", provider_key=provider_key, charity_number=charity_number)

    log.info("charity.run_complete", financial_rows=financial_rows, extract_rows=extract_rows)
