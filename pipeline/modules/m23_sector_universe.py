"""Module 23 — The sector universe (F1 of the population workstream).

The pipeline tracks 13 providers and 347 authorities, but the denominator —
how many organisations make up the sector — was unknown. This module
reconstructs it from sources the pipeline already reads, which makes it
reconciliation rather than collection: it fetches nothing and is a query over
what other modules left behind.

The inputs, and what each contributes:

  * `providers` and `provider_identifiers` — the tracked providers, asserted
    in config, and the identifiers that link register rows to them.
  * `companies` (m04) — the group structure Companies House published for the
    tracked providers, with m04's own match_basis carried over.
  * `charity_financials` (m03) — the charities the register API was read for.
  * `cqc_providers` (m05) — registered providers. Only the tracked handful is
    collected, so the CQC half of the universe is a floor, not a census —
    expanding it is new collection (B4-adjacent), not this phase's work.
  * `contracts` (m01) — every distinct awardee: 1,310 carry a GB-PPON
    supplier registration id, the rest are names. This is the bulk of the
    universe and the source of its main caveat: the notices were matched by
    CPV prefix and keyword, so the awardees include care, support and
    construction companies that won one in-scope lot. The universe is a
    capture of who shows up in the corpus, never a complete list of the
    sector.
  * `review_queue` — the `unmatched_buyer_name` and `possible_group_company`
    items. The build captures those names systematically as unresolved leads:
    unmatched buyers become name-only funders (after a fresh authority check)
    and possible-group companies become name-only candidates. Capture is not
    resolution: the original identity questions stay pending for a person.

The match-basis discipline is m04's, kept exactly — see migration 0045 for
the vocabulary. The one rule this module exists to enforce is its simplest
consequence: provider_key is set only through an identifier that a source
published (provider_identifiers, or a company row m04 seeded), never through
a name. A 'name_only_unconfirmed' row can never acquire a provider_key, which
is what keeps the universe from becoming a larger, less verifiable version of
the problem it was built to solve.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from collections import Counter
from typing import Any

import structlog

from pipeline import db, providers
from pipeline.keywords import SUPPLIER_NAME_VARIANTS
from pipeline.modules.m01_procurement import _build_authority_lookup, _match_buyer
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

# The one normaliser the whole universe merges on. Both suffix families are
# stripped so a funder ("Barnsley Metropolitan Borough Council") and an
# awardee ("Barnsley Metropolitan Borough Council Ltd") arrive at the same
# string; a name with a genuinely different word does not.
_SUFFIX_RE = re.compile(
    r"\b(limited|ltd|llp|plc|cic|metropolitan borough council|"
    r"metropolitan district council|county council|city council|borough council|"
    r"district council|unitary authority|royal borough of|london borough of|"
    r"city of|council)\b",
    re.IGNORECASE,
)


def normalise_name(name: str) -> str:
    text = (name or "").lower().replace("&", "and")
    # Apostrophes vanish rather than becoming a space: "Barnardo's" and
    # "Barnardos" are the same organisation, and the punctuation-to-space
    # pass below would otherwise keep them apart.
    text = re.sub(r"'", "", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = _SUFFIX_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


_VARIANT_LOOKUP: dict[str, str] = {}
for _key, _variants in SUPPLIER_NAME_VARIANTS.items():
    for _variant in _variants:
        _VARIANT_LOOKUP[normalise_name(_variant)] = _key


def _name_key(normalised: str) -> str:
    return "name:" + hashlib.sha256(normalised.encode()).hexdigest()[:16]


def _row_key(prefix: str, identifier: str) -> str:
    return f"{prefix}:{identifier}"


def _provider_identifiers(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    """scheme -> {identifier: provider_key}, read once and shared by every
    pass. Only verified identifiers can set provider_key on a universe row;
    discoveries stay unverified until a person confirms them.
    """
    by_scheme: dict[str, dict[str, str]] = {}
    for row in conn.execute(
        "SELECT provider_key, scheme, identifier FROM provider_identifiers "
        "WHERE status = 'verified'"
    ).fetchall():
        by_scheme.setdefault(row["scheme"], {})[row["identifier"]] = row["provider_key"]
    return by_scheme


def _link_provider(identifiers: dict[str, dict[str, str]], scheme: str,
                   value: str | None) -> str | None:
    if not value:
        return None
    return identifiers.get(scheme, {}).get(str(value).strip())


# --- the capture passes -------------------------------------------------------
#
# Every pass writes into the same `rows` (entity_key -> final columns, without
# the notice totals) and `stats` (entity_key -> accumulated notice sets), and
# the upsert loop at the end folds the two together. A merge by name never
# elevates or demotes a row's match_basis: the target's basis and type stand.

def _empty_stats() -> dict[str, Any]:
    return {
        "notice_ids": set(),
        "spellings": Counter(),
        "first_seen": None,
        "last_seen": None,
        "provenance": None,
    }


def _capture_provider_rows(rows: dict[str, dict], stats: dict[str, dict],
                           conn: sqlite3.Connection) -> None:
    """Pass A — the tracked providers, asserted in config. The anchor rows
    every variant-named awardee merges into."""
    for row in conn.execute(
        "SELECT provider_key, canonical_name FROM providers ORDER BY provider_key"
    ).fetchall():
        key = _row_key("provider", row["provider_key"])
        rows[key] = {
            "entity_key": key,
            "canonical_name": row["canonical_name"],
            "normalised_name": normalise_name(row["canonical_name"]),
            "entity_type": "provider",
            "provider_key": row["provider_key"],
            "match_basis": "seed",
            "source_system": "providers",
        }
        stats[key] = _empty_stats()


def _capture_company_rows(rows: dict[str, dict], stats: dict[str, dict],
                          identifiers: dict[str, dict[str, str]],
                          conn: sqlite3.Connection) -> None:
    """Pass B — companies (m04). match_basis carries over unchanged, so m04's
    'seed' rows stay identified and its 'name_only_unconfirmed' rows stay
    unconfirmed. A seeded company's provider_key travels with it; everything
    else links through provider_identifiers."""
    for row in conn.execute(
        "SELECT company_number, provider_key, company_name, match_basis, "
        "date_of_creation, source_url, retrieved_at, payload_sha256 "
        "FROM companies"
    ).fetchall():
        key = row["company_number"]
        seeded = row["match_basis"] == "seed"
        rows[key] = {
            "entity_key": key,
            "canonical_name": row["company_name"],
            "normalised_name": normalise_name(row["company_name"]),
            "entity_type": "company",
            "company_number": key,
            "provider_key": (row["provider_key"] if seeded
                             else _link_provider(identifiers, "company_number", key)),
            "match_basis": "seed" if seeded else "name_only_unconfirmed",
            "first_seen": row["date_of_creation"],
            "last_seen": row["date_of_creation"],
            "source_system": "companies",
            "source_url": row["source_url"],
            "retrieved_at": row["retrieved_at"],
            "payload_sha256": row["payload_sha256"],
        }
        stats[key] = _empty_stats()


def _capture_charity_rows(rows: dict[str, dict], stats: dict[str, dict],
                          identifiers: dict[str, dict[str, str]],
                          conn: sqlite3.Connection) -> None:
    """Pass C — charities (m03). The register stores no name in this
    warehouse, so the canonical name comes from the tracked provider the
    number links to; m03 only ever collected for linked charities, so that
    name exists. The number itself is the fallback, never an invented name."""
    providers_by_key = {
        row["provider_key"]: row["canonical_name"]
        for row in conn.execute("SELECT provider_key, canonical_name FROM providers")
    }
    rows_in = conn.execute(
        "SELECT DISTINCT charity_number, MIN(financial_year_end) AS first_year, "
        "MAX(financial_year_end) AS last_year FROM charity_financials "
        "GROUP BY charity_number"
    ).fetchall()
    for row in rows_in:
        number = str(row["charity_number"])
        key = _row_key("charity", number)
        provider_key = _link_provider(identifiers, "charity_number", number)
        name = providers_by_key.get(provider_key) if provider_key else None
        rows[key] = {
            "entity_key": key,
            "canonical_name": name or number,
            "normalised_name": normalise_name(name or number),
            "entity_type": "charity",
            "charity_number": number,
            "provider_key": provider_key,
            "match_basis": "register",
            "source_system": "charity_financials",
        }
        stats[key] = _empty_stats()


def _capture_cqc_rows(rows: dict[str, dict], stats: dict[str, dict],
                      identifiers: dict[str, dict[str, str]],
                      conn: sqlite3.Connection) -> None:
    """Pass D — CQC registered providers (m05). A provider whose companies
    house number matches a captured company is the same legal person and
    merges into that row; otherwise it is its own row, identified by its CQC
    provider id. provider_key comes only through provider_identifiers — the
    exact-name link m05 itself used is not trusted here."""
    for row in conn.execute(
        "SELECT provider_id, provider_name, companies_house_number, charity_number, "
        "registration_date, source_url, retrieved_at, payload_sha256 "
        "FROM cqc_providers"
    ).fetchall():
        provider_id = str(row["provider_id"])
        company_number = row["companies_house_number"]
        if company_number and company_number in rows:
            target = rows[company_number]
            target["cqc_provider_id"] = provider_id
            if not target.get("charity_number") and row["charity_number"]:
                target["charity_number"] = str(row["charity_number"])
            _merge_first_seen(target, row["registration_date"])
            continue

        key = _row_key("cqc", provider_id)
        rows[key] = {
            "entity_key": key,
            "canonical_name": row["provider_name"],
            "normalised_name": normalise_name(row["provider_name"]),
            "entity_type": "cqc_provider",
            "company_number": company_number,
            "charity_number": row["charity_number"],
            "cqc_provider_id": provider_id,
            "provider_key": (_link_provider(identifiers, "cqc_provider_id", provider_id)
                             or _link_provider(identifiers, "company_number", company_number)
                             or _link_provider(identifiers, "charity_number",
                                               row["charity_number"])),
            "match_basis": "register",
            "first_seen": row["registration_date"],
            "last_seen": row["registration_date"],
            "source_system": "cqc_providers",
            "source_url": row["source_url"],
            "retrieved_at": row["retrieved_at"],
            "payload_sha256": row["payload_sha256"],
        }
        stats[key] = _empty_stats()


def _contract_aggregates(conn: sqlite3.Connection) -> tuple[dict[str, dict], dict[str, dict]]:
    """One pass over the contracts, from which both the ppon and the name
    awardee passes read. Returns ({normalised_name: stats}, {ppon: stats})
    where each stats dict holds the distinct notice ids, the spellings, the
    first/last publication dates and the newest provenance row.
    """
    by_name: dict[str, dict] = {}
    by_ppon: dict[str, dict] = {}
    for row in conn.execute(
        "SELECT supplier_name_raw, supplier_ppon, notice_id, date_published, "
        "source_url, retrieved_at, payload_sha256 FROM contracts"
    ).fetchall():
        raw = row["supplier_name_raw"]
        if raw and str(raw).strip():
            norm = normalise_name(str(raw))
            _accumulate(by_name.setdefault(norm, _empty_stats()), row)
        if row["supplier_ppon"]:
            _accumulate(by_ppon.setdefault(str(row["supplier_ppon"]), _empty_stats()), row)
    return by_name, by_ppon


def _accumulate(stats: dict[str, Any], row) -> None:
    stats["notice_ids"].add(str(row["notice_id"]))
    raw = row["supplier_name_raw"]
    if raw:
        stats["spellings"][str(raw)] += 1
    if row["date_published"]:
        stamp = str(row["date_published"])[:10]
        if stats["first_seen"] is None or stamp < stats["first_seen"]:
            stats["first_seen"] = stamp
        if stats["last_seen"] is None or stamp > stats["last_seen"]:
            stats["last_seen"] = stamp
    if row["retrieved_at"] and (
        stats["provenance"] is None or row["retrieved_at"] > stats["provenance"]["retrieved_at"]
    ):
        stats["provenance"] = {
            "source_url": row["source_url"],
            "retrieved_at": row["retrieved_at"],
            "payload_sha256": row["payload_sha256"],
        }


def _merge_stats_into(target_stats: dict[str, Any], source_stats: dict[str, Any]) -> None:
    target_stats["notice_ids"].update(source_stats["notice_ids"])
    target_stats["spellings"].update(source_stats["spellings"])
    for field in ("first_seen", "last_seen"):
        value = source_stats[field]
        if value and (target_stats[field] is None
                      or (field == "first_seen" and value < target_stats[field])
                      or (field == "last_seen" and value > target_stats[field])):
            target_stats[field] = value
    if source_stats["provenance"] and (
        target_stats["provenance"] is None
        or source_stats["provenance"]["retrieved_at"] > target_stats["provenance"]["retrieved_at"]
    ):
        target_stats["provenance"] = source_stats["provenance"]


def _merge_first_seen(target: dict, value: str | None) -> None:
    if value and (target.get("first_seen") is None or value < target["first_seen"]):
        target["first_seen"] = value


def _finalise(row: dict, stats: dict[str, Any]) -> dict:
    """The row as it is stored: notice totals from the accumulated sets, and
    a representative provenance sample — never a sum over the notices, whose
    own rows keep their own provenance."""
    if not stats["notice_ids"]:
        return row
    row["notices_count"] = len(stats["notice_ids"])
    if stats["first_seen"]:
        _merge_first_seen(row, stats["first_seen"])
    if stats["last_seen"] and (row.get("last_seen") is None
                               or stats["last_seen"] > row["last_seen"]):
        row["last_seen"] = stats["last_seen"]
    if stats["provenance"] and not row.get("source_url"):
        row.update(stats["provenance"])
    return row


def _capture_awardees(rows: dict[str, dict], stats: dict[str, dict],
                      by_name: dict[str, dict], by_ppon: dict[str, dict],
                      normalised_lookup: dict[str, str]) -> tuple[int, int, int]:
    """Passes E and F — the awardees. PPON registrations first (they are the
    rows with an identifier), then every distinct supplier name, merged by
    configured variant or by exact normalised name. Returns (ppon rows, new
    name rows, names merged into existing rows)."""
    ppon_rows = 0
    name_rows = 0
    merged_away = 0

    for ppon, p_stats in sorted(by_ppon.items()):
        canonical = p_stats["spellings"].most_common(1)[0][0]
        key = _row_key("ppon", ppon)
        rows[key] = {
            "entity_key": key,
            "canonical_name": canonical,
            "normalised_name": normalise_name(canonical),
            "entity_type": "awardee",
            "ppon": ppon,
            "match_basis": "ppon",
            "source_system": "contracts",
        }
        stats[key] = p_stats
        normalised_lookup.setdefault(rows[key]["normalised_name"], key)
        ppon_rows += 1

    for norm, n_stats in sorted(by_name.items()):
        if not norm:
            continue
        variant_key = _VARIANT_LOOKUP.get(norm)
        if variant_key:
            target_key = _row_key("provider", variant_key)
        else:
            target_key = normalised_lookup.get(norm)
        if target_key:
            _merge_stats_into(stats[target_key], n_stats)
            merged_away += 1
            continue

        canonical = n_stats["spellings"].most_common(1)[0][0]
        key = _name_key(norm)
        rows[key] = {
            "entity_key": key,
            "canonical_name": canonical,
            "normalised_name": norm,
            "entity_type": "awardee",
            "match_basis": "name_only_unconfirmed",
            "source_system": "contracts",
        }
        stats[key] = n_stats
        normalised_lookup.setdefault(norm, key)
        name_rows += 1

    return ppon_rows, name_rows, merged_away


def _capture_funders(rows: dict[str, dict], stats: dict[str, dict],
                     conn: sqlite3.Connection, authority_lookup: dict[str, str],
                     normalised_lookup: dict[str, str]) -> tuple[int, int]:
    """Pass G — the funder population: buyer names m01 could not match to an
    authority, now captured systematically instead of one review item at a
    time. A name that matches an authority now (overrides may have changed
    since m01 ran) is skipped — it was never a funder. The rest merge by
    exact normalised name — a buyer that is also an awardee is one
    organisation — or become a name-only funder row. Returns (new rows,
    merged into existing).

    Pending items are captured as unresolved leads. Historical `answered`
    items are also read so older warehouses rebuild deterministically; new
    captures are never marked answered. A person's own decision
    ('approved'/'rejected') is respected."""
    created = 0
    merged = 0
    seen: set[str] = set()
    for row in conn.execute(
        "SELECT DISTINCT raw_value FROM review_queue "
        "WHERE item_type = 'unmatched_buyer_name' AND status IN ('pending', 'answered')"
    ).fetchall():
        raw = str(row["raw_value"]).strip()
        if not raw or raw in seen:
            continue
        seen.add(raw)
        if _match_buyer(raw, authority_lookup):
            continue
        norm = normalise_name(raw)
        target_key = normalised_lookup.get(norm)
        if target_key:
            merged += 1
            continue
        key = _name_key(norm)
        rows[key] = {
            "entity_key": key,
            "canonical_name": raw,
            "normalised_name": norm,
            "entity_type": "funder",
            "match_basis": "name_only_unconfirmed",
            "source_system": "review_queue",
        }
        stats[key] = _empty_stats()
        normalised_lookup.setdefault(norm, key)
        created += 1
    return created, merged


def _capture_possible_group_companies(rows: dict[str, dict], stats: dict[str, dict],
                                      conn: sqlite3.Connection) -> int:
    """Pass H — the `possible_group_company` candidates. Each carries a
    company number and the title its search returned; the candidate is
    captured under that number with m04's 'name_only_unconfirmed' basis —
    recorded, never linked. The confirmation the item asked for remains a
    human's, and it now has a row to confirm on.

    Pending and historical answered items are read alike so older warehouses
    rebuild deterministically. The universe row is an unresolved lead, not an
    answer to group membership. Decided items are not read."""
    from pipeline.modules.m04_companies import normalise_company_number

    created = 0
    for row in conn.execute(
        "SELECT raw_value FROM review_queue "
        "WHERE item_type = 'possible_group_company' "
        "AND status IN ('pending', 'answered')"
    ).fetchall():
        parts = str(row["raw_value"]).split(" ", 1)
        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
            continue
        number = normalise_company_number(parts[0].strip())
        if not number or number in rows:
            continue
        rows[number] = {
            "entity_key": number,
            "canonical_name": parts[1].strip(),
            "normalised_name": normalise_name(parts[1]),
            "entity_type": "company",
            "company_number": number,
            "match_basis": "name_only_unconfirmed",
            "source_system": "review_queue",
        }
        stats[number] = _empty_stats()
        created += 1
    return created


@register_module(
    "m23_sector_universe",
    supports_since=False,
    depends_on=("m01_procurement", "m03_charity_finance", "m04_companies", "m05_cqc"),
    depends_note="it reconciles their output — awardees, charities, companies, CQC providers — into one population",
    since_note="the universe is a reconciliation over what is collected; --since has no meaning here",
)
def run(ctx: ModuleContext) -> None:
    conn = ctx.conn
    providers.seed_providers(conn, commit=not ctx.dry_run)
    identifiers = _provider_identifiers(conn)
    authority_lookup = _build_authority_lookup(conn)

    rows: dict[str, dict] = {}
    stats: dict[str, dict] = {}
    normalised_lookup: dict[str, str] = {}

    ctx.phase("capturing the tracked providers and register entities")
    _capture_provider_rows(rows, stats, conn)
    _capture_company_rows(rows, stats, identifiers, conn)
    _capture_charity_rows(rows, stats, identifiers, conn)
    _capture_cqc_rows(rows, stats, identifiers, conn)
    for key, row in rows.items():
        normalised_lookup.setdefault(row["normalised_name"], key)
    if not ctx.dry_run:
        conn.commit()

    ctx.phase("reconciling the contract awardees")
    by_name, by_ppon = _contract_aggregates(conn)
    ppon_rows, name_rows, merged_away = _capture_awardees(
        rows, stats, by_name, by_ppon, normalised_lookup)
    if not ctx.dry_run:
        conn.commit()

    ctx.phase("capturing unmatched buyers as funders")
    funders_created, funders_merged = _capture_funders(
        rows, stats, conn, authority_lookup, normalised_lookup)
    if not ctx.dry_run:
        conn.commit()

    ctx.phase("capturing possible group companies")
    candidates = _capture_possible_group_companies(rows, stats, conn)
    if not ctx.dry_run:
        conn.commit()

    written = 0
    for key in ctx.track(sorted(rows), "universe rows"):
        db.upsert(conn, "sector_universe", _finalise(rows[key], stats[key]),
                  natural_key=["entity_key"])
        written += 1
    if not ctx.dry_run:
        conn.commit()

    counts = {
        kind: sum(1 for r in rows.values() if r["entity_type"] == kind)
        for kind in ("provider", "company", "charity", "cqc_provider", "awardee", "funder")
    }
    bases = {
        basis: sum(1 for r in rows.values() if r["match_basis"] == basis)
        for basis in ("seed", "register", "ppon", "name_only_unconfirmed")
    }
    log.info("universe.run_complete", rows=written,
             providers=counts["provider"], companies=counts["company"],
             charities=counts["charity"], cqc_providers=counts["cqc_provider"],
             awardees=counts["awardee"], funders=counts["funder"],
             by_basis=bases, awardee_names_merged=merged_away,
             funders_merged_into_awardees=funders_merged,
             group_company_candidates=candidates,
             note="the coverage denominator: the universe is the ~M in 'we track N of "
                  "the sector's ~M'; the identified rows are the N")
