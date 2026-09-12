"""Module 1 — Procurement notices (highest-yield module per the brief).

Three sources feed the same `contracts` table:
  - Find a Tender (FTS): above-threshold notices for the whole window, and
    (since the Procurement Act 2023 went live 24 Feb 2025) below-threshold
    notices too.
  - Contracts Finder (CF), live API: below-threshold notices for
    procurements that started before 24 Feb 2025 — a separate publishing
    system with its own ocid/notice-id namespace, so no collision risk with
    FTS.
  - Contracts Finder, CSV archive: the same publishing service's own
    daily OCDS-flattened-CSV dumps, catalogued on data.gov.uk and published
    by Crown Commercial Service back to December 2014 — well before
    WINDOW_START, which is where the live API's search index becomes
    reliable. See the docstring on `_walk_and_process_csv_archive` for why
    this exists as a separate channel rather than an earlier WINDOW_START.

Approach for the two live APIs (per the brief): walk each one's full release
stream for the date window via its cursor-based pagination — never filter
server-side by keyword — and apply CPV-prefix / keyword /
supplier-name-variant matching in-process. Only releases that match are
written to `contracts`; every page fetched is still archived to data/raw
regardless of match, so the keyword list can be revised later without
re-fetching (constraint: "re-filterable without re-fetching"). The CSV
archive channel applies the identical matching and buyer/supplier logic to
releases reconstructed from flattened CSV rows — see
`_unflatten_release_row`.

A fourth, optional channel — `--kag` — cross-checks the three above against
a third-party re-host of Contracts Finder on Kaggle (a single author's
university coursework upload, not CF's own publisher). It is deliberately
NOT a fourth way to populate `contracts`: it is the same source the other
three already fetch directly from the publisher, so a row from it would
carry weaker provenance than the primary channels for no new coverage, and
because it spans 2014-2025 — the whole of both other channels' windows,
unlike CF-CSV/live's clean split — it would silently overwrite a
primary-sourced value on every overlapping notice if it wrote there too. It
writes only to `procurement_channel_sightings` (migration 0058) and to
`review_queue` (`kaggle_coverage_gap`, `kaggle_cross_channel_mismatch`) —
see `_check_kaggle_against_other_channels`. Every channel, including the
three that do write `contracts`, records its own per-notice summary to that
same sightings table, so "do the three supply routes agree, and does one see
something the others miss" is answerable directly from it, not just from
whatever --kag happens to flag.

`pipeline run m01_procurement` takes `--api`, `--csv`, `--kag` or `--all` to
scope a run to one channel (or, for `--all`, both live-API/CSV-archive
channels together — `--kag` is never implied by `--all` and always needs
its own invocation, since it needs Kaggle credentials the other three don't
and exists to audit them rather than to be run routinely alongside them).
`--csv` is the default when none is given, since the two live channels are
re-walked incrementally on every run via their own cursors while the CSV
archive is a one-time historical backfill. Passing an unsupported flag to
any other module is a no-op with a warning; see ModuleMeta.supports_source
in pipeline/registry.py.

Buyer-to-ons_code matching is deterministic normalisation first (strip
common council-name suffixes, compare against pipeline.db's authorities
table — including retired rows, so historical notices referencing an
abolished council still join), then pipeline.buyer_name_overrides for the
residue. Anything still unmatched goes to review_queue — never guessed.
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
import zipfile
from dataclasses import dataclass
from dataclasses import field as _field
from datetime import date, timedelta

import structlog

from pipeline import collection, db
from pipeline.buyer_name_overrides import BUYER_NAME_OVERRIDES
from pipeline.config import Settings
from pipeline.http import PipelineHTTPClient, RobotsDisallowed
from pipeline.keywords import (
    RELEVANT_CPV_PREFIXES,
    SUBSTANCE_MISUSE_KEYWORDS,
    SUPPLIER_NAME_VARIANTS,
)
from pipeline.notice_urls import published_notice_url
from pipeline.registry import ModuleContext, register_module
from pipeline.writer import BatchWriter

log = structlog.get_logger()

SOURCE_FTS = "find_a_tender"
SOURCE_CF = "contracts_finder"
SOURCE_CF_CSV = "contracts_finder_csv_archive"
SOURCE_CF_KAGGLE = "contracts_finder_kaggle_archive"
FTS_URL = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"
CF_URL = "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"
WINDOW_START = date(2020, 8, 6)

# qmanhbeo/uk-public-procurement-data-contracts-finder on Kaggle: a single
# author's "cleaned and merged" re-host of Contracts Finder notices
# (2014-2025), uploaded as a university coursework project. See the module
# docstring for why this channel exists and what it is and is not allowed to
# write. Kaggle's per-file download endpoint is used (rather than the
# whole-dataset endpoint, which always zips) so the common case is a plain
# CSV response; `_kaggle_csv_text` still checks for a zip, since this is a
# third-party API this pipeline does not control the exact behaviour of.
KAGGLE_OWNER = "qmanhbeo"
KAGGLE_DATASET_SLUG = "uk-public-procurement-data-contracts-finder"
KAGGLE_CSV_FILENAME = "contracts_finder_2014-2025.csv"
KAGGLE_DOWNLOAD_URL = (
    f"https://www.kaggle.com/api/v1/datasets/download/{KAGGLE_OWNER}/"
    f"{KAGGLE_DATASET_SLUG}/{KAGGLE_CSV_FILENAME}"
)
# The kaggle walk checkpoints its row offset and commits every
# `settings.batch_write_rows` rows -- the file is one ~700MB download
# processed as a single long loop rather than many small requests, so there
# is no natural per-request checkpoint the way the other three channels have
# one per page/file.

# Crown Commercial Service's own CKAN catalogue of daily Contracts Finder
# OCDS-flattened-CSV dumps. robots.txt on this host disallows /api/ wholesale
# (Settings.robots_exceptions carries the documented, logged override) — it
# reads as aimed at crawlers hitting the search UI, not at scripted reuse of
# a public open-data catalogue API under OGL, the same reasoning already
# applied to the WhatDoTheyKnow feed exception.
CF_CSV_CKAN_API = "https://ckan.publishing.service.gov.uk/api/3/action/package_search"
CF_CSV_TITLE_RE = re.compile(r"Contracts Finder Notices (\d{2}) (\d{4})")

PSR_SI_ID = "2023/1348"  # The Health Care Services (Provider Selection Regime) Regulations 2023
_KEYWORDS_LOWER = [k.lower() for k in SUBSTANCE_MISUSE_KEYWORDS]
_DIRECT_AWARD_RE = re.compile(r"\bdirect award\D{0,10}?(\d)\b|\bda\s?-?\s?(\d)\b", re.IGNORECASE)

_COUNCIL_SUFFIX_RE = re.compile(
    r"\b(metropolitan borough council|metropolitan district council|"
    r"county council|city council|borough council|district council|"
    r"unitary authority|royal borough of|london borough of|city of|council)\b",
    re.IGNORECASE,
)


def _normalise_authority_name(name: str) -> str:
    text = name.lower().replace("&", "and")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = _COUNCIL_SUFFIX_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalise_supplier_name(name: str) -> str:
    text = re.sub(r"[^\w\s]", "", name.lower())
    return re.sub(r"\s+", " ", text).strip()


_SUPPLIER_LOOKUP: dict[str, tuple[str, str]] = {}
for _key, _variants in SUPPLIER_NAME_VARIANTS.items():
    _canonical = _variants[0]
    for _variant in _variants:
        _SUPPLIER_LOOKUP[_normalise_supplier_name(_variant)] = (_key, _canonical)


def _match_supplier_key(name: str | None) -> tuple[str, str] | None:
    if not name:
        return None
    return _SUPPLIER_LOOKUP.get(_normalise_supplier_name(name))


def _seed_supplier_aliases(conn) -> None:
    for key, variants in SUPPLIER_NAME_VARIANTS.items():
        canonical = variants[0]
        for variant in variants:
            db.upsert(conn, "supplier_aliases", {
                "alias_raw": variant, "supplier_key": key, "canonical_name": canonical,
            }, natural_key=["alias_raw"])


def _build_authority_lookup(conn) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for row in conn.execute("SELECT ons_code, name FROM authorities ORDER BY ons_code"):
        lookup.setdefault(_normalise_authority_name(row["name"]), row["ons_code"])
    return lookup


def _match_buyer(raw_name: str, authority_lookup: dict[str, str]) -> str | None:
    normalised = _normalise_authority_name(raw_name)
    if normalised in authority_lookup:
        return authority_lookup[normalised]
    if raw_name.strip() in BUYER_NAME_OVERRIDES:
        return BUYER_NAME_OVERRIDES[raw_name.strip()]
    if normalised in BUYER_NAME_OVERRIDES:
        return BUYER_NAME_OVERRIDES[normalised]
    return None


def _extract_cpv_codes(release: dict) -> set[str]:
    """Every place a release can carry a CPV code. `classification` (a
    single primary classification) and `additionalClassifications` (an
    array of secondary ones) are two genuinely different, sibling OCDS
    fields, both legitimate carriers of a CPV code, and both appear at two
    separate levels — directly on `tender`, and on each of `tender.items[]`
    — so there are four combinations to check, not one. Checking only some
    of them silently drops every release relying on the others, with no
    error to show for it: an unmatched CPV code looks identical to an
    absent one. Confirmed against two live samples (2026-08-23): a 2015
    notice with its only CPV at `items[0].classification`, and a January
    2016 notice with its only CPV at the tender-level
    `additionalClassifications[0]` — both sitting untouched in already-
    fetched archived bytes, invisible to scope-matching either way.
    """
    codes: set[str] = set()
    tender = release.get("tender") or {}
    for c in [tender.get("classification"), *(tender.get("additionalClassifications") or [])]:
        if c and c.get("scheme") == "CPV" and c.get("id"):
            codes.add(c["id"])
    for item in tender.get("items") or []:
        for c in [item.get("classification"), *(item.get("additionalClassifications") or [])]:
            if c and c.get("scheme") == "CPV" and c.get("id"):
                codes.add(c["id"])
    for award in release.get("awards") or []:
        for c in [award.get("classification"), *(award.get("additionalClassifications") or [])]:
            if c and c.get("scheme") == "CPV" and c.get("id"):
                codes.add(c["id"])
        for item in award.get("items") or []:
            for c in [item.get("classification"), *(item.get("additionalClassifications") or [])]:
                if c and c.get("scheme") == "CPV" and c.get("id"):
                    codes.add(c["id"])
    return codes


def _release_matches_scope(release: dict) -> bool:
    tender = release.get("tender") or {}
    text_parts = [tender.get("title"), tender.get("description"), release.get("description")]
    for award in release.get("awards") or []:
        text_parts.append(award.get("title"))
    text = " ".join(p for p in text_parts if p).lower()
    if any(kw in text for kw in _KEYWORDS_LOWER):
        return True

    codes = _extract_cpv_codes(release)
    if any(code.startswith(prefix) for code in codes for prefix in RELEVANT_CPV_PREFIXES):
        return True

    for party in release.get("parties") or []:
        if "supplier" in (party.get("roles") or []) and _match_supplier_key(party.get("name")):
            return True
    return False


def _classify_procedure(tender: dict) -> tuple[str | None, bool]:
    parts = [p for p in (tender.get("procurementMethod"), tender.get("procurementMethodDetails")) if p]
    procedure_type = ": ".join(parts) if parts else None

    legal_basis = tender.get("legalBasis") or {}
    psr_basis = (
        legal_basis.get("id") == PSR_SI_ID
        or "provider-selection-regime" in (legal_basis.get("uri") or "").lower()
        or "provider selection regime" in (tender.get("procurementMethodDetails") or "").lower()
    )
    return procedure_type, psr_basis


def _extract_direct_award_option(text: str | None) -> str | None:
    if not text:
        return None
    m = _DIRECT_AWARD_RE.search(text)
    if not m:
        return None
    digit = m.group(1) or m.group(2)
    return f"DA{digit}"


def _extension_terms(tender: dict) -> str | None:
    parts = []
    for lot in tender.get("lots") or []:
        renewal = (lot.get("renewal") or {}).get("description")
        options = (lot.get("options") or {}).get("description")
        parts.extend(p for p in (renewal, options) if p)
    return "; ".join(parts) if parts else None


def _iter_supplier_rows(release: dict) -> list[dict]:
    """One dict per (award, supplier) pair, or a single placeholder row
    (supplier_id='') when the release has no award yet (planning/tender
    stage). A multi-lot notice awarding to several suppliers yields one
    row per supplier, each carrying that specific award's value/dates.
    """
    awards = release.get("awards") or []
    if not awards:
        return [{"supplier_id": "", "supplier_name_raw": None, "value_core": None,
                  "value_max": None, "currency": None, "date_start": None, "date_end": None}]

    contracts_by_award = {c.get("awardID"): c for c in (release.get("contracts") or []) if c.get("awardID")}
    rows = []
    for award in awards:
        contract = contracts_by_award.get(award.get("id"))
        award_value = award.get("value") or {}
        contract_value = (contract or {}).get("value") or {}
        value_core = contract_value.get("amount") if contract_value.get("amount") is not None else award_value.get("amount")
        value_max = contract_value.get("amountGross") if contract_value.get("amountGross") is not None else award_value.get("amountGross")
        currency = contract_value.get("currency") or award_value.get("currency")
        period = (contract or {}).get("period") or {}

        for supplier in award.get("suppliers") or [{"id": "", "name": None}]:
            rows.append({
                "supplier_id": supplier.get("id") or "",
                "supplier_name_raw": supplier.get("name"),
                "value_core": value_core, "value_max": value_max, "currency": currency,
                "date_start": period.get("startDate"), "date_end": period.get("endDate"),
            })
    return rows


def _provenance(result, source_system: str) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": source_system,
        "payload_sha256": result.payload_sha256,
    }


def _channel_sighting_row(notice_id: str, source_system: str, fields: dict, result) -> dict:
    """The row `procurement_channel_sightings` would hold for what *this*
    channel itself observed for `notice_id`, kept alongside (never instead
    of) `contracts` — see migration 0058. Every channel builds one, not just
    --kag, so "do the supply routes agree" is answerable from one table
    rather than only from whatever --kag's own check flags. Pure -- writing
    it is the caller's job (batched for the three channels that populate
    `contracts`; immediate for --kag, which must read its own row straight
    back — see `_check_kaggle_against_other_channels`).
    """
    return {
        "notice_id": notice_id,
        "source_system": source_system,
        **fields,
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "payload_sha256": result.payload_sha256,
    }


def _record_channel_sighting(conn, notice_id: str, source_system: str, fields: dict, result) -> None:
    """Immediate single-row write built on `_channel_sighting_row` — kept for
    --kag, whose cross-channel check reads its own row straight back in the
    same call (see its docstring); the three channels that populate
    `contracts` batch this shape through a `BatchWriter` instead.
    """
    db.upsert(conn, "procurement_channel_sightings", _channel_sighting_row(notice_id, source_system, fields, result),
              natural_key=["notice_id", "source_system"])


@dataclass
class ReleaseWrite:
    """What `_process_release` (and `_process_csv_release_row`) would write
    for one release, as data rather than as an immediate write.

    Pure by design: a channel walk feeds these into its own `BatchWriter`s
    (see `_walk_and_process`/`_walk_and_process_csv_archive`) so many
    releases' worth of rows become one `db.upsert_many`/
    `record_parse_failures`/`record_review_items` call instead of one round
    trip per release — the buyer-matching, supplier/award-extraction and
    provenance logic itself is unchanged, only where the write happens.
    """
    contract_rows: list[dict] = _field(default_factory=list)
    sighting: dict | None = None
    # (source_url, field_name, raw_fragment, reason) — db.record_parse_failures' row shape.
    parse_failures: list[tuple[str | None, str, str, str]] = _field(default_factory=list)
    # (item_type, raw_value, context_json) — db.record_review_items' row shape.
    review_items: list[tuple[str, str, str | None]] = _field(default_factory=list)


def _process_release(module_name: str, source_system: str, release: dict, result, authority_lookup: dict[str, str]) -> ReleaseWrite:
    notice_id = release.get("id")
    if not notice_id:
        return ReleaseWrite(parse_failures=[
            (result.url, "id", json.dumps(release)[:500], "release missing notice id"),
        ])

    ocid = release.get("ocid")
    notice_type = ",".join(release.get("tag") or [])
    tender = release.get("tender") or {}
    buyer_party = next((p for p in (release.get("parties") or []) if "buyer" in (p.get("roles") or [])), None)
    buyer_name = (release.get("buyer") or {}).get("name") or (buyer_party or {}).get("name")

    review_items: list[tuple[str, str, str | None]] = []
    buyer_ons_code = None
    if buyer_name:
        buyer_ons_code = _match_buyer(buyer_name, authority_lookup)
        if buyer_ons_code is None:
            review_items.append(("unmatched_buyer_name", buyer_name,
                                  json.dumps({"ocid": ocid, "notice_id": notice_id})))

    cpv_codes = ",".join(sorted(_extract_cpv_codes(release))) or None
    procedure_type, psr_basis = _classify_procedure(tender)
    combined_text = " ".join(filter(None, [tender.get("title"), tender.get("description"), release.get("description")]))
    psr_option = _extract_direct_award_option(combined_text)
    extension_text = _extension_terms(tender)
    tender_value = tender.get("value") or {}
    provenance = _provenance(result, source_system)
    notice_web_url = published_notice_url(release, source_system)

    supplier_rows = _iter_supplier_rows(release)
    contract_rows = []
    for supplier_row in supplier_rows:
        value_core = supplier_row["value_core"] if supplier_row["value_core"] is not None else tender_value.get("amount")
        value_max = supplier_row["value_max"] if supplier_row["value_max"] is not None else tender_value.get("amountGross")
        currency = supplier_row["currency"] or tender_value.get("currency")
        if value_max is not None and value_max == value_core:
            value_max = None

        supplier_ppon = None
        if supplier_row["supplier_id"]:
            party = next((p for p in (release.get("parties") or []) if p.get("id") == supplier_row["supplier_id"]), None)
            if party and (party.get("identifier") or {}).get("scheme") == "GB-PPON":
                supplier_ppon = party["identifier"].get("id")

        contract_rows.append({
            "notice_id": notice_id,
            "supplier_id": supplier_row["supplier_id"],
            "ocid": ocid,
            "notice_type": notice_type,
            "buyer_name": buyer_name,
            "buyer_ons_code": buyer_ons_code,
            "supplier_name_raw": supplier_row["supplier_name_raw"],
            "supplier_ppon": supplier_ppon,
            "title": tender.get("title"),
            "description": tender.get("description"),
            "cpv_codes": cpv_codes,
            "value_core": value_core,
            "value_max": value_max,
            "currency": currency,
            "date_published": release.get("date"),
            "date_start": supplier_row["date_start"],
            "date_end": supplier_row["date_end"],
            "extension_terms_text": extension_text,
            "procedure_type": procedure_type,
            "psr_basis": 1 if psr_basis else 0,
            "psr_direct_award_option": psr_option,
            # Distinct from source_url in **provenance, which is the API page
            # these bytes came from. Migration 0032 says why both exist.
            "notice_web_url": notice_web_url,
            **provenance,
        })
    # A release can carry several award/supplier rows. Keep one row shape for
    # the whole release so procurement's high-volume path does not turn each
    # supplier into its own parse/round-trip/commit unit -- the caller's
    # BatchWriter is what actually turns this into one statement, now across
    # many releases rather than just this one.

    # Own-award values only (pre tender-estimate fallback) -- summing the
    # fallback would double-count the tender estimate as if it were an award
    # every time a notice has no award yet, which is most rows.
    award_values = [sr["value_core"] for sr in supplier_rows if sr.get("value_core") is not None]
    supplier_names = "|".join(sr["supplier_name_raw"] for sr in supplier_rows if sr.get("supplier_name_raw")) or None
    sighting = _channel_sighting_row(notice_id, source_system, {
        "ocid": ocid,
        "buyer_name": buyer_name,
        "title": tender.get("title"),
        "cpv_codes": cpv_codes,
        "tender_value_amount": tender_value.get("amount"),
        "tender_value_currency": tender_value.get("currency"),
        "total_award_value_amount": sum(award_values) if award_values else None,
        "supplier_names": supplier_names,
        "date_published": release.get("date"),
    }, result)

    return ReleaseWrite(contract_rows=contract_rows, sighting=sighting, review_items=review_items)


def _resolve_start(conn, cursor_key: str, explicit_since: str | None, default_start: date) -> tuple[str | None, date]:
    if explicit_since:
        return None, date.fromisoformat(explicit_since)
    cursor = db.get_cursor(conn, cursor_key)
    if cursor is None:
        return None, default_start
    if cursor.startswith("URL:"):
        return cursor[4:], default_start
    if cursor.startswith("DONE:"):
        return None, date.fromisoformat(cursor[5:])
    return None, default_start


def _existing_ocids(conn, ocids: set[str]) -> set[str]:
    """Which of `ocids` already have a `contracts` row.

    Purely a reporting signal for `collection_attempts.detail_json`'s
    new-vs-seen counts — idempotency itself still comes from
    `db.upsert_many`'s ON CONFLICT, this changes nothing about what gets
    written. One query per page/month/Kaggle-batch; skipped entirely when
    there is nothing to check.
    """
    if not ocids:
        return set()
    rows = conn.execute("SELECT ocid FROM contracts WHERE ocid = ANY(%s)", (sorted(ocids),)).fetchall()
    return {row["ocid"] for row in rows}


def _walk_and_process(
    client: PipelineHTTPClient, conn, module_name: str, source_system: str, base_url: str,
    date_params: tuple[str, str], resume_url: str | None, window_from: date, window_to: date,
    cursor_key: str, authority_lookup: dict[str, str], limit: int | None, dry_run: bool,
    settings: Settings,
) -> int:
    if resume_url:
        url, params = resume_url, None
    else:
        from_param, to_param = date_params
        url = base_url
        params = {
            from_param: f"{window_from.isoformat()}T00:00:00",
            to_param: f"{window_to.isoformat()}T00:00:00",
            "limit": 100,
        }

    # Read by the contracts writer's checkpoint only -- every page sets it to
    # that page's own resume point right before the writers are closed, so a
    # threshold-triggered flush mid-page (rare at 100 releases/page, real for
    # a release with many suppliers) always checkpoints to a page this loop
    # has actually finished, never to one still being built.
    cursor_value: list[str | None] = [None]

    def _checkpoint() -> None:
        if cursor_value[0] is not None:
            db.set_cursor(conn, cursor_key, cursor_value[0])

    def _on_contract_row_error(row: dict, exc: BaseException) -> None:
        # One malformed release must not cost the batch its siblings --
        # BatchWriter has already isolated it down to this single row via
        # SAVEPOINTs (writer.py) by the time this fires. Recorded like any
        # other unparseable-at-write-time value (settled decision 1), not
        # silently dropped.
        parse_failures_writer.write((
            row.get("source_url"), "contract_row",
            json.dumps({"notice_id": row.get("notice_id"), "supplier_id": row.get("supplier_id")})[:500],
            f"batch write failed: {exc}",
        ))

    contracts_writer = BatchWriter(
        conn, lambda batch: db.upsert_many(conn, "contracts", list(batch), natural_key=["notice_id", "supplier_id"]),
        checkpoint=_checkpoint, on_row_error=_on_contract_row_error,
        max_rows=settings.batch_write_rows, max_seconds=settings.batch_write_seconds,
        commit=not dry_run)
    sightings_writer = BatchWriter(
        conn, lambda batch: db.upsert_many(conn, "procurement_channel_sightings", list(batch),
                                            natural_key=["notice_id", "source_system"]),
        max_rows=settings.batch_write_rows, max_seconds=settings.batch_write_seconds, commit=not dry_run)
    parse_failures_writer = BatchWriter(
        conn, lambda batch: db.record_parse_failures(conn, module_name, list(batch)),
        max_rows=settings.batch_write_rows, max_seconds=settings.batch_write_seconds, commit=not dry_run)
    review_items_writer = BatchWriter(
        conn, lambda batch: db.record_review_items(conn, module_name, list(batch)),
        max_rows=settings.batch_write_rows, max_seconds=settings.batch_write_seconds, commit=not dry_run)

    def _flush_and_checkpoint(*, advance_cursor: bool, had_contract_writes: bool) -> None:
        contracts_writer.close()
        sightings_writer.close()
        parse_failures_writer.close()
        review_items_writer.close()
        if advance_cursor and not had_contract_writes:
            # Nothing landed in the contracts writer this page, so its own
            # checkpoint never fired -- BatchWriter.close() is a no-op with
            # nothing pending (see its docstring). A page with nothing to
            # write -- empty, fully out-of-scope, or cut short by --limit
            # before any match -- still has to move the cursor for itself,
            # or a long such stretch would leave a stale resume point.
            _checkpoint()
            if not dry_run:
                conn.commit()

    total_matched = 0
    processed = 0
    page_number = 0
    while url:
        page_number += 1
        result = client.get(url, params=params)
        params = None

        with collection.collection_attempt(
            conn, module=module_name, source_system=source_system,
            scope=f"page {page_number}: {url}", run_id=None,
        ) as attempt:
            if not result.ok:
                parse_failures_writer.write((result.url, "page", url, f"status {result.status_code}"))
                attempt.result_count = 0
                attempt.coverage_state = "unavailable"
                attempt.failure_class = f"http_{result.status_code}"
                # Cursor untouched -- next run retries this same page, the
                # same behaviour a failed fetch always had here.
                _flush_and_checkpoint(advance_cursor=False, had_contract_writes=False)
                return total_matched

            data = json.loads(result.body)
            releases = data.get("releases", [])
            if not releases:
                attempt.coverage_state = "no_results"

            page_matched = 0
            page_contract_rows = 0
            page_ocids: set[str] = set()
            hit_limit = False
            for release in releases:
                if _release_matches_scope(release):
                    bundle = _process_release(module_name, source_system, release, result, authority_lookup)
                    if bundle.contract_rows:
                        contracts_writer.write_many(bundle.contract_rows)
                        page_contract_rows += len(bundle.contract_rows)
                    if bundle.sighting is not None:
                        sightings_writer.write(bundle.sighting)
                    if bundle.parse_failures:
                        parse_failures_writer.write_many(bundle.parse_failures)
                    if bundle.review_items:
                        review_items_writer.write_many(bundle.review_items)
                    page_matched += len(bundle.contract_rows)
                    if release.get("ocid"):
                        page_ocids.add(release["ocid"])
                processed += 1
                if limit and processed >= limit:
                    hit_limit = True
                    break

            existing = _existing_ocids(conn, page_ocids)
            attempt.result_count = page_matched
            attempt.detail = {"new_ocids": len(page_ocids - existing), "seen_ocids": len(page_ocids & existing)}
            total_matched += page_matched

            next_url = (data.get("links") or {}).get("next")
            if hit_limit:
                # Resume this same page next run -- releases in it beyond the
                # limit have not been processed yet, so the page as a whole
                # is not done. `params=None` on resume (see the top of this
                # function) re-fetches the identical URL rather than the
                # dated search again.
                cursor_value[0] = f"URL:{url}"
                _flush_and_checkpoint(advance_cursor=True, had_contract_writes=page_contract_rows > 0)
                return total_matched

            cursor_value[0] = f"URL:{next_url}" if next_url else f"DONE:{window_to.isoformat()}"

        _flush_and_checkpoint(advance_cursor=True, had_contract_writes=page_contract_rows > 0)
        url = next_url

    return total_matched


# --- Contracts Finder CSV archive: pre-WINDOW_START historical backfill ------
#
# The live CF OCDS API's publishedFrom/publishedTo filter stops behaving as a
# clean chronological filter for windows entirely before ~2016 (verified
# manually: a publishedFrom/publishedTo pair entirely in 2008-2010 returned a
# release dated 2018, outside the requested range). WINDOW_START(2020-08-06)
# already sits well clear of that unreliable territory, so this channel does
# not touch the live API at all — it walks Crown Commercial Service's own
# daily CSV dumps of the same publishing service instead, for exactly the
# span the live channel does not cover: everything before WINDOW_START.
#
# Coverage from this channel is NOT uniform back to December 2014. CCS's
# resource counts per month rise from 4 (Dec 2014, a sparse early stub) to
# consistently 30+ (one file per day, plus 2 standing reference links) only
# from around March 2015. Earlier months are genuinely thinner archives, not
# a parsing gap here — this pipeline processes whatever CCS published for a
# month and does not try to infer or flag "completeness" itself.


def _unflatten_release_row(row: dict[str, str | None],
                            amount_failures: list[tuple[str, str]] | None = None) -> dict:
    """Rebuild one OCDS release dict from a flattened-CSV row.

    The daily archive files are the standard OCDS flattened-CSV
    serialisation (one release per row; each field's JSON path becomes a
    column header, e.g. `releases/0/tender/classification/id`, with numeric
    path segments for array indices). This reverses exactly that, so the
    result carries the same `ocid`/`id` values and the same nested shape the
    live OCDS APIs hand to `_process_release` — meaning the identical
    matching, buyer/supplier and provenance logic applies unchanged, and the
    existing (notice_id, supplier_id) natural key dedupes a CSV-sourced row
    against a live-API-sourced one for the same notice without any extra
    reconciliation logic.

    Only `releases/0/...` columns are read; `uri`, `publishedDate`,
    `publisher/...` etc. describe the OCDS *package* (the CSV file itself),
    not this release, and are not part of what `_process_release` consumes.
    Blank cells (the CSV form of "this field was absent") are skipped rather
    than written as empty strings, so `.get()` calls downstream see the same
    absence the JSON APIs would produce. `_drop_none_placeholders` cleans up
    the other blank-cell artefact: a list index this release's data first
    reaches above 0.
    """
    root: dict = {}
    prefix = "releases/0/"
    for column, value in row.items():
        if not column or not column.startswith(prefix) or value in (None, ""):
            continue
        _assign_flattened_path(root, column[len(prefix):].split("/"), value)
    _coerce_amount_fields(root, amount_failures)
    return _drop_none_placeholders(root)


def _assign_flattened_path(container: dict, path: list[str], value: str) -> None:
    """Walk/create nested dicts and lists per `path` (digit segments are list
    indices) and set `value` at the end. Whether a not-yet-seen segment
    should become a dict or a list is decided by looking one segment ahead
    (does the *next* segment look like an index?), since the flattened
    column name is the only signal of the original JSON's shape.
    """
    node = container
    for i, segment in enumerate(path):
        last = i == len(path) - 1
        if segment.isdigit():
            idx = int(segment)
            while len(node) <= idx:
                node.append(None)
            if last:
                node[idx] = value
                return
            if not isinstance(node[idx], (dict, list)):
                node[idx] = [] if path[i + 1].isdigit() else {}
            node = node[idx]
        else:
            if last:
                node[segment] = value
                return
            nxt = node.get(segment)
            if not isinstance(nxt, (dict, list)):
                nxt = [] if path[i + 1].isdigit() else {}
                node[segment] = nxt
            node = nxt


# OCDS's Amount schema always names its numeric fields this way regardless of
# nesting depth (tender.value, awards[].value, contracts[].value, ...), so a
# name-based rule is sufficient without hardcoding every path it can appear
# under — the flattened CSV's column set already varies file to file with
# whatever fields that day's releases actually used.
_AMOUNT_LEAF_KEYS = {"amount", "amountGross"}


def _drop_none_placeholders(node: object) -> object:
    """Strip list entries left as `None` by `_assign_flattened_path`'s pad.

    That function pads a list with `None` up to whatever index it next has
    to set — see its docstring. A release genuinely populates its own
    `parties`/`awards`/`suppliers` array elements from index 0, but this
    file's column set is a schema shared across every release in it, and a
    release whose only value at a given path first appears at, say, index 2
    (everything this release had at 0 and 1 happened to fall outside this
    file's columns) leaves 0 and 1 as bare `None`. A real OCDS release never
    contains a null array element, so surviving `None` here is always that
    padding artefact, not data — and left in, it reaches `_process_release`
    (parties) or `_iter_supplier_rows` (awards/suppliers) as something with
    no `.get()` to call, crashing on a release this CSV row simply never
    carried the full array for.
    """
    if isinstance(node, dict):
        return {key: _drop_none_placeholders(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_drop_none_placeholders(item) for item in node if item is not None]
    return node


def _coerce_amount_fields(node: object, failures: list[tuple[str, str]] | None = None,
                           path: str = "") -> None:
    """Make the CSV's text amounts numeric, and never pass a non-number on.

    Every cell in a flattened CSV is text, so `value/amount` arrives as
    `"90000"` where the live JSON APIs hand over a float.

    The failure case is the one that matters. The archive occasionally
    carries something that is not a number under an amount path -- a country
    name has been seen there -- and this used to leave the string in place
    and continue. That worked by accident: SQLite's type affinity stores
    'United Kingdom' in a REAL column without complaint, which is the same
    affinity trap `pipeline/pgload.py` refuses rows over. Against PostgreSQL
    the driver rejects it, and because one bad cell aborts the transaction
    the module ends having written nothing at all -- a whole month of
    notices lost to one malformed field.

    Neither outcome is acceptable, and settled decision 1 already says what
    the right one is: unparseable is NULL plus a parse_failures row. So the
    field becomes NULL, every other field on the release is still written,
    and the caller records what was actually in the cell. Nothing is guessed
    -- no separators stripped, no currency symbols removed -- because a
    value this code had to reinterpret is exactly the kind of figure nobody
    could defend a year later.

    Non-finite is refused for the same reason: float() accepts 'NaN' and
    'Infinity', PostgreSQL stores both in a double precision column, and
    neither is a contract value.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}/{key}" if path else key
            if key in _AMOUNT_LEAF_KEYS and isinstance(value, str):
                try:
                    parsed = float(value)
                except ValueError:
                    parsed = None
                if parsed is None or not math.isfinite(parsed):
                    node[key] = None
                    if failures is not None:
                        failures.append((child, value))
                else:
                    node[key] = parsed
            else:
                _coerce_amount_fields(value, failures, child)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _coerce_amount_fields(item, failures, f"{path}/{index}")


