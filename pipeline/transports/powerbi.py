"""Power BI querydata capture and conservative long-form extraction.

Power BI's canvas and CSS are presentation details.  The useful public data is
the JSON returned by ``querydata``/``public/query`` requests, but the response envelope changes
more often than the source's published labels.  This module therefore keeps
the exact response in the raw archive and extracts only the stable cell/value
part of the envelope.  Unknown shape is a parse failure, never an empty
dataset.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import multiprocessing
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import structlog

from pipeline import db
from pipeline.archive import get_archive
from pipeline.config import Settings
from pipeline.transports.browser_pilot import (
    ScrapyPlaywrightDisabled,
    ScrapyPlaywrightNotInstalled,
    _call_page_on_its_loop,
    _crawler_settings,
    drain_subprocess,
    playwright_available,
)
from pipeline.transports.scrapy_transport import ScrapyDisabled, available

log = structlog.get_logger()

QUERYDATA_RE = re.compile(r"(?:^|/)(?:querydata|public/query)(?:$|[/?])", re.IGNORECASE)
VOLATILE_QUERY_KEYS = {"s", "uid", "sid", "token", "requestid", "activityid"}
REPORT_PAGES = (
    "Adults in treatment",
    "Young people in treatment",
    "Socio demographics",
    "Mental health treatment need",
    "Substance use",
    "Routes into treatment",
    "Interventions",
    "Outcomes of treatment received",
    "Public access data",
    "Download data",
)
REGION_NAMES = {
    "England",
    "East Midlands",
    "East of England",
    "London",
    "North East",
    "North West",
    "South East",
    "South West",
    "West Midlands",
    "Yorkshire & the Humber",
}
REGION_SELECTIONS = (
    "East Midlands",
    "East of England",
    "London",
    "North East",
    "North West",
    "South East",
    "South West",
    "West Midlands",
    "Yorkshire & the Humber",
)


@dataclass(frozen=True)
class PowerBICapture:
    dashboard_url: str
    response_url: str
    method: str
    status_code: int
    content_type: str | None
    body: bytes
    request_body_sha256: str
    retrieved_at: datetime
    sequence: int
    error: str | None = None
    filter_context: dict[str, str] | None = None

    @property
    def payload_sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()

    @property
    def canonical_response_url(self) -> str:
        parts = urlsplit(self.response_url)
        query = [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in VOLATILE_QUERY_KEYS
        ]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "–", "—", "*", "c", "z", "x", ":"}:
        return None
    try:
        return float(text.rstrip("%"))
    except ValueError:
        return None


def parse_querydata(body: bytes | str) -> list[dict[str, Any]]:
    """Extract conservative cell rows from a Power BI querydata response.

    Power BI commonly stores result rows as ``C`` arrays below ``DM*``
    containers.  We retain the full local row context and column index because
    descriptor/semantic-query labels vary by report version.  A response with
    no cell arrays is rejected so a changed envelope cannot look like success.
    """
    try:
        document = json.loads(body)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid Power BI JSON: {exc}") from exc

    rows: list[dict[str, Any]] = []
    value_dicts: dict[str, list[Any]] = {}
    descriptor_names: dict[str, str] = {}

    def collect_metadata(value: Any) -> None:
        if isinstance(value, dict):
            dictionaries = value.get("ValueDicts")
            if isinstance(dictionaries, dict):
                for name, values in dictionaries.items():
                    if isinstance(values, list):
                        value_dicts[str(name)] = values
            descriptor = value.get("descriptor")
            if isinstance(descriptor, dict):
                for select in descriptor.get("Select", []):
                    if isinstance(select, dict):
                        name = select.get("Name")
                        key = select.get("Value")
                        if isinstance(name, str) and isinstance(key, str):
                            descriptor_names[key] = name
            for child in value.values():
                collect_metadata(child)
        elif isinstance(value, list):
            for child in value:
                collect_metadata(child)

    collect_metadata(document)

    def contains_key(value: Any, key: str) -> bool:
        if isinstance(value, dict):
            return key in value or any(contains_key(child, key) for child in value.values())
        if isinstance(value, list):
            return any(contains_key(child, key) for child in value)
        return False

    def walk(
        value: Any,
        path: tuple[str, ...] = (),
        slots: tuple[tuple[str | None, str | None], ...] = (),
        series_labels: tuple[str, ...] = (),
    ) -> None:
        if isinstance(value, dict):
            cells = value.get("C")
            row_slots = slots
            if isinstance(value.get("S"), list):
                row_slots = tuple(
                    (
                        item.get("N") if isinstance(item, dict) else None,
                        item.get("DN") if isinstance(item, dict) else None,
                    )
                    for item in value["S"]
                )
            row_series = series_labels
            for group in value.get("SH", []):
                if not isinstance(group, dict):
                    continue
                for group_rows in group.values():
                    if not isinstance(group_rows, list):
                        continue
                    labels = []
                    for group_row in group_rows:
                        if not isinstance(group_row, dict):
                            continue
                        label = next(
                            (
                                item
                                for key, item in group_row.items()
                                if key != "S" and not isinstance(item, (dict, list))
                            ),
                            None,
                        )
                        if isinstance(label, int) and isinstance(group_row.get("S"), list):
                            slot = group_row["S"][0]
                            dictionary = slot.get("DN") if isinstance(slot, dict) else None
                            if dictionary in value_dicts and 0 <= label < len(value_dicts[dictionary]):
                                label = value_dicts[dictionary][label]
                        if label is not None:
                            labels.append(str(label))
                    if labels:
                        row_series = tuple(labels)
            if isinstance(value.get("X"), list):
                base_context = {}
                for index, cell in enumerate(cells or []):
                    raw = cell.get("V") if isinstance(cell, dict) else cell
                    if isinstance(cell, dict) and "D" in cell and "V" not in cell:
                        raw = cell["D"]
                    slot_name, dictionary_name = (
                        row_slots[index] if index < len(row_slots) else (None, None)
                    )
                    decoded = raw
                    if (
                        isinstance(raw, int)
                        and not isinstance(raw, bool)
                        and dictionary_name in value_dicts
                        and 0 <= raw < len(value_dicts[dictionary_name])
                    ):
                        decoded = value_dicts[dictionary_name][raw]
                    if slot_name:
                        base_context[descriptor_names.get(slot_name, slot_name)] = decoded
                for series_index, series in enumerate(value["X"]):
                    if not isinstance(series, dict):
                        continue
                    metric_key, raw = next(
                        (
                            (key, item)
                            for key, item in series.items()
                            if key != "S" and not isinstance(item, (dict, list))
                        ),
                        (None, None),
                    )
                    if metric_key is None:
                        continue
                    metric_raw = descriptor_names.get(metric_key, metric_key)
                    dimensions = {
                        "dimensions": base_context,
                        "series_index": series_index,
                        "series_label": (
                            row_series[series_index]
                            if series_index < len(row_series)
                            else None
                        ),
                    }
                    rows.append(
                        {
                            "cell_path": ".".join(path + ("X", str(series_index))),
                            "column_index": series_index,
                            "metric_raw": metric_raw,
                            "value": _number(raw),
                            "value_text": "" if raw is None else str(raw),
                            "dimensions_json": json.dumps(
                                dimensions, sort_keys=True, default=str
                            ),
                            "time_period_raw": str(base_context.get(
                                "DIM_PendKey.pend.Variation.Date Hierarchy.Year", ""
                            )),
                        }
                    )
            if isinstance(cells, list):
                for column_index, cell in enumerate(cells):
                    if "X" in value or contains_key(value.get("PH"), "X"):
                        continue
                    raw = cell.get("V") if isinstance(cell, dict) else cell
                    if isinstance(cell, dict) and "D" in cell and "V" not in cell:
                        raw = cell["D"]
                    slot_name, dictionary_name = (
                        row_slots[column_index]
                        if column_index < len(row_slots)
                        else (None, None)
                    )
                    decoded = raw
                    if (
                        isinstance(raw, int)
                        and not isinstance(raw, bool)
                        and dictionary_name in value_dicts
                        and 0 <= raw < len(value_dicts[dictionary_name])
                    ):
                        decoded = value_dicts[dictionary_name][raw]
                    metric_raw = (
                        cell.get("N") if isinstance(cell, dict) else None
                    ) or descriptor_names.get(slot_name or "") or f"column_{column_index}"
                    context = {k: v for k, v in value.items() if k != "C"}
                    if slot_name or dictionary_name:
                        context["decoded_dimension"] = {
                            "descriptor": metric_raw,
                            "dictionary": dictionary_name,
                            "raw": raw,
                            "value": decoded,
                        }
                    rows.append(
                        {
                            "cell_path": ".".join(path),
                            "column_index": column_index,
                            "metric_raw": metric_raw,
                            "value": _number(decoded),
                            "value_text": "" if decoded is None else str(decoded),
                            "dimensions_json": json.dumps(context, sort_keys=True, default=str),
                        }
                    )
            for key, child in value.items():
                if key != "C":
                    child_path = path + (str(key),)
                    if re.fullmatch(r"DM\d+", str(key)) and isinstance(child, list):
                        inherited_slots = next(
                            (
                                tuple(
                                    (
                                        item.get("N") if isinstance(item, dict) else None,
                                        item.get("DN") if isinstance(item, dict) else None,
                                    )
                                    for item in child[0].get("S", [])
                                )
                                for item in child
                                if isinstance(item, dict) and isinstance(item.get("S"), list)
                            ),
                            slots,
                        )
                        for index, item in enumerate(child):
                            walk(item, child_path + (str(index),), inherited_slots, row_series)
                    else:
                        walk(child, child_path, row_slots, row_series)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, path + (str(index),), slots, series_labels)

    walk(document)
    if not rows:
        raise ValueError("Power BI response contained no recognised cell arrays")
    for index, row in enumerate(rows):
        row["row_index"] = index
    return rows


def persist_powerbi(ctx, specs: Sequence[dict[str, str]]) -> int:
    """Capture and persist a module's explicitly-owned public dashboards."""
    if ctx.dry_run:
        log.info("powerbi.capture_skipped", reason="dry_run")
        return 0
    try:
        captures = capture_powerbi_payloads(
            [spec["url"] for spec in specs],
            source_system="ohid_ndtms_powerbi",
            settings=ctx.settings,
            module="ndtms",
        )
    except (ScrapyDisabled, ScrapyPlaywrightDisabled, ScrapyPlaywrightNotInstalled) as exc:
        log.warning("powerbi.capture_disabled", reason=str(exc))
        return 0

    by_url = {spec["url"]: spec for spec in specs}
    written = 0
    for capture in captures:
        spec = by_url.get(capture.dashboard_url) or {}
        try:
            observations = parse_querydata(capture.body)
        except ValueError as exc:
            db.record_parse_failure(
                ctx.conn,
                "ndtms_powerbi",
                capture.canonical_response_url,
                "querydata",
                capture.payload_sha256,
                str(exc),
            )
            db.record_review_item(
                ctx.conn,
                "ndtms_powerbi",
                "querydata_parse_failure",
                capture.canonical_response_url,
                json.dumps({"payload_sha256": capture.payload_sha256, "error": str(exc)}),
            )
            continue
        provenance = {
            "source_url": capture.canonical_response_url,
            "retrieved_at": capture.retrieved_at.isoformat(),
            "http_status": capture.status_code,
            "source_system": "ohid_ndtms_powerbi",
        }
        dashboard_key = spec.get("key", "unknown")
        db.upsert(
            ctx.conn,
            "ndtms_powerbi_payloads",
            {
                "dashboard_key": dashboard_key,
                "payload_sha256": capture.payload_sha256,
                "cohort": spec.get("cohort", "unknown"),
                "dashboard_url": capture.dashboard_url,
                "response_url": capture.canonical_response_url,
                "request_body_sha256": capture.request_body_sha256,
                "sequence": capture.sequence,
                "http_status": capture.status_code,
                "content_type": capture.content_type,
                "archived_path": get_archive(ctx.settings)
                .lookup("ohid_ndtms_powerbi", capture.payload_sha256)
                .logical_path,
                **provenance,
            },
            natural_key=["dashboard_key", "payload_sha256"],
        )
        rows = []
        filter_context = capture.filter_context or {}
        for row in observations:
            dimensions = json.loads(row["dimensions_json"])
            if filter_context:
                dimensions["filter_context"] = filter_context
            row_dimensions = dimensions.get("dimensions", {})
            area_name = filter_context.get("authority")
            ons_code = filter_context.get("ons_code")
            if isinstance(row_dimensions, dict):
                for key, value in row_dimensions.items():
                    key_text = str(key).strip().lower().replace("_", " ")
                    if (
                        area_name is None
                        and key_text in {"area", "area name", "areaname", "local authority"}
                        and isinstance(value, str)
                        and value not in REGION_NAMES
                        and value != "England"
                    ):
                        area_name = value
                    if (
                        ons_code is None
                        and "code" in key_text
                        and isinstance(value, str)
                        and re.fullmatch(r"E\d{8}", value)
                    ):
                        ons_code = value
            rows.append(
                {
                    **row,
                    "dashboard_key": dashboard_key,
                    "payload_sha256": capture.payload_sha256,
                    "area_name_raw": area_name,
                    "ons_code": ons_code,
                    "dimensions_json": json.dumps(dimensions, sort_keys=True, default=str),
                    **provenance,
                }
            )
        for offset in range(0, len(rows), 5000):
            batch = rows[offset : offset + 5000]
            db.upsert_many(
                ctx.conn,
                "ndtms_powerbi_observations",
                batch,
                natural_key=["dashboard_key", "payload_sha256", "row_index"],
            )
            written += len(batch)
            if not ctx.dry_run:
                ctx.conn.commit()
    return written


