"""Adapter-only Scrapy pilot for ``m28_sar_reports``.

The national SAR library is a small number of index pages followed by a
large, deduplicated document set. This adapter keeps that two-phase shape,
reuses m28's HTML and URL parsers, and returns immutable fetch/parser results
for comparison. It does not read or write the database and does not replace
the HTTPX production module.
"""
from __future__ import annotations

import multiprocessing
from dataclasses import dataclass, replace
from typing import Sequence

import structlog

from pipeline.config import Settings
from pipeline.modules import m28_sar_reports as m28
from pipeline.transports.scrapy_transport import (
    ScrapyDisabled,
    ScrapyNotInstalled,
    _crawler_settings,
    available,
    drain_subprocess,
    transport_result_from_failure,
    transport_result_from_response,
)
from pipeline.transports.types import FailureClass, TransportResult

log = structlog.get_logger()

SOURCE_SYSTEM = "national_sar_library_pilot"


@dataclass(frozen=True)
class PilotIndexPage:
    page_url: str
    result: TransportResult
    document_links: tuple[dict, ...] = ()


@dataclass(frozen=True)
class PilotDocument:
    title: str
    library_year: int | None
    result: TransportResult


@dataclass(frozen=True)
class PilotCrawl:
    index_pages: tuple[PilotIndexPage, ...] = ()
    documents: tuple[PilotDocument, ...] = ()
    review_items: tuple[tuple[str, str, dict], ...] = ()
    robots_blocked: bool = False
    unreachable: bool = False


def fetch_m28_pilot(
    index_urls: Sequence[str] | None = None,
    *,
    settings: Settings,
    retain_bodies: bool = True,
    guard_destination: bool = False,
    resolver=None,
) -> PilotCrawl:
    """Fetch the m28 library indexes and their linked documents via Scrapy."""
    if not settings.scrapy_enabled:
        raise ScrapyDisabled("SCRAPY_ENABLED is False; enable it explicitly before running the m28 pilot.")
    if not available():
        raise ScrapyNotInstalled("The `scrapy` extra is not installed. Run `uv sync --extra scrapy`.")

    selected = list(index_urls or (
        m28.LIBRARY_URL, m28.SCIE_LIBRARY_URL, m28.SAB_DIRECTORY_URL,
    ))
    ctx = multiprocessing.get_context("spawn")
    queue: multiprocessing.Queue = ctx.Queue()
    process = ctx.Process(
        target=_run_pilot_crawl,
        args=(queue, selected, settings, retain_bodies, guard_destination, resolver),
    )
    log.info("m28_pilot.starting", index_pages=len(selected))
    process.start()
    items, timed_out = drain_subprocess(
        process, queue, settings.scrapy_runner_timeout_seconds)
    if items:
        crawl = items[-1]
    else:
        crawl = PilotCrawl(review_items=(
            ("m28_scrapy_pilot_timeout" if timed_out else "m28_scrapy_pilot_failed",
             "national_sar_library",
             {"timeout_seconds": settings.scrapy_runner_timeout_seconds,
              "exit_code": process.exitcode}),
        ), unreachable=not timed_out)
    log.info("m28_pilot.finished", index_pages=len(crawl.index_pages),
             documents=len(crawl.documents), review_items=len(crawl.review_items),
             unreachable=crawl.unreachable)
    return crawl


def _run_pilot_crawl(queue, index_urls, settings: Settings, retain_bodies: bool,
                     guard_destination: bool, resolver) -> None:
    try:
        from scrapy.crawler import CrawlerProcess

        crawler_settings = _crawler_settings(settings)
        crawler_settings.update({
            "PIPELINE_GUARD_DESTINATION": guard_destination,
            "PIPELINE_RESOLVER": resolver,
        })
        process = CrawlerProcess(settings=crawler_settings, install_root_handler=False)
        process.crawl(
            _spider_class(), index_urls=index_urls,
            retain_bodies=retain_bodies, result_queue=queue,
        )
        process.start()
    except Exception as exc:  # noqa: BLE001 - return an explicit crawl failure
        queue.put(PilotCrawl(review_items=(
            ("m28_scrapy_pilot_failed", "national_sar_library",
             {"error": f"{type(exc).__name__}: {exc}"}),
        )))


