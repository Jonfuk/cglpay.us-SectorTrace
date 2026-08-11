"""Module 8 — Prevention of Future Deaths reports.

judiciary.uk publishes PFD reports as a WordPress custom post type with a
REST endpoint, so this module reads structured JSON rather than scraping
listing pages, and the full report text arrives inline — no PDF fetching is
needed for the body. robots.txt allows all, and the shared client's default
one-request-per-two-seconds applies.

Only the categories the brief names are collected: alcohol/drug/medication,
mental health, and community health care and emergency services.

Two things this module is careful about:

  * The deceased is named in the page title and in a "Deceased name :" field.
    Neither reaches a public table; both go to restricted_pfd_persons, and
    pfd_reports is keyed on the coroner's own report reference. The coroner's
    own name is kept public — they are a public official named on the face of
    a published report, and the brief lists it among the fields to capture.

  * A provider being SENT a report and a provider being MENTIONED in one are
    recorded as different mention types and never merged. Being addressed by
    a coroner is a materially different fact from being named in passing, and
    counting them together would overstate the first.

MATTERS OF CONCERN is stored verbatim and indexed for workforce-related terms
so the relevant reports can be found quickly. The pipeline does not
summarise, score or characterise what a coroner found.
"""
from __future__ import annotations

import html as html_lib
import json
import re

import structlog

from pipeline import db, providers
from pipeline.http import PipelineHTTPClient
from pipeline.keywords import PFD_CONCERN_INDEX_TERMS, SUPPLIER_NAME_VARIANTS
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "judiciary_uk_pfd"
API_BASE = "https://www.judiciary.uk/wp-json/wp/v2"
PER_PAGE = 100

# judiciary.uk pfd_report_type term ids for the categories the brief names.
TARGET_CATEGORY_IDS = {
    262: "Alcohol, drug and medication related deaths",
    266: "Mental Health related deaths",
    263: "Community health care and emergency services related deaths",
}

# judiciary.uk uses two header spellings depending on the report's vintage:
# "Coroner name :" / "Coroner area :" on older reports, and "Coroners name:" /
# "Coroners Area:" on newer ones. Matching only the first form left the
# coroner unrecorded on roughly half of a 200-report sample.
_CORONER = r"Coroner(?:'?s)?"
_FIELD_PATTERNS = {
    "report_date": re.compile(r"Date of report\s*:\s*([^\n]{1,40}?)(?=\s{2,}|\s*Ref\s*:|$)", re.IGNORECASE),
    "report_ref": re.compile(r"\bRef\s*:\s*([A-Za-z0-9\-/]+)", re.IGNORECASE),
    "deceased_name": re.compile(
        rf"Deceased name\s*:\s*([^\n]{{1,80}}?)(?=\s{{2,}}|\s*{_CORONER}\s+name\s*:|$)", re.IGNORECASE),
    "coroner_name": re.compile(
        rf"{_CORONER}\s+name\s*:\s*([^\n]{{1,80}}?)(?=\s{{2,}}|\s*{_CORONER}\s+area\s*:|$)", re.IGNORECASE),
    "coroner_area": re.compile(
        rf"{_CORONER}\s+area\s*:\s*([^\n]{{1,120}}?)"
        rf"(?=\s{{2,}}|\s*Category\s*:|\s*This report is being sent to|$)", re.IGNORECASE),
}


def redact_name(text: str | None, name: str | None) -> str | None:
    """Remove a known name from text before it enters a public column.

    Deterministic: an exact, case-insensitive replacement of a name this
    module already read from the report's own header — not an attempt to
    detect names generally. Used on MATTERS OF CONCERN, where the deceased is
    named in roughly one report in twenty.
    """
    if not text or not name:
        return text
    if name.strip().lower().strip(".") in _NAME_PLACEHOLDERS:
        return text  # judiciary.uk already withheld it; nothing to redact
    redacted = re.sub(re.escape(name), "[name redacted]", text, flags=re.IGNORECASE)
    # Also catch the surname alone, which coroners often use after first use.
    parts = [p for p in re.split(r"\s+", name.strip()) if len(p) > 2]
    if parts:
        redacted = re.sub(rf"\b{re.escape(parts[-1])}\b", "[name redacted]",
                           redacted, flags=re.IGNORECASE)
    return redacted

