"""scrapy.md Phase 2 pilot for ``m34_icb_board_papers``.

This is deliberately an adapter-only pilot.  It reuses m34's existing crawl
contract and discovery rules, but supplies the fetched ``TransportResult``
objects from a bounded Scrapy spider.  The result is returned to the caller
for comparison; this module has no database access and is not registered as a
production module.  Until the comparison is reviewed, m34's HTTPX path stays
the only path that writes evidence.
"""
from __future__ import annotations

import multiprocessing
from urllib.parse import urljoin, urlparse

import structlog

from pipeline.config import Settings
from pipeline.modules import m34_icb_board_papers as m34
from pipeline.transports.scrapy_transport import (
    ScrapyDisabled,
    ScrapyNotInstalled,
    available,
    drain_subprocess,
    transport_result_from_failure,
    transport_result_from_response,
)
from pipeline.transports.types import FailureClass

log = structlog.get_logger()


def fetch_m34_pilot(
    icb_name: str,
    seed_url: str,
    *,
    from_registry: bool,
    since: str | None = None,
    settings: Settings,
    guard_destination: bool = False,
    resolver=None,
) -> m34.IcbCrawl:
    """Run one bounded m34 crawl through Scrapy and return its fetch result.

    ``from_registry`` and ``since`` have the same meaning as the arguments to
    ``m34.crawl_icb``.  The child process only fetches and archives bytes; it
    never parses documents or writes a row.  A second invocation is safe
    because the Scrapy reactor lives only for the child process.
    """
    if not settings.scrapy_enabled:
        raise ScrapyDisabled(
            "SCRAPY_ENABLED is False. Set it explicitly (and install "
            "`uv sync --extra scrapy`) before calling fetch_m34_pilot()."
        )
    if not available():
        raise ScrapyNotInstalled(
            "The `scrapy` extra is not installed. Run `uv sync --extra scrapy`."
        )

    ctx = multiprocessing.get_context("spawn")
    queue: multiprocessing.Queue = ctx.Queue()
    process = ctx.Process(
        target=_run_pilot_crawl,
        args=(queue, icb_name, seed_url, from_registry, since, settings,
              guard_destination, resolver),
    )
    log.info("m34_pilot.starting", icb_name=icb_name, seed_url=seed_url)
    process.start()
    items, timed_out = drain_subprocess(
        process, queue, settings.scrapy_runner_timeout_seconds)

    if items:
        crawl = items[-1]
    else:
        crawl = m34.IcbCrawl(
            icb_name=icb_name,
            seed_url=seed_url,
            from_registry=from_registry,
            unreachable=not timed_out,
        )
        crawl.review_items.append(
            ("icb_scrapy_pilot_timeout" if timed_out else "icb_scrapy_pilot_failed",
             seed_url, {"timeout_seconds": settings.scrapy_runner_timeout_seconds,
                         "exit_code": process.exitcode}))

    log.info(
        "m34_pilot.finished", icb_name=icb_name, seed_url=seed_url,
        pages_fetched=crawl.pages_fetched, documents=len(crawl.candidates),
        robots_blocked=crawl.robots_blocked, unreachable=crawl.unreachable,
    )
    return crawl


def _run_pilot_crawl(queue, icb_name: str, seed_url: str, from_registry: bool,
                     since: str | None, settings: Settings,
                     guard_destination: bool, resolver) -> None:
    """Start the two-phase spider in a fresh interpreter."""
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
                "pipeline.transports.scrapy_transport.ProvenanceArchiveMiddleware": 500,
            },
            "PIPELINE_SETTINGS": settings,
            "PIPELINE_GUARD_DESTINATION": guard_destination,
            "PIPELINE_RESOLVER": resolver,
        }
        process = CrawlerProcess(settings=crawler_settings, install_root_handler=False)
        process.crawl(
            _spider_class(), icb_name=icb_name, seed_url=seed_url,
            from_registry=from_registry, since=since, result_queue=queue,
        )
        process.start()
    except Exception as exc:  # noqa: BLE001 - report an explicit crawl result
        queue.put(m34.IcbCrawl(
            icb_name=icb_name, seed_url=seed_url, from_registry=from_registry,
            review_items=(("icb_scrapy_pilot_failed", seed_url,
                           {"error": f"{type(exc).__name__}: {exc}"}),),
        ))


