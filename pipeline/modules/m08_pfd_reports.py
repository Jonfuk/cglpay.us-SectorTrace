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
from dataclasses import dataclass, field

import structlog

from pipeline import db, ocr, pdftext, providers
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
    detect names generally.

    Every part of the name is removed, not just the surname. That changed when
    the module started reading the report PDFs rather than the structured REST
    stub, because full coroner prose uses the forename freely: the first real
    report checked said "As a result Kay was not referred to a senior medical
    practitioner", and surname-only redaction published it. Of the 1,059
    reports this applies to, 1,056 have a forename that would otherwise
    survive into a public column.

    The cost is over-redaction where a forename is also an ordinary word —
    18 of those 1,059 are called Mark, Rose, May, June or Joy, and a sentence
    about a date or a mark loses a word to the placeholder. That is the right
    way round to fail. This is a corpus of reports into people's deaths, and a
    legible sentence is worth less than a name kept out of a public column.
    """
    if not text or not name:
        return text
    if name.strip().lower().strip(".") in _NAME_PLACEHOLDERS:
        return text  # judiciary.uk already withheld it; nothing to redact

    redacted = re.sub(re.escape(name), "[name redacted]", text, flags=re.IGNORECASE)
    # Longest first, so a part never matches inside a longer one it belongs to.
    # Parts of one or two characters are skipped: an initial matches too much.
    parts = sorted((p for p in re.split(r"\s+", name.strip()) if len(p) > 2),
                    key=len, reverse=True)
    for part in parts:
        redacted = re.sub(rf"\b{re.escape(part)}\b", "[name redacted]",
                           redacted, flags=re.IGNORECASE)
        # Word boundaries are not enough on text that came from OCR, which
        # loses spaces: a real report produced "MsRichardson died some 9 days
        # later", where \bRichardson\b does not match because the character
        # before it is a letter. Longer parts are therefore also removed
        # without a boundary. The threshold keeps this away from short names
        # that live inside ordinary words -- "Rose" inside "prose".
        if len(part) >= _SUBSTRING_REDACTION_MIN:
            redacted = re.sub(re.escape(part), "[name redacted]",
                               redacted, flags=re.IGNORECASE)
    return redacted


def surviving_name_part(text: str | None, name: str | None) -> str | None:
    """A part of `name` still present in `text`, or None if it is clean.

    The post-condition, checked rather than assumed. Redaction is a series of
    substitutions and OCR text defeats the assumptions each one makes, so
    before anything reaches a public column this asks the only question that
    matters: is the name still in there? A caller that gets an answer other
    than None must not publish the text.
    """
    if not text or not name:
        return None
    if name.strip().lower().strip(".") in _NAME_PLACEHOLDERS:
        return None
    haystack = text.lower()
    for part in re.split(r"\s+", name.strip()):
        cleaned = part.strip(".,'").lower()
        if len(cleaned) > 2 and cleaned in haystack:
            return part
    return None

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

# Name parts at least this long are removed without requiring a word boundary.
# See redact_name: OCR loses spaces, and a boundary-anchored pattern misses a
# surname welded to the word before it.
_SUBSTRING_REDACTION_MIN = 5

_PDF_LINK_RE = re.compile(r'href="([^"]+\.pdf[^"]*)"', re.IGNORECASE)


def choose_report_pdf(urls: list[str]) -> str | None:
    """The report itself, out of the PDFs linked on a report's page.

    A page usually carries two: the coroner's report and one or more responses
    to it. They are different documents making different claims, and the
    matters of concern are in the first — a response is somebody answering
    them. judiciary.uk names both in the URL ("...-Prevention-of-Future-Deaths-
    Report-2024-0484.pdf" beside "2024-0484-Response-from-InMind.pdf"), which
    is what this reads.

    Returns None rather than guessing when nothing looks like a report: taking
    "the first PDF" would file a response as the coroner's concerns.
    """
    candidates = [url for url in urls if "response" not in url.lower()]
    for url in candidates:
        if "report" in url.lower():
            return url
    return candidates[0] if candidates else None


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


def index_concern_terms(matters_text: str, welded: bool = False) -> dict[str, int]:
    """Count of each watched term in MATTERS OF CONCERN. A finding aid only —
    presence of a word is not a conclusion about the report.

    `welded` drops the leading word boundary, for text that came from OCR,
    which still runs the occasional pair of words together — "onisown" for "on
    its own" in a report read during this work. A boundary-anchored search
    finds a term inside a welded run only if the run happens to begin with it,
    and the effect is silent: the reports hardest to read become the ones least
    findable, which is the opposite of what an index is for.

    This mattered far more before the OCR engine was changed, when the
    recogniser was Chinese-trained and produced whole clauses as one word. It
    is kept because OCR text is still imperfect, and because the looser match
    can only over-count — acceptable in a way it would not be elsewhere, since
    this column is explicitly a way of finding reports to read rather than a
    measurement of anything.
    """
    counts: dict[str, int] = {}
    text = (matters_text or "").lower()
    prefix = "" if welded else r"\b"
    for term in PFD_CONCERN_INDEX_TERMS:
        n = len(re.findall(rf"{prefix}{re.escape(term.lower())}", text))
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


@dataclass
class PdfRead:
    """What came back from trying to read a report's PDF.

    A record rather than a tuple because the interesting cases are the partial
    ones: no text but a URL worth reporting, text but from OCR and therefore
    weaker evidence, nothing at all and a reason why.
    """

    text: str | None = None
    urls: list[str] = field(default_factory=list)
    chosen: str | None = None
    reason: str | None = None
    # "pdf" for a real text layer, "ocr" for a scan that was read by machine.
    source: str | None = None


def fetch_pdf_report(client, settings, report_url: str) -> PdfRead:
    """The text of a report published only as a PDF.

    Roughly two thirds of PFD reports put nothing but a metadata header in the
    REST content: the report itself is a PDF, and it is not linked from the
    API response either. So this goes to the report's own page, finds the PDF
    there, and reads it.

    Two fetches per report, and there are over a thousand of them, which at the
    standard 2s/host is around seventy minutes of crawling. That cost is the
    reason the caller skips any report whose concerns it already holds: after
    the first pass this does nothing, and an interrupted pass resumes where it
    stopped because each page of results commits.

    `reason` is None on success and otherwise names what stopped it, because
    the reports this cannot read are not all the same problem and the review
    item that remains should say which one it hit. Sampling twelve of them
    found seven with no text layer at all — scanned paper, mostly from 2014 to
    2018 — which needs OCR rather than a person's judgement, and a queue item
    saying so is worth more than one saying "the concerns are in a PDF".
    """
    page = client.get(report_url)
    if not page.ok:
        log.info("pfd.report_page_unavailable", url=report_url,
                  status=page.status_code)
        return PdfRead(reason=f"report page returned {page.status_code}")

    html = page.body.decode("utf-8", "replace")
    urls = [url.replace("&amp;", "&")
             for url in dict.fromkeys(_PDF_LINK_RE.findall(html))]
    chosen = choose_report_pdf(urls)
    if chosen is None:
        return PdfRead(urls=urls, reason=(
            "no report PDF on the page" if not urls
            else "the only PDFs on the page are responses, not the report"))

    document = client.get(chosen)
    if not document.ok:
        log.info("pfd.report_pdf_unavailable", url=chosen,
                  status=document.status_code)
        return PdfRead(urls=urls, chosen=chosen,
                        reason=f"report PDF returned {document.status_code}")

    try:
        pages = pdftext.page_texts(settings, SOURCE_SYSTEM,
                                    document.payload_sha256, document.body)
    except Exception as exc:
        # A PDF that pdfplumber cannot open is a source problem, not a reason
        # to abandon the run. The caller falls back to raising the review item.
        log.warning("pfd.pdf_unreadable", url=chosen, error=f"{type(exc).__name__}: {exc}")
        return PdfRead(urls=urls, chosen=chosen,
                        reason=f"PDF could not be opened: {type(exc).__name__}")

    text = "\n".join(page_text for page_text in pages if page_text).strip()
    if text:
        return PdfRead(text=text, urls=urls, chosen=chosen, source="pdf")

    # pdfplumber opened it and every page came back empty: the document is a
    # picture of a document. Reading it needs OCR.
    if not ocr.enabled(settings):
        return PdfRead(urls=urls, chosen=chosen, reason=(
            f"the report PDF is a scan with no text layer ({len(pages)} pages); "
            + ("OCR is installed but switched off (set OCR_ENABLED)"
                if ocr.available() else "reading it needs the ocr extra")))

    try:
        ocr_pages = ocr.page_texts(settings, SOURCE_SYSTEM,
                                    document.payload_sha256, document.body)
    except Exception as exc:
        log.warning("pfd.ocr_failed", url=chosen, error=f"{type(exc).__name__}: {exc}")
        return PdfRead(urls=urls, chosen=chosen,
                        reason=f"OCR failed: {type(exc).__name__}")

    ocr_text = "\n".join(page_text for page_text in ocr_pages if page_text).strip()
    if not ocr_text:
        return PdfRead(urls=urls, chosen=chosen, reason=(
            f"OCR read the {len(ocr_pages)}-page scan and found no text on any page"))
    return PdfRead(text=ocr_text, urls=urls, chosen=chosen, source="ocr")


def _already_has_concerns(conn, report_ref: str) -> bool:
    """Whether a previous run already read this report's PDF.

    What makes the PDF pass affordable to repeat. Without it every run would
    spend another seventy minutes re-fetching a thousand documents whose
    contents are already in the warehouse.
    """
    row = conn.execute(
        "SELECT 1 FROM pfd_reports WHERE report_ref = ? "
        "AND matters_of_concern IS NOT NULL AND TRIM(matters_of_concern) <> ''",
        (report_ref,)).fetchone()
    return row is not None


def _is_before_since_ddmmyyyy(ctx, report_date: str | None) -> bool:
    """PFD headers give the report date as DD/MM/YYYY, not ISO.

    Passing that to the shared ISO helper would never parse, so it would
    always return False and `--since` would filter nothing while appearing to
    work. Unparseable or missing dates are still kept — dropping a report
    because its date could not be read would lose evidence.
    """
    boundary = ctx.since_date()
    if boundary is None or not report_date:
        return False
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})", report_date)
    if not m:
        return False
    from datetime import date as _date

    try:
        parsed = _date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return False
    return parsed < boundary


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


@register_module("m08_pfd_reports", supports_since=True)
def run(ctx: ModuleContext) -> None:
    module_name = "m08_pfd_reports"
    conn = ctx.conn
    providers.seed_providers(conn, commit=not ctx.dry_run)

    reports_written = 0
    recipient_mentions = 0
    body_mentions = 0
    seen_refs: set[str] = set()

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        ctx.phase("listing categories")
        for category_id, category_name in ctx.track(
                list(TARGET_CATEGORY_IDS.items()), "PFD categories"):
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
                    if _is_before_since_ddmmyyyy(ctx, fields.get("report_date")):
                        continue
                    seen_refs.add(report_ref)

                    deceased_name = fields.get("deceased_name")
                    matters = extract_matters_of_concern(text)
                    provenance = _provenance(result)

                    # The REST content is a metadata stub for about two thirds
                    # of reports. Go and read the PDF the page links to.
                    #
                    # `body_text` stays the stub unless the PDF is actually
                    # read: the header fields and the recipients list are
                    # cleanly structured in the stub and are not re-derived
                    # from PDF prose, so only the things the stub genuinely
                    # lacks — the concerns, the full text, and the provider
                    # mentions inside it — come from the document.
                    pdf_urls: list[str] = []
                    pdf_reason: str | None = None
                    concerns_source = "rest" if matters else None
                    if (matters is None and len(text) < 1500
                            and not _already_has_concerns(conn, report_ref)):
                        ctx.phase(f"reading the PDF for {report_ref}")
                        read = fetch_pdf_report(client, ctx.settings,
                                                 post.get("link") or "")
                        pdf_urls, pdf_reason = read.urls, read.reason
                        pdf_matters = extract_matters_of_concern(read.text or "")
                        if read.text and not pdf_matters:
                            pdf_reason = ("the report PDF was read but has no "
                                           "matters-of-concern section")

                        if pdf_matters and not deceased_name:
                            # Nothing to redact *with*. The header gave no name,
                            # so there is no way to know whether the coroner
                            # used one in this section — and "probably not" is
                            # not a standard to publish personal data against.
                            # The text is kept where restricted text belongs
                            # and the concerns column is left empty.
                            db.record_parse_failure(
                                conn, module_name, "deceased_name", report_ref,
                                "PDF carries matters of concern but the header gave no "
                                "name to redact against; concerns not stored publicly",
                                source_url=read.chosen or "")
                            pdf_reason = "no deceased name to redact against"
                            pdf_matters = None

                        # The post-condition, checked rather than assumed. OCR
                        # loses spaces, and "MsRichardson" defeated a
                        # word-boundary redaction on a real report — the
                        # surname would have gone into a public column. If any
                        # part of the name is still there after redacting,
                        # nothing is published and the reason is recorded.
                        if pdf_matters:
                            survivor = surviving_name_part(
                                redact_name(pdf_matters, deceased_name), deceased_name)
                            if survivor:
                                db.record_parse_failure(
                                    conn, module_name, "matters_of_concern", report_ref,
                                    f"redaction left part of the deceased's name "
                                    f"({survivor!r}) in the concerns; not stored publicly "
                                    f"(source={read.source})",
                                    source_url=read.chosen or "")
                                log.warning("pfd.redaction_incomplete",
                                             report_ref=report_ref, source=read.source)
                                pdf_reason = "redaction could not clear the name"
                                pdf_matters = None

                        if read.text:
                            text = read.text
                        if pdf_matters:
                            matters = pdf_matters
                            concerns_source = read.source
                            log.info("pfd.concerns_from_pdf", report_ref=report_ref,
                                      url=read.chosen, source=read.source,
                                      chars=len(pdf_matters))

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
                        # Which of the three routes these came from. OCR text
                        # is legible and not a faithful transcript, and a
                        # quotation drawn from this column may end up in a
                        # campaign document.
                        "concerns_source": concerns_source,
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

                    # Only when the PDF could not supply them either. The
                    # common case — a metadata stub whose PDF reads cleanly —
                    # no longer reaches here at all, which is the point: it was
                    # never a judgement anyone could make, it was a document
                    # this module had not gone and read.
                    if matters is None and len(text) < 1500:
                        db.record_review_item(
                            conn, module_name, "pfd_concerns_in_pdf_only", report_ref,
                            json.dumps({"report_url": post.get("link") or "",
                                         "body_chars": len(text),
                                         "pdfs_on_page": pdf_urls,
                                         "reason": pdf_reason or "not attempted",
                                         "note": "inline content is a metadata stub and the "
                                                  "report PDF did not yield the concerns; "
                                                  "see reason"}))

                    for term, occurrences in index_concern_terms(
                            matters or "", welded=concerns_source == "ocr").items():
                        db.upsert(conn, "pfd_concern_terms", {
                            "report_ref": report_ref, "term": term, "occurrences": occurrences,
                        }, natural_key=["report_ref", "term"])

                    # PDFs named in the REST content, plus any found on the
                    # report's own page when it was fetched above.
                    for url in dict.fromkeys(
                            [*_PDF_LINK_RE.findall(rendered), *pdf_urls]):
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
