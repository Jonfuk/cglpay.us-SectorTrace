"""Adapter-only Scrapy pilot for ``m24_council_spend``.

The pilot preserves m24's path probes, same-host file rule and three-file
authority ceiling, but lets Scrapy schedule different council hosts together.
It parses files with the existing m24 helpers and returns the results without
writing the warehouse. Production m24 remains HTTPX-backed until parity and
watched measurements are reviewed.
"""
from __future__ import annotations

import multiprocessing
from dataclasses import dataclass, replace
from typing import Sequence
from urllib.parse import urljoin, urlparse

import structlog

from pipeline.config import Settings
from pipeline.modules import m24_council_spend as m24
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

SOURCE_SYSTEM = "council_spend_transparency_pilot"


@dataclass(frozen=True)
class PilotPage:
    authority_ons_code: str
    page_url: str
    path_order: int
    result: TransportResult


@dataclass(frozen=True)
class PilotFile:
    authority_ons_code: str
    authority_name: str
    file_url: str
    discovered_from: str
    format_hint: str
    result: TransportResult
    rows: tuple[dict, ...] = ()
    parse_error: str | None = None


@dataclass(frozen=True)
class PilotCrawl:
    pages: tuple[PilotPage, ...] = ()
    files: tuple[PilotFile, ...] = ()
    review_items: tuple[tuple[str, str, dict], ...] = ()
    robots_blocked: bool = False
    unreachable: bool = False


def fetch_m24_pilot(
    authorities: Sequence[tuple[dict, str | None]],
    *,
    settings: Settings,
    retain_bodies: bool = True,
    guard_destination: bool = False,
    resolver=None,
) -> PilotCrawl:
    """Run m24 discovery for ``(authority_row, verified_base_url)`` pairs.

    The caller supplies the already verified authority websites; this keeps
    the pilot database-free and makes the exact watched scope explicit.
    """
    if not settings.scrapy_enabled:
        raise ScrapyDisabled("SCRAPY_ENABLED is False; enable it explicitly before running the m24 pilot.")
    if not available():
        raise ScrapyNotInstalled("The `scrapy` extra is not installed. Run `uv sync --extra scrapy`.")

    selected = [(dict(authority), base_url) for authority, base_url in authorities]
    ctx = multiprocessing.get_context("spawn")
    queue: multiprocessing.Queue = ctx.Queue()
    process = ctx.Process(
        target=_run_pilot_crawl,
        args=(queue, selected, settings, retain_bodies, guard_destination, resolver),
    )
    log.info("m24_pilot.starting", authorities=len(selected))
    process.start()
    items, timed_out = drain_subprocess(
        process, queue, settings.scrapy_runner_timeout_seconds)
    if items:
        crawl = items[-1]
    else:
        crawl = PilotCrawl(review_items=(
            ("m24_scrapy_pilot_timeout" if timed_out else "m24_scrapy_pilot_failed",
             "council_spend_transparency",
             {"timeout_seconds": settings.scrapy_runner_timeout_seconds,
              "exit_code": process.exitcode}),
        ), unreachable=not timed_out)
    log.info("m24_pilot.finished", pages=len(crawl.pages), files=len(crawl.files),
             review_items=len(crawl.review_items), unreachable=crawl.unreachable)
    return crawl


def _run_pilot_crawl(queue, authorities, settings: Settings, retain_bodies: bool,
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
            _spider_class(), authorities=authorities,
            retain_bodies=retain_bodies, result_queue=queue,
        )
        process.start()
    except Exception as exc:  # noqa: BLE001 - return an explicit crawl failure
        queue.put(PilotCrawl(review_items=(
            ("m24_scrapy_pilot_failed", "council_spend_transparency",
             {"error": f"{type(exc).__name__}: {exc}"}),
        )))


def _format_hint(file_url: str) -> str:
    path = file_url.lower().split("?")[0]
    if path.endswith(".xlsx"):
        return "xlsx"
    if path.endswith(".ods"):
        return "ods"
    if path.endswith(".xls"):
        return "xls"
    return "csv"