def _request_body_hash(request) -> str:
    try:
        body = request.post_data_buffer
    except Exception:  # pragma: no cover - Playwright version variance
        body = None
    if body is None:
        try:
            text = request.post_data
            body = text.encode("utf-8") if text else b""
        except Exception:
            body = b""
    return hashlib.sha256(body).hexdigest()


async def _await_page_tasks(page, tasks: list[asyncio.Task]) -> None:
    """Await response-body tasks on the Playwright loop that owns the page."""
    if not tasks:
        return

    async def gather_tasks():
        await asyncio.gather(*tasks, return_exceptions=True)

    page_loop = getattr(getattr(page, "_impl_obj", None), "_loop", None)
    current_loop = asyncio.get_running_loop()
    if page_loop is None or page_loop is current_loop:
        await gather_tasks()
        return
    future = asyncio.run_coroutine_threadsafe(gather_tasks(), page_loop)
    await asyncio.wrap_future(future)


def capture_powerbi_payloads(
    urls: Sequence[str],
    *,
    source_system: str,
    settings: Settings,
    module: str | None = None,
) -> list[PowerBICapture]:
    """Capture public querydata responses and archive exact response bytes."""
    if not settings.scrapy_enabled:
        raise ScrapyDisabled("SCRAPY_ENABLED is False")
    if not settings.scrapy_playwright_enabled:
        raise ScrapyPlaywrightDisabled("SCRAPY_PLAYWRIGHT_ENABLED is False")
    if not available():
        raise ScrapyDisabled("The scrapy extra is not installed")
    if not playwright_available():
        raise ScrapyPlaywrightNotInstalled("scrapy-playwright is not installed")

    requested = list(dict.fromkeys(urls))
    if not requested:
        return []
    ctx = multiprocessing.get_context("spawn")
    queue: multiprocessing.Queue = ctx.Queue()
    process = ctx.Process(target=_run_capture_crawl, args=(queue, requested, settings))
    log.info(
        "powerbi.capture_starting", source_system=source_system, module=module, urls=len(requested)
    )
    process.start()
    items, timed_out = drain_subprocess(
        process, queue, settings.scrapy_playwright_runner_timeout_seconds
    )
    if timed_out:
        log.warning("powerbi.capture_timeout", urls=len(requested))

    archive = get_archive(settings)
    captures: list[PowerBICapture] = []
    for item in items:
        if item.error or not item.body:
            continue
        sha = hashlib.sha256(item.body).hexdigest()
        archive.put(source_system, sha, item.content_type, item.body)
        captures.append(item)
    log.info(
        "powerbi.capture_finished",
        source_system=source_system,
        payloads=len(captures),
        timed_out=timed_out,
    )
    return captures


