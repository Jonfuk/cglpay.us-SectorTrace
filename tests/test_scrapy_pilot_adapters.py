"""Fixture-backed coverage for the adapter-only Scrapy module pilots."""
from __future__ import annotations

import hashlib
import http.server
import threading
from pathlib import Path
from urllib.parse import unquote

import pytest

pytest.importorskip("scrapy")

from pipeline.config import Settings
from pipeline.transports.pilots.m22_provider_pay_pages_pilot import fetch_m22_pilot
from pipeline.transports.pilots.m24_council_spend_pilot import fetch_m24_pilot
from pipeline.transports.pilots.m28_sar_reports_pilot import fetch_m28_pilot
from pipeline.transports.scrapy_transport import (
    ScrapyDisabled,
    _crawler_settings,
)


class _FixtureServer:
    def __init__(self, responses: dict[str, tuple[int, str, bytes]]):
        self.responses = responses
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def _handler(self):
        responses = self.responses

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - http.server API
                path = unquote(self.path.split("?", 1)[0])
                status, content_type, body = responses.get(
                    path, (404, "text/plain", b"not found"))
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        return Handler

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.thread.join(timeout=5)


@pytest.fixture
def fixture_server():
    servers: list[_FixtureServer] = []

    def start(responses):
        server = _FixtureServer(responses)
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.close()


@pytest.fixture
def scrapy_settings(tmp_path: Path) -> Settings:
    return Settings(
        contact_email="test@example.com",
        raw_archive_dir=tmp_path / "raw",
        scrapy_enabled=True,
        scrapy_autothrottle_enabled=False,
        scrapy_download_delay_seconds=0.0,
        scrapy_retry_max_attempts=1,
        scrapy_runner_timeout_seconds=30.0,
        _env_file=None,
    )


def test_scrapy_policy_uses_autothrottle_without_fixed_floor(tmp_path: Path):
    settings = Settings(
        contact_email="test@example.com", raw_archive_dir=tmp_path / "raw",
        scrapy_enabled=True, _env_file=None,
    )
    crawler = _crawler_settings(settings)
    assert crawler["AUTOTHROTTLE_ENABLED"] is True
    assert crawler["DOWNLOAD_DELAY"] == 0.0
    assert crawler["AUTOTHROTTLE_TARGET_CONCURRENCY"] == 0.5
    assert crawler["CONCURRENT_REQUESTS_PER_DOMAIN"] == 1
    assert crawler["AUTOTHROTTLE_MAX_DELAY"] == 60.0


def test_all_pilots_remain_disabled_by_default(tmp_path: Path):
    settings = Settings(
        contact_email="test@example.com", raw_archive_dir=tmp_path / "raw",
        _env_file=None,
    )
    with pytest.raises(ScrapyDisabled):
        fetch_m22_pilot({}, settings=settings)
    with pytest.raises(ScrapyDisabled):
        fetch_m24_pilot([], settings=settings)
    with pytest.raises(ScrapyDisabled):
        fetch_m28_pilot([], settings=settings)


def test_m22_pilot_reuses_bounded_link_and_pay_parser(fixture_server, scrapy_settings):
    server = fixture_server({
        "/robots.txt": (200, "text/plain", b"User-agent: *\nAllow: /\n"),
        "/": (200, "text/html", b'<a href="/pay">Pay and rewards</a>'),
        "/pay": (200, "text/html", "<h1>Rewards</h1><p>From £12.50 per hour.</p>".encode()),
    })
    crawl = fetch_m22_pilot(
        {"provider": [(server.base_url + "/", "fixture")]},
        settings=scrapy_settings,
    )
    assert [page.role for page in crawl.pages] == ["registered", "followed"]
    assert crawl.pages[1].mentions[0]["salary_min"] == 12.5
    for page in crawl.pages:
        page.result.require_provenance()


def test_m24_pilot_schedules_files_after_path_discovery(fixture_server, scrapy_settings):
    csv_body = b"Supplier,Amount,Description\nChange Grow Live,12.50,Support\n"
    server = fixture_server({
        "/robots.txt": (200, "text/plain", b"User-agent: *\nAllow: /\n"),
        "/": (200, "text/html", b'<a href="/payments.csv">Payments over 500</a>'),
        "/payments.csv": (200, "text/csv", csv_body),
    })
    crawl = fetch_m24_pilot(
        [({"ons_code": "E00000001", "name": "Test Council"}, server.base_url)],
        settings=scrapy_settings,
    )
    assert len(crawl.files) == 1
    assert crawl.files[0].rows[0]["payee"] == "Change Grow Live"
    assert crawl.files[0].rows[0]["amount"] == 12.5
    assert crawl.files[0].result.payload_sha256 == hashlib.sha256(csv_body).hexdigest()


def test_m28_pilot_deduplicates_library_documents(fixture_server, scrapy_settings):
    pdf_body = b"%PDF-1.4 fixture SAR"
    index = (
        b'<button class="collapsible">SARs 2026</button>'
        b'<table><tr><td>Test SAR</td><td><a href="/test.pdf">Download</a></td></tr></table>'
    )
    server = fixture_server({
        "/robots.txt": (200, "text/plain", b"User-agent: *\nAllow: /\n"),
        "/search.html": (200, "text/html", index),
        "/test.pdf": (200, "application/pdf", pdf_body),
    })
    crawl = fetch_m28_pilot(
        [server.base_url + "/search.html", server.base_url + "/search.html"],
        settings=scrapy_settings,
    )
    assert len(crawl.index_pages) == 1
    assert len(crawl.documents) == 1
    assert crawl.documents[0].title == "Test SAR"
    assert crawl.documents[0].result.payload_sha256 == hashlib.sha256(pdf_body).hexdigest()
