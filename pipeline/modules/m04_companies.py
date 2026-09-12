"""Module 4 — Corporate structure (Companies House).

Resolves which legal entities make up each provider's group, because the
entity that holds a contract is often not the entity that employs staff —
CGL's charity (03861209) and its trading subsidiary CHANGE, GROW, LIVE
SERVICES LIMITED (06228752) are distinct, and which one appears on a notice
determines who answers a tribunal claim and who transfers staff under TUPE.

Entity discovery is deliberately conservative, in two stages.

Companies House name search is fuzzy — "Change Grow Live" returns 10,000
results including "GROW CHANGE LTD" — so a hit is only considered at all
when its normalised name exactly equals a configured provider variant.

But an exact name match is still NOT proof of identity, because different
legal entities share names. Live data makes this concrete: "FORWARD TRUST
LIMITED" (01865768) is a dissolved company formerly called "BRADFORD &
BINGLEY PERSONAL FINANCE LIMITED", and a "HUMANKIND LTD" (16628351) was
incorporated in 2025 having previously been "HUMAN TRIBE LTD" — neither is
the charity of that name. So a name-only hit is stored with
provider_key NULL and match_basis 'name_only_unconfirmed', plus a
review_queue entry. The company record is captured (it is real data) but
the link to a provider is never asserted on a name alone.

Only identifiers that came from an authoritative cross-reference are
trusted to set provider_key: the Charity Commission register's
charity_co_reg_number (Module 3) and CQC's companiesHouseNumber (Module 5),
both of which arrive via provider_identifiers.

Former names are captured because they are authoritative aliases published
by Companies House, not guesses: CGL was "CRIME REDUCTION INITIATIVES" until
2016, so a pre-2016 notice naming CRI is a CGL record.

Officers are personal data and live only in restricted_company_officers; a
name-free v_company_officer_changes view carries the analytically useful
churn counts.

VIABILITY. Two further questions are answered from the same key and the same
client, because the register already holds the answers:

  * Insolvency. The company profile publishes `links.insolvency` and a
    `has_insolvency_history` flag, so the case list is fetched only where the
    source says there is one — no speculative request per company. A company
    with no case answers 404, which is "no case published" and not a failure.
    This is not hypothetical for this sector: LIFELINE PROJECT (01842240) went
    into administration in 2017 and was wound up in 2018.

    Dissolved is not insolvent. Both dissolved companies this pipeline holds
    have no insolvency case at all — a company can be struck off having paid
    everyone — so `company_status` says how a company ended and only the
    insolvency tables say whether it failed.

  * People with Significant Control (PSC, Phase 15/G3). The ownership edges
    for the entity graph: who owns or controls the companies that hold the
    sector's contracts. One fetch per target company, same key and client,
    stored in `company_psc` with names and month-and-year-of-birth in
    `restricted_company_psc`. A corporate PSC arrives with its own company
    number asserted by Companies House (`identification.company_number`) —
    that is an authoritative identifier and travels on the public row, but
    nothing is linked to a provider on a name, and a PSC who is an individual
    is never exported.

  * Disqualified directors. Companies House publishes no link from an
    appointment to a disqualification, so the only route is a name search of
    the register. That is exactly the kind of match this module already
    refuses to trust, and the consequence of being wrong is worse here than
    anywhere else in the pipeline: it would record that a named person had
    been banned from directing companies when they had not. So the sweep is
    narrow (serving directors only, who are the only people the question is
    about), and nothing is stored without corroboration on the published month
    and year of birth as well as the name. Weaker matches are review items.
    Expect no rows: acting while disqualified is a criminal offence, so this
    is a checkable negative rather than a discovery engine.

STREAMING (JON-36). Four Companies House streams -- company, filing-history,
insolvency-cases, charges -- are a change-notification mechanism only. No
event's own embedded payload is ever written to a table: a matching event
only ever triggers the same authoritative REST fetch this module already has
for that one company number (_refresh_company, or a single-endpoint function
directly). Four reasons this matters more than the extra REST round trip
costs:

  1. One writer per resource shape. _fetch_filings/_fetch_insolvency/etc.
     already carry the pagination, review-item and verbatim-vocabulary
     discipline docs/CAVEATS.md requires. A second parser reading the
     stream's embedded data would drift from these over time.
  2. The event's data is a snapshot at publish time; by the time a bounded
     batch run gets to it, a fresh REST read is strictly more current and no
     more expensive than trusting a possibly-stale embedded copy.
  3. Insolvency and charges both need the same verbatim date-vocabulary
     split _fetch_insolvency already implements correctly and is tested
     against -- reusing it is safer than a second implementation.
  4. This is what "replace repeated change polling" means here: it replaces
     polling every tracked company on every scheduled run with polling only
     the companies a stream said changed, whenever it says so. Each notified
     change still costs one authoritative REST call -- that is the trade,
     not the elimination of REST calls.

Companies House's own event volume across ~5.5M companies means a bounded
per-invocation catch-up run only as often as this module's normal schedule
will not keep pace in any meaningful sense. The intended shape is a second,
more frequent scheduled invocation (`pipeline run m04_companies
--stream-only`) alongside the slower full sweep -- see pipeline/cli.py. Off
by default (COMPANIES_HOUSE_STREAMING_ENABLED); a streaming API key is a
separate registered application from the REST key above, not interchangeable.

Filing-history events tagged category='accounts' seed a candidate
(companies_house_accounts_candidates), never evidence directly -- a human
promotes it through pipeline/promote.py, the same discipline m09/m10/m15's
candidates already follow. This evidence layer is deliberately named and
kept structurally separate from m03's charity_commission_filed_accounts: a
charity's own accounts filed with the Charity Commission and its trading
subsidiary's statutory accounts filed with Companies House are different
legal entities' filings under different regimes, and are never merged,
reconciled or read as duplicates. See docs/CAVEATS.md.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone

import structlog

from pipeline import db, providers
from pipeline.http import (
    PipelineHTTPClient,
    StreamCursorStale,
    StreamRateLimited,
    StreamTransientError,
)
from pipeline.keywords import SUPPLIER_NAME_VARIANTS
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "companies_house"
API_BASE = "https://api.company-information.service.gov.uk"
FILINGS_PER_PAGE = 100
MAX_FILINGS = 200
CHARGES_PER_PAGE = 25

# JON-36 streaming. Companies House's Streaming API is a separate host from
# the REST API above, authenticated with its own (separate) key.
STREAM_BASE = "https://stream.companieshouse.gov.uk"
STREAM_SOURCE_SYSTEM = "companies_house_streaming"
ACCOUNTS_SOURCE_SYSTEM = "companies_house_filed_accounts"

_RESOURCE_URI_COMPANY = re.compile(r"^/company/([A-Za-z0-9]+)")


def normalise_company_number(raw: str | int) -> str:
    """Companies House numbers are 8 characters, zero-padded. The Charity
    Commission publishes them unpadded ("3861209"), and an unpadded number
    404s against the API, so every number is normalised on the way in.
    Alphabetic prefixes (SC, NI, OC…) are preserved and not padded past 8.
    """
    text = str(raw).strip().upper()
    m = re.match(r"^([A-Z]*)(\d+)$", text)
    if not m:
        return text
    prefix, digits = m.group(1), m.group(2)
    return f"{prefix}{digits.zfill(8 - len(prefix))}"


def _normalise_company_name(name: str) -> str:
    text = re.sub(r"[^\w\s]", " ", (name or "").lower())
    text = re.sub(r"\b(limited|ltd|llp|plc|cic|c\.i\.c)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_NAME_LOOKUP: dict[str, str] = {}
for _key, _variants in SUPPLIER_NAME_VARIANTS.items():
    for _variant in _variants:
        _NAME_LOOKUP[_normalise_company_name(_variant)] = _key

# Too generic to accept from a fuzzy company-name search.
_UNSAFE_NAME_MATCHES = {"cgl", "via", "inclusion"}


def match_company_name(company_name: str | None) -> str | None:
    """Exact normalised match only. A near miss is a review item, not a match."""
    if not company_name:
        return None
    normalised = _normalise_company_name(company_name)
    if not normalised or normalised in _UNSAFE_NAME_MATCHES:
        return None
    return _NAME_LOOKUP.get(normalised)


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


def _format_address(address: dict | None) -> str | None:
    if not address:
        return None
    parts = [address.get(k) for k in (
        "address_line_1", "address_line_2", "locality", "region", "postal_code", "country")]
    joined = ", ".join(p for p in parts if p)
    return joined or None


def _officer_ref(officer: dict) -> str:
    ref = officer.get("person_number")
    if ref:
        return str(ref)
    # Some officer records omit person_number; derive a stable ref from the
    # fields that identify the appointment, so re-runs stay idempotent.
    basis = f"{officer.get('name')}|{officer.get('officer_role')}|{officer.get('appointed_on')}"
    return "H" + hashlib.sha256(basis.encode()).hexdigest()[:16]


def _seed_company_numbers(conn) -> list[tuple[str, str]]:
    rows = conn.execute(
        "SELECT provider_key, identifier FROM provider_identifiers "
        "WHERE scheme = 'company_number' ORDER BY provider_key"
    ).fetchall()
    return [(r["provider_key"], normalise_company_number(r["identifier"])) for r in rows]


def _fetch_company(client: PipelineHTTPClient, conn, module_name: str,
                    company_number: str, provider_key: str | None, match_basis: str) -> dict | None:
    result = client.get(f"{API_BASE}/company/{company_number}")
    if not result.ok:
        db.record_review_item(conn, module_name, "company_profile_unavailable", company_number,
                               json.dumps({"status": result.status_code, "provider_key": provider_key}))
        return None
    data = json.loads(result.body)

    db.upsert(conn, "companies", {
        "company_number": company_number,
        "provider_key": provider_key,
        "company_name": data.get("company_name") or company_number,
        "company_status": data.get("company_status"),
        "company_type": data.get("type"),
        "date_of_creation": data.get("date_of_creation"),
        "date_of_cessation": data.get("date_of_cessation"),
        "sic_codes": ",".join(data.get("sic_codes") or []) or None,
        "registered_address": _format_address(data.get("registered_office_address")),
        "jurisdiction": data.get("jurisdiction"),
        "match_basis": match_basis,
        **_provenance(result),
    }, natural_key=["company_number"])

    for previous in data.get("previous_company_names") or []:
        if not previous.get("name"):
            continue
        db.upsert(conn, "company_previous_names", {
            "company_number": company_number,
            "previous_name": previous["name"],
            "effective_from": previous.get("effective_from"),
            "ceased_on": previous.get("ceased_on"),
            **_provenance(result),
        }, natural_key=["company_number", "previous_name"])

    return data


def _fetch_officers(client: PipelineHTTPClient, conn, module_name: str,
                     company_number: str) -> tuple[int, list[dict]]:
    """Writes the officer list, and returns (count, serving directors).

    The serving directors travel back to the caller rather than being re-read
    from the table because the disqualification check needs their date of
    birth, and their date of birth is deliberately not stored. Companies House
    publishes it as a month and a year for exactly this reason; holding it
    would be collecting a person's birthday to answer a question about a
    provider's governance.
    """
    result = client.get(f"{API_BASE}/company/{company_number}/officers",
                         params={"items_per_page": 100})
    if not result.ok:
        db.record_review_item(conn, module_name, "company_officers_unavailable", company_number,
                               json.dumps({"status": result.status_code}))
        return 0, []
    written = 0
    serving_directors: list[dict] = []
    for officer in json.loads(result.body).get("items", []):
        address = officer.get("address") or {}
        officer_ref = _officer_ref(officer)
        db.upsert(conn, "restricted_company_officers", {
            "company_number": company_number,
            "officer_ref": officer_ref,
            "officer_name": officer.get("name"),
            "officer_role": officer.get("officer_role"),
            "appointed_on": officer.get("appointed_on"),
            "resigned_on": officer.get("resigned_on"),
            "nationality": officer.get("nationality"),
            "occupation": officer.get("occupation"),
            "address_locality": address.get("locality"),
        }, natural_key=["company_number", "officer_ref"])
        written += 1

        if is_serving_director(officer):
            serving_directors.append({
                "company_number": company_number,
                "officer_ref": officer_ref,
                "name": officer.get("name"),
                "person_number": officer.get("person_number"),
                "date_of_birth": officer.get("date_of_birth"),
            })
    return written, serving_directors


def _fetch_insolvency(client: PipelineHTTPClient, conn, module_name: str,
                       company_number: str, profile: dict | None, *,
                       force: bool = False) -> int:
    """Insolvency cases, where the company profile says there are any.

    Gated on the profile's own `links.insolvency` rather than probing every
    company: the register tells us where to look, and asking nine companies a
    question eight of them answer 404 to is a request budget spent on nothing.

    `force=True` skips the gate. The insolvency-cases stream consumer passes
    it: a stream event naming this company on this stream *is* the positive
    signal the gate otherwise exists to approximate, and there may be no
    fresh profile to hand at all (the stream names only the company, not its
    profile).
    """
    if not force:
        links = (profile or {}).get("links") or {}
        if not (links.get("insolvency") or (profile or {}).get("has_insolvency_history")):
            return 0

    result = client.get(f"{API_BASE}/company/{company_number}/insolvency")
    if not result.ok:
        # A 404 here would contradict the profile, which is worth noticing
        # rather than passing over — the gate above means we only ask when the
        # source has said there is something to fetch.
        db.record_review_item(
            conn, module_name, "company_insolvency_unavailable", company_number,
            json.dumps({"status": result.status_code,
                         "note": "the company profile advertises an insolvency history but the "
                                  "case list did not answer"}))
        return 0

    written = 0
    for index, case in enumerate(json.loads(result.body).get("cases", []), start=1):
        case_number = str(case.get("number") or index)
        db.upsert(conn, "company_insolvency_cases", {
            "company_number": company_number,
            "case_number": case_number,
            "case_type": case.get("type"),
            **_provenance(result),
        }, natural_key=["company_number", "case_number"])
        written += 1

        for entry in case.get("dates") or []:
            if not entry.get("type"):
                continue
            db.upsert(conn, "company_insolvency_case_dates", {
                "company_number": company_number,
                "case_number": case_number,
                "date_type": entry["type"],
                "date_value": entry.get("date"),
            }, natural_key=["company_number", "case_number", "date_type"])

        for practitioner in case.get("practitioners") or []:
            if not practitioner.get("name"):
                continue
            # Name, role and dates only. The address the source supplies is the
            # practitioner's firm and answers nothing this pipeline asks.
            db.upsert(conn, "restricted_company_insolvency_practitioners", {
                "company_number": company_number,
                "case_number": case_number,
                "practitioner_name": practitioner["name"],
                "role": practitioner.get("role"),
                "appointed_on": practitioner.get("appointed_on"),
                "ceased_to_act_on": practitioner.get("ceased_to_act_on"),
            }, natural_key=["company_number", "case_number", "practitioner_name"])

    return written


def _fetch_psc(client: PipelineHTTPClient, conn, module_name: str,
                company_number: str) -> int:
    """People with Significant Control — the ownership edges.

    One paged fetch per company; every company answers this endpoint (with a
    register, a statement, or nothing), so unlike insolvency there is no gate
    and a non-ok answer is recorded rather than passed over. A company whose
    register is redacted answers with a statement rather than items; that is
    worth a review item, because the absence of PSCs is then a redaction, not
    a fact.
    """
    written = 0
    start_index = 0
    statement_recorded = False

    while True:
        result = client.get(
            f"{API_BASE}/company/{company_number}/persons-with-significant-control",
            params={"items_per_page": 100, "start_index": start_index})
        if not result.ok:
            db.record_review_item(conn, module_name, "company_psc_unavailable",
                                   company_number,
                                   json.dumps({"status": result.status_code}))
            return written
        data = json.loads(result.body)
        register_view = data.get("register_view")
        items = data.get("items") or []

        if data.get("statement") and not statement_recorded:
            statement_recorded = True
            db.record_review_item(
                conn, module_name, "psc_register_statement", company_number,
                json.dumps({"register_view": register_view,
                            "note": "the register returns a statement rather than "
                                    "a list of PSCs (typically an exemption or a "
                                    "protected register); the absence of rows is "
                                    "a redaction, not a finding"}))

        for item in items:
            links = item.get("links") or {}
            self_link = links.get("self") or ""
            psc_ref = self_link.rstrip("/").rpartition("/")[2]
            if not psc_ref:
                # No register id: derive a stable one from the item's own
                # fields so re-runs stay idempotent.
                basis = f"{company_number}|{item.get('kind')}|{item.get('name')}"
                psc_ref = "H" + hashlib.sha256(basis.encode()).hexdigest()[:16]

            identification = item.get("identification") or {}
            db.upsert(conn, "company_psc", {
                "company_number": company_number,
                "psc_ref": psc_ref,
                "kind": item.get("kind"),
                "natures_of_control": ",".join(item.get("natures_of_control") or []) or None,
                "notifiable": 1 if item.get("notifiable") else 0,
                "is_sanctioned": 1 if item.get("is_sanctioned") else 0,
                "ceased_on": item.get("ceased_on"),
                "notified_on": item.get("notified_on"),
                "identification_company_number": identification.get("company_number"),
                "identification_legal_form": identification.get("legal_form"),
                "identification_country_registered": identification.get("country_registered"),
                "register_view": register_view,
                **_provenance(result),
            }, natural_key=["company_number", "psc_ref"])
            written += 1

            if "individual" in str(item.get("kind") or ""):
                born = item.get("date_of_birth") or {}
                db.upsert(conn, "restricted_company_psc", {
                    "company_number": company_number,
                    "psc_ref": psc_ref,
                    "name": item.get("name"),
                    "date_of_birth_month": born.get("month"),
                    "date_of_birth_year": born.get("year"),
                    "nationality": item.get("nationality"),
                    "country_of_residence": item.get("country_of_residence"),
                    "ceased_on": item.get("ceased_on"),
                }, natural_key=["company_number", "psc_ref"])

        total_count = data.get("total_count", 0)
        start_index += len(items)
        if not items or start_index >= total_count:
            return written


def _fetch_filings(client: PipelineHTTPClient, conn, module_name: str, company_number: str,
                    limit: int | None) -> int:
    written = 0
    start_index = 0
    cap = limit or MAX_FILINGS
    while written < cap:
        result = client.get(f"{API_BASE}/company/{company_number}/filing-history",
                             params={"items_per_page": FILINGS_PER_PAGE, "start_index": start_index})
        if not result.ok:
            db.record_review_item(conn, module_name, "company_filings_unavailable", company_number,
                                   json.dumps({"status": result.status_code}))
            return written
        data = json.loads(result.body)
        items = data.get("items", [])
        if not items:
            return written
        for item in items:
            transaction_id = item.get("transaction_id")
            if not transaction_id:
                continue
            links = item.get("links") or {}
            document_url = links.get("document_metadata")
            db.upsert(conn, "company_filings", {
                "company_number": company_number,
                "transaction_id": transaction_id,
                "filing_date": item.get("date"),
                "category": item.get("category"),
                "subcategory": (item.get("subcategory") if isinstance(item.get("subcategory"), str)
                                 else ",".join(item.get("subcategory") or []) or None),
                "description": item.get("description"),
                "document_url": document_url,
                **_provenance(result),
            }, natural_key=["company_number", "transaction_id"])
            written += 1
            if written >= cap:
                break
        start_index += len(items)
        if start_index >= data.get("total_count", 0):
            break
    return written


_CHARGE_DATE_FIELDS = (
    "acquired_on", "created_on", "delivered_on",
    "satisfied_on", "resolved_on", "covering_instrument_date",
)


def _charge_ref(item: dict, company_number: str) -> str:
    self_link = (item.get("links") or {}).get("self") or ""
    ref = self_link.rstrip("/").rpartition("/")[2]
    if ref:
        return ref
    # No id in the register response: derive a stable one the same way
    # _officer_ref/company_psc's psc_ref already do, so a re-run stays
    # idempotent.
    basis = f"{company_number}|{item.get('created_on')}|{(item.get('classification') or {}).get('description')}"
    return "H" + hashlib.sha256(basis.encode()).hexdigest()[:16]


def _fetch_charges(client: PipelineHTTPClient, conn, module_name: str,
                    company_number: str, profile: dict | None, *,
                    force: bool = False) -> int:
    """Charges register (mortgages, debentures and the like registered
    against a company) -- new in JON-36, run unconditionally on every
    ordinary sweep regardless of whether streaming is ever turned on.

    Gated on the profile's own `links.charges`, the same pattern
    `_fetch_insolvency` uses for `links.insolvency` -- unless `force=True`,
    which the charges-stream consumer passes, since the event is itself the
    positive signal.

    VERIFY BEFORE SHIPPING: `CHARGES_PER_PAGE` and the field names below
    (`persons_entitled` shape, the exact set of date fields a charge
    carries) are taken from Companies House's published documentation, not a
    freshly captured live response. Confirm against a real
    `/company/{number}/charges` call before relying on this in production --
    the ticket's own opening instruction is to verify current source shape
    first.
    """
    if not force:
        links = (profile or {}).get("links") or {}
        if not links.get("charges"):
            return 0

    written = 0
    start_index = 0
    while True:
        result = client.get(f"{API_BASE}/company/{company_number}/charges",
                             params={"items_per_page": CHARGES_PER_PAGE, "start_index": start_index})
        if not result.ok:
            if result.status_code == 404:
                return written  # no charges register for this company; not an error
            db.record_review_item(conn, module_name, "company_charges_unavailable", company_number,
                                   json.dumps({"status": result.status_code}))
            return written
        data = json.loads(result.body)
        items = data.get("items", [])
        for item in items:
            charge_ref = _charge_ref(item, company_number)
            classification = item.get("classification") or {}
            persons = item.get("persons_entitled") or []
            db.upsert(conn, "company_charges", {
                "company_number": company_number,
                "charge_ref": charge_ref,
                "classification_type": classification.get("type"),
                "classification_description": classification.get("description"),
                "status": item.get("status"),
                "charge_code": item.get("charge_code"),
                "particulars": (item.get("particulars") or {}).get("description"),
                "persons_entitled": ", ".join(
                    p["name"] for p in persons if p.get("name")) or None,
                **_provenance(result),
            }, natural_key=["company_number", "charge_ref"])
            written += 1

            for date_type in _CHARGE_DATE_FIELDS:
                value = item.get(date_type)
                if value:
                    db.upsert(conn, "company_charge_dates", {
                        "company_number": company_number,
                        "charge_ref": charge_ref,
                        "date_type": date_type,
                        "date_value": value,
                    }, natural_key=["company_number", "charge_ref", "date_type"])

        total_count = data.get("total_count", 0)
        start_index += len(items)
        if not items or start_index >= total_count:
            return written


def _refresh_company(client: PipelineHTTPClient, conn, module_name: str,
                      company_number: str, provider_key: str | None,
                      match_basis: str, *, filings_limit: int | None = None) -> dict | None:
    """One company's full authoritative refresh -- profile, previous names,
    officers, filings, insolvency, PSC, charges.

    Shared by the REST sweep's per-company loop and by every streaming
    consumer, so a company reached by either route is written through
    exactly one code path. See the module docstring's STREAMING section for
    why a stream event never writes anything itself.
    """
    data = _fetch_company(client, conn, module_name, company_number, provider_key, match_basis)
    if data is None:
        return None

    # Only write an identifier back for entities whose link to the provider
    # came from an authoritative cross-reference, never from a name match —
    # otherwise a same-named unrelated company would become a permanent (if
    # unverified) part of the group.
    if provider_key is not None:
        providers.record_discovered_identifier(
            conn, provider_key, "company_number", company_number,
            discovered_by=module_name, role=data.get("type"))

    officers, directors = _fetch_officers(client, conn, module_name, company_number)
    filings = _fetch_filings(client, conn, module_name, company_number, filings_limit)
    insolvency_cases = _fetch_insolvency(client, conn, module_name, company_number, data)
    psc = _fetch_psc(client, conn, module_name, company_number)
    charges = _fetch_charges(client, conn, module_name, company_number, data)
    return {
        "data": data,
        "directors": directors,
        "officers": officers,
        "filings": filings,
        "insolvency_cases": insolvency_cases,
        "psc": psc,
        "charges": charges,
    }


# --- streaming discovery (JON-36) -------------------------------------------
#
# See the module docstring's STREAMING section for the design rationale.
# Each consumer below is a thin binding of one stream name to the existing
# fetch function it triggers on a match; _consume_stream owns the actual
# connect/checkpoint/error-handling loop.

def _known_company_numbers(conn) -> set[str]:
    """Every company already in `companies`, any match_basis -- worth
    watching for future changes even before a human confirms a name-only
    match, since the company row itself is real data either way."""
    return {row["company_number"] for row in
            conn.execute("SELECT company_number FROM companies")}


def _company_number_from_resource_uri(resource_uri: str | None) -> str | None:
    """'/company/12345678/filing-history/...' -> '12345678'. Cheap and
    common to all four streams; avoids inspecting a whole event body just to
    decide whether it is worth acting on."""
    if not resource_uri:
        return None
    m = _RESOURCE_URI_COMPANY.match(resource_uri)
    return normalise_company_number(m.group(1)) if m else None


def _record_stream_event(conn, stream: str, event, resource_uri: str | None,
                          company_number: str | None) -> None:
    """The one row that satisfies exact-byte provenance for the triggering
    notification itself, independent of whatever REST fetch it causes.
    Called only for a matched event whose bytes the caller has already
    archived via `client.archive_line`.
    """
    envelope = event.data or {}
    event_meta = envelope.get("event") or {}
    db.upsert(conn, "company_stream_events", {
        "stream": stream,
        "timepoint": event_meta.get("timepoint"),
        "resource_kind": envelope.get("resource_kind"),
        "resource_uri": resource_uri,
        "event_type": event_meta.get("type"),
        "company_number": company_number,
        "source_url": f"{STREAM_BASE}{resource_uri}" if resource_uri else f"{STREAM_BASE}/{stream}",
        "retrieved_at": event.received_at.isoformat(),
        "http_status": 200,
        "source_system": STREAM_SOURCE_SYSTEM,
        "payload_sha256": hashlib.sha256(event.raw).hexdigest(),
    }, natural_key=["stream", "timepoint"])


def _consume_stream(client: PipelineHTTPClient, conn, module_name: str, stream: str,
                     known: set[str], settings, on_match) -> dict:
    """Open (or reopen, up to `companies_house_stream_max_reconnects` times)
    a connection at the checkpointed timepoint for one stream, and for every
    event naming a company this pipeline already tracks: archive the raw
    line, record it, and call `on_match(company_number, event_data)`.

    Progress is checkpointed (`module_cursors`, key
    `m04_companies:stream:<stream>`) after a clean pass and before returning
    on any of the three handled failure modes, so a partial run's real
    progress is never discarded. One stream's failure never aborts the
    other three -- each is a separate call from `run()`.
    """
    cursor_key = f"m04_companies:stream:{stream}"
    stats = {"scanned": 0, "matched": 0, "reconnects": 0, "parse_failures": 0}
    reconnects_left = settings.companies_house_stream_max_reconnects

    while True:
        cursor = db.get_cursor(conn, cursor_key)
        params = ({"timepoint": cursor[len("TIMEPOINT:"):]}
                  if cursor and cursor.startswith("TIMEPOINT:") else None)
        last_timepoint = None
        try:
            for event in client.stream_events(
                    f"{STREAM_BASE}/{stream}", params=params,
                    max_events=settings.companies_house_stream_max_events,
                    max_seconds=settings.companies_house_stream_max_seconds):
                stats["scanned"] += 1
                if event.parse_error:
                    stats["parse_failures"] += 1
                    db.record_parse_failure(
                        conn, module_name, "companies_house_stream_event",
                        event.raw.decode("utf-8", "replace")[:500], event.parse_error,
                        f"{STREAM_BASE}/{stream}")
                    # No timepoint could be read from an unparseable line, so
                    # the cursor cannot skip past it -- a persistently
                    # malformed line would stall this stream at that point
                    # until it is cleared by hand. Expected to be vanishingly
                    # rare against a first-party government API.
                    continue

                envelope = event.data or {}
                resource_uri = envelope.get("resource_uri")
                number = _company_number_from_resource_uri(resource_uri)
                timepoint = (envelope.get("event") or {}).get("timepoint")

                if number is not None and number in known:
                    stats["matched"] += 1
                    client.archive_line(event.raw)
                    _record_stream_event(conn, stream, event, resource_uri, number)
                    on_match(number, envelope)
                    conn.commit()

                if timepoint is not None:
                    last_timepoint = timepoint

            if last_timepoint is not None:
                db.set_cursor(conn, cursor_key, f"TIMEPOINT:{last_timepoint}")
                conn.commit()
            return stats  # budget reached, or a clean end of the connection

        except StreamCursorStale:
            db.record_review_item(
                conn, module_name, "companies_house_stream_cursor_stale", stream,
                json.dumps({"note": "Companies House's streaming retention window is "
                            "undocumented; the cursor is reset to start from now rather "
                            "than guessing a replacement timepoint -- any change "
                            "published in the gap is unrecoverable and not backfilled"}))
            db.set_cursor(conn, cursor_key, "")
            conn.commit()
            log.warning("companies.stream_cursor_stale", stream=stream)
            return stats

        except StreamRateLimited as exc:
            if last_timepoint is not None:
                db.set_cursor(conn, cursor_key, f"TIMEPOINT:{last_timepoint}")
                conn.commit()
            # Do not busy-wait inside a foreground pipeline run: stop
            # consuming this stream for this run and let the next scheduled
            # invocation retry from the checkpoint above.
            log.warning("companies.stream_rate_limited", stream=stream,
                        retry_after=exc.retry_after)
            return stats

        except StreamTransientError:
            if last_timepoint is not None:
                db.set_cursor(conn, cursor_key, f"TIMEPOINT:{last_timepoint}")
                conn.commit()
            reconnects_left -= 1
            stats["reconnects"] += 1
            log.warning("companies.stream_transient_error", stream=stream,
                        reconnects_left=reconnects_left)
            if reconnects_left <= 0:
                return stats
            time.sleep(settings.companies_house_stream_connect_retry_wait_seconds)
            continue


def _consume_company_stream(rest_client: PipelineHTTPClient, stream_client: PipelineHTTPClient,
                             conn, module_name: str, known: set[str], settings) -> dict:
    def on_match(number, _envelope):
        row = conn.execute(
            "SELECT provider_key, match_basis FROM companies WHERE company_number = %s",
            (number,)).fetchone()
        if row is None:
            return
        _refresh_company(rest_client, conn, module_name, number,
                          row["provider_key"], row["match_basis"])
    return _consume_stream(stream_client, conn, module_name, "companies", known, settings, on_match)


def _seed_accounts_candidates(conn, company_number: str) -> int:
    """After `_fetch_filings` has refreshed `company_filings` for this
    company, pick up any 'accounts'-category filing not yet a candidate.

    Reads from `company_filings` rather than the raw stream event: the REST
    re-fetch just ran and is the authoritative copy, and this makes the
    function work identically whether it was called after a stream event or
    any future one-off backfill, with no dependence on the event's own shape.
    """
    rows = conn.execute(
        "SELECT transaction_id, filing_date, description, subcategory, document_url "
        "FROM company_filings WHERE company_number = %s AND category = 'accounts' "
        "AND document_url IS NOT NULL", (company_number,)).fetchall()
    written = 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for row in rows:
        # The candidate's own payload_sha256 hashes a synthetic identity
        # string, not fetched bytes -- the candidate was never itself
        # "fetched" as a document, the same "candidate provenance is the
        # listing, not the document" pattern the three existing promote.py
        # kinds already use. The real document bytes are only hashed once a
        # human promotes it, via pipeline/promote.py.
        identity = f"{company_number}|{row['transaction_id']}"
        db.upsert(conn, "companies_house_accounts_candidates", {
            "company_number": company_number,
            "candidate_url": row["document_url"],
            "transaction_id": row["transaction_id"],
            "filing_date": row["filing_date"],
            "description": row["description"],
            "accounts_type": row["subcategory"],
            "discovered_at": now,
            "discovery_method": "filing_history_stream",
            "source_url": f"{API_BASE}/company/{company_number}/filing-history/{row['transaction_id']}",
            "retrieved_at": now,
            "http_status": 200,
            "source_system": ACCOUNTS_SOURCE_SYSTEM,
            "payload_sha256": hashlib.sha256(identity.encode()).hexdigest(),
        }, natural_key=["company_number", "candidate_url"],
           preserve=("verified", "rejected", "verified_at"))
        written += 1
    return written


def _consume_filing_stream(rest_client: PipelineHTTPClient, stream_client: PipelineHTTPClient,
                            conn, module_name: str, known: set[str], settings) -> dict:
    def on_match(number, _envelope):
        _fetch_filings(rest_client, conn, module_name, number, limit=None)
        _seed_accounts_candidates(conn, number)
    return _consume_stream(stream_client, conn, module_name, "filings", known, settings, on_match)


def _consume_insolvency_stream(rest_client: PipelineHTTPClient, stream_client: PipelineHTTPClient,
                                conn, module_name: str, known: set[str], settings) -> dict:
    def on_match(number, _envelope):
        _fetch_insolvency(rest_client, conn, module_name, number, profile=None, force=True)
    return _consume_stream(stream_client, conn, module_name, "insolvency-cases", known, settings, on_match)


def _consume_charges_stream(rest_client: PipelineHTTPClient, stream_client: PipelineHTTPClient,
                             conn, module_name: str, known: set[str], settings) -> dict:
    def on_match(number, _envelope):
        _fetch_charges(rest_client, conn, module_name, number, profile=None, force=True)
    return _consume_stream(stream_client, conn, module_name, "charges", known, settings, on_match)


# --- disqualified directors ---------------------------------------------------
#
# See the module docstring for why this is narrow and why it stores almost
# nothing. The short version: a wrong match here is an assertion that a named
# person was banned from directing companies.

def is_serving_director(officer: dict) -> bool:
    """Serving directors only.

    Disqualification bars a person from acting as a director, so a serving
    director is the only officer the question is actually about. Sweeping
    resigned officers and company secretaries as well would multiply the
    number of people searched against a disqualification register several-fold
    in exchange for answering a question nobody asked.
    """
    role = (officer.get("officer_role") or "").lower()
    return "director" in role and not officer.get("resigned_on")


def split_officer_name(name: str | None) -> tuple[str, list[str]]:
    """Companies House writes officer names as "SURNAME, Forename Other".

    Returns (surname, forenames), both lower-cased, or ("", []) when the name
    cannot be split. A name with no comma is treated as "Forename … Surname",
    which is the other form the register uses.
    """
    text = re.sub(r"\s+", " ", (name or "").strip())
    if not text:
        return "", []
    if "," in text:
        surname, _, forenames = text.partition(",")
        return surname.strip().lower(), [p.lower() for p in forenames.split() if p]
    parts = text.split()
    if len(parts) < 2:
        return "", []
    return parts[-1].lower(), [p.lower() for p in parts[:-1]]


def disqualification_search_term(name: str | None) -> str | None:
    """The name to put to the register's search, as a person would write it."""
    surname, forenames = split_officer_name(name)
    if not surname or not forenames:
        return None
    return f"{forenames[0]} {surname}".strip()