def _select_best_cf_csv_packages(packages: list[dict]) -> dict[tuple[int, int], dict]:
    """One package per (year, month), the one actually holding the data.

    CCS's own re-harvesting leaves old package records behind with an
    emptied resource list rather than deleting them — many months have 2-3
    dataset records under different slugs (`contracts-finder-notices-01-2016`
    vs `...-01-20161`), and for a Sep-2021-to-Aug-2023 stretch the original
    slug's resource list is consistently empty while a re-numbered twin holds
    the real files. There is no predictable suffix pattern, so every variant
    a search turns up is compared on what it actually contains: most CSV
    resources wins, ties broken by whichever was modified most recently.
    """
    best: dict[tuple[int, int], dict] = {}
    for package in packages:
        match = CF_CSV_TITLE_RE.search(package.get("title") or "")
        if not match:
            continue
        month, year = int(match.group(1)), int(match.group(2))
        key = (year, month)
        csv_count = sum(1 for r in (package.get("resources") or [])
                         if (r.get("format") or "").strip().upper() == "CSV")
        package = {**package, "_csv_count": csv_count}
        current = best.get(key)
        if current is None:
            best[key] = package
            continue
        if (csv_count, package.get("metadata_modified") or "") > \
           (current["_csv_count"], current.get("metadata_modified") or ""):
            best[key] = package
    return best


