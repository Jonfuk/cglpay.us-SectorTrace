"""Module 24 — council spend-transparency files (G5).

The strongest procurement evidence the corpus could hold: "council X paid
provider Y £Z in [period]" is actual money, not a notice. Councils publish
£500+ spend as files on their own sites — the Local Government Transparency
Code — and there is no central API for them, so this module harvests in the
m09/m10 shape: discover the file on the authority's own domain (B4's full
website coverage is what makes the discovery possible), fetch it through the
pipeline client (archived, with provenance), and parse line items.

DISCOVERY. For each authority with a base_url, a bounded set of likely
spend-transparency paths is tried (the same approach m09 uses for CDP
documents: a 404 is expected and unremarkable), and links whose URL or text
carries the spend vocabulary — spend, expenditure, payments, suppliers,
invoices, transparency — are followed when they point at a data file
(csv, xlsx, ods). At most MAX_FILES_PER_AUTHORITY files are fetched per
authority; a council that publishes no file under those paths stays a
council with no file discovered here, which the review queue records as
`council_spend_none_found` rather than leaving it to look like a gap.

PARSING. Line-item quality varies council to council, so the NULL
discipline does the work: `payee`, `amount_text` and `description` are
verbatim, `amount` is the same figure parsed as a number (NULL where the
council's formatting could not be read, never a guess and never a zero),
and `period` is the label the council's own file used. A file that cannot
be parsed at all is `council_spend_files.parse_status = 'unreadable'` plus
a `parse_failures` row and a review item — an unreadable file is a fact
about the council, not evidence that it published nothing. Supported
formats: CSV (the common case), XLSX via `pipeline.xlsx`, and ODS via the
same odfpy reader m13 uses.

PROVIDER MATCHING. `provider_key` is set only by an exact-normalised match
of the payee against the tracked providers' own name variants — m04's
discipline, the same rule m16 and m20 apply to their sources. A payee that
matches no provider keeps its verbatim name and a NULL key; the universe
work (m23) owns name reconciliation at scale, and a near-miss is never
stored as a match.

There is deliberately NO arithmetic across rows or sources: no monthly
totals, no share-of-spend, no comparison against contracts. The rows are
what the council published, one line per payment.
"""
from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import structlog
from odf.opendocument import load as load_ods
from odf.table import Table, TableCell, TableRow
from odf.text import P

from pipeline import db
from pipeline.authority_websites import website_for
from pipeline.http import RobotsDisallowed
from pipeline.keywords import SUPPLIER_NAME_VARIANTS
from pipeline.parallel import fetch_in_parallel, worker_count
from pipeline.registry import ModuleContext, register_module
from pipeline.xlsx import XlsxError, iter_sheet_stream, sheet_names

log = structlog.get_logger()

SOURCE_SYSTEM = "council_spend_transparency"

# Paths where a council is likely to publish its spend transparency files.
# Tried in order; a 404 is expected and unremarkable, exactly as in m09.
SPEND_PATHS = [
    "/",
    "/transparency",
    "/about-your-council/transparency",
    "/your-council/transparency",
    "/finance-and-governance",
    "/open-data",
    "/data",
    "/spend",
    "/expenditure",
    "/payments-over-500",
    "/transparency-data",
]

# How many files one authority's pages may yield before the discovery stops
# following. The budget exists so a council that lists its whole spend
# archive costs bounded requests; the newest file is fetched first.
MAX_FILES_PER_AUTHORITY = 3

# What makes a link worth following. The URL must end in a data-file
# extension AND the URL or anchor text must carry the spend vocabulary — a
# lone .csv on a transparency page is not necessarily spend data, and this
# pipeline does not guess what a file is.
FILE_EXTENSIONS = (".csv", ".xlsx", ".xls", ".ods")
SPEND_WORDS = re.compile(
    r"spend|expenditure|payment|payments|supplier|invoice|transparency|"
    r"over-500|over-500|over500", re.IGNORECASE)

