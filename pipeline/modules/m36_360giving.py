"""Module 36 — 360Giving grants (received and made) for tracked providers.

Feasibility: `docs/m36-360giving-grantnav-feasibility.md`. That document
verified live that "GrantNav" and "the 360Giving API" are not the same
thing: GrantNav's documented bulk endpoints are gone and its `/search` is
both robots-disallowed and unreliable, while `api.threesixtygiving.org` is a
separate, working REST API with no robots.txt and no key requirement. This
module reads only that API.

Scoped to the tracked providers, not the API's full ~450,000-organisation
universe: every `charity_number`/`company_number` already on file in
`provider_identifiers` (the same table m03/m04 already read) is turned into a
360Giving org id (`GB-CHC-<n>` / `GB-COH-<n>`) and walked for both
`grants_received` and `grants_made`. A provider can — and, confirmed against
Change Grow Live's real grants, does — appear under either identifier scheme
on different grants, so a provider with both numbers is looked up under
both; `provider_identifiers` never grows because of it, this module only
reads it.

There is no date, amount or incremental filter on any endpoint (verified
live — see the feasibility doc §3), so a run re-fetches each tracked
provider's own grants in full rather than asking for "what's new". That is a
bounded, provider-scoped re-pull, not a corpus-wide crawl, and cheap enough
not to need one.
"""
from __future__ import annotations

import json
from datetime import date

import structlog

from pipeline import db, providers
from pipeline.http import PipelineHTTPClient
from pipeline.modules.m04_companies import normalise_company_number
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "three_sixty_giving_api"
API_BASE = "https://api.threesixtygiving.org/api/v1"
PAGE_SIZE = 100
DIRECTIONS = ("received", "made")


def _org_id(scheme: str, identifier: str) -> str:
    if scheme == "charity_number":
        return f"GB-CHC-{identifier}"
    if scheme == "company_number":
        return f"GB-COH-{normalise_company_number(identifier)}"
    raise ValueError(f"unsupported identifier scheme for a 360Giving org id: {scheme!r}")


def _target_identifiers(conn) -> list[tuple[str, str, str]]:
    """(provider_key, scheme, identifier) for every charity/company number on
    file. Unverified identifiers are included, the same choice m03's
    `_target_charities` makes for its own targets: an identifier that has not
    yet been confirmed still tells this module where to look, and it is
    matched here by that identifier alone, never by name.
    """
    rows = conn.execute(
        "SELECT provider_key, scheme, identifier FROM provider_identifiers "
        "WHERE scheme IN ('charity_number', 'company_number') "
        "ORDER BY provider_key, scheme, identifier"
    ).fetchall()
    return [(r["provider_key"], r["scheme"], r["identifier"]) for r in rows]


def _normalise_date(raw) -> str | None:
    """Publishers mix bare 'YYYY-MM-DD' dates with full ISO timestamps for
    the same field — confirmed on two real Change Grow Live grants from two
    different publishers. Both share the same first 10 characters, so this
    is a slice, not two format strings to maintain. Unparseable input is
    dropped; `award_date_raw` keeps it verbatim regardless.
    """
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10]).isoformat()
    except ValueError:
        return None


def _first(orgs) -> dict:
    return (orgs or [{}])[0] or {}


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