def names_agree(officer_name: str | None, register_title: str | None) -> bool:
    """Whether an officer and a register hit are even the same name.

    The two sides write names in opposite orders — Companies House gives an
    officer as "SMITH, Aaron Donald" and the register gives a search hit as
    "Aaron Donald SMITH" — which split_officer_name handles because the comma
    is what distinguishes them.
    """
    surname, forenames = split_officer_name(officer_name)
    hit_surname, hit_forenames = split_officer_name(register_title)
    if not surname or not forenames or not hit_surname or not hit_forenames:
        return False
    return surname == hit_surname and forenames[0] == hit_forenames[0]


def dates_of_birth_agree(officer: dict, published: str | None) -> bool:
    """Month and year only — all Companies House publishes for a director.

    Weak alone, decisive alongside a full name. A missing date on either side
    is never treated as agreement: no corroboration is possible, so there is
    nothing to corroborate with.
    """
    born = officer.get("date_of_birth") or {}
    month, year = born.get("month"), born.get("year")
    if not month or not year or not published or len(str(published)) < 7:
        return False
    text = str(published)
    try:
        return int(text[:4]) == int(year) and int(text[5:7]) == int(month)
    except ValueError:
        return False


def search_hit_is_worth_opening(officer: dict, item: dict) -> tuple[bool, bool]:
    """(name agrees, date of birth agrees) for one register search hit.

    Decided from the search response alone, which already carries the hit's
    full name and date of birth. This is what keeps the sweep bounded: the
    register's search is fuzzy — a search for one director's name returns
    every approximate match it holds — and opening each hit's detail record to
    find that out would be one request per stranger, at one every two seconds,
    per director. Nothing is opened until both the name and the date of birth
    already agree.
    """
    if not names_agree(officer.get("name"), item.get("title")):
        return False, False
    return True, dates_of_birth_agree(officer, item.get("date_of_birth"))