# The Local Government Transparency Code mandates several other datasets a
# council publishes alongside its £500 spend, and "transparency" in the
# link is enough for SPEND_WORDS to follow them. They have a different
# schema — no payee/amount pair — so each is fetched only to fail header
# detection and land in parse_failures. A link whose URL or text carries
# one of these is not a payments file. (Every term here was observed doing
# exactly that in the review queue: fraud returns, senior-salary tables,
# grants-to-VCS lists, asset and land registers, parking-space inventories.)
NON_SPEND_WORDS = re.compile(
    r"\bfraud\b|salar|senior[\s_-]?pay|pay[\s_-]?multiple|"
    r"\bgrants?\b|\bassets?\b|\bland\b|parking", re.IGNORECASE)

_LINK_RE = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                      re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")

# Header synonyms for the columns a spend file must carry. The payee column
# and the amount column are required; period and description are optional
# and NULL where absent. Keys are matched against the header cell lower-cased
# and whitespace-normalised; the lists are deliberately tolerant of the
# variations councils actually use.
_PAYEE_HEADERS = ("supplier", "payee", "vendor", "beneficiary", "creditor",
                  "organisation", "organization", "company", "supplier name",
                  "payee name", "name of supplier", "supplier organisation",
                  "vendor name", "beneficiary name", "creditor name",
                  "supplier / beneficiary", "merchant", "merchant name",
                  "body name", "trading name", "recipient", "paid to")
_AMOUNT_HEADERS = ("amount", "value", "net amount", "gross amount", "total",
                   "amount paid", "payment amount", "amount (£)",
                   "amount excluding vat", "spend", "expenditure", "cost",
                   "transaction amount", "invoice amount", "total amount",
                   "payment value", "amount in sterling", "gross value",
                   "net value", "amount gbp")
_PERIOD_HEADERS = ("period", "month", "date", "payment date", "invoice date",
                   "financial year", "financial period", "month/year",
                   "date of payment")
_DESCRIPTION_HEADERS = ("description", "details", "service", "category",
                        "expenditure category", "purpose", "summary",
                        "goods and services")