def _discover_cf_csv_months(client: PipelineHTTPClient, conn, module_name: str,
                             window_end: date) -> list[tuple[date, dict]]:
    """Every 'Contracts Finder Notices MM YYYY' CKAN package whose month
    precedes `window_end`, resolved to its most complete variant and sorted
    chronologically. Always walks the full catalogue (a handful of requests,
    ~200 packages) rather than persisting a page cursor — cheap, and it means
    a month CCS republishes under yet another slug is picked up automatically
    on the next run instead of staying pinned to whichever variant existed
    when a discovery cursor was last saved.
    """
    packages: list[dict] = []
    start = 0
    rows = 100
    while True:
        result = client.get(CF_CSV_CKAN_API, params={
            "q": 'title:"Contracts Finder Notices"', "rows": rows, "start": start,
        })
        if not result.ok:
            db.record_parse_failure(conn, module_name, "ckan_search", CF_CSV_CKAN_API,
                                     f"status {result.status_code}", source_url=result.url)
            break
        data = json.loads(result.body)
        if not data.get("success"):
            db.record_parse_failure(conn, module_name, "ckan_search", CF_CSV_CKAN_API,
                                     "CKAN response success=false", source_url=result.url)
            break
        page = (data.get("result") or {}).get("results") or []
        packages.extend(page)
        start += len(page)
        total = (data.get("result") or {}).get("count", 0)
        if not page or start >= total:
            break

    best_by_month = _select_best_cf_csv_packages(packages)
    months = [(date(year, month, 1), package) for (year, month), package in best_by_month.items()
              if date(year, month, 1) < window_end]
    months.sort(key=lambda entry: entry[0])
    return months