def disqualification_match_basis(officer: dict, record: dict) -> str | None:
    """How, if at all, a register record corroborates an officer's identity.

    'person_number'          both sides carry the same Companies House person
                              number — an identifier match.
    'name_and_date_of_birth' surname, first forename and the published month
                              and year of birth all agree.
    None                     anything less, which is never stored.

    The date-of-birth test is what makes this usable at all. Companies House
    publishes only a month and a year for a serving director, which is weak on
    its own but decisive alongside a full name: sharing a surname, a forename
    and a birth month with a disqualified director is a coincidence worth
    acting on, sharing a name alone is not.
    """
    officer_person = str(officer.get("person_number") or "").strip()
    record_person = str(record.get("person_number") or "").strip()
    if officer_person and officer_person == record_person:
        return "person_number"

    surname, forenames = split_officer_name(officer.get("name"))
    if not surname or not forenames:
        return None
    if surname != (record.get("surname") or "").strip().lower():
        return None
    if forenames[0] != (record.get("forename") or "").strip().lower():
        return None

    born = officer.get("date_of_birth") or {}
    month, year = born.get("month"), born.get("year")
    if not month or not year:
        # No published date of birth means no corroboration is possible, and a
        # name on its own is not enough to write this row.
        return None
    record_dob = str(record.get("date_of_birth") or "")
    if len(record_dob) < 7:
        return None
    try:
        if int(record_dob[:4]) != int(year) or int(record_dob[5:7]) != int(month):
            return None
    except ValueError:
        return None
    return "name_and_date_of_birth"


