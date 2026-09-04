"""scrapy.md Phase 2 pilot: `m32_sab_site_reviews` on the Scrapy transport.

Ports the *fetching* half of `pipeline.modules.m32_sab_site_reviews` — the
bounded per-board crawl (`crawl_board`) — onto Scrapy's scheduler, reusing
the existing module's discovery constants and page parsers directly rather
than re-implementing them:

  * `SAR_PATHS`, `MAX_SUBPAGES_PER_SAB`, `MAX_PAGES_PER_SAB`,
    `MAX_DOCS_PER_SAB` — the same bounded crawl shape.
  * `sar_links_on_page`, `sar_subpages_on_page` — the same link/subpage
    extraction, called with the same arguments `crawl_board` calls them
    with.
  * `classify_document` — the same hybrid-ingest gate `run()` uses, applied
    identically here (see `classify_pilot_documents` below).

**What is deliberately different, and why.** `crawl_board` fetches
sequentially through one `PipelineHTTPClient`, discovering pages and then
documents in one pass. This spider expresses the same two phases —
discover every page and subpage, then fetch the deduplicated document
set — through Scrapy's `spider_idle` signal: the homepage/`SAR_PATHS`/
subpage requests are scheduled first, and once the scheduler is idle (no
page requests left, meaning discovery is complete) the handler schedules
the deduplicated document requests and raises `DontCloseSpider` to keep the
spider open for them. This is the standard two-phase pattern that signal
exists for, not a bespoke workaround.

**Network vs. classification, and why they are split across the process
boundary.** This spider runs inside `fetch_m32_pilot`'s spawned subprocess
(see `pipeline.transports.scrapy_transport`'s module docstring for why
every Scrapy crawl in this package runs in one) and only fetches — it never
extracts PDF/DOCX text, never calls `classify_document`, and never touches
`pipeline.db`. Body-text extraction and classification (`classify_pilot_documents`)
run back in the parent process afterwards: both are pure library work with no
network dependency, and keeping them there means they need no subprocess
plumbing and can be driven directly (and monkeypatched directly) from a test,
the same way `pipeline.modules.m28_sar_reports`'s own PDF reading is tested
today.

**No database access anywhere in this module.** A pilot's job is to produce
a result comparable with `crawl_board`'s, not to write evidence — see
`pipeline/transports/pilots/__init__.py`. `classify_pilot_documents` takes
`existing_sha` (the byte-identical-to-the-library check `run()` makes
against `sar_documents`) and `sab_index` (the board-name resolution index
`run()` builds from `safeguarding_adults_boards`) as plain arguments so a
caller that *does* have a connection can supply them without this module
needing one itself.

**OCR is out of scope for the pilot.** `_read_pdf_text` reads a PDF's text
layer only; `pipeline.modules.m28_sar_reports._read_pdf`'s OCR fallback for
scanned PDFs is not reproduced here, so a scanned SAR pilots as "no body
text" regardless of `OCR_ENABLED`. That only affects classification, not
discovery: the document is still found and fetched, just without text to
resolve a board name from — the same review-queue-bound outcome a person
would reach for it either way once `from_index`/`strong_link` cannot be
paired with a resolved name.
"""
from __future__ import annotations

import multiprocessing
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import structlog

from pipeline.config import Settings
from pipeline.modules import m28_sar_reports as m28
from pipeline.modules import m32_sab_site_reviews as m32
from pipeline.transports.scrapy_transport import (
    ScrapyDisabled,
    ScrapyNotInstalled,
    available,
    drain_subprocess,
    transport_result_from_failure,
    transport_result_from_response,
)
from pipeline.transports.types import FailureClass, TransportResult

log = structlog.get_logger()

SOURCE_SYSTEM = "sab_website_pilot"


@dataclass(frozen=True)
class PilotFetchRecord:
    """One candidate document as the subprocess fetched it. `link_text` and
    `from_index` are `crawl_board`'s own per-candidate context, carried
    alongside the fetch so `classify_pilot_documents` has everything
    `classify_document` needs.
    """

    result: TransportResult
    link_text: str
    from_index: bool


