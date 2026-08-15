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
"""
from __future__ import annotations

import hashlib
import json
import re

import structlog

from pipeline import db, providers
from pipeline.http import PipelineHTTPClient
from pipeline.keywords import SUPPLIER_NAME_VARIANTS
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "companies_house"
API_BASE = "https://api.company-information.service.gov.uk"
FILINGS_PER_PAGE = 100
MAX_FILINGS = 200


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
                       company_number: str, profile: dict) -> int:
    """Insolvency cases, where the company profile says there are any.

    Gated on the profile's own `links.insolvency` rather than probing every
    company: the register tells us where to look, and asking nine companies a
    question eight of them answer 404 to is a request budget spent on nothing.
    """
    links = profile.get("links") or {}
    if not (links.get("insolvency") or profile.get("has_insolvency_history")):
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


@register_module(
    "m04_companies",
    supports_since=False,
    depends_on=("m03_charity_finance", "m05_cqc",),
    depends_note="both publish company numbers into provider_identifiers; without them every name match stays unconfirmed",
    since_note="company profiles and officer lists are current-state snapshots, not a dated stream",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m04_companies"
    conn = ctx.conn
    api_key = ctx.settings.require_companies_house_key()
    providers.seed_providers(conn, commit=not ctx.dry_run)

    companies_written = 0
    officers_written = 0
    filings_written = 0
    insolvency_cases = 0
    psc_written = 0
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
            data = _fetch_company(client, conn, module_name, company_number, provider_key, match_basis)
            if data is None:
                continue
            companies_written += 1

            # Only write an identifier back for entities whose link to the
            # provider came from an authoritative cross-reference, never from
            # a name match — otherwise a same-named unrelated company would
            # become a permanent (if unverified) part of the group.
            if provider_key is not None:
                providers.record_discovered_identifier(
                    conn, provider_key, "company_number", company_number,
                    discovered_by=module_name,
                    role=data.get("type"),
                )

            officers, directors = _fetch_officers(client, conn, module_name, company_number)
            officers_written += officers
            serving_directors.extend(directors)
            filings_written += _fetch_filings(client, conn, module_name, company_number, ctx.limit)
            insolvency_cases += _fetch_insolvency(
                client, conn, module_name, company_number, data)
            psc_written += _fetch_psc(client, conn, module_name, company_number)

            if not ctx.dry_run:
                conn.commit()

        # After every company, so a director of several group companies is one
        # search rather than one per appointment.
        ctx.phase("checking directors against the disqualified register")
        disqualifications, unconfirmed = _sweep_disqualifications(
            client, conn, module_name, serving_directors)
        if not ctx.dry_run:
            conn.commit()

    log.info("companies.run_complete", companies=companies_written,
              officers=officers_written, filings=filings_written,
              insolvency_cases=insolvency_cases,
              psc=psc_written,
              serving_directors_checked=len(serving_directors),
              disqualifications=disqualifications,
              unconfirmed_disqualification_names=unconfirmed)
