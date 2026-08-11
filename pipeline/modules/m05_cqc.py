"""Module 5 — CQC registered locations.

The CQC API has no provider-name filter, so this follows the same pattern as
Module 1: page the full provider index once (~64k rows, id and name only),
filter locally, then fetch detail for matches only. That keeps the corpus
re-filterable without re-fetching if the provider list changes.

Matching is exact-on-normalised-name, because a substring search returns
plainly unrelated companies — "With You" also matches "At Home With You
Limited", "With You Care Ltd" and "Care With You Ltd". Substring hits are
written to review_queue as candidates instead of being accepted; that is
also how a genuine variant such as CQC's "We are With You" gets picked up,
by a human confirming it rather than the pipeline guessing.

Scope limit, per the brief and recorded in the migration: CQC registration
covers only some regulated activities, so this is a map of regulated
locations and NOT a complete service map. Most community drug and alcohol
services are not CQC-registered.

Registered managers' names are embedded in each location's regulated
activities; those go only to restricted_cqc_location_contacts.
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

SOURCE_SYSTEM = "cqc_public_api"
API_BASE = "https://api.service.cqc.org.uk/public/v1"
INDEX_PAGE_SIZE = 1000


def _normalise_name(name: str) -> str:
    text = re.sub(r"[^\w\s]", " ", (name or "").lower())
    text = re.sub(r"\b(limited|ltd|llp|plc|cic)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_NAME_LOOKUP: dict[str, str] = {}
for _key, _variants in SUPPLIER_NAME_VARIANTS.items():
    for _variant in _variants:
        _NAME_LOOKUP[_normalise_name(_variant)] = _key

# Ordinary words / short acronyms that would produce nonsense substring hits.
_UNSAFE_MATCHES = {"cgl", "via", "inclusion"}


def match_provider_name(provider_name: str | None) -> tuple[str | None, str | None]:
    """(provider_key, basis). 'exact' is auto-accepted; 'substring' is only
    ever a review candidate, never treated as a match.
    """
    if not provider_name:
        return None, None
    normalised = _normalise_name(provider_name)
    if not normalised:
        return None, None

    exact = _NAME_LOOKUP.get(normalised)
    if exact:
        return exact, "exact"

    tokens = normalised.split()
    for variant_normalised, provider_key in _NAME_LOOKUP.items():
        if variant_normalised in _UNSAFE_MATCHES:
            continue
        variant_tokens = variant_normalised.split()
        if not variant_tokens or len(variant_tokens) > len(tokens):
            continue
        window = len(variant_tokens)
        for start in range(len(tokens) - window + 1):
            if tokens[start:start + window] == variant_tokens:
                return provider_key, "substring"
    return None, None


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


def _normalise_authority_name(name: str) -> str:
    text = (name or "").lower().replace("&", "and")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(
        r"\b(metropolitan borough council|county council|city council|borough council|"
        r"district council|unitary authority|royal borough of|london borough of|council)\b",
        " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _build_authority_lookup(conn) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for row in conn.execute("SELECT ons_code, name FROM authorities ORDER BY ons_code"):
        lookup.setdefault(_normalise_authority_name(row["name"]), row["ons_code"])
    return lookup


def _fetch_provider_index(client: PipelineHTTPClient, conn, module_name: str) -> list[dict]:
    """Full provider index (id + name only). Paged, then filtered locally."""
    providers_seen: list[dict] = []
    page = 1
    while True:
        result = client.get(f"{API_BASE}/providers",
                             params={"perPage": INDEX_PAGE_SIZE, "page": page})
        if not result.ok:
            db.record_review_item(conn, module_name, "cqc_provider_index_failed", str(page),
                                   json.dumps({"status": result.status_code}))
            break
        data = json.loads(result.body)
        providers_seen.extend(data.get("providers", []))
        total_pages = data.get("totalPages") or 1
        if page >= total_pages:
            break
        page += 1
    return providers_seen


def _contact_ref(activity_name: str, contact: dict) -> str:
    basis = "|".join(str(contact.get(k) or "") for k in
                      ("personTitle", "personGivenName", "personFamilyName", "personRole"))
    return hashlib.sha256(f"{activity_name}|{basis}".encode()).hexdigest()[:16]


def _store_location(conn, module_name: str, provider_id: str, provider_key: str | None,
                     location: dict, result, authority_lookup: dict[str, str]) -> None:
    location_id = location.get("locationId")
    if not location_id:
        db.record_parse_failure(conn, module_name, "locationId", json.dumps(location)[:300],
                                 "location record has no locationId", source_url=result.url)
        return

    ratings = (location.get("currentRatings") or {}).get("overall") or {}
    activities = [a.get("name") for a in (location.get("regulatedActivities") or []) if a.get("name")]
    service_types = [s.get("name") for s in (location.get("gacServiceTypes") or []) if s.get("name")]

    la_raw = location.get("localAuthority")
    ons_code = authority_lookup.get(_normalise_authority_name(la_raw)) if la_raw else None
    if la_raw and ons_code is None:
        db.record_review_item(conn, module_name, "unmatched_cqc_local_authority", la_raw,
                               json.dumps({"location_id": location_id}))

    db.upsert(conn, "cqc_locations", {
        "location_id": location_id,
        "provider_id": provider_id,
        "provider_key": provider_key,
        "location_name": location.get("name"),
        "postal_code": location.get("postalCode"),
        "latitude": location.get("onspdLatitude"),
        "longitude": location.get("onspdLongitude"),
        "local_authority_raw": la_raw,
        "local_authority_ons_code": ons_code,
        "region": location.get("region"),
        "registration_status": location.get("registrationStatus"),
        "registration_date": location.get("registrationDate"),
        "last_inspection_date": (location.get("lastInspection") or {}).get("date"),
        "overall_rating": ratings.get("rating"),
        "overall_rating_date": ratings.get("reportDate"),
        "regulated_activities": ",".join(activities) or None,
        "service_types": ",".join(service_types) or None,
        **_provenance(result),
    }, natural_key=["location_id"])

    for report in location.get("reports") or []:
        link_id = report.get("linkId")
        if not link_id:
            continue
        db.upsert(conn, "cqc_location_reports", {
            "location_id": location_id,
            "report_link_id": link_id,
            "report_date": report.get("reportDate"),
            "first_visit_date": report.get("firstVisitDate"),
            "report_uri": report.get("reportUri"),
            **_provenance(result),
        }, natural_key=["location_id", "report_link_id"])

    for activity in location.get("regulatedActivities") or []:
        for contact in activity.get("contacts") or []:
            name_parts = [contact.get("personTitle"), contact.get("personGivenName"),
                           contact.get("personFamilyName")]
            db.upsert(conn, "restricted_cqc_location_contacts", {
                "location_id": location_id,
                "contact_ref": _contact_ref(activity.get("name") or "", contact),
                "person_name": " ".join(p for p in name_parts if p) or None,
                "person_role": contact.get("personRole"),
                "regulated_activity": activity.get("name"),
            }, natural_key=["location_id", "contact_ref"])


@register_module(
    "m05_cqc",
    supports_since=False,
    since_note="CQC publishes current registration state, not a dated stream",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m05_cqc"
    conn = ctx.conn
    key = ctx.settings.require_cqc_key()
    providers.seed_providers(conn)
    authority_lookup = _build_authority_lookup(conn)

    provider_rows = 0
    location_rows = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        headers = {"Ocp-Apim-Subscription-Key": key}
        client.set_default_headers(headers)

        index = _fetch_provider_index(client, conn, module_name)
        log.info("cqc.index_fetched", providers=len(index))

        matched: list[tuple[str, str]] = []
        for entry in index:
            provider_key, basis = match_provider_name(entry.get("providerName"))
            if basis == "exact":
                matched.append((entry["providerId"], provider_key))
            elif basis == "substring":
                db.record_review_item(
                    conn, module_name, "possible_cqc_provider",
                    f"{entry.get('providerId')} {entry.get('providerName')}",
                    json.dumps({"provider_key_guess": provider_key,
                                 "note": "name contains a provider variant but is not an exact "
                                          "match; confirm before treating as this provider"}),
                )
        if not ctx.dry_run:
            conn.commit()

        if ctx.limit:
            matched = matched[:ctx.limit]
        log.info("cqc.providers_matched", count=len(matched))

        for provider_id, provider_key in matched:
            detail = client.get(f"{API_BASE}/providers/{provider_id}")
            if not detail.ok:
                db.record_review_item(conn, module_name, "cqc_provider_unavailable", provider_id,
                                       json.dumps({"status": detail.status_code}))
                continue
            data = json.loads(detail.body)

            db.upsert(conn, "cqc_providers", {
                "provider_id": provider_id,
                "provider_key": provider_key,
                "provider_name": data.get("name") or provider_id,
                "companies_house_number": data.get("companiesHouseNumber"),
                "charity_number": data.get("charityNumber"),
                "registration_status": data.get("registrationStatus"),
                "registration_date": data.get("registrationDate"),
                "ownership_type": data.get("ownershipType"),
                "organisation_type": data.get("organisationType"),
                "postal_code": data.get("postalCode"),
                "match_basis": "exact_name",
                **_provenance(detail),
            }, natural_key=["provider_id"])
            provider_rows += 1

            # CQC publishes the provider's Companies House and charity numbers;
            # record them so the provider entity gains cross-referenced ids.
            if data.get("companiesHouseNumber"):
                providers.record_discovered_identifier(
                    conn, provider_key, "company_number", str(data["companiesHouseNumber"]).strip(),
                    discovered_by=module_name, role="CQC-registered provider")
            if data.get("charityNumber"):
                providers.record_discovered_identifier(
                    conn, provider_key, "charity_number", str(data["charityNumber"]).strip(),
                    discovered_by=module_name, role="CQC-registered provider")
            providers.record_discovered_identifier(
                conn, provider_key, "cqc_provider_id", provider_id, discovered_by=module_name)

            for location_id in data.get("locationIds") or []:
                loc_result = client.get(f"{API_BASE}/locations/{location_id}")
                if not loc_result.ok:
                    db.record_review_item(conn, module_name, "cqc_location_unavailable", location_id,
                                           json.dumps({"status": loc_result.status_code}))
                    continue
                _store_location(conn, module_name, provider_id, provider_key,
                                 json.loads(loc_result.body), loc_result, authority_lookup)
                location_rows += 1
                if not ctx.dry_run:
                    conn.commit()

            log.info("cqc.provider_complete", provider_id=provider_id, provider_key=provider_key)

    log.info("cqc.run_complete", providers=provider_rows, locations=location_rows)