def _process_csv_release_row(module_name: str, source_system: str, row: dict,
                              result, authority_lookup: dict[str, str]) -> ReleaseWrite | None:
    """`None` for a row this module has nothing to say about (no id, or out
    of scope) -- distinct from a `ReleaseWrite` with empty lists, which would
    still be worth a caller's attention (e.g. a bundle carrying only a parse
    failure). Kept pure like `_process_release`; the caller batches whatever
    comes back.
    """
    amount_failures: list[tuple[str, str]] = []
    release = _unflatten_release_row(row, amount_failures)
    if not release.get("id"):
        return None
    if not _release_matches_scope(release):
        return None
    bundle = _process_release(module_name, source_system, release, result, authority_lookup)
    if amount_failures:
        # Recorded only for a release this module is actually keeping. A
        # malformed amount on a row that fails the scope check is a fact
        # about someone else's playground-equipment notice, and
        # parse_failures is a bug list about this pipeline's own parsers
        # rather than a log of every oddity in the archive.
        extra = [(result.url, field_path, raw_value, "amount is not a finite number; stored as NULL")
                 for field_path, raw_value in amount_failures]
        bundle.parse_failures = [*extra, *bundle.parse_failures]
    return bundle


def _walk_and_process_csv_archive(
    client: PipelineHTTPClient, conn, module_name: str, source_system: str,
    cursor_key: str, window_end: date, authority_lookup: dict[str, str],
    limit: int | None, dry_run: bool, settings: Settings,
) -> int:
    """Historical Contracts Finder backfill from CCS's own CSV dumps — see
    the module docstring and the block comment above for why this channel
    exists alongside the two live OCDS APIs.

    Checkpointed per completed month (`DONE:YYYY-MM`), not per file: a month
    is ~30 small, individually cached/conditional fetches, so an interrupted
    month simply re-walks its own files next run — cheap, and idempotent via
    the same (notice_id, supplier_id) upsert the live channels use. Every
    row across a month's files is batched into the contracts/sightings/
    parse_failures/review_items writers below and flushed once the month is
    done, so a busy month's several thousand rows become a handful of
    statements rather than one round trip each.
    """
    months = _discover_cf_csv_months(client, conn, module_name, window_end)
    cursor = db.get_cursor(conn, cursor_key)
    done_through = date.fromisoformat(cursor[5:]) if cursor and cursor.startswith("DONE:") else None

    # Read by the contracts writer's checkpoint only -- set to the month just
    # finished right before the writers are closed, so a threshold-triggered
    # flush mid-month (real: a busy month is thousands of rows) always
    # checkpoints to the last month actually completed, never to one still
    # in progress -- an in-progress month must never read as DONE.
    cursor_value: list[str | None] = [None]

    def _checkpoint() -> None:
        if cursor_value[0] is not None:
            db.set_cursor(conn, cursor_key, cursor_value[0])

    def _on_contract_row_error(row: dict, exc: BaseException) -> None:
        # One malformed release must not cost the batch its siblings --
        # BatchWriter has already isolated it down to this single row via
        # SAVEPOINTs (writer.py) by the time this fires. Recorded like any
        # other unparseable-at-write-time value (settled decision 1), not
        # silently dropped.
        parse_failures_writer.write((
            row.get("source_url"), "contract_row",
            json.dumps({"notice_id": row.get("notice_id"), "supplier_id": row.get("supplier_id")})[:500],
            f"batch write failed: {exc}",
        ))

    contracts_writer = BatchWriter(
        conn, lambda batch: db.upsert_many(conn, "contracts", list(batch), natural_key=["notice_id", "supplier_id"]),
        checkpoint=_checkpoint, on_row_error=_on_contract_row_error,
        max_rows=settings.batch_write_rows, max_seconds=settings.batch_write_seconds,
        commit=not dry_run)
    sightings_writer = BatchWriter(
        conn, lambda batch: db.upsert_many(conn, "procurement_channel_sightings", list(batch),
                                            natural_key=["notice_id", "source_system"]),
        max_rows=settings.batch_write_rows, max_seconds=settings.batch_write_seconds, commit=not dry_run)
    parse_failures_writer = BatchWriter(
        conn, lambda batch: db.record_parse_failures(conn, module_name, list(batch)),
        max_rows=settings.batch_write_rows, max_seconds=settings.batch_write_seconds, commit=not dry_run)
    review_items_writer = BatchWriter(
        conn, lambda batch: db.record_review_items(conn, module_name, list(batch)),
        max_rows=settings.batch_write_rows, max_seconds=settings.batch_write_seconds, commit=not dry_run)

    def _flush_and_checkpoint(*, advance_cursor: bool, had_contract_writes: bool) -> None:
        contracts_writer.close()
        sightings_writer.close()
        parse_failures_writer.close()
        review_items_writer.close()
        if advance_cursor and not had_contract_writes:
            # Nothing landed in the contracts writer this month, so its own
            # checkpoint never fired -- BatchWriter.close() is a no-op with
            # nothing pending. A month with nothing to write still has to
            # move the cursor for itself, or the next run re-discovers and
            # re-walks it for nothing.
            _checkpoint()
            if not dry_run:
                conn.commit()

    total_matched = 0
    processed = 0
    for month_start, package in months:
        if done_through and month_start <= done_through:
            continue

        with collection.collection_attempt(
            conn, module=module_name, source_system=source_system,
            scope=month_start.strftime("%Y-%m"), run_id=None,
        ) as attempt:
            csv_resources = sorted(
                (r for r in (package.get("resources") or [])
                 if (r.get("format") or "").strip().upper() == "CSV" and r.get("url")),
                key=lambda r: r.get("url"),
            )
            month_matched = 0
            month_contract_rows = 0
            month_row_count = 0
            month_ocids: set[str] = set()
            hit_limit = False
            for resource in csv_resources:
                try:
                    result = client.get(resource["url"])
                except RobotsDisallowed:
                    # A handful of the earliest (Dec 2014) files are hosted on
                    # www.dropbox.com rather than CCS's own domain, whose
                    # robots.txt disallows /s/ (shared-link paths) for every
                    # crawler but Twitterbot/facebookexternalhit link-preview
                    # bots — a blanket anti-scraping stance on Dropbox's part,
                    # not the "aimed at a search UI" situation the
                    # robots_exceptions entries above are for. Recorded and
                    # skipped rather than added there or left to take the whole
                    # month down.
                    review_items_writer.write(("cf_csv_file_robots_disallowed", resource["url"],
                                                json.dumps({"month": month_start.isoformat()})))
                    continue
                if not result.ok:
                    parse_failures_writer.write((result.url, "csv_file", resource["url"],
                                                  f"status {result.status_code}"))
                    continue
                try:
                    text = result.body.decode("utf-8-sig")
                except UnicodeDecodeError as exc:
                    parse_failures_writer.write((result.url, "csv_file", resource["url"], str(exc)))
                    continue
                for row in csv.DictReader(io.StringIO(text)):
                    month_row_count += 1
                    bundle = _process_csv_release_row(module_name, source_system, row, result, authority_lookup)
                    if bundle is not None:
                        if bundle.contract_rows:
                            contracts_writer.write_many(bundle.contract_rows)
                            month_contract_rows += len(bundle.contract_rows)
                        if bundle.sighting is not None:
                            sightings_writer.write(bundle.sighting)
                            ocid = bundle.sighting.get("ocid")
                            if ocid:
                                month_ocids.add(ocid)
                        if bundle.parse_failures:
                            parse_failures_writer.write_many(bundle.parse_failures)
                        if bundle.review_items:
                            review_items_writer.write_many(bundle.review_items)
                        month_matched += len(bundle.contract_rows)
                    processed += 1
                    if limit and processed >= limit:
                        hit_limit = True
                        break
                if hit_limit:
                    break

            if month_row_count == 0:
                attempt.coverage_state = "no_results"
            existing = _existing_ocids(conn, month_ocids)
            attempt.result_count = month_matched
            attempt.detail = {"new_ocids": len(month_ocids - existing), "seen_ocids": len(month_ocids & existing)}
            total_matched += month_matched

            if hit_limit:
                # Cursor untouched -- an interrupted month simply re-walks
                # its own files next run (see the docstring above).
                _flush_and_checkpoint(advance_cursor=False, had_contract_writes=False)
                return total_matched

            cursor_value[0] = f"DONE:{month_start.isoformat()}"

        _flush_and_checkpoint(advance_cursor=True, had_contract_writes=month_contract_rows > 0)

    return total_matched


