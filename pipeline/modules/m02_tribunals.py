"""Module 2 — Employment tribunal judgments, and Employment Appeal Tribunal
decisions.

Discovery via the GOV.UK Search API with format filter
`employment_tribunal_decision` (verified against a known CGL case before
being used at scale — see tests), querying each respondent name variant
separately because the comma form ("Change, Grow, Live") appears in real
judgments and matches differently from the unspaced form.

The EAT pass (G4, Phase 15) searches `employment_appeal_tribunal_decision`
on the same host and through the same client. An appeal is a different layer
from the judgment it reviews — a decision affirmed or overturned is a
materially different datum — so appeals live in their own tables and are
never arithmetically combined with first-instance cases. In an appeal either
party can be a provider (a provider may appeal, or a claimant may appeal
against one), so both sides of the title are matched and the side recorded.
The search engine indexes judgment bodies, so a hit can mention a provider
in its text without either party being one — the title match decides
attribution, and a body-only mention is queued for review rather than
attributed.

Field confidence, per the brief: `tribunal_decision_categories`,
`tribunal_decision_decision_date` and `tribunal_decision_country` come from
GOV.UK's own structured page metadata and are HIGH confidence. Outcome is
not published as structured metadata, so it's derived from the judgment
body text and flagged LOW — a downstream consumer can filter on
outcome_confidence rather than being silently handed a guess.

Personal data: GOV.UK puts the claimant's name in the title, the URL slug
and the indexed body text. Names go only to restricted_tribunal_parties
and restricted_eat_parties; the public tables key on case_number or the
neutral citation plus a deterministic claim_ref pseudonym derived from it.

Region: the case-number office prefix is extracted mechanically, but this
pipeline has no verified prefix->region mapping, so region stays NULL and
the prefix goes to review_queue until tribunal_office_regions is populated
from a citable source. The "Heard at:" line is captured verbatim as
hearing_venue_raw to make that verification possible — it is NOT used to
infer the region automatically.
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

SOURCE_SYSTEM = "govuk_employment_tribunal_decisions"
GOVUK_SEARCH_URL = "https://www.gov.uk/api/search.json"
GOVUK_CONTENT_BASE = "https://www.gov.uk/api/content"
DECISION_FORMAT = "employment_tribunal_decision"
EAT_FORMAT = "employment_appeal_tribunal_decision"

SEARCH_FIELDS = [
    "title", "link",
    "tribunal_decision_categories",
    "tribunal_decision_decision_date",
    "tribunal_decision_country",
]

# Case numbers appear in decision titles as "...: 1308908/2022" and in the
# slug as "-1308908-slash-2022". Both forms are parsed mechanically.
#
# Real titles are messier than the canonical form, and each variant below
# was observed in live GOV.UK data (see tests):
#   * trailing text after the number  -> "...: 3205625/2022 and Others"
#   * a space instead of the slash    -> "...: 2201707 2018"
# so the number is not anchored to end-of-string and the separator accepts
# whitespace as well as "/". The year is constrained to 20xx so a stray
# number elsewhere in a title cannot be mistaken for one.
CASE_NUMBER_TITLE_RE = re.compile(r":\s*(\d{6,8})[\s/]+(20\d{2})\b")
CASE_NUMBER_SLUG_RE = re.compile(r"-(\d{6,8})-slash-(20\d{2})\b")
HEARD_AT_RE = re.compile(r"Heard at:?\s*([^\r\n]{1,80})", re.IGNORECASE)

# Outcome phrases looked for in the judgment body. Deliberately a small,
# explicit set of unambiguous phrases: anything not matched is left NULL
# rather than force-fitted into a category.
# Judgments phrase the same outcome as "the claim", "the claims" or "the
# complaint(s)" interchangeably, so each pattern accepts all three nouns.
_CLAIM_NOUN = r"(?:claim|complaint)s?"
OUTCOME_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("struck_out", re.compile(r"\b(?:is|are) struck out\b", re.IGNORECASE)),
    ("dismissed", re.compile(rf"\b{_CLAIM_NOUN} (?:is|are) dismissed\b|\bis dismissed\b", re.IGNORECASE)),
    ("upheld", re.compile(rf"\b{_CLAIM_NOUN} (?:is|are) well[- ]founded\b|\bsucceeds\b", re.IGNORECASE)),
    ("withdrawn", re.compile(r"\bis withdrawn\b|\bupon withdrawal\b", re.IGNORECASE)),
]


def claim_ref_for(case_number: str) -> str:
    """Stable pseudonym derived from the PUBLIC case number — never from a
    name. Deterministic so re-runs and exports agree, and reversible only
    by joining the restricted table.
    """
    digest = hashlib.sha256(f"tribunal:{case_number}".encode()).hexdigest()
    return f"ET-{digest[:12].upper()}"


def parse_case_number(title: str, link: str) -> tuple[str, str, str] | None:
    """Returns (case_number, office_prefix, case_year) or None.

    office_prefix is the leading digits before the serial portion; for a
    7-digit number like 1308908 that's '13', for 8-digit '2409308' style
    numbers the same first-two-digit convention applies. This is a purely
    mechanical split — it asserts nothing about which office it maps to.
    """
    m = CASE_NUMBER_TITLE_RE.search(title or "")
    if not m:
        m = CASE_NUMBER_SLUG_RE.search(link or "")
    if not m:
        return None
    serial, year = m.group(1), m.group(2)
    return f"{serial}/{year}", serial[:2], year


def extract_claimant_name(title: str) -> str | None:
    """Decision titles are '<Claimant> v <Respondent>: <case number>'."""
    if not title:
        return None
    head = title.split(":")[0]
    parts = re.split(r"\s+v\s+", head, maxsplit=1)
    return parts[0].strip() if len(parts) == 2 else None


def extract_respondent_name(title: str) -> str | None:
    if not title:
        return None
    head = title.split(":")[0]
    parts = re.split(r"\s+v\s+", head, maxsplit=1)
    return parts[1].strip() if len(parts) == 2 else None


def _normalise_respondent(name: str) -> str:
    text = re.sub(r"[^\w\s]", "", (name or "").lower())
    text = re.sub(r"\b(limited|ltd|llp|plc|cic)\b", "", text)
    return re.sub(r"\s+", " ", text).strip()


_RESPONDENT_LOOKUP: dict[str, str] = {}
for _key, _variants in SUPPLIER_NAME_VARIANTS.items():
    for _variant in _variants:
        _RESPONDENT_LOOKUP[_normalise_respondent(_variant)] = _key

# Variants too short/generic to be safe as a component match inside a
# multi-respondent string. "CGL" as a standalone respondent is fine, but
# hunting for it inside longer names would match unrelated employers, and
# "Via"/"Inclusion" are ordinary English words.
_UNSAFE_COMPONENT_VARIANTS = {"cgl", "via", "inclusion"}


def match_respondent(respondent_name: str | None) -> tuple[str | None, str | None]:
    """Resolve a respondent string to (provider_key, match_basis).

    'exact'     -> the whole respondent string is a known name variant.
    'component' -> a known variant appears as a whole-token run inside a
                   multi-respondent string ("Lifeline Project (in
                   administration) and Change Grow Live"). Deterministic, not
                   fuzzy: matching is on token boundaries, so "Via" cannot
                   match inside "Viaduct".
    (None, None) -> no match; caller must not treat this as a provider case.
    """
    if not respondent_name:
        return None, None

    normalised = _normalise_respondent(respondent_name)
    if not normalised:
        return None, None

    exact = _RESPONDENT_LOOKUP.get(normalised)
    if exact:
        return exact, "exact"

    tokens = normalised.split()
    for variant_normalised, provider_key in _RESPONDENT_LOOKUP.items():
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


def match_provider_key(respondent_name: str | None) -> str | None:
    """Convenience wrapper returning just the provider_key."""
    return match_respondent(respondent_name)[0]


def extract_outcome(body_text: str | None) -> str | None:
    """Best-effort outcome from judgment text. Always LOW confidence — the
    caller records that. Returns None rather than guessing when no
    unambiguous phrase is present.
    """
    if not body_text:
        return None
    for label, pattern in OUTCOME_PATTERNS:
        if pattern.search(body_text):
            return label
    return None


def extract_hearing_venue(body_text: str | None) -> str | None:
    if not body_text:
        return None
    m = HEARD_AT_RE.search(body_text)
    if not m:
        return None
    # Trim the trailing " On: <date>" the judgments append on the same line.
    venue = re.split(r"\s+On:\s*", m.group(1))[0]
    return venue.strip() or None


# --- Employment Appeal Tribunal (G4, Phase 15) ---------------------------------

# EAT decisions cite themselves as "[2026] EAT 34"; the title is
# "Appellant v Respondent: [2026] EAT 34".
EAT_CITATION_RE = re.compile(r"\[(20\d{2})\]\s*EAT\s*(\d+)\b")
# The first-instance cases an appeal reviews are referenced in its body as
# "Case No.: 2303961/2024" (all three real punctuations observed live).
ET_CASE_NO_RE = re.compile(r"Case\s*No\.?\s*:?\s*(\d{6,8}/20\d{2})")

# Outcome phrases from the judgment body, matched in order: "allowed in part"
# must be tested before "allowed". Small, explicit, unambiguous; anything
# else stays NULL rather than force-fitted.
EAT_OUTCOME_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("allowed_in_part", re.compile(r"\bappeal\s+(?:is\s+)?allowed\s+in\s+part\b", re.IGNORECASE)),
    ("allowed", re.compile(
        r"\bappeal\s+(?:is\s+)?allowed\b|\bwe\s+allow\s+the\s+appeal\b|\bappeal\s+succeeds\b",
        re.IGNORECASE)),
    ("dismissed", re.compile(r"\bappeal\s+(?:is\s+)?dismissed\b|\bappeal\s+fails\b", re.IGNORECASE)),
    ("withdrawn", re.compile(r"\bappeal\s+(?:is\s+)?withdrawn\b", re.IGNORECASE)),
    ("remitted", re.compile(r"\bappeal\s+(?:is\s+)?remitted\b|\bremitted\s+to\b", re.IGNORECASE)),
]


def extract_eat_citation(title: str | None) -> str | None:
    """The neutral citation, "[2026] EAT 34", from an EAT decision title."""
    if not title:
        return None
    m = EAT_CITATION_RE.search(title)
    return f"[{m.group(1)}] EAT {m.group(2)}" if m else None


def split_eat_parties(title: str | None) -> tuple[str | None, str | None]:
    """(appellant, respondent) from "Appellant v Respondent: [2026] EAT 34".
    EAT titles put both names before the citation, so the head split on " v "
    gives the two parties; unlike first-instance decisions there is no case
    number inside the title to get in the way.
    """
    if not title:
        return None, None
    head = title.split(":")[0]
    parts = re.split(r"\s+v\s+", head, maxsplit=1)
    if len(parts) != 2:
        return None, None
    appellant, respondent = parts[0].strip(), parts[1].strip()
    return (appellant or None), (respondent or None)


def extract_eat_outcome(body_text: str | None) -> str | None:
    """Best-effort outcome from the judgment body. Always LOW confidence —
    the caller records that; nothing here is structured metadata."""
    if not body_text:
        return None
    for label, pattern in EAT_OUTCOME_PATTERNS:
        if pattern.search(body_text):
            return label
    return None


def extract_underlying_et_cases(body_text: str | None) -> str | None:
    """The first-instance case numbers an appeal reviews, comma-joined and
    deduplicated, exactly as the judgment spells them."""
    if not body_text:
        return None
    found = []
    for match in ET_CASE_NO_RE.finditer(body_text):
        if match.group(1) not in found:
            found.append(match.group(1))
    return ",".join(found) or None


def _collect_eat_decisions(client: PipelineHTTPClient, conn, module_name: str,
                            ctx: ModuleContext) -> dict:
    """The EAT pass: one search per name variant, both title parties
    matched, body-only mentions queued for review rather than attributed.

    Returns a counts dict for the run summary.
    """
    counts = {"cases": 0, "documents": 0, "unmatched": 0, "body_mentions": 0}

    def _search_eat(query: str) -> list[dict]:
        results: list[dict] = []
        start = 0
        page_size = 100 if not ctx.limit else min(100, ctx.limit)
        while True:
            result = client.get(GOVUK_SEARCH_URL, params={
                "q": f'"{query}"',
                "filter_format": EAT_FORMAT,
                "fields": ",".join(SEARCH_FIELDS),
                "count": page_size,
                "start": start,
            })
            if not result.ok:
                return results
            data = json.loads(result.body)
            batch = data.get("results", [])
            for row in batch:
                results.append({"row": row, "result": result})
            if ctx.limit and len(results) >= ctx.limit:
                return results[:ctx.limit]
            start += len(batch)
            if not batch or start >= data.get("total", 0):
                return results

    for variant in ctx.track(SUPPLIER_NAME_VARIANTS["change_grow_live"], "EAT name variants"):
        for hit in _search_eat(variant):
            row, search_result = hit["row"], hit["result"]
            title, link = row.get("title"), row.get("link")
            citation = extract_eat_citation(title)
            if citation is None:
                db.record_parse_failure(conn, module_name, "eat_citation", title or link or "",
                                         "could not extract a neutral citation from the title",
                                         source_url=search_result.url)
                continue

            appellant, respondent = split_eat_parties(title)
            provider_key, side, basis = None, None, None
            for candidate, candidate_side in ((appellant, "appellant"),
                                               (respondent, "respondent")):
                matched_key, matched_basis = match_respondent(candidate)
                if matched_key:
                    provider_key, side, basis = matched_key, candidate_side, matched_basis
                    break

            if provider_key is None:
                # The search engine indexes bodies, so a hit can name a
                # provider without either party being one (the Attorney
                # General's restriction-order judgments list the target's
                # litigation history, including provider cases, in the body).
                # Attribution is never made on a body mention; it is queued.
                db.record_review_item(
                    conn, module_name, "eat_body_mention_only", citation,
                    json.dumps({"searched_variant": variant, "link": link,
                                "note": "neither title party matched a provider; the "
                                        "search may have matched the judgment body. "
                                        "Read the decision before treating it as "
                                        "provider evidence."}))
                counts["body_mentions"] += 1
                continue

            if ctx.is_before_since(row.get("tribunal_decision_decision_date")):
                continue

            content_result = client.get(f"{GOVUK_CONTENT_BASE}{link}")
            body_text = None
            attachments: list[dict] = []
            landmark = None
            if content_result.ok:
                content = json.loads(content_result.body)
                details = content.get("details", {})
                body_text = (details.get("metadata") or {}).get("hidden_indexable_content")
                landmark = (details.get("metadata") or {}).get("tribunal_decision_landmark")
                attachments = details.get("attachments", []) or []
            else:
                db.record_parse_failure(conn, module_name, "eat_decision_page", link or "",
                                         f"content API returned {content_result.status_code}",
                                         source_url=content_result.url)

            outcome = extract_eat_outcome(body_text)

            db.upsert(conn, "eat_cases", {
                "neutral_citation": citation,
                "decision_date": row.get("tribunal_decision_decision_date"),
                "provider_key": provider_key,
                "provider_side": side,
                "provider_match_basis": basis,
                "categories": ",".join(row.get("tribunal_decision_categories") or []) or None,
                "landmark": landmark,
                "outcome": outcome,
                # Outcome is only ever body-text derived: GOV.UK publishes no
                # structured outcome field for EAT decisions either.
                "outcome_confidence": "low" if outcome else None,
                "underlying_et_cases": extract_underlying_et_cases(body_text),
                "document_count": len(attachments),
                **_provenance(search_result),
            }, natural_key=["neutral_citation"])
            counts["cases"] += 1

            db.upsert(conn, "restricted_eat_parties", {
                "neutral_citation": citation,
                "appellant_name_raw": appellant,
                "respondent_name_raw": respondent,
                "page_title_raw": title,
                "source_slug": link,
            }, natural_key=["neutral_citation"])

            for attachment in attachments:
                url = attachment.get("url")
                if not url or not url.startswith("http"):
                    continue
                db.upsert(conn, "eat_documents", {
                    "neutral_citation": citation,
                    "document_url": url,
                    "document_title": attachment.get("title"),
                    "content_type": attachment.get("content_type"),
                    **_provenance(content_result),
                }, natural_key=["neutral_citation", "document_url"])
                counts["documents"] += 1

            if not ctx.dry_run:
                conn.commit()

    return counts


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


def _search_decisions(client: PipelineHTTPClient, query: str, limit: int | None) -> list[dict]:
    """Page through search results for one respondent name variant."""
    results: list[dict] = []
    start = 0
    page_size = 100 if not limit else min(100, limit)
    while True:
        result = client.get(GOVUK_SEARCH_URL, params={
            "q": f'"{query}"',
            "filter_format": DECISION_FORMAT,
            "fields": ",".join(SEARCH_FIELDS),
            "count": page_size,
            "start": start,
        })
        if not result.ok:
            return results
        data = json.loads(result.body)
        batch = data.get("results", [])
        for row in batch:
            results.append({"row": row, "result": result})
        if limit and len(results) >= limit:
            return results[:limit]
        start += len(batch)
        if not batch or start >= data.get("total", 0):
            return results


def _region_for_prefix(conn, office_prefix: str) -> str | None:
    row = conn.execute(
        "SELECT region FROM tribunal_office_regions WHERE office_prefix = ?", (office_prefix,)
    ).fetchone()
    return row["region"] if row else None


@register_module("m02_tribunals", supports_since=True)
def run(ctx: ModuleContext) -> None:
    module_name = "m02_tribunals"
    conn = ctx.conn
    providers.seed_providers(conn, commit=not ctx.dry_run)

    seen_cases: set[str] = set()
    unmapped_prefixes: set[str] = set()
    total_cases = 0
    total_documents = 0
    skipped_unmatched = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        ctx.phase("searching decisions")
        for variant in ctx.track(
                SUPPLIER_NAME_VARIANTS["change_grow_live"], "name variants"):
            hits = _search_decisions(client, variant, ctx.limit)
            log.info("tribunals.searched", variant=variant, hits=len(hits))
            for hit in hits:
                row, search_result = hit["row"], hit["result"]
                title, link = row.get("title"), row.get("link")

                parsed = parse_case_number(title or "", link or "")
                if parsed is None:
                    db.record_parse_failure(conn, module_name, "case_number", title or link or "",
                                             "could not extract case number from title or slug",
                                             source_url=search_result.url)
                    continue
                case_number, office_prefix, case_year = parsed
                if case_number in seen_cases:
                    continue  # same case surfaced by another name variant
                seen_cases.add(case_number)

                respondent = extract_respondent_name(title or "")
                provider_key, match_basis = match_respondent(respondent)

                if provider_key is None:
                    # Searching an ambiguous acronym ("CGL") surfaces unrelated
                    # employers. Admitting them would make COUNT(*) on this
                    # table an indefensible figure, so they are recorded for
                    # review instead of stored as provider cases.
                    db.record_review_item(
                        conn, module_name, "unmatched_tribunal_respondent", respondent or (title or ""),
                        json.dumps({"case_number": case_number, "link": link,
                                     "note": "respondent did not match any known provider name variant"}),
                    )
                    skipped_unmatched += 1
                    continue

                if ctx.is_before_since(row.get("tribunal_decision_decision_date")):
                    continue

                if match_basis == "component":
                    db.record_review_item(
                        conn, module_name, "multi_respondent_tribunal_case", respondent or "",
                        json.dumps({"case_number": case_number, "provider_key": provider_key,
                                     "note": "provider named alongside co-respondents; confirm attribution"}),
                    )

                # Fetch the decision page for attachments + body text.
                content_result = client.get(f"{GOVUK_CONTENT_BASE}{link}")
                body_text = None
                attachments: list[dict] = []
                if content_result.ok:
                    content = json.loads(content_result.body)
                    details = content.get("details", {})
                    body_text = (details.get("metadata") or {}).get("hidden_indexable_content")
                    attachments = details.get("attachments", []) or []
                else:
                    db.record_parse_failure(conn, module_name, "decision_page", link or "",
                                             f"content API returned {content_result.status_code}",
                                             source_url=content_result.url)

                region = _region_for_prefix(conn, office_prefix)
                if region is None:
                    unmapped_prefixes.add(office_prefix)

                outcome = extract_outcome(body_text)

                db.upsert(conn, "tribunal_cases", {
                    "case_number": case_number,
                    "claim_ref": claim_ref_for(case_number),
                    "provider_key": provider_key,
                    "provider_match_basis": match_basis,
                    "respondent_normalised": _normalise_respondent(respondent) or None,
                    "office_prefix": office_prefix,
                    "case_year": case_year,
                    "region": region,
                    "hearing_venue_raw": extract_hearing_venue(body_text),
                    "decision_date": row.get("tribunal_decision_decision_date"),
                    "country": row.get("tribunal_decision_country"),
                    "jurisdiction_codes": ",".join(row.get("tribunal_decision_categories") or []) or None,
                    "outcome": outcome,
                    # Outcome is only ever body-text derived: GOV.UK publishes
                    # no structured outcome field, so it is never 'high'.
                    "outcome_confidence": "low" if outcome else None,
                    "document_count": len(attachments),
                    **_provenance(search_result),
                }, natural_key=["case_number"])
                total_cases += 1

                claimant = extract_claimant_name(title or "")
                db.upsert(conn, "restricted_tribunal_parties", {
                    "case_number": case_number,
                    "claimant_name_raw": claimant,
                    "page_title_raw": title,
                    "source_slug": link,
                }, natural_key=["case_number"])

                for attachment in attachments:
                    url = attachment.get("url")
                    if not url or not url.startswith("http"):
                        continue
                    db.upsert(conn, "tribunal_documents", {
                        "case_number": case_number,
                        "document_url": url,
                        "document_title": attachment.get("title"),
                        "document_type": _document_type(attachment.get("title")),
                        "content_type": attachment.get("content_type"),
                        "archived_path": None,
                        **_provenance(content_result),
                    }, natural_key=["case_number", "document_url"])
                    total_documents += 1

                if not ctx.dry_run:
                    conn.commit()

        # The appeal pass runs after the first-instance pass so the two
        # evidence layers are collected and committed in the same order a
        # reader would meet them, and so the log lines read top-down.
        ctx.phase("searching appeal decisions")
        eat = _collect_eat_decisions(client, conn, module_name, ctx)

    for prefix in sorted(unmapped_prefixes):
        db.record_review_item(conn, module_name, "unmapped_tribunal_office_prefix", prefix,
                               json.dumps({"note": "populate tribunal_office_regions from a citable source; "
                                                    "see hearing_venue_raw on affected cases"}))

    log.info("tribunals.run_complete", cases=total_cases, documents=total_documents,
              skipped_unmatched_respondents=skipped_unmatched,
              unmapped_prefixes=sorted(unmapped_prefixes),
              eat_cases=eat["cases"], eat_documents=eat["documents"],
              eat_body_only_mentions=eat["body_mentions"])


def _document_type(attachment_title: str | None) -> str | None:
    """Classify from the attachment title only where it states the type
    explicitly; otherwise NULL rather than assumed 'judgment'.
    """
    if not attachment_title:
        return None
    lowered = attachment_title.lower()
    if "judgment with reasons" in lowered:
        return "judgment_with_reasons"
    if "reconsideration" in lowered:
        return "reconsideration"
    if "written reasons" in lowered:
        return "written_reasons"
    if "judgment" in lowered:
        return "judgment"
    return None