def _run_capture_crawl(queue, urls: list[str], settings: Settings) -> None:
    try:
        from scrapy.crawler import CrawlerProcess

        launch_options: dict = {"headless": True}
        if settings.scrapy_playwright_executable_path:
            launch_options["executable_path"] = settings.scrapy_playwright_executable_path
        crawler_settings = _crawler_settings(settings)
        crawler_settings.update(
            {
                "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
                "DOWNLOAD_HANDLERS": {
                    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
                    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
                },
                "PLAYWRIGHT_BROWSER_TYPE": "chromium",
                "PLAYWRIGHT_LAUNCH_OPTIONS": launch_options,
                "PLAYWRIGHT_MAX_CONTEXTS": settings.scrapy_playwright_max_contexts,
                "PLAYWRIGHT_MAX_PAGES_PER_CONTEXT": settings.scrapy_playwright_max_pages_per_context,
                "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": int(
                    settings.scrapy_playwright_navigation_timeout_seconds * 1000
                ),
                "MEMUSAGE_ENABLED": True,
                "MEMUSAGE_LIMIT_MB": settings.scrapy_playwright_memory_limit_mb,
                "PIPELINE_GUARD_DESTINATION": False,
            }
        )
        process = CrawlerProcess(settings=crawler_settings, install_root_handler=False)
        process.crawl(
            _powerbi_spider_class(),
            urls=urls,
            result_queue=queue,
            source_system="ohid_ndtms_powerbi",
            wait_seconds=settings.scrapy_playwright_capture_wait_seconds,
        )
        process.start()
    except Exception as exc:  # pragma: no cover - subprocess boundary
        queue.put(
            PowerBICapture(
                dashboard_url="",
                response_url="",
                method="",
                status_code=0,
                content_type=None,
                body=b"",
                request_body_sha256="",
                retrieved_at=datetime.now(timezone.utc),
                sequence=0,
                error=f"{type(exc).__name__}: {exc}",
            )
        )