# --- Kaggle cross-check archive: coverage/mismatch audit, never `contracts` -
#
# See the module docstring for why this channel exists and what it must not
# do. The CSV's exact column names were not independently verified against a
# fetched copy of the file — the uploader's own extraction script does not
# match the column names Kaggle's dataset preview shows, which is itself a
# small sign of how lightly curated this particular re-host is — so every
# logical field is looked up by normalised name (`_kaggle_column_index`)
# rather than assumed to sit at one fixed header spelling. A field this
# export does not carry, however it is spelled, reads as NULL, the same
# "unparseable is NULL" discipline as everywhere else in this module.

def _kaggle_column_index(fieldnames: list[str]) -> dict[str, str]:
    """Lowercased, non-alphanumeric-stripped column name -> the header's
    actual spelling, so `tender_endDate`, `tender_end_date` and
    `TenderEndDate` all resolve to whichever one this export used.
    """
    index: dict[str, str] = {}
    for name in fieldnames:
        key = re.sub(r"[^a-z0-9]", "", name.lower())
        index.setdefault(key, name)
    return index


def _kaggle_field(row: dict, index: dict[str, str], *candidates: str) -> str | None:
    for candidate in candidates:
        header = index.get(re.sub(r"[^a-z0-9]", "", candidate.lower()))
        if header is not None:
            value = row.get(header)
            if value not in (None, ""):
                return value
    return None