@dataclass(frozen=True)
class PilotCrawl:
    """What one board's Scrapy pilot crawl produced — the same shape as
    `m32_sab_site_reviews.BoardCrawl`, so the two are diffable field for
    field in a parity test.
    """

    sab_name: str
    base_url: str
    pages_fetched: int = 0
    homepage_status: int = 0
    homepage_sha256: str = ""
    documents: tuple[PilotFetchRecord, ...] = ()
    review_items: tuple[tuple[str, str, dict], ...] = ()
    robots_blocked: bool = False
    unreachable: bool = False
    timed_out: bool = False


@dataclass(frozen=True)
class PilotDocument:
    """One document after classification — `PilotFetchRecord` plus what
    `classify_document` decided, and the body-text/archive facts a
    comparison against `sar_documents`/`review_queue` needs.
    """

    document_url: str
    link_text: str
    from_index: bool
    status_code: int | None
    payload_sha256: str
    raw_archive_ref: str | None
    has_body_text: bool
    outcome: str  # "ingest" | "candidate" | "board_mismatch" | "duplicate_of_library" | "unavailable" | "ext_unsupported"
    reason: str | None = None
    text_board: str | None = None


def fetch_m32_pilot(
    sab_name: str,
    base_url: str,
    *,
    settings: Settings,
    guard_destination: bool = False,
    resolver=None,
) -> PilotCrawl:
    """Runs the Scrapy pilot crawl for one board and returns what it found —
    the network half only; call `classify_pilot_documents` on the result to
    get `crawl_board`'s classified outcome for each document.

    Same gates as `pipeline.transports.scrapy_transport.fetch_via_scrapy`:
    refuses to run unless `settings.scrapy_enabled` and the `scrapy` extra
    are both present, and runs the crawl in a spawned subprocess for the
    same reactor-restart reason.
    """
    if not settings.scrapy_enabled:
        raise ScrapyDisabled(
            "SCRAPY_ENABLED is False. Set it explicitly (and install "
            "`uv sync --extra scrapy`) before calling fetch_m32_pilot()."
        )
    if not available():
        raise ScrapyNotInstalled(
            "The `scrapy` extra is not installed. Run `uv sync --extra scrapy`."
        )

    ctx = multiprocessing.get_context("spawn")
    queue: multiprocessing.Queue = ctx.Queue()
    process = ctx.Process(
        target=_run_pilot_crawl,
        args=(queue, sab_name, base_url, settings, guard_destination, resolver),
    )
    log.info("m32_pilot.starting", sab_name=sab_name, base_url=base_url)
    process.start()
    items, timed_out = drain_subprocess(process, queue, settings.scrapy_runner_timeout_seconds)

    if timed_out:
        log.warning("m32_pilot.timeout", sab_name=sab_name, base_url=base_url,
                     timeout=settings.scrapy_runner_timeout_seconds)
    if not items:
        crawl = PilotCrawl(sab_name=sab_name, base_url=base_url, timed_out=timed_out,
                            unreachable=not timed_out)
    else:
        crawl = items[-1]

    log.info("m32_pilot.finished", sab_name=sab_name, base_url=base_url,
              pages_fetched=crawl.pages_fetched, documents=len(crawl.documents),
              robots_blocked=crawl.robots_blocked, unreachable=crawl.unreachable)
    return crawl


