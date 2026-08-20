"""Module 5 — CQC registered locations.

The CQC syndication API has no provider-name filter, so providers to walk
are discovered rather than looked up: `pipeline/cqc_bulk.py`'s weekly
care-directory CSV names every regulated provider once per location row,
deduplicated locally to id-and-name pairs and matched exactly as an API
provider-index entry would be. That CSV is also what m26_cqc_directory
cross-checks against this module's own output -- here it does the opposite
job, discovery rather than verification, but it is the same file either way.

If the bulk export cannot be read (host down, page layout changed, expected
columns missing), discovery falls back to the CQC API's own `/providers`
index, paged in full (~64k rows) exactly as this module always used to --
slower, and this used to be unconditional (see `_fetch_provider_index`), but
it means an unreachable bulk export degrades the run rather than stopping it.

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

Matched providers are walked in priority order (`_prioritise`): the target
provider first, every other tracked comparator next in the order
pipeline/keywords.py lists them. That matters more than it otherwise would
because of the other half of this: a `module_cursors` row (see README's
"only m01_procurement truly resumes" -- this is the second) records which
providers this pass has already fully walked. A run that gets interrupted
resumes past them next time instead of starting over from the target
provider again; a run that reaches the end of `matched` clears the cursor,
so the following invocation still does the full fresh refresh this module
is meant to do (`supports_since=False`) rather than silently skipping
everyone forever.
"""
from __future__ import annotations

import hashlib
import json
import re

import httpx
import structlog

from pipeline import cqc_bulk, db, providers
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
        try:
            result = client.get(f"{API_BASE}/providers",
                                 params={"perPage": INDEX_PAGE_SIZE, "page": page})
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            # A page that never comes back (retries exhausted) must not be
            # indistinguishable from "the index ends here" — but it also
            # must not take the whole run down; whatever pages were fetched
            # are still usable, just recorded as an incomplete index.
            db.record_review_item(conn, module_name, "cqc_provider_index_failed", str(page),
                                   json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
            break
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


def _match_providers(pairs, conn, module_name: str) -> list[tuple[str, str]]:
    """pairs: iterable of (provider_id, provider_name), from either
    discovery path. Exact matches come back as (provider_id, provider_key);
    substring hits go to review_queue exactly as before, regardless of
    which path found them -- one matching policy, one outcome either way.
    """
    matched: list[tuple[str, str]] = []
    for provider_id, provider_name in pairs:
        provider_key, basis = match_provider_name(provider_name)
        if basis == "exact":
            matched.append((provider_id, provider_key))
        elif basis == "substring":
            db.record_review_item(
                conn, module_name, "possible_cqc_provider", f"{provider_id} {provider_name}",
                json.dumps({"provider_key_guess": provider_key,
                             "note": "name contains a provider variant but is not an exact "
                                      "match; confirm before treating as this provider"}))
    return matched


def _discover_matched_providers(ctx: ModuleContext, module_name: str, key: str) -> list[tuple[str, str]]:
    """(provider_id, provider_key) for every exact-matched provider.

    Preferred path: CQC's own weekly bulk care-directory CSV (see
    pipeline/cqc_bulk.py), which names every regulated provider in one
    ~18MB download rather than the ~64k-row `/providers` index paged one
    page at a time -- this used to be, in the module's own words, "the
    longest silent stretch in the pipeline". If the bulk export cannot be
    read, this falls back to that same paginated index instead of leaving
    the run with nothing to walk: slower, but the module still finishes.
    """
    with PipelineHTTPClient(cqc_bulk.SOURCE_SYSTEM, settings=ctx.settings, conn=ctx.conn) as bulk_client:
        ctx.phase("finding the current CQC care directory")
        rows = cqc_bulk.fetch_directory_rows(bulk_client, ctx.conn, module_name)

    if rows is not None:
        seen: dict[str, str] = {}
        for row in rows:
            seen.setdefault(row.provider_id, row.provider_name)
        log.info("cqc.discovered_via_bulk_export", providers_in_directory=len(seen))
        matched = _match_providers(seen.items(), ctx.conn, module_name)
    else:
        log.warning("cqc.bulk_export_unavailable_for_discovery",
                    note="falling back to the paginated /providers index")
        with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=ctx.conn) as api_client:
            api_client.set_default_headers({"Ocp-Apim-Subscription-Key": key})
            ctx.phase("paging provider index (fallback)")
            index = _fetch_provider_index(api_client, ctx.conn, module_name)
        log.info("cqc.index_fetched", providers=len(index))
        matched = _match_providers(
            ((entry.get("providerId"), entry.get("providerName"))
             for entry in index if entry.get("providerId")),
            ctx.conn, module_name)

    # One commit covering everything discovery wrote (bulk/index fetch
    # failures, substring candidates) -- same durability guarantee the old
    # single-path version had: if the run dies shortly after this, what it
    # found is not lost with it.
    if not ctx.dry_run:
        ctx.conn.commit()
    return matched