def _kaggle_amount(row: dict, index: dict[str, str], *candidates: str) -> float | None:
    raw = _kaggle_field(row, index, *candidates)
    if raw is None:
        return None
    try:
        parsed = float(raw)
    except ValueError:
        return None
    # float() accepts 'NaN' and 'Infinity' and PostgreSQL stores both in a
    # double precision column; neither is a contract value. Same refusal as
    # `_coerce_amount_fields` makes for the CSV-archive channel.
    return parsed if math.isfinite(parsed) else None


def _map_kaggle_row_to_release(row: dict, index: dict[str, str]) -> dict | None:
    """Reconstructs a minimal OCDS-shaped release from one Kaggle CSV row —
    just enough of the shape for `_release_matches_scope`,
    `_extract_cpv_codes` and `_iter_supplier_rows` to run unchanged, the same
    reuse `_unflatten_release_row` gets for the CSV-archive channel.

    Unlike that channel, the source file is not itself a flattened-JSON
    serialisation, so there is no general unflattening rule here — each
    field is named explicitly, defensively, from candidate column names.
    Returns None (never a partial release) when no ocid can be found at all,
    since a release this pipeline cannot identify cannot be compared against
    anything.

    Confirmed against a live sample of the real file (2026-08-23; the
    uploader's own extraction script — see the module docstring — turned out
    not to match it): there is no release/notice id column at all, only
    `ocid` — the file keeps one row per contracting *process*, not per
    release, so `ocid` is used as this release's `id` too. There is also no
    currency column anywhere in the file; `_check_kaggle_against_other_
    channels`'s currency comparison is written defensively enough that this
    just means it never fires for Kaggle rows, never a crash — nothing here
    invents a currency the file does not state, even though it is
    overwhelmingly likely GBP.
    """
    ocid = _kaggle_field(row, index, "ocid")
    if not ocid:
        return None

    buyer_name = _kaggle_field(row, index, "buyer", "buyer_name")
    tags = _kaggle_field(row, index, "release_tag", "release_tags_all", "tag")
    cpv_id = _kaggle_field(row, index, "cpv_main", "cpv_id")
    additional_cpv_ids = _kaggle_field(row, index, "cpv_additional", "additional_cpv_ids") or ""

    value_amount = _kaggle_amount(row, index, "tender_value", "value_amount", "tender_value_amount")
    value_currency = _kaggle_field(row, index, "value_currency", "tender_value_currency")
    award_value_amount = _kaggle_amount(row, index, "award_value", "award_value_amount")
    award_value_currency = _kaggle_field(row, index, "award_value_currency")

    supplier_names = [n for n in (_kaggle_field(row, index, "supplier", "supplier_party_names",
                                                 "award_suppliers_names") or "").split("|") if n]
    supplier_ids = [i for i in (_kaggle_field(row, index, "supplier_party_ids", "award_suppliers_ids")
                                 or "").split("|") if i]

    tender: dict = {
        "title": _kaggle_field(row, index, "tender_title", "release_title", "title"),
        "description": _kaggle_field(row, index, "tender_description", "description"),
    }
    if value_amount is not None or value_currency:
        tender["value"] = {"amount": value_amount, "currency": value_currency}
    if cpv_id:
        tender["classification"] = {"scheme": "CPV", "id": cpv_id}
    if additional_cpv_ids:
        tender["items"] = [{"additionalClassifications": [
            {"scheme": "CPV", "id": c} for c in additional_cpv_ids.split("|") if c]}]

    parties = []
    for position, name in enumerate(supplier_names):
        supplier_id = supplier_ids[position] if position < len(supplier_ids) else ""
        parties.append({"id": supplier_id, "name": name, "roles": ["supplier"]})

    release: dict = {
        "id": ocid,
        "ocid": ocid,
        "tag": tags.split("|") if tags else [],
        "date": _kaggle_field(row, index, "notice_publish_date", "release_date", "publisheddate"),
        "tender": tender,
        "buyer": {"name": buyer_name} if buyer_name else {},
        "parties": parties,
    }

    if award_value_amount is not None or supplier_names:
        award: dict = {"id": "1"}
        if award_value_amount is not None:
            award["value"] = {"amount": award_value_amount, "currency": award_value_currency}
        award["suppliers"] = [
            {"id": supplier_ids[position] if position < len(supplier_ids) else "", "name": name}
            for position, name in enumerate(supplier_names)
        ]
        release["awards"] = [award]

    contract_start = _kaggle_field(row, index, "contract_start_date")
    contract_end = _kaggle_field(row, index, "contract_end_date")
    if contract_start or contract_end:
        release["contracts"] = [{"awardID": "1", "period": {"startDate": contract_start, "endDate": contract_end}}]

    return release