def classify_pilot_documents(
    crawl: PilotCrawl,
    *,
    settings: Settings,
    sab_name: str,
    sab_index: dict | None = None,
    existing_sha: frozenset[str] = frozenset(),
) -> list[PilotDocument]:
    """`classify_document` applied to every document `fetch_m32_pilot`
    fetched — pure and DB-free, run in the parent process (or a test)
    rather than inside the crawl subprocess. See the module docstring for
    why the split.
    """
    sab_index = sab_index or {}
    documents: list[PilotDocument] = []
    for record in crawl.documents:
        fetched = record.result
        document_url = fetched.final_url or fetched.requested_url
        if not fetched.ok:
            documents.append(PilotDocument(
                document_url=document_url, link_text=record.link_text,
                from_index=record.from_index, status_code=fetched.status_code,
                payload_sha256=fetched.payload_sha256, raw_archive_ref=fetched.raw_archive_ref,
                has_body_text=False, outcome="unavailable",
                reason=f"{fetched.failure_class.value}: {fetched.failure_detail}"))
            continue

        ext = m28.document_extension(document_url)
        if ext is None:
            documents.append(PilotDocument(
                document_url=document_url, link_text=record.link_text,
                from_index=record.from_index, status_code=fetched.status_code,
                payload_sha256=fetched.payload_sha256, raw_archive_ref=fetched.raw_archive_ref,
                has_body_text=False, outcome="ext_unsupported"))
            continue

        body_text, _source = _read_body_text(
            settings, ext, document_url, fetched.body, fetched.payload_sha256)
        duplicate_of_library = fetched.payload_sha256 in existing_sha
        classification = m32.classify_document(
            document_url=document_url, link_text=record.link_text, body_text=body_text,
            from_index=record.from_index, sab_name=sab_name, sab_index=sab_index,
            duplicate_of_library=duplicate_of_library)

        documents.append(PilotDocument(
            document_url=document_url, link_text=record.link_text,
            from_index=record.from_index, status_code=fetched.status_code,
            payload_sha256=fetched.payload_sha256, raw_archive_ref=fetched.raw_archive_ref,
            has_body_text=bool(body_text), outcome=classification.outcome,
            reason=classification.reason, text_board=classification.text_board))
    return documents


def _read_body_text(settings: Settings, ext: str, document_url: str, body: bytes,
                     sha256: str) -> tuple[str | None, str | None]:
    """`m28_sar_reports._read_pdf`/`_read_docx` minus the database (no
    `parse_failures` row on a read failure — there is nothing to persist a
    pilot's failures against) and minus OCR (see the module docstring).
    `sha256` must be `payload_sha256` from the same fetch — `pdftext.page_texts`
    uses it as a cache key and requires it be the exact digest of `body`.
    """
    if ext == ".pdf":
        try:
            pages = m28.pdftext.page_texts(settings, SOURCE_SYSTEM, sha256, body)
        except Exception:
            return None, None
        text = "\n".join(page for page in pages if page).strip()
        return (text, "pdf") if text else (None, None)
    if ext == ".docx":
        from pipeline.documents.inspect import DOCX_MIME
        from pipeline.documents.parsers import DOCXParser

        try:
            parsed = DOCXParser().parse(body, DOCX_MIME)
        except Exception:
            return None, None
        text = parsed.text.strip()
        return (text, "docx") if text else (None, None)
    return None, None


def _run_pilot_crawl(queue, sab_name: str, base_url: str, settings: Settings,
                      guard_destination: bool, resolver) -> None:
    """Runs inside the spawned subprocess — a fresh interpreter, same as
    `scrapy_transport._run_bounded_crawl`.
    """
    try:
        from scrapy.crawler import CrawlerProcess

        crawler_settings = {
            "LOG_ENABLED": False,
            "TELNETCONSOLE_ENABLED": False,
            "ROBOTSTXT_OBEY": False,
            "COOKIES_ENABLED": False,
            "RETRY_ENABLED": False,
            "AUTOTHROTTLE_ENABLED": False,
            "USER_AGENT": settings.user_agent,
            "DOWNLOAD_TIMEOUT": settings.scrapy_download_timeout_seconds,
            "DOWNLOAD_DELAY": settings.scrapy_download_delay_seconds,
            "CONCURRENT_REQUESTS_PER_DOMAIN": settings.scrapy_concurrent_requests_per_domain,
            "DOWNLOADER_MIDDLEWARES": {
                "pipeline.transports.scrapy_transport.StructuredLoggingMiddleware": 100,
                "pipeline.transports.scrapy_transport.RobotsComplianceMiddleware": 200,
                "pipeline.transports.scrapy_transport.DestinationGuardMiddleware": 250,
                "pipeline.transports.scrapy_transport.RetryWithBackoffMiddleware": 950,
                "pipeline.transports.scrapy_transport.ProvenanceArchiveMiddleware": 900,
            },
            "PIPELINE_SETTINGS": settings,
            "PIPELINE_GUARD_DESTINATION": guard_destination,
            "PIPELINE_RESOLVER": resolver,
        }
        process = CrawlerProcess(settings=crawler_settings, install_root_handler=False)
        process.crawl(_spider_class(), sab_name=sab_name, base_url=base_url, result_queue=queue)
        process.start()
    except Exception as exc:  # noqa: BLE001 - reported, not swallowed
        queue.put(PilotCrawl(sab_name=sab_name, base_url=base_url,
                              review_items=(("m32_pilot_crawl_failed", base_url,
                                             {"error": f"{type(exc).__name__}: {exc}"}),)))