def _spider_class():
    """Build the spider lazily so importing the pilot does not require Scrapy."""
    import scrapy
    from scrapy import signals
    from scrapy.exceptions import DontCloseSpider

    class _IcbPilotSpider(scrapy.Spider):
        name = "pipeline_m34_icb_board_papers_pilot"

        def __init__(self, icb_name, seed_url, from_registry, since,
                     result_queue, **kwargs):
            super().__init__(**kwargs)
            self.icb_name = icb_name
            self.seed_url = seed_url
            self.from_registry = bool(from_registry)
            self.since = since
            self.result_queue = result_queue
            parsed_seed = urlparse(seed_url)
            self.origin = f"{parsed_seed.scheme}://{parsed_seed.netloc}"
            self.host = parsed_seed.netloc
            self.seed_path = parsed_seed.path or "/"
            paths = ([self.seed_path, *m34.MEETING_PATHS]
                     if self.from_registry else list(m34.MEETING_PATHS))
            self.initial_paths = list(dict.fromkeys(paths))
            self.initial_order = {path: i for i, path in enumerate(self.initial_paths)}
            self.source_system = m34.SOURCE_SYSTEM
            self.module = "m34_pilot"

            self.pages_fetched = 0
            self.index_status = 0
            self.index_sha = ""
            self.reached_anything = False
            self.robots_blocked = False
            self.resolved_index = None
            self.resolved_index_order = None
            self.fetched_pages: set[str] = set()
            self.subpages: list[str] = []
            # URL -> (link text, from-index, discovery method, page order).
            # Scrapy completes requests concurrently, so the page order is
            # carried explicitly to retain m34's deterministic path order.
            self.candidate_links: dict[str, tuple[str, bool, str, int]] = {}
            self.candidates: list[tuple] = []
            self.document_order: dict[str, int] = {}
            self.review_items: list[tuple] = []
            self._documents_issued = False

        @classmethod
        def from_crawler(cls, crawler, *args, **kwargs):
            spider = super().from_crawler(crawler, *args, **kwargs)
            crawler.signals.connect(spider._spider_idle, signal=signals.spider_idle)
            return spider

        def _page_request(self, url: str, *, path: str, path_order: int):
            return scrapy.Request(
                url, callback=self.parse_page, errback=self.page_failed,
                dont_filter=True,
                meta={"handle_httpstatus_all": True,
                      "pipeline_requested_url": url, "path": path,
                      "path_order": path_order},
            )

        def _initial_requests(self):
            for path in self.initial_paths:
                if self.pages_fetched >= m34.MAX_PAGES_PER_ICB:
                    break
                url = urljoin(self.origin + "/", path.lstrip("/"))
                yield self._page_request(
                    url, path=path, path_order=self.initial_order[path])

        async def start(self):
            # Scrapy 2.13 uses the async start hook; retaining the synchronous
            # hook below keeps the pilot compatible with the project's 2.11
            # minimum as well.
            for request in self._initial_requests():
                yield request

        def start_requests(self):
            yield from self._initial_requests()

        def parse_page(self, response):
            if self.pages_fetched >= m34.MAX_PAGES_PER_ICB:
                return
            result = transport_result_from_response(
                response, transport="scrapy", source_system=self.source_system,
                module=self.module)
            if not result.ok:
                return

            self.reached_anything = True
            self.pages_fetched += 1
            page_url = (result.final_url or result.requested_url).split("#")[0]
            self.fetched_pages.add(page_url)
            path = response.meta.get("path", "")
            path_order = response.meta.get("path_order", len(self.initial_paths))
            if path in ("/", ""):
                self.index_status = result.status_code or 0
                self.index_sha = result.payload_sha256
                landed = urlparse(result.final_url or result.requested_url).netloc
                if landed:
                    self.host = landed
            is_subpage = path == "subpage_hop"
            is_index = (is_subpage
                        or (path == self.seed_path and self.from_registry)
                        or bool(m34.GOVERNANCE_VOCAB.search(path)))
            if (is_index and (self.resolved_index_order is None
                              or path_order < self.resolved_index_order)):
                self.resolved_index = page_url
                self.resolved_index_order = path_order

            html_text = result.body.decode("utf-8", "replace")
            for href, raw_text in m34._LINK_RE.findall(html_text):
                url = urljoin(page_url, href.strip()).split("#")[0]
                if m34._host_key(urlparse(url).netloc) != m34._host_key(self.host):
                    continue
                url_path = url.lower().split("?")[0]
                text = m34._link_text(raw_text)
                if url_path.endswith(m34.m28._DOCUMENT_EXTENSIONS):
                    method = "subpage_hop" if is_subpage else f"path_crawl:{path}"
                    previous = self.candidate_links.get(url)
                    if previous is None:
                        self.candidate_links[url] = (text, is_index, method, path_order)
                    else:
                        old_text, old_index, old_method, old_order = previous
                        if path_order < old_order:
                            old_text, old_method, old_order = text, method, path_order
                        self.candidate_links[url] = (
                            old_text or text, old_index or is_index,
                            old_method, old_order)
                elif (m34.GOVERNANCE_VOCAB.search(f"{url} {text}")
                      and url not in self.fetched_pages
                      and url not in self.subpages):
                    self.subpages.append(url)
                    if len(self.subpages) <= m34.MAX_SUBPAGES_PER_ICB:
                        yield self._page_request(
                            url, path="subpage_hop",
                            path_order=len(self.initial_paths) + len(self.subpages) - 1)

        def page_failed(self, failure):
            request = failure.request
            url = request.meta.get("pipeline_requested_url", request.url)
            if request.meta.get("failure_class") is FailureClass.ROBOTS_DISALLOWED:
                self.review_items.append(
                    ("icb_paper_robots_disallowed", url, {"icb": self.icb_name}))
                self.robots_blocked = True

        def _spider_idle(self, spider):
            if self._documents_issued:
                return
            self._documents_issued = True
            if not self.reached_anything and not self.robots_blocked:
                return
            ordered_candidates = sorted(
                self.candidate_links.items(), key=lambda item: item[1][3])
            for count, (doc_url, (link_text, from_index, method, _path_order)) in enumerate(
                    ordered_candidates):
                if count >= m34.MAX_DOCS_PER_ICB:
                    self.review_items.append(
                        ("icb_doc_ceiling_reached", self.icb_name,
                         {"icb": self.icb_name, "ceiling": m34.MAX_DOCS_PER_ICB,
                          "note": "crawl truncated; raise MAX_DOCS_PER_ICB or "
                                  "tighten MEETING_PATHS"}))
                    break
                if (m34._before_since(
                        self.since, m34.parse_meeting_date(link_text)
                        or m34.parse_meeting_date(doc_url))):
                    continue
                self.document_order[doc_url] = count
                yield_request = scrapy.Request(
                    doc_url, callback=self.parse_document,
                    errback=self.document_failed, dont_filter=True,
                    meta={"handle_httpstatus_all": True,
                          "pipeline_requested_url": doc_url,
                          "link_text": link_text, "from_index": from_index,
                          "discovery_method": method},
                )
                self.crawler.engine.crawl(yield_request)
            raise DontCloseSpider

        def parse_document(self, response):
            result = transport_result_from_response(
                response, transport="scrapy", source_system=self.source_system,
                module=self.module)
            self.candidates.append((
                result, response.meta.get("link_text", ""),
                bool(response.meta.get("from_index")),
                response.meta.get("discovery_method", ""),
            ))

        def document_failed(self, failure):
            request = failure.request
            doc_url = request.meta.get("pipeline_requested_url", request.url)
            if request.meta.get("failure_class") is FailureClass.ROBOTS_DISALLOWED:
                self.review_items.append(
                    ("icb_paper_robots_disallowed", doc_url,
                     {"icb": self.icb_name}))
                return
            result = transport_result_from_failure(
                failure, transport="scrapy", source_system=self.source_system,
                module=self.module)
            self.review_items.append(
                ("icb_doc_unavailable", doc_url,
                 {"icb": self.icb_name, "status": result.status_code}))

        def closed(self, reason):
            if not self.reached_anything and not self.robots_blocked:
                unreachable = True
            else:
                unreachable = False
            board_url = self.resolved_index or self.seed_url
            board_url_source = (
                "registry" if self.from_registry
                and self.resolved_index in (None, self.seed_url)
                else "path_probe" if self.resolved_index else "directory_link")
            self.result_queue.put(m34.IcbCrawl(
                icb_name=self.icb_name, seed_url=self.seed_url,
                from_registry=self.from_registry, board_url=board_url,
                board_url_source=board_url_source, pages_fetched=self.pages_fetched,
                index_status=self.index_status, index_sha=self.index_sha,
                ceiling_reached=(len(self.candidate_links) > m34.MAX_DOCS_PER_ICB),
                candidates=sorted(
                    self.candidates,
                    key=lambda item: self.document_order.get(
                        item[0].requested_url, len(self.document_order))),
                review_items=self.review_items,
                robots_blocked=self.robots_blocked, unreachable=unreachable,
            ))

    return _IcbPilotSpider