def _default_priority_order() -> tuple[str, ...]:
    # Every tracked provider, target first, everyone else in the order
    # pipeline/keywords.py lists them -- deliberately not a flat priority
    # set. Every provider m05_cqc can ever match is already one of these
    # (match_provider_name only returns a key from SUPPLIER_NAME_VARIANTS),
    # so treating all 13 as equally "priority" would rank them all the
    # same and fall straight back to CQC's arbitrary index order -- the
    # target provider needs to outrank the rest, not tie with them.
    return (providers.TARGET_PROVIDER_KEY,
            *(key for key in SUPPLIER_NAME_VARIANTS if key != providers.TARGET_PROVIDER_KEY))


def _prioritise(matched: list[tuple[str, str]],
                 priority_order: tuple[str, ...] | None = None,
                 ) -> list[tuple[str, str]]:
    """Walk order: `priority_order` first (in the rank it names), anything
    else after, in the order CQC's index returned it.

    m05_cqc has no cursor and does not resume (see README's "only
    m01_procurement truly resumes") -- for a run that is slow, gets
    interrupted, or hits a fetch it cannot recover from partway through,
    order is the only lever for making sure the providers that matter most
    are not the ones left stale. Stable sort: ties (including everything
    unranked) keep their original relative order.
    """
    order = priority_order if priority_order is not None else _default_priority_order()
    rank = {key: i for i, key in enumerate(order)}
    return sorted(matched, key=lambda pair: rank.get(pair[1], len(order)))


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
    depends_on=("m00_geography",),
    depends_note="resolves each location's local authority to an ONS code",
    since_note="CQC publishes current registration state, not a dated stream",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m05_cqc"
    conn = ctx.conn
    key = ctx.settings.require_cqc_key()
    providers.seed_providers(conn, commit=not ctx.dry_run)
    authority_lookup = _build_authority_lookup(conn)

    provider_rows = 0
    location_rows = 0

    ctx.phase("discovering CQC providers")
    matched = _prioritise(_discover_matched_providers(ctx, module_name, key))

    # Resume: a `--limit` run is deliberately partial (a smoke test, say),
    # so it neither reads nor writes the cursor -- only a real full-coverage
    # run participates in resuming or clearing it. `completed_ids` names
    # providers this pass has already fully walked (see the per-provider
    # cursor update below); skipping them is what makes an interrupted run
    # continue past the target provider next time instead of re-walking it.
    completed_ids: set[str] = set()
    resuming = False
    if ctx.limit is None:
        cursor = db.get_cursor(conn, module_name)
        if cursor:
            completed_ids = set(json.loads(cursor))
            resuming = True
            before = len(matched)
            matched = [pair for pair in matched if pair[0] not in completed_ids]
            log.info("cqc.resuming_interrupted_pass", already_done=len(completed_ids),
                     remaining=len(matched), skipped=before - len(matched))

    if ctx.limit:
        matched = matched[:ctx.limit]
    log.info("cqc.providers_matched", count=len(matched), resuming=resuming)

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        headers = {"Ocp-Apim-Subscription-Key": key}
        client.set_default_headers(headers)

        for provider_id, provider_key in ctx.track(matched, "CQC providers"):
            # One provider's persistent 5xx/429 (retries exhausted) must not
            # abort every provider still to come in `matched` — it goes to
            # review like any other unavailable provider, and the run moves on.
            try:
                detail = client.get(f"{API_BASE}/providers/{provider_id}")
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                db.record_review_item(conn, module_name, "cqc_provider_unavailable", provider_id,
                                       json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
                continue
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
                # Same reasoning as the provider fetch above: a location
                # that keeps failing after retries must not silently
                # truncate every remaining location for this provider (and
                # every provider after it) for the rest of the run.
                try:
                    loc_result = client.get(f"{API_BASE}/locations/{location_id}")
                except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                    db.record_review_item(conn, module_name, "cqc_location_unavailable", location_id,
                                           json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
                    continue
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

            # Recorded only once every one of this provider's locations has
            # been through the loop above -- marking it done any earlier
            # would let a resumed run skip a provider it never finished.
            if not ctx.dry_run and ctx.limit is None:
                completed_ids.add(provider_id)
                db.set_cursor(conn, module_name, json.dumps(sorted(completed_ids)))
                conn.commit()

        if not ctx.dry_run and ctx.limit is None:
            # Reaching the end of `matched` means this pass is done, however
            # many runs it took to get here -- clear the cursor so the next
            # invocation does the full fresh refresh this module always
            # promises (supports_since=False) rather than finding every
            # provider already marked complete and walking none of them.
            db.set_cursor(conn, module_name, "")
            conn.commit()

    log.info("cqc.run_complete", providers=provider_rows, locations=location_rows)