def _parse_file(body: bytes, file_url: str, format_hint: str) -> tuple[list[dict], str | None]:
    if format_hint == "xls":
        return [], "legacy .xls is not supported; the file was archived"
    if format_hint == "csv":
        return m24._parse_csv(body, file_url)
    return m24._parse_xlsx_ods(body, file_url, format_hint)


def _spider_class():
    """Build the spider lazily so importing the pilot needs no Scrapy extra."""
    import scrapy
    from scrapy import signals
    from scrapy.exceptions import DontCloseSpider

    class _CouncilSpendSpider(scrapy.Spider):
        name = "pipeline_m24_council_spend_pilot"

        def __init__(self, authorities, retain_bodies, result_queue, **kwargs):
            super().__init__(**kwargs)
            self.authorities = authorities
            self.retain_bodies = retain_bodies
            self.result_queue = result_queue
            self.source_system = SOURCE_SYSTEM
            self.module = "m24_council_spend_pilot"
            self.pages: list[PilotPage] = []
            self.files: list[PilotFile] = []
            self.review_items: list[tuple[str, str, dict]] = []
            self.candidate_files: dict[str, tuple[int, int, str, str]] = {}
            self.scheduled_pages: set[tuple[str, str]] = set()
            self.files_issued = False
            self.reached_anything = False
            self.robots_blocked = False

        @classmethod
        def from_crawler(cls, crawler, *args, **kwargs):
            spider = super().from_crawler(crawler, *args, **kwargs)
            crawler.signals.connect(spider._spider_idle, signal=signals.spider_idle)
            return spider

        def _page_request(self, authority_index: int, authority: dict,
                          base_url: str, path_order: int):
            url = urljoin(base_url.rstrip("/") + "/", m24.SPEND_PATHS[path_order].lstrip("/"))
            key = (authority["ons_code"], url)
            if key in self.scheduled_pages:
                return None
            self.scheduled_pages.add(key)
            return scrapy.Request(
                url, callback=self.parse_page, errback=self.page_failed,
                meta={"handle_httpstatus_all": True,
                      "pipeline_requested_url": url,
                      "authority_index": authority_index,
                      "authority": authority,
                      "base_url": base_url,
                      "path_order": path_order},
            )

        async def start(self):
            for authority_index, (authority, base_url) in enumerate(self.authorities):
                if not base_url:
                    self.review_items.append((
                        "authority_website_unknown", authority["ons_code"],
                        {"authority": authority["name"]}))
                    continue
                for path_order in range(len(m24.SPEND_PATHS)):
                    request = self._page_request(
                        authority_index, authority, base_url, path_order)
                    if request is not None:
                        yield request

        def start_requests(self):
            for authority_index, (authority, base_url) in enumerate(self.authorities):
                if not base_url:
                    self.review_items.append((
                        "authority_website_unknown", authority["ons_code"],
                        {"authority": authority["name"]}))
                    continue
                for path_order in range(len(m24.SPEND_PATHS)):
                    request = self._page_request(
                        authority_index, authority, base_url, path_order)
                    if request is not None:
                        yield request

        def parse_page(self, response):
            authority = response.meta["authority"]
            result = transport_result_from_response(
                response, transport="scrapy", source_system=self.source_system,
                module=self.module)
            stored_result = result if self.retain_bodies else replace(result, body=b"")
            self.pages.append(PilotPage(
                authority_ons_code=authority["ons_code"],
                page_url=result.final_url or result.requested_url,
                path_order=response.meta["path_order"], result=stored_result,
            ))
            if not result.ok:
                self.review_items.append((
                    "council_spend_path_unavailable", response.url,
                    {"authority": authority["name"], "status": result.status_code}))
                return
            self.reached_anything = True
            host = urlparse(response.meta["base_url"]).netloc
            for file_url in m24._file_urls_on_page(
                    result.body.decode("utf-8", "replace"),
                    result.final_url or result.requested_url, host):
                value = (response.meta["authority_index"],
                         response.meta["path_order"],
                         authority["name"], response.meta["base_url"])
                previous = self.candidate_files.get(file_url)
                if previous is None or value[:2] < previous[:2]:
                    self.candidate_files[file_url] = value

        def page_failed(self, failure):
            request = failure.request
            url = request.meta.get("pipeline_requested_url", request.url)
            authority = request.meta["authority"]
            if request.meta.get("failure_class") is FailureClass.ROBOTS_DISALLOWED:
                self.robots_blocked = True
                self.review_items.append((
                    "council_spend_path_robots_disallowed", url,
                    {"authority": authority["name"]}))
                return
            result = transport_result_from_failure(
                failure, transport="scrapy", source_system=self.source_system,
                module=self.module)
            self.review_items.append((
                "council_spend_path_unavailable", url,
                {"authority": authority["name"],
                 "failure_class": result.failure_class.value}))

        def _file_requests(self):
            counts: dict[int, int] = {}
            for file_url, (authority_index, path_order, name, base_url) in sorted(
                    self.candidate_files.items(), key=lambda item: (
                        item[1][0], item[1][1], item[0])):
                if counts.get(authority_index, 0) >= m24.MAX_FILES_PER_AUTHORITY:
                    continue
                counts[authority_index] = counts.get(authority_index, 0) + 1
                authority = self.authorities[authority_index][0]
                yield scrapy.Request(
                    file_url, callback=self.parse_file, errback=self.file_failed,
                    meta={"handle_httpstatus_all": True,
                          "pipeline_requested_url": file_url,
                          "authority": authority, "authority_name": name,
                          "discovered_from": base_url},
                )

        def _spider_idle(self, spider):
            if self.files_issued:
                return
            self.files_issued = True
            for request in self._file_requests():
                self.crawler.engine.crawl(request)
            if self.candidate_files:
                raise DontCloseSpider

        def parse_file(self, response):
            authority = response.meta["authority"]
            result = transport_result_from_response(
                response, transport="scrapy", source_system=self.source_system,
                module=self.module)
            hint = _format_hint(response.meta.get("pipeline_requested_url", response.url))
            if not result.ok:
                self.review_items.append((
                    "council_spend_file_unavailable", response.url,
                    {"authority": authority["name"], "status": result.status_code}))
                return
            rows, error = _parse_file(result.body, response.url, hint)
            stored_result = result if self.retain_bodies else replace(result, body=b"")
            self.files.append(PilotFile(
                authority_ons_code=authority["ons_code"],
                authority_name=authority["name"],
                file_url=response.meta["pipeline_requested_url"],
                discovered_from=response.meta["discovered_from"],
                format_hint=hint, result=stored_result,
                rows=tuple(rows), parse_error=error,
            ))
            if error:
                self.review_items.append((
                    "council_spend_unreadable", response.url,
                    {"authority": authority["name"], "error": error}))

        def file_failed(self, failure):
            request = failure.request
            url = request.meta.get("pipeline_requested_url", request.url)
            authority = request.meta["authority"]
            if request.meta.get("failure_class") is FailureClass.ROBOTS_DISALLOWED:
                self.robots_blocked = True
                self.review_items.append((
                    "council_spend_file_robots_disallowed", url,
                    {"authority": authority["name"]}))
                return
            result = transport_result_from_failure(
                failure, transport="scrapy", source_system=self.source_system,
                module=self.module)
            self.review_items.append((
                "council_spend_file_unavailable", url,
                {"authority": authority["name"],
                 "failure_class": result.failure_class.value}))

        def closed(self, reason):
            self.result_queue.put(PilotCrawl(
                pages=tuple(self.pages), files=tuple(self.files),
                review_items=tuple(self.review_items),
                robots_blocked=self.robots_blocked,
                unreachable=not self.reached_anything and not self.robots_blocked,
            ))

    return _CouncilSpendSpider