def _grant_row(entry: dict, *, direction: str, provider_key: str,
                scheme: str, identifier: str, result) -> dict | None:
    grant_id = entry.get("grant_id")
    data = entry.get("data") or {}
    if not grant_id:
        return None
    # Received: the other side is who funded it. Made: the other side is who
    # it went to. Either field can carry more than one organisation (a
    # co-funded grant, or several recipients on one award); only the first is
    # kept as the counterparty. No tracked provider has been found making a
    # grant at all yet (see the feasibility doc §7), so a real multi-recipient
    # case is unverified rather than deliberately unhandled.
    counterparty = _first(data.get("fundingOrganization") if direction == "received"
                           else data.get("recipientOrganization"))
    licence = entry.get("data_license") or {}
    grant_programme = data.get("grantProgramme") or []
    return {
        "grant_id": grant_id,
        "direction": direction,
        "provider_key": provider_key,
        "matched_scheme": scheme,
        "matched_identifier": identifier,
        "counterparty_org_id": counterparty.get("id"),
        "counterparty_name": counterparty.get("name"),
        "title": data.get("title"),
        "description": data.get("description"),
        "amount_awarded": data.get("amountAwarded"),
        "currency": data.get("currency"),
        "award_date_raw": data.get("awardDate"),
        "award_date": _normalise_date(data.get("awardDate")),
        "date_modified": data.get("dateModified"),
        "grant_programme_title": grant_programme[0].get("title") if grant_programme else None,
        "data_license_url": licence.get("url"),
        "data_license_name": licence.get("name"),
        **_provenance(result),
    }


def _fetch_direction(client: PipelineHTTPClient, conn, module_name: str, *,
                      org_id: str, direction: str, provider_key: str,
                      scheme: str, identifier: str) -> list[dict]:
    """Every page for one organisation/direction pair.

    A 404 means this identifier is simply not known to 360Giving — the
    outcome for almost every provider identifier checked, confirmed live
    against a made-up org id, not a fault — so it is not a review item, only
    a debug-level log line. Any other failed status is.
    """
    rows: list[dict] = []
    url = f"{API_BASE}/org/{org_id}/grants_{direction}/"
    params: dict | None = {"limit": PAGE_SIZE}
    while url:
        result = client.get(url, params=params)
        params = None  # `next` already carries its own query string
        if result.status_code == 404:
            log.debug("threesixtygiving.org_id_unknown", org_id=org_id, direction=direction)
            return rows
        if not result.ok:
            db.record_review_item(
                conn, module_name, "three_sixty_giving_org_unavailable", org_id,
                json.dumps({"direction": direction, "status": result.status_code}))
            return rows
        payload = json.loads(result.body)
        for entry in payload.get("results") or []:
            row = _grant_row(entry, direction=direction, provider_key=provider_key,
                              scheme=scheme, identifier=identifier, result=result)
            if row is None:
                db.record_parse_failure(
                    conn, module_name, "grant_id", json.dumps(entry)[:500],
                    "grant record has no grant_id", source_url=result.url)
                continue
            rows.append(row)
        url = payload.get("next")
    return rows


@register_module(
    "m36_360giving", supports_since=False,
    since_note="the API has no date or incremental filter on any endpoint "
               "(verified live; docs/m36-360giving-grantnav-feasibility.md "
               "§3) — every run re-fetches each tracked provider's own "
               "grants in full, a bounded provider-scoped re-pull rather "
               "than a corpus-wide crawl",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m36_360giving"
    conn = ctx.conn
    providers.seed_providers(conn, commit=not ctx.dry_run)

    targets = _target_identifiers(conn)
    if not targets:
        log.info("threesixtygiving.no_targets",
                  note="no provider has a charity_number or company_number in provider_identifiers")
        return

    total_rows = 0
    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        for provider_key, scheme, identifier in ctx.track(targets, "provider identifiers"):
            org_id = _org_id(scheme, identifier)
            grant_rows: list[dict] = []
            for direction in DIRECTIONS:
                grant_rows.extend(_fetch_direction(
                    client, conn, module_name, org_id=org_id, direction=direction,
                    provider_key=provider_key, scheme=scheme, identifier=identifier))

            if grant_rows:
                db.upsert_many(conn, "three_sixty_giving_grants", grant_rows,
                                natural_key=["grant_id", "direction", "provider_key"])
                total_rows += len(grant_rows)
            # Committed per identifier, not once at the end — see m11's
            # identical comment on why a long-lived write transaction under
            # `run all --jobs N` starves every other module on the warehouse.
            if not ctx.dry_run:
                conn.commit()

    log.info("threesixtygiving.run_complete", total_rows=total_rows)
