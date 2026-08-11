"""Module 1 — Procurement notices (highest-yield module per the brief).

Two OCDS sources, both required:
  - Find a Tender (FTS): above-threshold notices for the whole window, and
    (since the Procurement Act 2023 went live 24 Feb 2025) below-threshold
    notices too.
  - Contracts Finder (CF): below-threshold notices for procurements that
    started before 24 Feb 2025 — a separate publishing system with its own
    ocid/notice-id namespace, so no collision risk with FTS.

Approach (per the brief): walk each API's full release stream for the date
window via its cursor-based pagination — never filter server-side by
keyword — and apply CPV-prefix / keyword / supplier-name-variant matching
in-process. Only releases that match are written to `contracts`; every page
fetched is still archived to data/raw regardless of match, so the keyword
list can be revised later without re-fetching (constraint: "re-filterable
without re-fetching").

Buyer-to-ons_code matching is deterministic normalisation first (strip
common council-name suffixes, compare against pipeline.db's authorities
table — including retired rows, so historical notices referencing an
abolished council still join), then pipeline.buyer_name_overrides for the
residue. Anything still unmatched goes to review_queue — never guessed.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta

import structlog

from pipeline import db
from pipeline.buyer_name_overrides import BUYER_NAME_OVERRIDES
from pipeline.http import PipelineHTTPClient
from pipeline.keywords import RELEVANT_CPV_PREFIXES, SUBSTANCE_MISUSE_KEYWORDS, SUPPLIER_NAME_VARIANTS
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_FTS = "find_a_tender"
SOURCE_CF = "contracts_finder"
FTS_URL = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"
CF_URL = "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"
WINDOW_START = date(2020, 8, 6)

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
    codes: set[str] = set()
    tender = release.get("tender") or {}
    classification = tender.get("classification") or {}
    if classification.get("scheme") == "CPV" and classification.get("id"):
        codes.add(classification["id"])
    for item in tender.get("items") or []:
        for c in item.get("additionalClassifications") or []:
            if c.get("scheme") == "CPV" and c.get("id"):
                codes.add(c["id"])
    for award in release.get("awards") or []:
        for item in award.get("items") or []:
            for c in item.get("additionalClassifications") or []:
                if c.get("scheme") == "CPV" and c.get("id"):
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


def _process_release(conn, module_name: str, source_system: str, release: dict, result, authority_lookup: dict[str, str]) -> int:
    notice_id = release.get("id")
    if not notice_id:
        db.record_parse_failure(conn, module_name, "id", json.dumps(release)[:500],
                                 "release missing notice id", source_url=result.url)
        return 0

    ocid = release.get("ocid")
    notice_type = ",".join(release.get("tag") or [])
    tender = release.get("tender") or {}
    buyer_party = next((p for p in (release.get("parties") or []) if "buyer" in (p.get("roles") or [])), None)
    buyer_name = (release.get("buyer") or {}).get("name") or (buyer_party or {}).get("name")

    buyer_ons_code = None
    if buyer_name:
        buyer_ons_code = _match_buyer(buyer_name, authority_lookup)
        if buyer_ons_code is None:
            db.record_review_item(conn, module_name, "unmatched_buyer_name", buyer_name,
                                   json.dumps({"ocid": ocid, "notice_id": notice_id}))

    cpv_codes = ",".join(sorted(_extract_cpv_codes(release))) or None
    procedure_type, psr_basis = _classify_procedure(tender)
    combined_text = " ".join(filter(None, [tender.get("title"), tender.get("description"), release.get("description")]))
    psr_option = _extract_direct_award_option(combined_text)
    extension_text = _extension_terms(tender)
    tender_value = tender.get("value") or {}
    provenance = _provenance(result, source_system)

    rows_written = 0
    for supplier_row in _iter_supplier_rows(release):
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

        db.upsert(conn, "contracts", {
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
            **provenance,
        }, natural_key=["notice_id", "supplier_id"])
        rows_written += 1
    return rows_written


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


def _walk_and_process(
    client: PipelineHTTPClient, conn, module_name: str, source_system: str, base_url: str,
    date_params: tuple[str, str], resume_url: str | None, window_from: date, window_to: date,
    cursor_key: str, authority_lookup: dict[str, str], limit: int | None, dry_run: bool,
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

    total_matched = 0
    processed = 0
    while url:
        result = client.get(url, params=params)
        params = None
        if not result.ok:
            db.record_parse_failure(conn, module_name, "page", url, f"status {result.status_code}", source_url=result.url)
            return total_matched

        data = json.loads(result.body)
        for release in data.get("releases", []):
            if _release_matches_scope(release):
                total_matched += _process_release(conn, module_name, source_system, release, result, authority_lookup)
            processed += 1
            if limit and processed >= limit:
                db.set_cursor(conn, cursor_key, f"URL:{url}")
                if not dry_run:
                    conn.commit()
                return total_matched

        next_url = (data.get("links") or {}).get("next")
        db.set_cursor(conn, cursor_key, f"URL:{next_url}" if next_url else f"DONE:{window_to.isoformat()}")
        if not dry_run:
            conn.commit()
        url = next_url

    return total_matched


@register_module(
    "m01_procurement", supports_since=True,
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

    window_to = date.today() + timedelta(days=1)
    sources = [
        ("fts", SOURCE_FTS, FTS_URL, ("updatedFrom", "updatedTo")),
        ("cf", SOURCE_CF, CF_URL, ("publishedFrom", "publishedTo")),
    ]

    for source_key, source_system, base_url, date_params in sources:
        cursor_key = f"{module_name}:{source_key}"
        resume_url, window_from = _resolve_start(conn, cursor_key, ctx.since, WINDOW_START)
        with PipelineHTTPClient(source_system, settings=ctx.settings, conn=conn) as client:
            matched = _walk_and_process(
                client, conn, module_name, source_system, base_url, date_params,
                resume_url, window_from, window_to, cursor_key, authority_lookup,
                ctx.limit, ctx.dry_run,
            )
        log.info("procurement.source_complete", source=source_key, matched_rows=matched)