def _sweep_disqualifications(client: PipelineHTTPClient, conn, module_name: str,
                              directors: list[dict]) -> tuple[int, int]:
    """Check serving directors against the disqualified officers register.

    Returns (rows written, candidates queued for review). One search per
    distinct person, not per appointment: a director of three companies in a
    group is one person and one question.
    """
    written = 0
    queued = 0
    searched: dict[str, list[dict]] = {}
    for director in directors:
        term = disqualification_search_term(director.get("name"))
        if term:
            searched.setdefault(term, []).append(director)

    for term, appointments in sorted(searched.items()):
        result = client.get(f"{API_BASE}/search/disqualified-officers",
                             params={"q": term, "items_per_page": 20})
        if not result.ok:
            db.record_review_item(
                conn, module_name, "disqualification_search_failed", term,
                json.dumps({"status": result.status_code}))
            continue

        for item in json.loads(result.body).get("items", []):
            self_link = (item.get("links") or {}).get("self") or ""
            # Corporate disqualifications exist (sanctioned entities) but a
            # company is not a serving director of these providers.
            if "/natural/" not in self_link:
                continue

            # Which of this term's directors, if any, this hit could be —
            # decided from the search response, before anything is opened.
            candidates = []
            for director in appointments:
                name_agrees, dob_agrees = search_hit_is_worth_opening(director, item)
                if name_agrees and dob_agrees:
                    candidates.append(director)
                elif name_agrees:
                    # Same name, different birth month or year: a namesake.
                    # Recorded so the sweep's misses are visible, and
                    # deliberately without the register record's own name,
                    # date of birth or case — the whole point of the row is
                    # that this is NOT known to be the same person, and
                    # copying their details into it would attach a
                    # disqualified person's identity to a director who is not
                    # them.
                    db.record_review_item(
                        conn, module_name, "unconfirmed_disqualification_name_match",
                        f"{director['company_number']} {director['officer_ref']}",
                        json.dumps({"searched_term": term,
                                     "note": "the disqualified officers register holds a record "
                                              "under this director's name whose date of birth "
                                              "does not match; NOT stored as a disqualification"}))
                    queued += 1
            if not candidates:
                continue

            detail_result = client.get(f"{API_BASE}{self_link}")
            if not detail_result.ok:
                continue
            record = json.loads(detail_result.body)

            for director in candidates:
                # Re-checked against the full record, which carries the person
                # number the search response does not. The search filter above
                # is about bounding requests; this is the decision.
                basis = disqualification_match_basis(director, record)
                if basis is None:
                    continue

                for disqualification in record.get("disqualifications") or []:
                    case_identifier = disqualification.get("case_identifier")
                    if not case_identifier:
                        continue
                    reason = disqualification.get("reason") or {}
                    db.upsert(conn, "restricted_officer_disqualifications", {
                        "company_number": director["company_number"],
                        "officer_ref": director["officer_ref"],
                        "officer_name": director.get("name"),
                        "case_identifier": case_identifier,
                        "disqualification_type": disqualification.get("disqualification_type"),
                        "disqualified_from": disqualification.get("disqualified_from"),
                        "disqualified_until": disqualification.get("disqualified_until"),
                        "reason_act": reason.get("act"),
                        "reason_description": reason.get("description_identifier"),
                        "disqualified_company_names": ", ".join(
                            disqualification.get("company_names") or []) or None,
                        "match_basis": basis,
                        **_provenance(detail_result),
                    }, natural_key=["company_number", "officer_ref", "case_identifier"])
                    written += 1

    return written, queued