_SENT_TO_HEADER_RE = re.compile(
    r"THIS REPORT IS BEING SENT TO\s*:?(.{0,1200}?)(?:\d\.\s*CORONER\b|\bCORONER'?S LEGAL POWERS\b)",
    re.IGNORECASE | re.DOTALL)

# Heading wording varies: "MATTERS OF CONCERN", the singular "MATTER OF
# CONCERN", and a bare "CONCERNS" all occur in live reports. The bare form is
# matched case-sensitively via an inline flag, because lowercase "concerns" is
# an ordinary word and matching it caught plain prose.
_MATTERS_RE = re.compile(
    r"(?:MATTERS? OF CONCERN|(?-i:CONCERNS))\b"
    r"(.*?)(?=\bACTION SHOULD BE TAKEN\b|\bYOUR RESPONSE\b|\bCOPIES\b|$)",
    re.IGNORECASE | re.DOTALL)

# Values judiciary.uk uses in the deceased-name field when it has itself
# withheld the name. Treating these as a name to redact would rewrite
# unrelated text (and produce nested "[name [name redacted]]" markers).
_NAME_PLACEHOLDERS = {"redacted", "unknown", "not stated", "n/a", "na", "withheld", "anonymised"}

_PDF_LINK_RE = re.compile(r'href="([^"]+\.pdf[^"]*)"', re.IGNORECASE)