def _link_text(raw: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", raw or "")).strip()


def _normalise_name(name: str) -> str:
    """Same whole-word normalisation family as m20: match on the words that
    distinguish a supplier, drop the words that never do."""
    text = re.sub(r"[^\w\s]", " ", (name or "").lower())
    text = re.sub(r"\b(limited|ltd|llp|plc|cic|trust|foundation|company|the)\b",
                  " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalise_header(value: str) -> str:
    """Lower-case and whitespace-normalise a header cell, and drop a
    currency/unit qualifier: councils label the money column "Amount (£)",
    "Value £", "Amount (GBP)", "Amount (net)", and the synonym list should
    not need a variant for every bracketed form."""
    text = (value or "").lower().replace("£", " ")
    text = re.sub(
        r"[\(\[]\s*(?:gbp|pounds?|sterling|net|gross|excl\.?\s*vat|"
        r"incl\.?\s*vat|000s?|)\s*[\)\]]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _match_headers(header: list[str], synonyms: tuple[str, ...]) -> int | None:
    """The first header cell matching a synonym, else None."""
    for index, cell in enumerate(header):
        if _normalise_header(cell) in synonyms:
            return index
    return None


def _to_number(text: str) -> float | None:
    """A spend cell as a number. Blank is NULL; unreadable is NULL — the
    verbatim text survives in amount_text, and a number is never assumed."""
    text = (text or "").strip()
    if not text:
        return None
    text = text.replace("£", "").replace(",", "").strip()
    text = re.sub(r"^\((.+)\)$", r"-\1", text)  # accounting negative
    try:
        return float(text)
    except ValueError:
        return None


@dataclass
class SpendFindings:
    """Everything one authority's fetching produced, and nothing written yet.

    Workers run on a thread pool and must not touch the module's connection,
    so what they would have written is carried back here and written by the
    main thread — the same separation m10 uses.
    """

    ons_code: str
    name: str
    files: list[dict] = field(default_factory=list)   # file-level rows to write
    lines: list[dict] = field(default_factory=list)   # line-item rows to write
    review_items: list[tuple[str, str, dict]] = field(default_factory=list)
    parse_failures: list[tuple[str, str, str, str]] = field(default_factory=list)

    def flag(self, item_type: str, raw_value: str, context: dict) -> None:
        self.review_items.append((item_type, raw_value, context))


def _file_urls_on_page(page_html: str, page_url: str, host: str) -> list[str]:
    """Data-file links on one page whose URL or text carries spend vocabulary.

    Restricted to the same host as the page (the m09 rule, so a crawl cannot
    wander onto unrelated domains). A link to a data file that says nothing
    spend-like is not followed — what a file contains is not guessed from
    its extension alone.
    """
    out: list[str] = []
    for href, raw_text in _LINK_RE.findall(page_html or ""):
        url = urljoin(page_url, href.strip())
        if urlparse(url).netloc != host:
            continue
        path = url.lower().split("?")[0]
        if not path.endswith(FILE_EXTENSIONS):
            continue
        haystack = f"{url} {_link_text(raw_text)}"
        if not SPEND_WORDS.search(haystack):
            continue
        if NON_SPEND_WORDS.search(haystack):
            continue
        out.append(url)
    return out


def _parse_csv(body: bytes, file_url: str) -> tuple[list[dict], str | None]:
    """A CSV spend file as line-item rows. Returns (rows, error)."""
    # Decode incrementally from the archived bytes. A large spend export must
    # not briefly exist as both its complete byte payload and a second
    # complete decoded string before parsing starts.
    stream = io.TextIOWrapper(io.BytesIO(body), encoding="utf-8-sig",
                              errors="replace", newline="")
    reader = csv.reader(stream)
    header = next((row for row in reader if any(cell.strip() for cell in row)), None)
    if header is None:
        return [], "the file has no rows"
    header = [cell.strip() for cell in header]
    payee_idx = _match_headers(header, _PAYEE_HEADERS)
    amount_idx = _match_headers(header, _AMOUNT_HEADERS)
    if payee_idx is None or amount_idx is None:
        return [], (f"no payee column ({payee_idx is None}) or amount column "
                    f"({amount_idx is None}) in the header")
    period_idx = _match_headers(header, _PERIOD_HEADERS)
    desc_idx = _match_headers(header, _DESCRIPTION_HEADERS)

    out: list[dict] = []
    for raw in reader:
        if not any(cell.strip() for cell in raw):
            continue
        if len(raw) <= max(payee_idx, amount_idx):
            continue
        payee = (raw[payee_idx] or "").strip()
        if not payee:
            continue
        amount_text = (raw[amount_idx] or "").strip()
        out.append({
            "payee": payee[:500],
            "amount": _to_number(amount_text),
            "amount_text": amount_text[:500] or None,
            "period": (raw[period_idx].strip()[:120]
                       if period_idx is not None and period_idx < len(raw)
                       and raw[period_idx].strip() else None),
            "description": (raw[desc_idx].strip()[:1000]
                            if desc_idx is not None and desc_idx < len(raw)
                            and raw[desc_idx].strip() else None),
        })
    return out, None


def _xlsx_header_and_rows(body: bytes) -> tuple[dict[str, str], Iterator[dict[str, str]]] | None:
    """Return the first non-empty header and a streaming view of the rest.

    Spend workbooks sometimes carry several sheets, but the old parser kept
    every sheet's rows before it started parsing. Inspecting one header first
    lets the second pass retain only the four columns this module stores while
    keeping the XML reader bounded to one sheet at a time.
    """
    names = sheet_names(body)
    first_sheet = None
    header: dict[str, str] | None = None
    for name in names:
        rows = iter_sheet_stream(body, name)
        try:
            candidate = next(rows)
        except StopIteration:
            rows.close()
            continue
        rows.close()
        first_sheet = name
        header = candidate
        break
    if first_sheet is None or header is None:
        return None

    wanted = _PAYEE_HEADERS + _AMOUNT_HEADERS + _PERIOD_HEADERS + _DESCRIPTION_HEADERS
    keep = {letter for letter, value in header.items()
            if _normalise_header(value) in wanted}

    def data_rows() -> Iterator[dict[str, str]]:
        skipped_header = False
        for name in names:
            for row in iter_sheet_stream(body, name, keep=keep):
                if name == first_sheet and not skipped_header:
                    skipped_header = True
                    continue
                yield row

    return header, data_rows()


def _parse_xlsx_ods(body: bytes, file_url: str, format_hint: str) -> tuple[list[dict], str | None]:
    """An XLSX or ODS spend file as line-item rows."""
    if format_hint == "xlsx":
        try:
            header_row = _xlsx_header_and_rows(body)
        except (XlsxError, OSError, ValueError) as exc:
            return [], f"could not read the workbook as xlsx: {exc}"
        if header_row is None:
            return [], "the workbook has no rows"
        header, rows = header_row
        columns = {_normalise_header(value): letter
                   for letter, value in header.items()}

        def column(synonyms: tuple[str, ...]) -> str | None:
            for synonym in synonyms:
                if _normalise_header(synonym) in columns:
                    return columns[_normalise_header(synonym)]
            return None

        payee_col = column(_PAYEE_HEADERS)
        amount_col = column(_AMOUNT_HEADERS)
        if payee_col is None or amount_col is None:
            return [], (f"no payee column ({payee_col is None}) or amount column "
                        f"({amount_col is None}) in the sheet header")
        period_col = column(_PERIOD_HEADERS)
        desc_col = column(_DESCRIPTION_HEADERS)
        out: list[dict] = []
        for raw in rows:
            payee = (raw.get(payee_col) or "").strip()
            if not payee:
                continue
            amount_text = (raw.get(amount_col) or "").strip()
            out.append({
                "payee": payee[:500],
                "amount": _to_number(amount_text),
                "amount_text": amount_text[:500] or None,
                "period": ((raw.get(period_col) or "").strip()[:120]
                           if period_col is not None and raw.get(period_col) else None),
                "description": ((raw.get(desc_col) or "").strip()[:1000]
                                if desc_col is not None and raw.get(desc_col) else None),
            })
        return out, None

    # ODS, through the same reader m13 uses.
    try:
        document = load_ods(io.BytesIO(body))
    except Exception as exc:  # noqa: BLE001 - the file is unreadable as ODS
        return [], f"could not read the workbook as ODS: {exc}"
    ods_rows: list[list[str]] = []
    for table in document.getElementsByType(Table):
        for row in table.getElementsByType(TableRow):
            cells = []
            for cell in row.getElementsByType(TableCell):
                text = "".join(p.firstChild.data or "" for p in
                               cell.getElementsByType(P)
                               if p.firstChild is not None)
                cells.append(text)
            if any(cell.strip() for cell in cells):
                ods_rows.append(cells)
    if not ods_rows:
        return [], "the workbook has no rows"
    header = ods_rows[0]
    payee_idx = _match_headers(header, _PAYEE_HEADERS)
    amount_idx = _match_headers(header, _AMOUNT_HEADERS)
    if payee_idx is None or amount_idx is None:
        return [], (f"no payee column ({payee_idx is None}) or amount column "
                    f"({amount_idx is None}) in the sheet header")
    period_idx = _match_headers(header, _PERIOD_HEADERS)
    desc_idx = _match_headers(header, _DESCRIPTION_HEADERS)
    out = []
    for raw in ods_rows[1:]:
        if len(raw) <= max(payee_idx, amount_idx):
            continue
        payee = (raw[payee_idx] or "").strip()
        if not payee:
            continue
        amount_text = (raw[amount_idx] or "").strip()
        out.append({
            "payee": payee[:500],
            "amount": _to_number(amount_text),
            "amount_text": amount_text[:500] or None,
            "period": (raw[period_idx].strip()[:120]
                       if period_idx is not None and period_idx < len(raw)
                       and raw[period_idx].strip() else None),
            "description": (raw[desc_idx].strip()[:1000]
                            if desc_idx is not None and desc_idx < len(raw)
                            and raw[desc_idx].strip() else None),
        })
    return out, None


def _provider_lookups(conn) -> dict[str, str]:
    """normalised payee name -> provider_key, from the tracked providers' own
    variants. The same exact-match discipline as m20: a name matches only
    when a provider's own variant normalises to it."""
    out: dict[str, str] = {}
    for provider_key, variants in SUPPLIER_NAME_VARIANTS.items():
        for variant in variants:
            normalised = _normalise_name(variant)
            if normalised:
                out.setdefault(normalised, provider_key)
    return out


def collect_authority(unit, client) -> SpendFindings:
    """One authority's entire fetch workload. Runs on a pool thread."""
    authority, site = unit
    findings = SpendFindings(ons_code=authority["ons_code"], name=authority["name"])

    if site is None or not site.base_url:
        findings.flag("authority_website_unknown", authority["ons_code"],
                      {"authority": authority["name"],
                       "note": "no verified base URL; the spend file cannot be "
                               "discovered"})
        return findings

    host = urlparse(site.base_url).netloc
    candidate_files: list[str] = []
    for path in SPEND_PATHS:
        url = urljoin(site.base_url, path)
        try:
            result = client.get(url)
        except RobotsDisallowed:
            findings.flag("council_spend_path_robots_disallowed", url,
                          {"authority": authority["name"]})
            continue
        if not result.ok:
            continue
        candidate_files.extend(_file_urls_on_page(
            result.body.decode("utf-8", errors="replace"), result.url, host))

    # Newest-first is unknowable without fetching, so dedupe and take the
    # first MAX_FILES_PER_AUTHORITY in discovery order.
    seen: set[str] = set()
    for file_url in candidate_files:
        if file_url in seen:
            continue
        seen.add(file_url)
        if len(findings.files) >= MAX_FILES_PER_AUTHORITY:
            break

        try:
            file_result = client.get(file_url)
        except RobotsDisallowed:
            findings.flag("council_spend_file_robots_disallowed", file_url,
                          {"authority": authority["name"]})
            continue
        if not file_result.ok:
            findings.flag("council_spend_file_unavailable", file_url,
                          {"authority": authority["name"],
                           "status": file_result.status_code})
            continue

        path = file_url.lower().split("?")[0]
        format_hint = ("xlsx" if path.endswith(".xlsx")
                       else "ods" if path.endswith(".ods")
                       else "csv")
        provenance = {
            "source_url": file_result.url,
            "retrieved_at": file_result.retrieved_at.isoformat(),
            "http_status": file_result.status_code,
            "source_system": SOURCE_SYSTEM,
            "payload_sha256": file_result.payload_sha256,
        }
        if path.endswith(".xls"):
            # Legacy binary XLS is not supported by the stdlib reader; a
            # council publishing only that is recorded as unreadable, not
            # skipped.
            findings.files.append({
                "authority_ons_code": authority["ons_code"],
                "file_url": file_url,
                "discovered_from": site.base_url,
                "file_format": "xls",
                "parse_status": "unreadable",
                "row_count": None,
                **provenance,
            })
            findings.parse_failures.append((
                "spend_file", file_url,
                "legacy .xls is not supported; the file was archived",
                file_result.url))
            findings.flag("council_spend_unreadable", file_url,
                          {"authority": authority["name"],
                           "note": "legacy .xls format, archived but not parsed"})
            continue

        if format_hint == "csv":
            lines, error = _parse_csv(file_result.body, file_url)
        else:
            lines, error = _parse_xlsx_ods(file_result.body, file_url, format_hint)

        if error:
            findings.files.append({
                "authority_ons_code": authority["ons_code"],
                "file_url": file_url,
                "discovered_from": site.base_url,
                "file_format": format_hint,
                "parse_status": "unreadable",
                "row_count": None,
                **provenance,
            })
            findings.parse_failures.append(
                ("spend_file", file_url, error, file_result.url))
            findings.flag("council_spend_unreadable", file_url,
                          {"authority": authority["name"], "note": error})
            continue

        findings.files.append({
            "authority_ons_code": authority["ons_code"],
            "file_url": file_url,
            "discovered_from": site.base_url,
            "file_format": format_hint,
            "parse_status": "parsed",
            "row_count": len(lines),
            **provenance,
        })
        for index, line in enumerate(lines):
            findings.lines.append({
                "authority_ons_code": authority["ons_code"],
                "file_url": file_url,
                "row_index": index,
                **line,
                **provenance,
            })

    if not findings.files and not findings.review_items:
        findings.flag("council_spend_none_found", authority["ons_code"],
                      {"authority": authority["name"],
                       "note": "no spend file discovered under the likely "
                               "transparency paths"})
    return findings


@register_module(
    "m24_council_spend",
    supports_since=False,
    depends_on=("m00_geography", "m15_foi"),
    depends_note="the spend file is discovered on the authority's own website, which m15 supplies for every authority",
    since_note="spend files publish the current period; rows carry retrieved_at rather than a source date",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m24_council_spend"
    conn = ctx.conn
    by_name = _provider_lookups(conn)

    authorities = conn.execute(
        "SELECT ons_code, name FROM authorities WHERE active_to IS NULL "
        "ORDER BY name").fetchall()
    if not authorities:
        log.info("council_spend.no_authorities", note="run m00_geography first")
        return

    if ctx.limit:
        authorities = authorities[:ctx.limit]

    units = [(authority, website_for(authority["ons_code"], conn))
             for authority in authorities]

    files_written = 0
    lines_written = 0
    workers = worker_count(ctx.settings, ctx.limit)

    stream = fetch_in_parallel(units, collect_authority,
                               source_system=SOURCE_SYSTEM, settings=ctx.settings,
                               max_workers=workers, cache_conn=conn)
    for outcome in ctx.track(stream, "councils", total=len(units)):
        authority, _site = outcome.unit
        if not outcome.ok:
            db.record_review_item(
                conn, module_name, "council_spend_collection_failed",
                authority["ons_code"],
                json.dumps({"authority": authority["name"],
                             "error": f"{type(outcome.error).__name__}: {outcome.error}"}))
            if not ctx.dry_run:
                conn.commit()
            continue

        findings = outcome.value
        for item_type, raw_value, context in findings.review_items:
            db.record_review_item(conn, module_name, item_type, raw_value,
                                  json.dumps(context))
        for failure_field, raw, reason, source_url in findings.parse_failures:
            db.record_parse_failure(conn, module_name, failure_field, raw, reason,
                                    source_url=source_url)

        for file_row in findings.files:
            db.upsert(conn, "council_spend_files", file_row,
                      natural_key=["authority_ons_code", "file_url"])
            files_written += 1

        for line in findings.lines:
            provider_key = by_name.get(_normalise_name(line["payee"]))
            db.upsert(conn, "council_spend", {
                **line,
                "provider_key": provider_key,
            }, natural_key=["authority_ons_code", "file_url", "row_index"])
            lines_written += 1

        if not ctx.dry_run:
            conn.commit()

    log.info("council_spend.run_complete", files=files_written,
              lines=lines_written)
