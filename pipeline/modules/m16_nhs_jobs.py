"""Module 16 — NHS Jobs advertised pay.

The one source in this pipeline that publishes pay directly. An advert says
what an employer offers for a named role on a named date, which is not a
composite (the charity accounts wage-per-head) and not a proxy (the sector
workforce census). It is also the only evidence here of the thing the census
cannot show: the same role advertised again, and again.

The crawl has two passes (the "sustained crawl" of the phase plan):

  1. **Employer searches** — every provider name variant, as described
     below. Attribution is on the advert's own employer field.
  2. **Role-keyword searches** — the sector's role vocabulary (ROLE_KEYWORDS).
     Employer search is relevance-ranked, so an employer's adverts come
     first, but a name the search interprets loosely can strand adverts
     past the page cap; a role search surfaces adverts by title whatever
     their employer. Attribution stays on the advert's own employer field —
     the keyword that found an advert never decides whose it is. `surfaced_by`
     records which pass first surfaced each advert, and the two passes agree
     on every other rule: what counts as "the service states it found
     nothing", what counts as a markup change, and what gets discarded.

WHAT THE SEARCH ACTUALLY DOES, measured against the live service:

  * `employer=Change Grow Live` -> "20 jobs found", page 1 all CGL, page 2
                                   drifting into other employers.
  * `employer=Turning Point`    -> "5 jobs found", one of which is West Point
                                   Medical Centre.
  * `employer=Richmond Fellowship` -> "18 jobs found", every one of them
                                   Kingston and Richmond NHS Foundation Trust.
  * `employer=Zzqxwv Nonexistent Employer Ltd` -> "659 jobs found", from
                                   Employ-Ability, NHS Employers, Nimbuscare
                                   and others. None of them the employer asked
                                   for, because there is no such employer.
  * `employer=Addaction`        -> "No result found for Addaction", a distinct
                                   page with its own markup.

So the search sometimes falls back to a broad match and sometimes genuinely
finds nothing, and the two look completely different. Both matter:

  1. **A non-empty result set is not evidence about the employer searched
     for.** Attribution is on the advert's OWN employer field, matched with
     the same whole-token rule as m02 and m08. An advert whose employer
     matches no known provider is discarded and counted — never stored under
     the name that was searched. "Richmond Fellowship" returning eighteen
     adverts and none of them attributable is a real, recorded answer.

  2. **An empty result set is a statement the service makes explicitly**, so
     "searched and found nothing" and "could not read the page" stay
     distinguishable, as in m10. A page that is neither is a markup change and
     is recorded as one rather than passed off as an employer with no
     vacancies.

Paging stops as soon as a page yields nothing attributable. Results are
relevance-ranked, so once past the employer's own adverts every further page
is the fallback — requests to a public service in exchange for rows this
module would discard.

Coverage is a floor. NHS Jobs carries NHS and some commissioned-provider
adverts; a charity advertising only on its own site is invisible here. Every
count off this table has to be presented as a minimum.

robots.txt: www.jobs.nhs.uk answers /robots.txt with an HTML page (a "Service
Domain Information" shell), not a rules file. It contains no user-agent,
allow or disallow directives at all, so there are no rules to honour —
verified rather than assumed, and re-checked on 2026-08-11. The shared
client's one-request-per-two-seconds-per-host applies as everywhere else.

Licence: Crown copyright on the service; the advert content is the employer's.
"""
from __future__ import annotations

import html as html_lib
import json
import re
from datetime import date
from urllib.parse import urljoin

import structlog

from pipeline import db, providers
from pipeline.http import PipelineHTTPClient
from pipeline.keywords import SUPPLIER_NAME_VARIANTS
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "nhs_jobs"
SEARCH_URL = "https://www.jobs.nhs.uk/candidate/search/results"

# NHS Jobs paginates ten adverts to a page. Five pages per name variant is 50
# adverts, and no provider in scope advertises anywhere near that at once —
# CGL, the largest, showed 20. The cap exists so that a variant which the
# search decides to interpret loosely (see the module docstring: a name it
# does not recognise returns hundreds of unrelated adverts) costs a bounded
# number of requests instead of paging through the whole service.
MAX_RESULT_PAGES = 5

