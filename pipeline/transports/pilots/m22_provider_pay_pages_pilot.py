"""Adapter-only Scrapy pilot for ``m22_provider_pay_pages``.

The production module remains HTTPX-backed. This pilot moves only the
bounded, same-host page discovery onto Scrapy and reuses m22's parser and
link-selection rules. It returns page-shaped data for parity and watched
measurements; it never opens a database connection or writes evidence.
"""
from __future__ import annotations

import multiprocessing
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

import structlog

from pipeline.config import Settings
from pipeline.modules import m22_provider_pay_pages as m22
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

SOURCE_SYSTEM = "provider_pay_pages_pilot"


@dataclass(frozen=True)
class PilotPage:
    provider_key: str
    page_url: str
    role: str
    result: TransportResult
    title: str | None = None
    mentions: tuple[dict, ...] = ()
    parse_failures: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class PilotCrawl:
    pages: tuple[PilotPage, ...] = ()
    review_items: tuple[tuple[str, str, dict], ...] = ()
    robots_blocked: bool = False
    unreachable: bool = False


def fetch_m22_pilot(
    provider_pages: Mapping[str, Sequence[tuple[str, str]]] | None = None,
    *,
    settings: Settings,
    retain_bodies: bool = True,
    guard_destination: bool = False,
    resolver=None,
) -> PilotCrawl:
    """Run the bounded m22 crawl through Scrapy.

    ``provider_pages`` has the same shape as ``m22.PROVIDER_PAY_PAGES``:
    provider key -> ``(url, note)`` entries. The note is retained only by the
    registry and is not needed by the crawl, so the pilot records each entry
    as a registered page just as m22 does.
    """
    if not settings.scrapy_enabled:
        raise ScrapyDisabled("SCRAPY_ENABLED is False; enable it explicitly before running the m22 pilot.")
    if not available():
        raise ScrapyNotInstalled("The `scrapy` extra is not installed. Run `uv sync --extra scrapy`.")

    selected = {
        key: list(value)
        for key, value in (provider_pages or m22.PROVIDER_PAY_PAGES).items()
    }
    ctx = multiprocessing.get_context("spawn")
    queue: multiprocessing.Queue = ctx.Queue()
    process = ctx.Process(
        target=_run_pilot_crawl,
        args=(queue, selected, settings, retain_bodies, guard_destination, resolver),
    )
    log.info("m22_pilot.starting", providers=len(selected))
    process.start()
    items, timed_out = drain_subprocess(
        process, queue, settings.scrapy_runner_timeout_seconds)
    if items:
        crawl = items[-1]
    else:
        crawl = PilotCrawl(
            review_items=((
                "m22_scrapy_pilot_timeout" if timed_out else "m22_scrapy_pilot_failed",
                "provider_pay_pages",
                {"timeout_seconds": settings.scrapy_runner_timeout_seconds,
                 "exit_code": process.exitcode},
            ),),
            unreachable=not timed_out,
        )
    log.info("m22_pilot.finished", pages=len(crawl.pages),
             review_items=len(crawl.review_items), unreachable=crawl.unreachable)
    return crawl


def _run_pilot_crawl(queue, provider_pages, settings: Settings, retain_bodies: bool,
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
            _spider_class(), provider_pages=provider_pages,
            retain_bodies=retain_bodies, result_queue=queue,
        )
        process.start()
    except Exception as exc:  # noqa: BLE001 - return an explicit crawl failure
        queue.put(PilotCrawl(review_items=(
            ("m22_scrapy_pilot_failed", "provider_pay_pages",
             {"error": f"{type(exc).__name__}: {exc}"}),
        )))


def _spider_class():
    """Build the spider lazily so the module imports without Scrapy installed."""
    import scrapy

    class _ProviderPaySpider(scrapy.Spider):
        name = "pipeline_m22_provider_pay_pilot"

        def __init__(self, provider_pages, retain_bodies, result_queue, **kwargs):
            super().__init__(**kwargs)
            self.provider_pages = provider_pages
            self.retain_bodies = retain_bodies
            self.result_queue = result_queue
            self.source_system = SOURCE_SYSTEM
            self.module = "m22_provider_pay_pages_pilot"
            self.pages: list[PilotPage] = []
            self.review_items: list[tuple[str, str, dict]] = []
            self.visited: set[tuple[str, str]] = set()
            self.followed: dict[str, int] = {}
            self.reached_anything = False
            self.robots_blocked = False

        def _request(self, provider_key: str, url: str, role: str):
            key = (provider_key, url)
            if key in self.visited:
                return None
            self.visited.add(key)
            return scrapy.Request(
                url, callback=self.parse_page, errback=self.page_failed,
                meta={"handle_httpstatus_all": True,
                      "pipeline_requested_url": url,
                      "provider_key": provider_key, "role": role},
            )

        async def start(self):
            for provider_key, entries in self.provider_pages.items():
                for url, _note in entries:
                    request = self._request(provider_key, url, "registered")
                    if request is not None:
                        yield request

        def start_requests(self):
            for provider_key, entries in self.provider_pages.items():
                for url, _note in entries:
                    request = self._request(provider_key, url, "registered")
                    if request is not None:
                        yield request

        def parse_page(self, response):
            provider_key = response.meta["provider_key"]
            role = response.meta["role"]
            if role == "followed":
                # Count attempted followed pages, not only successful ones;
                # a dead link must not let a crawl exceed m22's bound.
                self.followed[provider_key] = self.followed.get(provider_key, 0) + 1
            result = transport_result_from_response(
                response, transport="scrapy", source_system=self.source_system,
                module=self.module)
            if not result.ok:
                self.review_items.append((
                    "pay_page_unavailable", response.url,
                    {"provider_key": provider_key, "status": result.status_code},
                ))
                return

            self.reached_anything = True
            html = result.body.decode("utf-8", "replace")
            parser = m22._PageParser()
            parser.feed(html)
            parser.close()
            mentions, failures = m22.extract_mentions(html)
            stored_result = result if self.retain_bodies else replace(result, body=b"")
            self.pages.append(PilotPage(
                provider_key=provider_key,
                page_url=result.final_url or result.requested_url,
                role=role,
                result=stored_result,
                title=parser.title,
                mentions=tuple(mentions),
                parse_failures=tuple(failures),
            ))

            if self.followed.get(provider_key, 0) >= m22.MAX_FOLLOWED_PAGES:
                return
            page_url = result.final_url or result.requested_url
            for link in m22._linked_pages(page_url, parser):
                request = self._request(provider_key, link, "followed")
                if request is not None:
                    yield request

        def page_failed(self, failure):
            request = failure.request
            url = request.meta.get("pipeline_requested_url", request.url)
            if request.meta.get("failure_class") is FailureClass.ROBOTS_DISALLOWED:
                self.robots_blocked = True
                self.review_items.append((
                    "pay_page_robots_disallowed", url,
                    {"provider_key": request.meta.get("provider_key")},
                ))
                return
            result = transport_result_from_failure(
                failure, transport="scrapy", source_system=self.source_system,
                module=self.module)
            self.review_items.append((
                "pay_page_unavailable", url,
                {"provider_key": request.meta.get("provider_key"),
                 "failure_class": result.failure_class.value},
            ))

        def closed(self, reason):
            self.result_queue.put(PilotCrawl(
                pages=tuple(self.pages),
                review_items=tuple(self.review_items),
                robots_blocked=self.robots_blocked,
                unreachable=not self.reached_anything and not self.robots_blocked,
            ))

    return _ProviderPaySpider
