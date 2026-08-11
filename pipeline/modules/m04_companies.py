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


def _fetch_officers(client: PipelineHTTPClient, conn, module_name: str, company_number: str) -> int:
    result = client.get(f"{API_BASE}/company/{company_number}/officers",
                         params={"items_per_page": 100})
    if not result.ok:
        db.record_review_item(conn, module_name, "company_officers_unavailable", company_number,
                               json.dumps({"status": result.status_code}))
        return 0
    written = 0
    for officer in json.loads(result.body).get("items", []):
        address = officer.get("address") or {}
        db.upsert(conn, "restricted_company_officers", {
            "company_number": company_number,
            "officer_ref": _officer_ref(officer),
            "officer_name": officer.get("name"),
            "officer_role": officer.get("officer_role"),
            "appointed_on": officer.get("appointed_on"),
            "resigned_on": officer.get("resigned_on"),
            "nationality": officer.get("nationality"),
            "occupation": officer.get("occupation"),
            "address_locality": address.get("locality"),
        }, natural_key=["company_number", "officer_ref"])
        written += 1
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
    providers.seed_providers(conn)

    companies_written = 0
    officers_written = 0
    filings_written = 0

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

            officers_written += _fetch_officers(client, conn, module_name, company_number)
            filings_written += _fetch_filings(client, conn, module_name, company_number, ctx.limit)

            if not ctx.dry_run:
                conn.commit()

    log.info("companies.run_complete", companies=companies_written,
              officers=officers_written, filings=filings_written)