def _search_candidates(client: PipelineHTTPClient, conn, module_name: str,
                        known: set[str]) -> list[tuple[str, str, str]]:
    """Search each provider name variant. Returns exact matches only;
    everything else is queued for human review rather than accepted.
    """
    accepted: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    for provider_key, variants in SUPPLIER_NAME_VARIANTS.items():
        for variant in variants:
            if _normalise_company_name(variant) in _UNSAFE_NAME_MATCHES:
                continue
            result = client.get(f"{API_BASE}/search/companies",
                                 params={"q": variant, "items_per_page": 50})
            if not result.ok:
                db.record_review_item(conn, module_name, "company_search_failed", variant,
                                       json.dumps({"status": result.status_code}))
                continue
            for item in json.loads(result.body).get("items", []):
                number = normalise_company_number(item.get("company_number") or "")
                title = item.get("title") or ""
                if not number or number in known or number in seen:
                    continue
                matched_key = match_company_name(title)
                if matched_key == provider_key:
                    seen.add(number)
                    accepted.append((provider_key, number, title))
                    # Captured, but NOT linked to the provider: sharing a name
                    # is not being the same legal entity. A human confirms.
                    db.record_review_item(
                        conn, module_name, "unconfirmed_name_match", f"{number} {title}",
                        json.dumps({"provider_key_candidate": provider_key,
                                     "searched_variant": variant,
                                     "note": "exact name match only; confirm this is the same legal "
                                              "entity before linking (check incorporation date, status "
                                              "and previous names) then add to provider_identifiers"}),
                    )
                else:
                    db.record_review_item(
                        conn, module_name, "possible_group_company", f"{number} {title}",
                        json.dumps({"searched_variant": variant, "provider_key": provider_key,
                                     "note": "name did not exactly match a configured variant; "
                                              "confirm before treating as part of the group"}),
                    )
    return accepted