def strip_html(raw_html: str) -> str:
    """Readable text from the rendered post content."""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw_html or "", flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = text.replace("’", "'").replace("‘", "'")
    text = re.sub(r"[ \t ]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def parse_header_fields(text: str) -> dict:
    """The structured header judiciary.uk puts at the top of each report."""
    out: dict[str, str | None] = {}
    for field, pattern in _FIELD_PATTERNS.items():
        m = pattern.search(text or "")
        value = m.group(1).strip().rstrip(".").strip() if m else None
        out[field] = value or None
    return out


def extract_recipients(text: str) -> list[str]:
    """Organisations under 'THIS REPORT IS BEING SENT TO'.

    Numbered list entries only. Deliberately conservative: the surrounding
    prose often also names a family or another body ("I am also sending this
    to…"), and those are not recipients of the report itself.
    """
    m = _SENT_TO_HEADER_RE.search(text or "")
    if not m:
        return []
    block = m.group(1)
    # cut at the "I am also sending this to..." aside, which is not a recipient list
    block = re.split(r"\bI am also sending\b", block, flags=re.IGNORECASE)[0]

    recipients: list[str] = []
    for line in re.split(r"\n|(?=\b\d{1,2}\.\s)", block):
        cleaned = re.sub(r"^\s*\d{1,2}[\.\)]\s*", "", line).strip()
        cleaned = cleaned.strip(" ;,.")
        if not cleaned or len(cleaned) < 3 or len(cleaned) > 160:
            continue
        if re.match(r"^(and|the family|copies?)\b", cleaned, re.IGNORECASE):
            continue
        if cleaned not in recipients:
            recipients.append(cleaned)
    return recipients


def extract_matters_of_concern(text: str) -> str | None:
    m = _MATTERS_RE.search(text or "")
    if not m:
        return None
    section = m.group(1).strip()
    section = re.sub(r"^(are as follows|is|are)\s*[.:]?\s*", "", section, flags=re.IGNORECASE).strip()
    return section or None


def index_concern_terms(matters_text: str) -> dict[str, int]:
    """Count of each watched term in MATTERS OF CONCERN. A finding aid only —
    presence of a word is not a conclusion about the report.
    """
    counts: dict[str, int] = {}
    text = (matters_text or "").lower()
    for term in PFD_CONCERN_INDEX_TERMS:
        n = len(re.findall(rf"\b{re.escape(term.lower())}", text))
        if n:
            counts[term] = n
    return counts


def _normalise(name: str) -> str:
    text = re.sub(r"[^\w\s]", " ", (name or "").lower())
    text = re.sub(r"\b(limited|ltd|llp|plc|cic)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Short/ambiguous variants that would produce nonsense matches in free text.
_UNSAFE_VARIANTS = {"cgl", "via", "inclusion"}

_PROVIDER_VARIANTS: list[tuple[str, str, list[str]]] = []
for _key, _variants in SUPPLIER_NAME_VARIANTS.items():
    for _variant in _variants:
        _n = _normalise(_variant)
        if _n and _n not in _UNSAFE_VARIANTS:
            _PROVIDER_VARIANTS.append((_key, _variant, _n.split()))


def find_provider_mentions(text: str) -> list[tuple[str, str]]:
    """(provider_key, matched_variant) for providers named in `text`.

    Whole-token matching, so "Via" cannot match inside "Viaduct" and short
    acronyms are excluded entirely — a false positive here would attribute a
    coroner's report to an organisation that had nothing to do with it.
    """
    tokens = _normalise(text).split()
    if not tokens:
        return []
    found: dict[str, str] = {}
    for provider_key, variant, variant_tokens in _PROVIDER_VARIANTS:
        window = len(variant_tokens)
        if window > len(tokens):
            continue
        for start in range(len(tokens) - window + 1):
            if tokens[start:start + window] == variant_tokens:
                found.setdefault(provider_key, variant)
                break
    return sorted(found.items())


def redact_known_names_across_reports(conn) -> int:
    """Second redaction pass over matters_of_concern, using every deceased
    name in the corpus rather than only the current report's.

    Needed because a coroner's concerns can name a third party — someone who
    is the subject of a *different* PFD report, or is referenced from another
    investigation. Per-report redaction cannot see those, and a live run left
    six such names in a public column.

    Deterministic: the name list comes from the source's own "Deceased name"
    fields, and matching is exact. Applied only to matters_of_concern —
    coroner_name is legitimately public and is left alone, even when a
    coroner shares a name with someone's deceased.
    """
    names = [
        row["deceased_name"].strip()
        for row in conn.execute(
            "SELECT deceased_name FROM restricted_pfd_persons WHERE deceased_name IS NOT NULL")
        if row["deceased_name"]
        and len(row["deceased_name"].strip()) > 6
        and row["deceased_name"].strip().lower().strip("[]") not in _NAME_PLACEHOLDERS
    ]
    if not names:
        return 0

    redacted_rows = 0
    for row in conn.execute(
            "SELECT report_ref, matters_of_concern FROM pfd_reports "
            "WHERE matters_of_concern IS NOT NULL").fetchall():
        original = row["matters_of_concern"]
        cleaned = original
        for name in names:
            if name in cleaned:
                cleaned = cleaned.replace(name, "[name redacted]")
        if cleaned != original:
            conn.execute("UPDATE pfd_reports SET matters_of_concern = ? WHERE report_ref = ?",
                          (cleaned, row["report_ref"]))
            redacted_rows += 1
    return redacted_rows


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


@register_module("m08_pfd_reports")
def run(ctx: ModuleContext) -> None:
    module_name = "m08_pfd_reports"
    conn = ctx.conn
    providers.seed_providers(conn)

    reports_written = 0
    recipient_mentions = 0
    body_mentions = 0
    seen_refs: set[str] = set()

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        for category_id, category_name in TARGET_CATEGORY_IDS.items():
            page = 1
            while True:
                result = client.get(f"{API_BASE}/pfd", params={
                    "pfd_report_type": category_id, "per_page": PER_PAGE, "page": page,
                    "orderby": "date", "order": "desc",
                })
                if not result.ok:
                    # WordPress returns 400 past the last page rather than an
                    # empty array, so this is the normal end-of-pagination.
                    if result.status_code not in (400, 404):
                        db.record_review_item(
                            conn, module_name, "pfd_listing_unavailable", str(category_id),
                            json.dumps({"page": page, "status": result.status_code}))
                    break

                try:
                    posts = json.loads(result.body)
                except json.JSONDecodeError:
                    db.record_parse_failure(conn, module_name, "listing", str(category_id),
                                             "listing response was not valid JSON",
                                             source_url=result.url)
                    break
                if not isinstance(posts, list) or not posts:
                    break

                for post in posts:
                    rendered = (post.get("content") or {}).get("rendered", "")
                    text = strip_html(rendered)
                    fields = parse_header_fields(text)
                    report_ref = fields.get("report_ref")
                    page_title = strip_html((post.get("title") or {}).get("rendered", ""))

                    if not report_ref:
                        # Without the coroner's reference there is no key that
                        # is free of the deceased's name, so this is logged
                        # rather than keyed on the title.
                        db.record_parse_failure(
                            conn, module_name, "report_ref", post.get("link") or "",
                            "no 'Ref :' field found; cannot key without using the title",
                            source_url=result.url)
                        continue
                    if report_ref in seen_refs:
                        continue  # a report can carry more than one category
                    seen_refs.add(report_ref)

                    deceased_name = fields.get("deceased_name")
                    matters = extract_matters_of_concern(text)
                    provenance = _provenance(result)

                    db.upsert(conn, "pfd_reports", {
                        "report_ref": report_ref,
                        "report_date": fields.get("report_date"),
                        "coroner_name": fields.get("coroner_name"),
                        "coroner_area": fields.get("coroner_area"),
                        "categories": category_name,
                        "report_url": post.get("link") or "",
                        # Redacted before it reaches a public column: coroners
                        # name the deceased inside this section fairly often.
                        "matters_of_concern": redact_name(matters, deceased_name),
                        **provenance,
                    }, natural_key=["report_ref"])
                    reports_written += 1

                    db.upsert(conn, "restricted_pfd_persons", {
                        "report_ref": report_ref,
                        "deceased_name": deceased_name,
                        "page_title_raw": page_title,
                    }, natural_key=["report_ref"])

                    # Full text is restricted: the deceased is named throughout
                    # a PFD report, not just in the header field.
                    db.upsert(conn, "restricted_pfd_report_text", {
                        "report_ref": report_ref, "body_text": text,
                    }, natural_key=["report_ref"])

                    recipients = extract_recipients(text)
                    for organisation in recipients:
                        db.upsert(conn, "pfd_recipients", {
                            "report_ref": report_ref, "organisation_name": organisation,
                        }, natural_key=["report_ref", "organisation_name"])

                    recipient_text = " ; ".join(recipients)
                    recipient_keys = {k for k, _ in find_provider_mentions(recipient_text)}
                    for provider_key, variant in find_provider_mentions(recipient_text):
                        db.upsert(conn, "pfd_provider_mentions", {
                            "report_ref": report_ref, "provider_key": provider_key,
                            "mention_type": "recipient", "matched_name": variant,
                        }, natural_key=["report_ref", "provider_key", "mention_type"])
                        recipient_mentions += 1

                    # Named in the report but NOT addressed by it — a different
                    # fact, recorded separately and never merged with the above.
                    for provider_key, variant in find_provider_mentions(text):
                        if provider_key in recipient_keys:
                            continue
                        db.upsert(conn, "pfd_provider_mentions", {
                            "report_ref": report_ref, "provider_key": provider_key,
                            "mention_type": "body_text", "matched_name": variant,
                        }, natural_key=["report_ref", "provider_key", "mention_type"])
                        body_mentions += 1

                    # Roughly two thirds of reports publish only a metadata
                    # stub inline, with the report itself as a PDF that is not
                    # linked in the REST content. Recorded so the missing
                    # concerns are visibly a source limitation, not a parser
                    # failure — and so the PDFs can be chased separately.
                    if matters is None and len(text) < 1500:
                        db.record_review_item(
                            conn, module_name, "pfd_concerns_in_pdf_only", report_ref,
                            json.dumps({"report_url": post.get("link") or "",
                                         "body_chars": len(text),
                                         "note": "inline content is a metadata stub; matters of "
                                                  "concern are in a PDF not linked in the REST content"}))

                    for term, occurrences in index_concern_terms(matters or "").items():
                        db.upsert(conn, "pfd_concern_terms", {
                            "report_ref": report_ref, "term": term, "occurrences": occurrences,
                        }, natural_key=["report_ref", "term"])

                    for url in dict.fromkeys(_PDF_LINK_RE.findall(rendered)):
                        lowered = url.lower()
                        document_type = ("response" if "response" in lowered
                                          else "report" if "report" in lowered else None)
                        db.upsert(conn, "pfd_documents", {
                            "report_ref": report_ref, "document_url": url.replace("&amp;", "&"),
                            "document_type": document_type,
                        }, natural_key=["report_ref", "document_url"])

                    if ctx.limit and reports_written >= ctx.limit:
                        break

                if not ctx.dry_run:
                    conn.commit()

                log.info("pfd.page_processed", category=category_id, page=page, posts=len(posts))
                if ctx.limit and reports_written >= ctx.limit:
                    break
                if len(posts) < PER_PAGE:
                    break
                page += 1

            if ctx.limit and reports_written >= ctx.limit:
                break

    # Runs once the whole corpus is present, since it needs every name.
    cross_redacted = redact_known_names_across_reports(conn)
    if not ctx.dry_run:
        conn.commit()

    log.info("pfd.run_complete", reports=reports_written,
              recipient_mentions=recipient_mentions, body_mentions=body_mentions,
              cross_report_redactions=cross_redacted)