def _check_kaggle_against_other_channels(conn, module_name: str, ocid: str) -> None:
    """Everything --kag itself decides: never a correction to `contracts`,
    only a review item pointing a human at what to check, because Kaggle's
    own transcription is not trusted over the primary channels'.

    Matched by `ocid`, not `notice_id` — Kaggle's file carries no release id
    (see `_map_kaggle_row_to_release`), only the OCDS *process* id, so its
    own sighting rows are stored under notice_id=ocid. The other three
    channels' rows keep their real release id as notice_id but do carry the
    correct `ocid` too, and a contracting process can have several releases
    (tender, then award) across which ocid is the one thing that stays
    constant — so ocid is the only identifier both sides can actually agree
    on, and comparing on notice_id here would never match anything a live
    channel recorded, however completely it covers the process.

    A process with no sighting from any other source_system is a coverage
    gap worth checking by hand against the live source — most plausibly it
    means the live walk or CSV archive missed something, since --api/--csv
    already walk the same underlying publisher this Kaggle re-host does.
    Where another channel does have it, only fields that both ultimately
    came from the same published OCDS data — so should agree, modulo
    formatting — are compared, text fields case/whitespace-folded first so
    "DERBYSHIRE COUNTY COUNCIL" vs "Derbyshire County Council" is not
    reported as a finding. `total_award_value_amount` is deliberately not
    one of the compared fields, since Kaggle keeps only the first award on a
    multi-award notice and would "mismatch" against every genuinely
    multi-award notice for a reason that has nothing to do with either
    channel being wrong; currency fields rarely mismatch in practice either,
    since the Kaggle file carries no currency column at all.
    """
    kaggle_row = conn.execute(
        "SELECT * FROM procurement_channel_sightings WHERE notice_id = %s AND source_system = %s",
        (ocid, SOURCE_CF_KAGGLE)).fetchone()
    others = conn.execute(
        "SELECT * FROM procurement_channel_sightings WHERE ocid = %s AND source_system != %s",
        (ocid, SOURCE_CF_KAGGLE)).fetchall()

    if not others:
        db.record_review_item(conn, module_name, "kaggle_coverage_gap", ocid, json.dumps({
            "note": "seen in the Kaggle re-host but no --api/--csv sighting shares this ocid; "
                    "check whether the live walk or CSV archive missed this contracting process",
            "buyer_name": kaggle_row["buyer_name"], "title": kaggle_row["title"],
        }))
        return

    # Case/whitespace only ("DERBYSHIRE COUNTY COUNCIL" vs "Derbyshire County
    # Council") is not a finding -- an early sample against production
    # (2026-08-23) was ~20% this, drowning out the genuine differences (a
    # real one: several dozen contracts_finder_csv_archive rows carry an
    # e-tendering platform's own name -- "DUE NORTH LIMITED", "IN-TEND
    # LIMITED" -- as buyer_name, confirmed against the archived source bytes
    # to be exactly what Contracts Finder itself published that day, not a
    # parsing bug here). Numeric/currency fields need no such normalisation.
    def _fold(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip()).casefold()

    for other in others:
        mismatches = {}
        for field in ("buyer_name", "title", "tender_value_amount", "tender_value_currency"):
            kaggle_value, other_value = kaggle_row[field], other[field]
            if kaggle_value is None or other_value is None:
                continue
            if isinstance(kaggle_value, str) and isinstance(other_value, str):
                if _fold(kaggle_value) == _fold(other_value):
                    continue
            elif kaggle_value == other_value:
                continue
            mismatches[field] = {"kaggle": kaggle_value, other["source_system"]: other_value}
        if mismatches:
            db.record_review_item(conn, module_name, "kaggle_cross_channel_mismatch", ocid,
                                   json.dumps({"other_source": other["source_system"], "fields": mismatches}))


def _process_kaggle_release_row(conn, module_name: str, row: dict, index: dict[str, str], result) -> int:
    release = _map_kaggle_row_to_release(row, index)
    if release is None:
        db.record_parse_failure(conn, module_name, "kaggle_row", json.dumps(row)[:500],
                                 "no ocid column found", source_url=result.url)
        return 0
    if not _release_matches_scope(release):
        return 0

    ocid = release["ocid"]  # == release["id"]; the file has no separate release id, see the mapper
    supplier_rows = _iter_supplier_rows(release)
    award_values = [sr["value_core"] for sr in supplier_rows if sr.get("value_core") is not None]
    supplier_names = "|".join(sr["supplier_name_raw"] for sr in supplier_rows if sr.get("supplier_name_raw")) or None
    tender_value = (release.get("tender") or {}).get("value") or {}

    _record_channel_sighting(conn, ocid, SOURCE_CF_KAGGLE, {
        "ocid": ocid,
        "buyer_name": (release.get("buyer") or {}).get("name"),
        "title": (release.get("tender") or {}).get("title"),
        "cpv_codes": ",".join(sorted(_extract_cpv_codes(release))) or None,
        "tender_value_amount": tender_value.get("amount"),
        "tender_value_currency": tender_value.get("currency"),
        "total_award_value_amount": sum(award_values) if award_values else None,
        "supplier_names": supplier_names,
        "date_published": release.get("date"),
    }, result)

    _check_kaggle_against_other_channels(conn, module_name, ocid)
    return 1