def _run_streams(rest_client: PipelineHTTPClient, stream_client: PipelineHTTPClient,
                  conn, module_name: str, settings) -> None:
    """The four stream consumers, over the companies this pipeline already
    tracks. Shared by `--stream-only` and by the tail of an ordinary sweep
    when streaming is enabled.

    Two clients, deliberately: `stream_client` (the streaming key) only ever
    reads events and archives the odd matched line; every authoritative
    write goes through `rest_client` (the REST key) via the same fetch
    functions the ordinary sweep uses. Companies House states the two keys
    are separate registered applications and are not interchangeable, so a
    stream-triggered REST call must never ride on the streaming client's
    auth.
    """
    known = _known_company_numbers(conn)
    for consume in (_consume_company_stream, _consume_filing_stream,
                    _consume_insolvency_stream, _consume_charges_stream):
        stats = consume(rest_client, stream_client, conn, module_name, known, settings)
        log.info("companies.stream_consumed", fn=consume.__name__, **stats)


@register_module(
    "m04_companies",
    supports_since=False,
    depends_on=("m03_charity_finance", "m05_cqc",),
    depends_note="both publish company numbers into provider_identifiers; without them every name match stays unconfirmed",
    since_note="company profiles and officer lists are current-state snapshots, not a dated stream. "
               "Streaming timepoints (module_cursors, keys 'm04_companies:stream:<name>') are a "
               "separate resumability mechanism from --since and are unaffected by it.",
    supports_source=True,
    source_note="--stream-only runs just the bounded streaming catch-up (companies/filings/"
                "insolvency/charges) and skips the full REST sweep; see pipeline/cli.py.",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m04_companies"
    conn = ctx.conn
    providers.seed_providers(conn, commit=not ctx.dry_run)

    if ctx.source == "stream":
        # --stream-only: frequent, cheap catch-up. Skips the full REST sweep
        # entirely -- see the module docstring's STREAMING section for why
        # this is meant to be scheduled far more often than the normal run.
        if not ctx.settings.companies_house_streaming_enabled:
            log.info("companies.stream_disabled",
                      note="COMPANIES_HOUSE_STREAMING_ENABLED is false; nothing to do")
            return
        api_key = ctx.settings.require_companies_house_key()
        streaming_key = ctx.settings.require_companies_house_streaming_key()
        with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as rest_client, \
             PipelineHTTPClient(STREAM_SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as stream_client:
            rest_client.set_basic_auth(api_key, "")
            stream_client.set_basic_auth(streaming_key, "")
            _run_streams(rest_client, stream_client, conn, module_name, ctx.settings)
        return

    api_key = ctx.settings.require_companies_house_key()

    companies_written = 0
    officers_written = 0
    filings_written = 0
    insolvency_cases = 0
    psc_written = 0
    charges_written = 0
    serving_directors: list[dict] = []

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        client.set_basic_auth(api_key, "")

        seeds = _seed_company_numbers(conn)
        known = {number for _, number in seeds}
        targets = [(pk, num, "seed") for pk, num in seeds]

        for provider_key, number, title in _search_candidates(client, conn, module_name, known):
            known.add(number)
            # provider_key deliberately None: see module docstring. The company
            # is recorded, the link is not asserted until a human confirms it.
            targets.append((None, number, "name_only_unconfirmed"))
            log.info("companies.unconfirmed_name_match", provider_key_candidate=provider_key,
                      company_number=number, title=title)

        if not targets:
            log.info("companies.no_targets",
                      note="no seeded company numbers and no exact name matches")
            return

        for provider_key, company_number, match_basis in ctx.track(targets, "companies"):
            refreshed = _refresh_company(client, conn, module_name, company_number,
                                          provider_key, match_basis, filings_limit=ctx.limit)
            if refreshed is None:
                continue
            companies_written += 1
            officers_written += refreshed["officers"]
            serving_directors.extend(refreshed["directors"])
            filings_written += refreshed["filings"]
            insolvency_cases += refreshed["insolvency_cases"]
            psc_written += refreshed["psc"]
            charges_written += refreshed["charges"]

            if not ctx.dry_run:
                conn.commit()

        # After every company, so a director of several group companies is one
        # search rather than one per appointment.
        ctx.phase("checking directors against the disqualified register")
        disqualifications, unconfirmed = _sweep_disqualifications(
            client, conn, module_name, serving_directors)
        if not ctx.dry_run:
            conn.commit()

    if ctx.settings.companies_house_streaming_enabled:
        # Fresh clients, not the REST one above (which is already closed by
        # here): stream-sourced rows must carry
        # source_system="companies_house_streaming", not "companies_house",
        # and the streaming key is a separate registered application from
        # the REST key -- see _run_streams's docstring for why both are
        # opened even though only one call site (the REST sweep) is active.
        ctx.phase("consuming Companies House streams")
        streaming_key = ctx.settings.require_companies_house_streaming_key()
        with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as rest_client, \
             PipelineHTTPClient(STREAM_SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as stream_client:
            rest_client.set_basic_auth(api_key, "")
            stream_client.set_basic_auth(streaming_key, "")
            _run_streams(rest_client, stream_client, conn, module_name, ctx.settings)

    log.info("companies.run_complete", companies=companies_written,
              officers=officers_written, filings=filings_written,
              insolvency_cases=insolvency_cases,
              psc=psc_written,
              charges=charges_written,
              serving_directors_checked=len(serving_directors),
              disqualifications=disqualifications,
              unconfirmed_disqualification_names=unconfirmed)