def _spider_class():
    """Build the spider lazily so importing the pilot needs no Scrapy extra."""
    import scrapy
    from scrapy import signals
    from scrapy.exceptions import DontCloseSpider

    class _SarLibrarySpider(scrapy.Spider):
        name = "pipeline_m28_sar_reports_pilot"

        def __init__(self, index_urls, retain_bodies, result_queue, **kwargs):
            super().__init__(**kwargs)
            self.index_urls = list(dict.fromkeys(index_urls))
            self.retain_bodies = retain_bodies
            self.result_queue = result_queue
            self.source_system = SOURCE_SYSTEM
            self.module = "m28_sar_reports_pilot"
            self.index_pages: list[PilotIndexPage] = []
            self.documents: list[PilotDocument] = []
            self.review_items: list[tuple[str, str, dict]] = []
            self.document_links: dict[str, tuple[str, int | None]] = {}
            self.documents_issued = False
            self.reached_anything = False
            self.robots_blocked = False

        @classmethod
        def from_crawler(cls, crawler, *args, **kwargs):
            spider = super().from_crawler(crawler, *args, **kwargs)
            crawler.signals.connect(spider._spider_idle, signal=signals.spider_idle)
            return spider

        def _index_request(self, url: str):
            return scrapy.Request(
                url, callback=self.parse_index, errback=self.index_failed,
                meta={"handle_httpstatus_all": True,
                      "pipeline_requested_url": url},
            )

        async def start(self):
            for url in self.index_urls:
                yield self._index_request(url)

        def start_requests(self):
            for url in self.index_urls:
                yield self._index_request(url)

        def parse_index(self, response):
            result = transport_result_from_response(
                response, transport="scrapy", source_system=self.source_system,
                module=self.module)
            if not result.ok:
                self.review_items.append((
                    "sar_library_index_unavailable", response.url,
                    {"status": result.status_code}))
                return
            self.reached_anything = True
            url = result.final_url or result.requested_url
            is_scie = "scie" in url.lower()
            if is_scie:
                rows = m28.parse_scie_library_page(
                    result.body.decode("utf-8", "replace"))
            else:
                rows = m28.parse_library_page(
                    result.body.decode("utf-8", "replace"))
            links: list[dict] = []
            for row in rows:
                document_url = m28.resolve_document_url(
                    row["href"], url)
                if m28.document_extension(document_url) is None:
                    continue
                title = row.get("title") or ""
                library_year = row.get("library_year")
                links.append({"title": title, "library_year": library_year,
                              "document_url": document_url})
                self.document_links.setdefault(
                    document_url, (title, library_year))
            self.index_pages.append(PilotIndexPage(
                page_url=url,
                result=result if self.retain_bodies else replace(result, body=b""),
                document_links=tuple(links),
            ))

        def index_failed(self, failure):
            request = failure.request
            url = request.meta.get("pipeline_requested_url", request.url)
            if request.meta.get("failure_class") is FailureClass.ROBOTS_DISALLOWED:
                self.robots_blocked = True
                self.review_items.append((
                    "sar_library_index_robots_disallowed", url, {}))
                return
            result = transport_result_from_failure(
                failure, transport="scrapy", source_system=self.source_system,
                module=self.module)
            self.review_items.append((
                "sar_library_index_unavailable", url,
                {"failure_class": result.failure_class.value}))

        def _document_requests(self):
            for document_url, (title, library_year) in self.document_links.items():
                yield scrapy.Request(
                    document_url, callback=self.parse_document,
                    errback=self.document_failed,
                    meta={"handle_httpstatus_all": True,
                          "pipeline_requested_url": document_url,
                          "title": title, "library_year": library_year},
                )

        def _spider_idle(self, spider):
            if self.documents_issued:
                return
            self.documents_issued = True
            for request in self._document_requests():
                self.crawler.engine.crawl(request)
            if self.document_links:
                raise DontCloseSpider

        def parse_document(self, response):
            result = transport_result_from_response(
                response, transport="scrapy", source_system=self.source_system,
                module=self.module)
            if not result.ok:
                self.review_items.append((
                    "sar_document_unavailable", response.url,
                    {"status": result.status_code}))
                return
            stored_result = result if self.retain_bodies else replace(result, body=b"")
            self.documents.append(PilotDocument(
                title=response.meta.get("title", ""),
                library_year=response.meta.get("library_year"),
                result=stored_result,
            ))

        def document_failed(self, failure):
            request = failure.request
            url = request.meta.get("pipeline_requested_url", request.url)
            if request.meta.get("failure_class") is FailureClass.ROBOTS_DISALLOWED:
                self.robots_blocked = True
                self.review_items.append((
                    "sar_document_robots_disallowed", url, {}))
                return
            result = transport_result_from_failure(
                failure, transport="scrapy", source_system=self.source_system,
                module=self.module)
            self.review_items.append((
                "sar_document_unavailable", url,
                {"failure_class": result.failure_class.value}))

        def closed(self, reason):
            self.result_queue.put(PilotCrawl(
                index_pages=tuple(self.index_pages),
                documents=tuple(self.documents),
                review_items=tuple(self.review_items),
                robots_blocked=self.robots_blocked,
                unreachable=not self.reached_anything and not self.robots_blocked,
            ))

    return _SarLibrarySpider