def _spider_class():
    """Builds the pilot spider class — see `scrapy_transport._spider_class`
    for why this is a function (keeps `scrapy.Spider` out of this module's
    top level, so it stays importable without the `scrapy` extra).
    """
    import scrapy
    from scrapy import signals
    from scrapy.exceptions import DontCloseSpider

    class _SabSitePilotSpider(scrapy.Spider):
        name = "pipeline_m32_sab_site_pilot"

        def __init__(self, sab_name, base_url, result_queue, **kwargs):
            super().__init__(**kwargs)
            self.sab_name = sab_name
            self.base_url = base_url
            self.result_queue = result_queue
            self.host = urlparse(base_url).netloc
            self.source_system = SOURCE_SYSTEM
            self.module = "m32_pilot"

            self.pages_fetched = 0
            self.homepage_status = 0
            self.homepage_sha256 = ""
            self.reached_anything = False
            self.robots_blocked = False
            self.fetched_pages: set[str] = set()
            self.subpages_seen: set[str] = set()
            # doc_url -> (link_text, from_index) — the same merge rule
            # crawl_board applies: first link text wins, from_index is
            # sticky once any page vouches for it.
            self.candidate_urls: dict[str, tuple[str, bool]] = {}
            self.documents: list[PilotFetchRecord] = []
            self.review_items: list[tuple[str, str, dict]] = []
            self._docs_issued = False

        @classmethod
        def from_crawler(cls, crawler, *args, **kwargs):
            spider = super().from_crawler(crawler, *args, **kwargs)
            crawler.signals.connect(spider._spider_idle, signal=signals.spider_idle)
            return spider

        # --- phase 1: page/subpage discovery --------------------------------

        def _page_request(self, url: str, *, is_index_hint: bool, is_homepage: bool):
            return scrapy.Request(
                url, callback=self.parse_page, errback=self.page_failed, dont_filter=True,
                priority=1000 if is_homepage else 0,
                meta={"handle_httpstatus_all": True, "pipeline_requested_url": url,
                      "is_index_hint": is_index_hint, "is_homepage": is_homepage},
            )

        async def start(self):
            for path in m32.SAR_PATHS[:m32.MAX_PAGES_PER_SAB]:
                url = urljoin(self.base_url, path)
                yield self._page_request(
                    url, is_index_hint=bool(m32._SAR_LINK_VOCAB.search(path)),
                    is_homepage=(path == "/"))

        def start_requests(self):
            # Scrapy < 2.13 compatibility path, as in _BoundedFetchSpider.
            for path in m32.SAR_PATHS[:m32.MAX_PAGES_PER_SAB]:
                url = urljoin(self.base_url, path)
                yield self._page_request(
                    url, is_index_hint=bool(m32._SAR_LINK_VOCAB.search(path)),
                    is_homepage=(path == "/"))

        def parse_page(self, response):
            if self.pages_fetched >= m32.MAX_PAGES_PER_SAB:
                return
            result = transport_result_from_response(
                response, transport="scrapy", source_system=self.source_system,
                module=self.module)
            if not result.ok:
                return  # crawl_board: `if not result.ok: continue` — no review item

            self.reached_anything = True
            self.pages_fetched += 1
            page_url = (result.final_url or result.requested_url).split("#")[0]
            self.fetched_pages.add(page_url)

            if response.meta.get("is_homepage"):
                self.homepage_status = result.status_code or 0
                self.homepage_sha256 = result.payload_sha256
                landed = urlparse(result.final_url or "").netloc
                if landed:
                    self.host = landed

            is_index = bool(response.meta.get("is_index_hint"))
            html_text = result.body.decode("utf-8", "replace")
            for doc_url, link_text in m32.sar_links_on_page(html_text, page_url, self.host, is_index):
                text, idx = self.candidate_urls.get(doc_url, (link_text, False))
                self.candidate_urls[doc_url] = (text or link_text, idx or is_index)

            if len(self.subpages_seen) >= m32.MAX_SUBPAGES_PER_SAB:
                return
            for sub in m32.sar_subpages_on_page(html_text, page_url, self.host):
                if len(self.subpages_seen) >= m32.MAX_SUBPAGES_PER_SAB:
                    break
                if sub in self.subpages_seen or sub.split("#")[0] in self.fetched_pages:
                    continue
                self.subpages_seen.add(sub)
                yield self._page_request(sub, is_index_hint=True, is_homepage=False)

        def page_failed(self, failure):
            request = failure.request
            url = request.meta.get("pipeline_requested_url", request.url)
            if request.meta.get("failure_class") is FailureClass.ROBOTS_DISALLOWED:
                self.review_items.append(
                    ("sab_site_robots_disallowed", url, {"sab_name": self.sab_name}))
                self.robots_blocked = True
            # Any other page failure: crawl_board silently continues past it.

        # --- phase 2: fetch the deduplicated document set -------------------

        def _spider_idle(self, spider):
            if self._docs_issued:
                return
            self._docs_issued = True
            if not self.reached_anything and not self.robots_blocked:
                return  # PilotCrawl.unreachable is set by the caller from this
            requests = list(self._document_requests())
            if not requests:
                return
            for request in requests:
                self.crawler.engine.crawl(request)
            raise DontCloseSpider

        def _document_requests(self):
            for count, (doc_url, (link_text, from_index)) in enumerate(self.candidate_urls.items()):
                if count >= m32.MAX_DOCS_PER_SAB:
                    break
                yield scrapy.Request(
                    doc_url, callback=self.parse_document, errback=self.document_failed,
                    dont_filter=True,
                    meta={"handle_httpstatus_all": True, "pipeline_requested_url": doc_url,
                          "link_text": link_text, "from_index": from_index},
                )

        def parse_document(self, response):
            result = transport_result_from_response(
                response, transport="scrapy", source_system=self.source_system,
                module=self.module)
            self.documents.append(PilotFetchRecord(
                result=result, link_text=response.meta.get("link_text", ""),
                from_index=bool(response.meta.get("from_index"))))

        def document_failed(self, failure):
            request = failure.request
            doc_url = request.meta.get("pipeline_requested_url", request.url)
            if request.meta.get("failure_class") is FailureClass.ROBOTS_DISALLOWED:
                self.review_items.append(
                    ("sab_site_robots_disallowed", doc_url, {"sab_name": self.sab_name}))
            else:
                result = transport_result_from_failure(
                    failure, transport="scrapy", source_system=self.source_system,
                    module=self.module)
                self.review_items.append((
                    "sab_site_doc_unavailable", doc_url,
                    {"sab_name": self.sab_name, "status": result.status_code}))

        def closed(self, reason):
            self.result_queue.put(PilotCrawl(
                sab_name=self.sab_name, base_url=self.base_url,
                pages_fetched=self.pages_fetched, homepage_status=self.homepage_status,
                homepage_sha256=self.homepage_sha256, documents=tuple(self.documents),
                review_items=tuple(self.review_items), robots_blocked=self.robots_blocked,
                unreachable=not self.reached_anything and not self.robots_blocked,
            ))

    return _SabSitePilotSpider