# The sustained crawl's second pass: role-keyword searches alongside the
# employer searches. Employer search is relevance-ranked, so an employer's
# own adverts come first — but an advert can still be missed when the search
# interprets the name loosely (or the employer's adverts sit past the page
# cap). A role search over the sector's own vocabulary surfaces adverts by
# title, whatever their employer, and every one of them is attributed on its
# own employer field with the same rule as the employer pass — the keyword
# that found an advert never decides who it belongs to.
#
# The keywords are the roles the sector's workforce actually holds; the list
# is bounded on purpose, because each term costs up to five pages of
# requests for rows that are mostly other employers' adverts.
ROLE_KEYWORDS: list[str] = [
    "substance misuse",
    "recovery worker",
    "recovery coordinator",
    "drug and alcohol",
    "alcohol worker",
    "harm reduction",
]

# How an advert was first surfaced. 'employer_search' for a name search,
# 'role_search' for a keyword search; recorded so the CAVEATS reading
# ("the search that surfaced it means nothing on its own") stays checkable.
SURFACED_BY_EMPLOYER = "employer_search"
SURFACED_BY_ROLE = "role_search"

_TAG_RE = re.compile(r"<[^>]+>")

# Each advert is an <li data-test="search-result">. The data-test attributes
# are the service's own test hooks and are the most stable thing on the page —
# the CSS classes around them are NHS.UK frontend utilities that change with
# the design system.
#
# Adverts are NOT matched with a single <li>...</li> pattern. Each one nests
# two more <ul>/<li> lists for the salary and contract fields, so the obvious
# non-greedy pattern ends every advert at the first nested </li> and silently
# yields a row with a title, a reference and nothing else — which reads
# downstream as an advert that published no pay. The list is bounded by its
# own closing tag and then split at each advert's opening tag instead.
_RESULTS_LIST_RE = re.compile(
    r'<ul\b[^>]*class="[^"]*\bsearch-results\b[^"]*"[^>]*>', re.IGNORECASE)