def _kaggle_csv_text(body: bytes, module_name: str, conn, source_url: str) -> str | None:
    """Kaggle's per-file download endpoint (used here, over the
    whole-dataset one, precisely to avoid this) has been observed to serve
    the raw file directly; handled defensively rather than assumed, since
    this is a third-party API this pipeline does not control the behaviour
    of. `PK\\x03\\x04` is the zip local-file-header magic number.
    """
    payload = body
    if body[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                csv_names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
                if not csv_names:
                    db.record_parse_failure(conn, module_name, "kaggle_zip", source_url,
                                             "zip archive contains no CSV member")
                    return None
                payload = archive.read(csv_names[0])
        except zipfile.BadZipFile as exc:
            db.record_parse_failure(conn, module_name, "kaggle_zip", source_url, str(exc))
            return None
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        db.record_parse_failure(conn, module_name, "kaggle_csv", source_url, str(exc))
        return None


def _walk_and_process_kaggle(
    client: PipelineHTTPClient, conn, module_name: str, cursor_key: str,
    limit: int | None, dry_run: bool, settings: Settings,
) -> int:
    """Downloads the Kaggle archive's one CSV file and walks it row by row.

    The download itself goes through the same conditional-request cache and
    content-addressed archive as every other fetch in this pipeline, so only
    the first run pays the ~700MB transfer — a later run's `client.get()`
    gets a 304 and the cached bytes. Checkpointed by row offset (`ROW:n`),
    since one file has no natural per-request boundary to checkpoint on the
    way the other three channels' pages/months do; `DONE` once every row has
    been read means later runs are a no-op until the archive changes.

    Unlike the other two channels that write `contracts`, each row's actual
    writes here stay direct (`_process_kaggle_release_row` calls
    `db.upsert`/`db.record_review_item` on `conn` itself, not through a
    `BatchWriter`): `_check_kaggle_against_other_channels` reads the sighting
    a row *just* wrote straight back, in the same call, to compare it
    against the other channels' sightings for the same ocid -- deferring
    that write into a batch would leave it invisible to that read until the
    batch happened to flush, misreporting a coverage gap for every row in
    between. Only the periodic-commit cadence changed here, from the
    module's own constant to `settings.batch_write_rows`, and the whole walk
    is wrapped in one `collection_attempt` — there is no natural per-request
    page/month boundary to attempt more finely against, per the note above.
    """
    cursor = db.get_cursor(conn, cursor_key)
    if cursor == "DONE":
        return 0
    resume_from = int(cursor[4:]) if cursor and cursor.startswith("ROW:") else 0

    with collection.collection_attempt(
        conn, module=module_name, source_system=SOURCE_CF_KAGGLE,
        scope=f"rows from {resume_from}", run_id=None,
    ) as attempt:
        result = client.get(KAGGLE_DOWNLOAD_URL)
        if not result.ok:
            db.record_parse_failure(conn, module_name, "kaggle_download", KAGGLE_DOWNLOAD_URL,
                                     f"status {result.status_code}", source_url=result.url)
            attempt.result_count = 0
            attempt.coverage_state = "unavailable"
            attempt.failure_class = f"http_{result.status_code}"
            if not dry_run:
                conn.commit()
            return 0

        text = _kaggle_csv_text(result.body, module_name, conn, result.url)
        if text is None:
            attempt.result_count = 0
            attempt.coverage_state = "unavailable"
            if not dry_run:
                conn.commit()
            return 0

        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            db.record_parse_failure(conn, module_name, "kaggle_csv", result.url, "CSV has no header row")
            attempt.result_count = 0
            attempt.coverage_state = "unavailable"
            if not dry_run:
                conn.commit()
            return 0
        index = _kaggle_column_index(reader.fieldnames)

        total_matched = 0
        processed = 0
        matched_ocids: set[str] = set()

        def _finish(result_count: int) -> None:
            attempt.result_count = result_count
            existing = _existing_ocids(conn, matched_ocids)
            attempt.detail = {"new_ocids": len(matched_ocids - existing), "seen_ocids": len(matched_ocids & existing)}

        for row_index, row in enumerate(reader):
            if row_index < resume_from:
                continue
            written = _process_kaggle_release_row(conn, module_name, row, index, result)
            total_matched += written
            if written:
                ocid = _kaggle_field(row, index, "ocid")
                if ocid:
                    matched_ocids.add(ocid)
            processed += 1

            if processed % settings.batch_write_rows == 0:
                db.set_cursor(conn, cursor_key, f"ROW:{row_index + 1}")
                if not dry_run:
                    conn.commit()
            if limit and processed >= limit:
                db.set_cursor(conn, cursor_key, f"ROW:{row_index + 1}")
                _finish(total_matched)
                if not dry_run:
                    conn.commit()
                return total_matched

        db.set_cursor(conn, cursor_key, "DONE")
        if processed == 0:
            attempt.coverage_state = "no_results"
        _finish(total_matched)
        if not dry_run:
            conn.commit()
        return total_matched


def backfill_channel_sightings(conn) -> int:
    """One-time repair for `contracts` rows written before
    `procurement_channel_sightings` (migration 0058) existed.

    --api/--csv's own cursors are already `DONE` once a notice is processed,
    so they never naturally revisit it — meaning without this, every notice
    fetched before this table existed has no sighting row from the channel
    that actually found it, and looks identical to a genuine coverage gap to
    `_check_kaggle_against_other_channels`. That is exactly what happened on
    first deploy (2026-08-23): --kag raised thousands of `kaggle_coverage_gap`
    items against notices `contracts` already held correctly, sourced from
    `find_a_tender`/`contracts_finder`/`contracts_finder_csv_archive`.

    Deliberately conservative about what it can answer from `contracts`
    alone: `value_core` there is already "award value if present, else the
    tender estimate" (see `_process_release`'s fallback) — a decision already
    applied per row, and not something this can unpick back into a separate
    tender estimate vs. awarded total after the fact. So this leaves
    tender_value_amount/tender_value_currency/total_award_value_amount NULL
    rather than guess; that only makes the mismatch check unable to compare
    values for pre-existing notices (a NULL never mismatches), and does not
    weaken the coverage-gap check at all, which only tests presence.

    Idempotent (`ON CONFLICT DO NOTHING` on the same natural key
    `_record_channel_sighting` uses) and safe to run more than once, or
    alongside a fresh run continuing to add rows the normal way.
    """
    cursor = conn.execute(
        "INSERT INTO procurement_channel_sightings "
        "(notice_id, source_system, ocid, buyer_name, title, cpv_codes, date_published, "
        " source_url, retrieved_at, http_status, payload_sha256) "
        "SELECT notice_id, source_system, MIN(ocid), MIN(buyer_name), MIN(title), "
        "       MIN(cpv_codes), MIN(date_published), MIN(source_url), MIN(retrieved_at), "
        "       MIN(http_status), MIN(payload_sha256) "
        "FROM contracts WHERE source_system IN (%s, %s, %s) "
        "GROUP BY notice_id, source_system "
        "ON CONFLICT (notice_id, source_system) DO NOTHING",
        (SOURCE_FTS, SOURCE_CF, SOURCE_CF_CSV),
    )
    return cursor.rowcount if cursor.rowcount is not None and cursor.rowcount >= 0 else 0


@register_module(
    "m01_procurement", supports_since=True,
    supports_source=True,
    source_note="'api' runs only the Find a Tender + Contracts Finder live channels; "
                 "'csv' (the CLI default) runs only the pre-WINDOW_START CCS CSV "
                 "archive backfill; 'kag' runs only the Kaggle cross-check archive "
                 "(needs KAGGLE_USERNAME/KAGGLE_KEY); 'all' runs the live channels + "
                 "CSV archive — 'kag' is never included in 'all' and always needs its "
                 "own invocation.",
    depends_on=("m00_geography",),
    depends_note="matches free-text buyer names against the authorities table",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m01_procurement"
    conn = ctx.conn

    _seed_supplier_aliases(conn)
    if not ctx.dry_run:
        conn.commit()
    authority_lookup = _build_authority_lookup(conn)

    # ctx.source ("api" | "csv" | "kag" | "all", set by --api/--csv/--kag/--all
    # on the CLI, "csv" by default) scopes this run to one channel below (or,
    # for "all", the two that write `contracts`). See the register_module()
    # source_note and the module docstring for why the two live APIs, the CSV
    # archive and the Kaggle cross-check are four independent channels, and
    # why "all" never implies "kag".
    if ctx.source not in ("api", "csv", "kag", "all"):
        raise ValueError(f"ctx.source must be 'api', 'csv', 'kag' or 'all'; got {ctx.source!r}")

    if ctx.source in ("api", "all"):
        window_to = date.today() + timedelta(days=1)
        sources = [
            ("fts", SOURCE_FTS, FTS_URL, ("updatedFrom", "updatedTo")),
            ("cf", SOURCE_CF, CF_URL, ("publishedFrom", "publishedTo")),
        ]

        for source_key, source_system, base_url, date_params in ctx.track(sources, "sources"):
            cursor_key = f"{module_name}:{source_key}"
            resume_url, window_from = _resolve_start(conn, cursor_key, ctx.since, WINDOW_START)
            with PipelineHTTPClient(source_system, settings=ctx.settings, conn=conn) as client:
                matched = _walk_and_process(
                    client, conn, module_name, source_system, base_url, date_params,
                    resume_url, window_from, window_to, cursor_key, authority_lookup,
                    ctx.limit, ctx.dry_run, ctx.settings,
                )
            log.info("procurement.source_complete", source=source_key, matched_rows=matched)

    if ctx.source in ("csv", "all"):
        # Historical Contracts Finder backfill — CCS's own CSV dumps for
        # everything before WINDOW_START. Not part of the `sources` loop
        # above: it doesn't page through a live API window, it walks a
        # discovered list of monthly files, and its own cursor
        # (`DONE:YYYY-MM`) is unrelated to `ctx.since`, which governs the two
        # live channels' incremental catch-up.
        ctx.phase("cf_csv_archive")
        csv_cursor_key = f"{module_name}:cf_csv"
        with PipelineHTTPClient(SOURCE_CF_CSV, settings=ctx.settings, conn=conn) as client:
            matched = _walk_and_process_csv_archive(
                client, conn, module_name, SOURCE_CF_CSV, csv_cursor_key, WINDOW_START,
                authority_lookup, ctx.limit, ctx.dry_run, ctx.settings,
            )
        log.info("procurement.source_complete", source="cf_csv", matched_rows=matched)

    if ctx.source == "kag":
        # Coverage/mismatch audit against a third-party re-host — see the
        # module docstring. Deliberately excluded from "all": it needs its
        # own Kaggle credentials, downloads ~700MB on a first run, and exists
        # to check the other three channels rather than to run alongside
        # them routinely.
        ctx.phase("cf_kaggle_archive")
        kaggle_cursor_key = f"{module_name}:kaggle"
        username, key = ctx.settings.require_kaggle_credentials()
        with PipelineHTTPClient(SOURCE_CF_KAGGLE, settings=ctx.settings, conn=conn) as client:
            client.set_basic_auth(username, key)
            matched = _walk_and_process_kaggle(client, conn, module_name, kaggle_cursor_key,
                                                ctx.limit, ctx.dry_run, ctx.settings)
        log.info("procurement.source_complete", source="kaggle", matched_rows=matched)