def _powerbi_spider_class():
    import scrapy

    class _PowerBISpider(scrapy.Spider):
        name = "pipeline_powerbi_capture"

        def __init__(self, urls, result_queue, source_system, wait_seconds=5.0, **kwargs):
            super().__init__(**kwargs)
            self.urls = list(urls)
            self.result_queue = result_queue
            self.source_system = source_system
            self.module = "ndtms"
            self.wait_seconds = wait_seconds

        def _request(self, url):
            return scrapy.Request(
                url,
                callback=self.parse,
                errback=self.on_failure,
                dont_filter=True,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_init_callback": self._init_page,
                    "pipeline_requested_url": url,
                },
            )

        def start_requests(self):
            yield from (self._request(url) for url in self.urls)

        async def start(self):
            for url in self.urls:
                yield self._request(url)

        async def _init_page(self, page, request):
            """Install the listener before scrapy-playwright navigates."""
            captures: list[PowerBICapture] = []
            pending: list[asyncio.Task] = []
            state = {"sequence": 0}

            async def handle(network_response):
                if (
                    network_response.request.method != "POST"
                    or not QUERYDATA_RE.search(network_response.url)
                    or not 200 <= network_response.status < 300
                ):
                    return
                sequence = state["sequence"]
                state["sequence"] += 1
                try:
                    body = await network_response.body()
                    captures.append(
                        PowerBICapture(
                            dashboard_url=request.url,
                            response_url=network_response.url,
                            method=network_response.request.method,
                            status_code=network_response.status,
                            content_type=network_response.headers.get("content-type"),
                            body=body,
                            request_body_sha256=_request_body_hash(network_response.request),
                            retrieved_at=datetime.now(timezone.utc),
                            sequence=sequence,
                            filter_context=dict(
                                getattr(page, "_pipeline_powerbi_filter_context", {})
                            ),
                        )
                    )
                except Exception as exc:
                    captures.append(
                        PowerBICapture(
                            dashboard_url=request.url,
                            response_url=network_response.url,
                            method="POST",
                            status_code=network_response.status,
                            content_type=None,
                            body=b"",
                            request_body_sha256="",
                            retrieved_at=datetime.now(timezone.utc),
                            sequence=sequence,
                            error=f"{type(exc).__name__}: {exc}",
                            filter_context=dict(
                                getattr(page, "_pipeline_powerbi_filter_context", {})
                            ),
                        )
                    )

            def on_response(network_response):
                pending.append(asyncio.create_task(handle(network_response)))

            page.on("response", on_response)
            # Playwright pages accept Python attributes; keeping the lists on
            # the page avoids a process-global registry and its cross-tab mixups.
            page._pipeline_powerbi_captures = captures
            page._pipeline_powerbi_pending = pending
            page._pipeline_powerbi_filter_context = {}

        async def parse(self, response):
            page = response.meta.get("playwright_page")
            captures = getattr(page, "_pipeline_powerbi_captures", []) if page else []
            pending = getattr(page, "_pipeline_powerbi_pending", []) if page else []
            try:
                if page is not None:
                    await asyncio.sleep(self.wait_seconds)
                    await self._visit_report_pages(page)
                    await _await_page_tasks(page, pending)
            finally:
                if page is not None:
                    try:
                        if not page.is_closed():
                            await _call_page_on_its_loop(page, "close")
                    except Exception:
                        pass
            for item in captures:
                self.result_queue.put(item)

        async def _visit_report_pages(self, page):
            """Visit named report pages so their visual queries are emitted."""
            report_frame = next(
                (frame for frame in page.frames if "app.powerbi.com/reportEmbed" in frame.url),
                None,
            )
            if report_frame is None:
                return
            for label in REPORT_PAGES:
                try:
                    buttons = await report_frame.get_by_role(
                        "tab", name=label, exact=True
                    ).all()
                    for button in buttons:
                        if await button.is_visible():
                            await button.click(timeout=3000)
                            await asyncio.sleep(1.0)
                            if label in {"Adults in treatment", "Young people in treatment"}:
                                try:
                                    await asyncio.wait_for(
                                        self._visit_area_filters(page, report_frame, label),
                                        timeout=20.0,
                                    )
                                except asyncio.TimeoutError:
                                    log.warning(
                                        "powerbi.area_filter_timeout", report_page=label
                                    )
                            elif label == "Download data":
                                try:
                                    await asyncio.wait_for(
                                        self._visit_download_regions(page, report_frame),
                                        timeout=30.0,
                                    )
                                except asyncio.TimeoutError:
                                    log.warning("powerbi.download_filter_timeout")
                            break
                except Exception:
                    # Pages differ between cohorts and report revisions; an
                    # absent or temporarily stale page control is not a crawl
                    # failure when other visual requests were captured.
                    continue

        async def _area_combos(self, report_frame):
            combos = []
            for label in (
                "AreaName",
                "Area Name Multi Select",
                "Authority",
                "AuthorityName",
                "Local Authority",
                "LocalAuthority",
            ):
                combo = report_frame.get_by_role("combobox", name=label, exact=True)
                if await combo.count():
                    combos.append((label, combo))
            return combos

        async def _filter_options(self, report_frame, combo, label):
            await combo.click(timeout=3000)
            await asyncio.sleep(0.2)
            listboxes = await report_frame.locator('[role="listbox"]').all()
            target = None
            for listbox in listboxes:
                aria_label = await listbox.get_attribute("aria-label")
                if aria_label and aria_label.strip().lower() == label.lower():
                    target = listbox
                    break
            target = target or (listboxes[-1] if listboxes else None)
            if target is None:
                return []
            values = await target.get_by_role("option").all_text_contents()
            await combo.press("Escape")
            return list(dict.fromkeys(value.strip() for value in values if value.strip()))

        async def _select_filter_value(self, report_frame, label, value):
            listboxes = await report_frame.locator('[role="listbox"]').all()
            target = None
            for listbox in listboxes:
                aria_label = await listbox.get_attribute("aria-label")
                if aria_label and aria_label.strip().lower() == label.lower():
                    target = listbox
                    break
            if target is None:
                return False
            option = target.get_by_role("option", name=value, exact=True)
            if not await option.count():
                return False
            await option.click(timeout=3000)
            return True

        async def _visit_area_filters(self, page, report_frame, report_label):
            """Capture filter-driven queries, including nested authority lists.

            The public report currently exposes regions on some pages and a
            local-authority list on others.  We discover the list at runtime
            instead of hard-coding council names, because Power BI can change
            which visual owns the filter between report revisions.
            """
            if report_label not in {"Adults in treatment", "Young people in treatment"}:
                return
            combos = await self._area_combos(report_frame)
            for label, combo in combos:
                options = await self._filter_options(report_frame, combo, label)
                options = [value for value in options if value not in {"Select all", "All"}]
                if not options:
                    continue
                for area in options:
                    try:
                        await combo.click(timeout=3000)
                    except Exception:
                        continue
                    context = {"area_name": area}
                    if area in REGION_NAMES:
                        context["region"] = area
                    else:
                        context["authority"] = area
                    page._pipeline_powerbi_filter_context = context
                    if not await self._select_filter_value(report_frame, label, area):
                        await combo.press("Escape")
                        continue
                    await asyncio.sleep(0.8)
                    # A region selection may reveal a second authority combo.
                    for child_label, child_combo in await self._area_combos(report_frame):
                        if child_label.lower() == label.lower():
                            continue
                        child_options = await self._filter_options(
                            report_frame, child_combo, child_label
                        )
                        child_options = [
                            value for value in child_options if value not in {"Select all", "All"}
                        ]
                        for authority in child_options:
                            try:
                                await child_combo.click(timeout=3000)
                            except Exception:
                                continue
                            page._pipeline_powerbi_filter_context = {
                                "region": area,
                                "authority": authority,
                            }
                            if not await self._select_filter_value(
                                report_frame, child_label, authority
                            ):
                                await child_combo.press("Escape")
                                continue
                            await asyncio.sleep(0.8)
                            page._pipeline_powerbi_filter_context = {
                                "region": area,
                                "authority": authority,
                            }

        async def _visit_download_regions(self, page, report_frame):
            """Select each region on Download data to expose its LA rows."""
            combo = report_frame.get_by_role(
                "combobox", name="Geographic area(s)", exact=True
            )
            if not await combo.count():
                return
            # The Download data visual finishes binding after the page tab is
            # visible; selecting it before the table is ready leaves the
            # virtualised popup without any option nodes.
            await asyncio.sleep(4.0)
            # Power BI keeps a multi-select popup open after an option click.
            # Using the option locator directly is materially more reliable
            # than re-discovering its virtualised listbox on every selection.
            await combo.click(timeout=3000)
            england = report_frame.get_by_role(
                "option", name="England", exact=True
            )
            if await england.count():
                await england.click(timeout=3000)
            previous = None
            for region in REGION_SELECTIONS:
                if previous:
                    old = report_frame.get_by_role("option", name=previous, exact=True)
                    if await old.count():
                        await old.click(timeout=3000)
                option = report_frame.get_by_role("option", name=region, exact=True)
                if not await option.count():
                    continue
                page._pipeline_powerbi_filter_context = {"region": region}
                await option.click(timeout=3000)
                await asyncio.sleep(1.0)
                previous = region

        async def on_failure(self, failure):
            request = failure.request
            self.result_queue.put(
                PowerBICapture(
                    dashboard_url=request.url,
                    response_url="",
                    method="GET",
                    status_code=0,
                    content_type=None,
                    body=b"",
                    request_body_sha256="",
                    retrieved_at=datetime.now(timezone.utc),
                    sequence=0,
                    error=f"{type(failure.value).__name__}: {failure.value}",
                )
            )

    return _PowerBISpider