_UL_OPEN_RE = re.compile(r"<ul\b", re.IGNORECASE)
_UL_CLOSE_RE = re.compile(r"</ul\s*>", re.IGNORECASE)
_RESULT_START_RE = re.compile(r'<li\b[^>]*data-test="search-result"[^>]*>', re.IGNORECASE)
_TITLE_LINK_RE = re.compile(
    r'<a\b[^>]*href="([^"]+)"[^>]*data-test="search-result-job-title"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL)
# The employer is the text directly inside the <h3>, before the
# <div class="location-font-size"> that holds the sites.
_LOCATION_H3_RE = re.compile(
    r'data-test="search-result-location"[^>]*>\s*<h3\b[^>]*>(.*?)</h3>',
    re.IGNORECASE | re.DOTALL)
_EMPLOYER_RE = re.compile(r"^(.*?)(?:<div\b|$)", re.DOTALL)
_LOCATIONS_RE = re.compile(
    r'<div\b[^>]*class="[^"]*\blocation-font-size\b[^"]*"[^>]*>(.*?)</div>',
    re.IGNORECASE | re.DOTALL)
_FIELD_RE_CACHE: dict[str, re.Pattern[str]] = {}
_JOB_REFERENCE_RE = re.compile(r"/candidate/jobadvert/([^/?#]+)", re.IGNORECASE)
_NEXT_PAGE_RE = re.compile(
    r'<a\b[^>]*href="([^"]+)"[^>]*data-test="search-next-page"', re.IGNORECASE | re.DOTALL)
# "20 jobs found for Change Grow Live" — the service's own count for the
# search, which is not the number of adverts about that employer.
_REPORTED_TOTAL_RE = re.compile(
    r"data-test=['\"]search-result-query['\"].*?>\s*([\d,]+)\s+jobs?\s+found",
    re.IGNORECASE | re.DOTALL)
# The same heading element on a search that found nothing: "No result found
# for Addaction". Anchored on that element rather than matched anywhere on the
# page, so a job advert whose title contains the phrase cannot empty a run.
_NO_RESULTS_RE = re.compile(
    r"data-test=['\"]search-result-query['\"][^>]*>\s*No result found",
    re.IGNORECASE | re.DOTALL)

_MONTHS = {name.lower(): number for number, name in enumerate(
    ("January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"), start=1)}
_LONG_DATE_RE = re.compile(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b")

# "£38,114.53 to £44,469.24 a year", "£23.83 an hour", "£1,850 a session".
_MONEY = r"£\s*([\d,]+(?:\.\d+)?)"
_SALARY_RANGE_RE = re.compile(rf"{_MONEY}\s*(?:to|-|–|—)\s*{_MONEY}", re.IGNORECASE)
_SALARY_SINGLE_RE = re.compile(_MONEY)
# The service writes the unit as "a year" / "an hour". Anything outside this
# set is left NULL rather than guessed at, and the raw string is always kept.
_PERIODS = {
    "year": "year", "annum": "year", "yearly": "year", "annually": "year",
    "hour": "hour", "hourly": "hour",
    "session": "session",
    "month": "month", "monthly": "month",
    "week": "week", "weekly": "week",
    "day": "day", "daily": "day",
}
_PERIOD_RE = re.compile(r"\ba[n]?\s+(" + "|".join(sorted(_PERIODS)) + r")\b", re.IGNORECASE)


def _text(raw: str | None) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(_TAG_RE.sub(" ", raw or ""))).strip()


def _results_list(page_html: str) -> str:
    """The contents of the results <ul>, bounded by its own closing tag.

    Depth-counted because each advert nests further <ul>s. Returning the
    remainder of the document on unbalanced markup would be worse than
    returning nothing: it is the case where a caller cannot tell a short page
    from a broken one.
    """
    opening = _RESULTS_LIST_RE.search(page_html or "")
    if opening is None:
        return ""
    depth, pos = 1, opening.end()
    while depth:
        next_open = _UL_OPEN_RE.search(page_html, pos)
        next_close = _UL_CLOSE_RE.search(page_html, pos)
        if next_close is None:
            return ""
        if next_open is not None and next_open.start() < next_close.start():
            depth += 1
            pos = next_open.end()
        else:
            depth -= 1
            pos = next_close.end()
            if depth == 0:
                return page_html[opening.end():next_close.start()]
    return ""


def _result_blocks(page_html: str) -> list[str]:
    """One HTML fragment per advert, split at each advert's opening tag."""
    body = _results_list(page_html)
    starts = [match.start() for match in _RESULT_START_RE.finditer(body)]
    return [body[start:end] for start, end in zip(starts, starts[1:] + [len(body)])]


def _field(block: str, data_test: str) -> str | None:
    """The <strong> value of one `data-test="search-result-<name>"` list item.

    Every one of these is optional in the service's own template, so a missing
    field is None rather than an error — an advert with no closing date is an
    advert with no closing date.
    """
    pattern = _FIELD_RE_CACHE.get(data_test)
    if pattern is None:
        pattern = re.compile(
            rf'data-test="search-result-{re.escape(data_test)}"[^>]*>(.*?)</li>',
            re.IGNORECASE | re.DOTALL)
        _FIELD_RE_CACHE[data_test] = pattern
    match = pattern.search(block)
    if not match:
        return None
    strong = re.search(r"<strong\b[^>]*>(.*?)</strong>", match.group(1),
                        re.IGNORECASE | re.DOTALL)
    value = _text(strong.group(1) if strong else match.group(1))
    # Without a <strong> the label comes along with the value ("Salary: ...").
    if not strong:
        value = re.sub(r"^[A-Za-z ]{3,20}:\s*", "", value)
    return value or None


def parse_uk_date(raw: str | None) -> str | None:
    """"11 August 2026" -> "2026-08-11".

    Reformatting, not inference: a value that does not parse returns None so
    the caller can record it rather than store a guess.
    """
    if not raw:
        return None
    match = _LONG_DATE_RE.search(raw)
    if not match:
        return None
    month = _MONTHS.get(match.group(2).lower())
    if month is None:
        return None
    try:
        return date(int(match.group(3)), month, int(match.group(1))).isoformat()
    except ValueError:
        return None


def parse_salary(raw: str | None) -> dict:
    """The advert's salary line as figures, or an honest admission that it is not.

    Returns salary_min, salary_max, salary_period and salary_basis:

      'range'      two figures, both from the advert
      'single'     one figure, written to BOTH min and max so that a range
                    query over the table does not silently drop single-value
                    adverts
      'not_stated' no figure at all ("Depends on experience") — what the
                    employer chose to publish, not a parser failure
      'unparsed'   a currency figure is present and could not be read; the
                    caller records a parse failure for it

    No conversion between periods, ever. An hourly rate annualised is a number
    the source never published and that depends on contracted hours this
    pipeline does not know.
    """
    text = (raw or "").strip()
    out: dict = {"salary_raw": text or None, "salary_min": None, "salary_max": None,
                 "salary_period": None, "salary_basis": "not_stated"}
    if not text:
        return out

    period_match = _PERIOD_RE.search(text)
    if period_match:
        out["salary_period"] = _PERIODS[period_match.group(1).lower()]

    def _amount(value: str) -> float | None:
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None

    range_match = _SALARY_RANGE_RE.search(text)
    if range_match:
        low, high = _amount(range_match.group(1)), _amount(range_match.group(2))
        if low is not None and high is not None:
            # Stored as published even when the advert writes them the wrong
            # way round; ordering them is the caller's business, and silently
            # swapping would hide a genuine oddity in the source.
            out.update(salary_min=low, salary_max=high, salary_basis="range")
            return out

    single_match = _SALARY_SINGLE_RE.search(text)
    if single_match:
        amount = _amount(single_match.group(1))
        if amount is not None:
            out.update(salary_min=amount, salary_max=amount, salary_basis="single")
            return out

    if "£" in text:
        out["salary_basis"] = "unparsed"
    return out


# --- attributing an advert to a provider -------------------------------------
#
# Same rule as m02 and m08, and for the same reason: the employer string on the
# advert is the only thing that says whose advert this is. Duplicated rather
# than shared because each module normalises the field it actually has — a
# tribunal respondent list, a coroner's prose, an employer name — and folding
# them into one helper would mean one of them matching text it was not written
# for.

def _normalise_employer(name: str | None) -> str:
    text = re.sub(r"[^\w\s]", " ", (name or "").lower())
    text = re.sub(r"\b(limited|ltd|llp|plc|cic|group)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Variants too short or too ordinary to match safely inside a longer employer
# name. "Via" and "Inclusion" are English words; "CGL" as a whole employer name
# is fine, but hunting for it inside one is not.
_UNSAFE_COMPONENT_VARIANTS = {"cgl", "via", "inclusion"}

_EMPLOYER_LOOKUP: dict[str, str] = {}
for _key, _variants in SUPPLIER_NAME_VARIANTS.items():
    for _variant in _variants:
        _normalised = _normalise_employer(_variant)
        if _normalised:
            _EMPLOYER_LOOKUP.setdefault(_normalised, _key)


def match_employer(employer_name: str | None) -> tuple[str | None, str | None]:
    """(provider_key, match_basis) for the employer named on an advert.

    'exact'     the whole employer name is a known variant.
    'component' a known variant appears as a whole-token run inside a longer
                 name ("Change Grow Live Services").
    (None, None) no match — the caller must not treat the advert as this
                 provider's, however it was found.
    """
    normalised = _normalise_employer(employer_name)
    if not normalised:
        return None, None

    exact = _EMPLOYER_LOOKUP.get(normalised)
    if exact:
        return exact, "exact"

    tokens = normalised.split()
    for variant_normalised, provider_key in _EMPLOYER_LOOKUP.items():
        if variant_normalised in _UNSAFE_COMPONENT_VARIANTS:
            continue
        variant_tokens = variant_normalised.split()
        if not variant_tokens or len(variant_tokens) > len(tokens):
            continue
        window = len(variant_tokens)
        for start in range(len(tokens) - window + 1):
            if tokens[start:start + window] == variant_tokens:
                return provider_key, "component"
    return None, None


def search_variants() -> list[tuple[str, str]]:
    """(provider_key, name variant) pairs to search, in a stable order.

    Comparators are searched as well as the target: a pay campaign argument is
    a comparison, and one provider's advertised bands on their own say nothing
    about whether they are low.

    The unsafe variants are skipped as searches too, not just as matches. They
    cannot be attributed to anything, so searching them would be requests to a
    public service in exchange for adverts this module would then discard.

    Variants that differ only in punctuation are searched once. "Change, Grow,
    Live" and "Change Grow Live" return the same twenty adverts and the same
    reported total — checked against the live service, because m02 found the
    comma form does matter in tribunal titles and it was worth knowing whether
    it mattered here.
    """
    pairs: list[tuple[str, str]] = []
    already: set[str] = set()
    for provider_key in sorted(SUPPLIER_NAME_VARIANTS):
        for variant in SUPPLIER_NAME_VARIANTS[provider_key]:
            normalised = _normalise_employer(variant)
            if normalised in _UNSAFE_COMPONENT_VARIANTS or normalised in already:
                continue
            already.add(normalised)
            pairs.append((provider_key, variant))
    return pairs


def reported_total(page_html: str) -> int | None:
    """The count the service prints above the results.

    Recorded, never trusted as a count of the provider's adverts — it is the
    size of a result set that includes whatever the search decided was close
    enough. Kept because the gap between it and the number of adverts actually
    matched is the measure of how loose a given search was.
    """
    match = _REPORTED_TOTAL_RE.search(page_html or "")
    if not match:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None


def has_no_results(page_html: str) -> bool:
    """True when the service states the search found nothing.

    "Searched and found nothing" and "could not read the page" must not look
    the same, and the service says which: a search with no hits serves a
    different heading ("No result found for Addaction") and no results list at
    all. Without this, a provider who does not advertise here would be
    indistinguishable from a parser that has stopped working.
    """
    return bool(_NO_RESULTS_RE.search(page_html or ""))


def next_result_page_url(page_html: str, page_url: str) -> str | None:
    """The service's own next-page link, or None on the last page.

    Followed rather than constructed: building `page=N+1` by hand would page
    happily past the end of a result set and read the fallback results the
    service serves there as more of the same search.
    """
    match = _NEXT_PAGE_RE.search(page_html or "")
    if not match:
        return None
    return urljoin(page_url, html_lib.unescape(match.group(1).strip()))


def parse_search_results(page_html: str, page_url: str) -> list[dict]:
    """One dict per advert on a results page, in the order the page lists them.

    Parses only; attribution and storage are the caller's, because an advert
    that cannot be attributed must not be written under the name that was
    searched for.
    """
    rows: list[dict] = []
    seen: set[str] = set()

    for block in _result_blocks(page_html or ""):
        title_match = _TITLE_LINK_RE.search(block)
        if title_match is None:
            continue
        href = html_lib.unescape(title_match.group(1).strip())
        reference_match = _JOB_REFERENCE_RE.search(href)
        if reference_match is None:
            continue
        job_reference = html_lib.unescape(reference_match.group(1))
        if job_reference in seen:
            continue
        seen.add(job_reference)

        employer = None
        locations: list[str] = []
        heading = _LOCATION_H3_RE.search(block)
        if heading:
            employer_match = _EMPLOYER_RE.search(heading.group(1))
            employer = _text(employer_match.group(1)) if employer_match else None
            sites_match = _LOCATIONS_RE.search(heading.group(1))
            if sites_match:
                # One site per line, each but the last with a trailing comma —
                # the service's template emits them that way. Split on the
                # lines and NOT on the commas: "Liverpool, Merseyside L11 4SJ"
                # is a single site, and comma-splitting invents a place called
                # Liverpool. If the service ever puts them all on one line this
                # under-splits, which leaves the source's own text intact
                # rather than manufacturing locations out of it.
                for line in sites_match.group(1).splitlines():
                    cleaned = _text(line).rstrip(",").strip()
                    if cleaned and cleaned not in locations:
                        locations.append(cleaned)

        salary = parse_salary(_field(block, "salary"))
        posted_raw = _field(block, "publicationDate")
        closing_raw = _field(block, "closingDate")

        rows.append({
            "job_reference": job_reference,
            # Without the search query the link carries. The same advert
            # reached by two provider searches is one advert at one address;
            # keeping "?employer=…&page=1" would make its URL depend on how it
            # happened to be found. How it was found is recorded separately, in
            # searched_variant and in source_url.
            "advert_url": urljoin(page_url, href.split("?")[0]),
            "job_title": _text(title_match.group(2)) or None,
            "employer_name_raw": employer or None,
            "locations": locations,
            "contract_type": _field(block, "jobType"),
            "working_pattern": _field(block, "workingPattern"),
            "posted_date_raw": posted_raw,
            "posted_date": parse_uk_date(posted_raw),
            "closing_date_raw": closing_raw,
            "closing_date": parse_uk_date(closing_raw),
            **salary,
        })

    return rows


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


def _write_advert_page(conn, adverts: list[dict], locations: list[dict]) -> None:
    """Persist one result page in stable batches, keeping page commits intact."""
    db.upsert_many(
        conn, "nhs_job_adverts", adverts, natural_key=["job_reference"],
        preserve=["searched_variant", "surfaced_by"],
    )
    db.upsert_many(
        conn, "nhs_job_advert_locations", locations,
        natural_key=["job_reference", "location_raw"],
    )


@register_module(
    "m16_nhs_jobs", supports_since=True,
    since_note="filters on the advert's posted date; adverts with an unreadable "
                "date are kept rather than dropped")
def run(ctx: ModuleContext) -> None:
    module_name = "m16_nhs_jobs"
    conn = ctx.conn
    providers.seed_providers(conn, commit=not ctx.dry_run)

    adverts_written = 0
    discarded_unmatched = 0
    pages_fetched = 0
    seen_references: set[str] = set()
    unmatched_employers: dict[str, str] = {}

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        ctx.phase("searching employers")
        for provider_key, variant in ctx.track(search_variants(), "employer searches"):
            url: str | None = SEARCH_URL
            params: dict | None = {"employer": variant, "page": 1}
            matched_here = 0
            returned_here = 0
            reported_here: int | None = None

            for _page in range(MAX_RESULT_PAGES):
                if url is None:
                    break
                result = client.get(url, params=params)
                params = None  # only the first request carries them; then follow links
                pages_fetched += 1

                if not result.ok:
                    db.record_review_item(
                        conn, module_name, "nhs_jobs_search_unavailable", variant,
                        json.dumps({"status": result.status_code, "url": result.url,
                                     "note": "search did not answer; this variant's adverts "
                                              "are missing from this run"}))
                    break

                page_html = result.body.decode("utf-8", "replace")
                if reported_here is None:
                    reported_here = reported_total(page_html)

                rows = parse_search_results(page_html, result.url)
                if not rows:
                    # Empty and broken are different, and the service says
                    # which. Getting this wrong in either direction is a
                    # silent error: reading a markup change as "no vacancies"
                    # loses evidence, and reading a genuine empty search as a
                    # markup change sends someone chasing a bug that is not
                    # there.
                    if has_no_results(page_html):
                        db.record_review_item(
                            conn, module_name, "nhs_jobs_search_no_matches", variant,
                            json.dumps({"url": result.url,
                                         "note": "the service states it found nothing for this "
                                                  "name; the provider may not advertise here"}))
                    else:
                        db.record_review_item(
                            conn, module_name, "nhs_jobs_results_unrecognised", variant,
                            json.dumps({"url": result.url,
                                         "reported_total": reported_here,
                                         "note": "a 200 that is neither a results page nor the "
                                                  "service's own 'no result found' page — the "
                                                  "markup has moved"}))
                    break

                returned_here += len(rows)
                matched_on_this_page = 0
                page_adverts: list[dict] = []
                page_locations: list[dict] = []

                for row in rows:
                    matched_key, match_basis = match_employer(row["employer_name_raw"])
                    if matched_key is None:
                        # The search returns adverts from employers it merely
                        # considers similar. Storing them under the searched
                        # name is how this table would become indefensible.
                        discarded_unmatched += 1
                        if row["employer_name_raw"]:
                            unmatched_employers.setdefault(row["employer_name_raw"], variant)
                        continue

                    # Counted on attribution, before the filters below. An
                    # advert this search found and correctly identified is a
                    # productive result whether or not an earlier variant
                    # already collected it. Counted after the de-duplication,
                    # a provider's second name variant ("Change Grow Live
                    # Services Ltd") logged "every advert belonged to a
                    # different employer" when it had in fact found all
                    # fourteen of the target's.
                    matched_here += 1
                    matched_on_this_page += 1

                    if ctx.is_before_since(row["posted_date"]):
                        continue
                    if row["job_reference"] in seen_references:
                        continue
                    seen_references.add(row["job_reference"])

                    if row["posted_date_raw"] and not row["posted_date"]:
                        db.record_parse_failure(
                            conn, module_name, "posted_date", row["posted_date_raw"],
                            "advert date did not parse as '<D> <Month> <YYYY>'",
                            source_url=result.url)
                    if row["salary_basis"] == "unparsed":
                        db.record_parse_failure(
                            conn, module_name, "salary", row["salary_raw"] or "",
                            "a currency figure was present but could not be read",
                            source_url=result.url)

                    page_adverts.append({
                        "job_reference": row["job_reference"],
                        "provider_key": matched_key,
                        "provider_match_basis": match_basis,
                        "employer_name_raw": row["employer_name_raw"],
                        "job_title": row["job_title"],
                        "advert_url": row["advert_url"],
                        "salary_raw": row["salary_raw"],
                        "salary_min": row["salary_min"],
                        "salary_max": row["salary_max"],
                        "salary_period": row["salary_period"],
                        "salary_basis": row["salary_basis"],
                        "contract_type": row["contract_type"],
                        "working_pattern": row["working_pattern"],
                        "posted_date": row["posted_date"],
                        "closing_date": row["closing_date"],
                        "searched_variant": variant,
                        "surfaced_by": SURFACED_BY_EMPLOYER,
                        **_provenance(result),
                    })
                    adverts_written += 1

                    for location in row["locations"]:
                        page_locations.append({
                            "job_reference": row["job_reference"],
                            "location_raw": location,
                        })

                    if ctx.limit and adverts_written >= ctx.limit:
                        break

                _write_advert_page(conn, page_adverts, page_locations)
                if not ctx.dry_run:
                    conn.commit()

                if ctx.limit and adverts_written >= ctx.limit:
                    break
                if not matched_on_this_page:
                    # Results are relevance-ranked, so an employer's own
                    # adverts come first. A page with none of them means this
                    # search has run past them into the fallback, and every
                    # further page would be requests to a public service in
                    # exchange for rows that would be discarded. Costs a
                    # theoretical advert stranded behind a page of noise;
                    # counts off this table are a floor anyway.
                    break
                url = next_result_page_url(page_html, result.url)

            # How loose was this search? The gap between what came back and
            # what could be attributed is the only honest measure of it, and
            # it is recorded per variant rather than summed away.
            if returned_here and not matched_here:
                db.record_review_item(
                    conn, module_name, "nhs_jobs_search_matched_nothing", variant,
                    json.dumps({"provider_key": provider_key,
                                 "reported_total": reported_here,
                                 "adverts_returned": returned_here,
                                 "note": "every advert the search returned belonged to a "
                                          "different employer; this provider may simply not "
                                          "advertise on NHS Jobs"}))

            log.info("nhs_jobs.variant_searched", provider_key=provider_key,
                      variant=variant, reported_total=reported_here,
                      adverts_returned=returned_here, adverts_matched=matched_here)

            if ctx.limit and adverts_written >= ctx.limit:
                break

        # --- the sustained crawl's role-keyword pass ---------------------------
        #
        # Same attribution rule as the employer pass: the advert's OWN
        # employer field decides, never the term that surfaced it. What
        # differs is what gets recorded, on purpose:
        #
        #   * a keyword with no results is a normal outcome, not a finding
        #     about a provider — no `nhs_jobs_search_no_matches` item;
        #   * adverts returned but not attributable are counted, not queued —
        #     a role search surfaces mostly other employers' adverts, and
        #     the `unmatched_nhs_jobs_employer` queue belongs to the
        #     employer pass, which samples the same pool;
        #   * everything else — a search that does not answer, a page that
        #     is neither results nor "no result found" — is recorded exactly
        #     as the employer pass records it, because a markup change is a
        #     markup change whichever pass tripped over it.
        ctx.phase("searching by role keywords")
        role_adverts = 0
        role_returned = 0
        role_discarded = 0
        for term in ctx.track(ROLE_KEYWORDS, "role searches"):
            url: str | None = SEARCH_URL
            params: dict | None = {"keyword": term, "page": 1}
            for _page in range(MAX_RESULT_PAGES):
                if url is None:
                    break
                result = client.get(url, params=params)
                params = None
                pages_fetched += 1

                if not result.ok:
                    db.record_review_item(
                        conn, module_name, "nhs_jobs_search_unavailable",
                        f"keyword:{term}",
                        json.dumps({"status": result.status_code, "url": result.url,
                                     "note": "role search did not answer; adverts "
                                             "surfaced by it are missing from this run"}))
                    break

                page_html = result.body.decode("utf-8", "replace")
                rows = parse_search_results(page_html, result.url)
                if not rows:
                    if not has_no_results(page_html):
                        db.record_review_item(
                            conn, module_name, "nhs_jobs_results_unrecognised",
                            f"keyword:{term}",
                            json.dumps({"url": result.url,
                                         "note": "a 200 that is neither a results page "
                                                  "nor the service's own 'no result "
                                                  "found' page — the markup has moved"}))
                    break

                role_returned += len(rows)
                matched_on_this_page = 0
                page_adverts = []
                page_locations = []
                for row in rows:
                    matched_key, match_basis = match_employer(row["employer_name_raw"])
                    if matched_key is None:
                        role_discarded += 1
                        continue
                    matched_on_this_page += 1
                    if ctx.is_before_since(row["posted_date"]):
                        continue
                    if row["job_reference"] in seen_references:
                        continue
                    seen_references.add(row["job_reference"])

                    if row["posted_date_raw"] and not row["posted_date"]:
                        db.record_parse_failure(
                            conn, module_name, "posted_date", row["posted_date_raw"],
                            "advert date did not parse as '<D> <Month> <YYYY>'",
                            source_url=result.url)
                    if row["salary_basis"] == "unparsed":
                        db.record_parse_failure(
                            conn, module_name, "salary", row["salary_raw"] or "",
                            "a currency figure was present but could not be read",
                            source_url=result.url)

                    page_adverts.append({
                        "job_reference": row["job_reference"],
                        "provider_key": matched_key,
                        "provider_match_basis": match_basis,
                        "employer_name_raw": row["employer_name_raw"],
                        "job_title": row["job_title"],
                        "advert_url": row["advert_url"],
                        "salary_raw": row["salary_raw"],
                        "salary_min": row["salary_min"],
                        "salary_max": row["salary_max"],
                        "salary_period": row["salary_period"],
                        "salary_basis": row["salary_basis"],
                        "contract_type": row["contract_type"],
                        "working_pattern": row["working_pattern"],
                        "posted_date": row["posted_date"],
                        "closing_date": row["closing_date"],
                        "searched_variant": f"keyword:{term}",
                        "surfaced_by": SURFACED_BY_ROLE,
                        **_provenance(result),
                    })
                    role_adverts += 1

                    for location in row["locations"]:
                        page_locations.append({
                            "job_reference": row["job_reference"],
                            "location_raw": location,
                        })

                    if ctx.limit and adverts_written + role_adverts >= ctx.limit:
                        break

                _write_advert_page(conn, page_adverts, page_locations)
                if not ctx.dry_run:
                    conn.commit()
                if ctx.limit and adverts_written + role_adverts >= ctx.limit:
                    break
                if not matched_on_this_page:
                    break
                url = next_result_page_url(page_html, result.url)

            log.info("nhs_jobs.role_search_done", term=term, adverts_returned=role_returned)
            if ctx.limit and adverts_written + role_adverts >= ctx.limit:
                break

    for employer_name, variant in sorted(unmatched_employers.items()):
        db.record_review_item(
            conn, module_name, "unmatched_nhs_jobs_employer", employer_name,
            json.dumps({"surfaced_by_variant": variant,
                         "note": "returned by a provider search but its employer name "
                                  "matches no known provider variant; not stored"}))
    if not ctx.dry_run:
        conn.commit()

    log.info("nhs_jobs.run_complete", adverts=adverts_written,
              role_adverts=role_adverts,
              discarded_unmatched_employer=discarded_unmatched,
              role_returned=role_returned, role_discarded=role_discarded,
              distinct_unmatched_employers=len(unmatched_employers),
              pages_fetched=pages_fetched)
