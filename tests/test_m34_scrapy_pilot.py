"""Offline parity coverage for the m34 Scrapy pilot.

The fixture is a real local socket because the pilot runs in a spawned
subprocess; neither this test nor the pilot is allowed to fetch a live source.
The production m34 module is still exercised through its HTTPX crawl function
for the comparison, but neither path writes the database here.
"""
from __future__ import annotations

import hashlib
import http.server
import threading
from pathlib import Path
from urllib.parse import unquote

import pytest

pytest.importorskip("scrapy")

from pipeline.archive import FilesystemArchive
from pipeline.config import Settings
from pipeline.http import PipelineHTTPClient
from pipeline.modules import m34_icb_board_papers as m34
from pipeline.transports.pilots.m34_icb_board_papers_pilot import fetch_m34_pilot

ICB_NAME = "NHS Testshire Integrated Care Board"
PAPER_BYTES = b"%PDF-1.4 testshire board paper"
MINUTES_BYTES = b"PK fake testshire minutes docx"


@pytest.fixture
def fixture_server():
    servers: list[tuple[http.server.ThreadingHTTPServer, threading.Thread]] = []

    def start() -> str:
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                path = unquote(self.path)
                if path == "/robots.txt":
                    body, status, content_type = b"User-agent: *\nAllow: /\n", 200, "text/plain"
                elif path in ("/", "/board"):
                    body = (
                        b'<a href="/governance/meetings">Board meetings</a>'
                        b'<a href="/papers/2026-08-01-board-pack.pdf">Board pack</a>'
                    )
                    status, content_type = 200, "text/html"
                elif path == "/governance/meetings":
                    body = (
                        b'<a href="/papers/2026-08-01-board-pack.pdf">Minutes</a>'
                        b'<a href="/papers/2026-07-01-committee-minutes.docx">'
                        b'Committee minutes</a>'
                    )
                    status, content_type = 200, "text/html"
                elif path == "/papers/2026-08-01-board-pack.pdf":
                    body, status, content_type = PAPER_BYTES, 200, "application/pdf"
                elif path == "/papers/2026-07-01-committee-minutes.docx":
                    body, status, content_type = MINUTES_BYTES, 200, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                else:
                    body, status, content_type = b"<p>no governance papers here</p>", 200, "text/html"
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        return f"http://127.0.0.1:{server.server_port}/board"

    yield start
    for server, thread in servers:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture
def httpx_settings(tmp_path: Path) -> Settings:
    return Settings(
        contact_email="test@example.com", raw_archive_dir=tmp_path / "httpx-raw",
        default_rate_limit_seconds=0.0, _env_file=None,
    )


@pytest.fixture
def scrapy_settings(tmp_path: Path) -> Settings:
    return Settings(
        contact_email="test@example.com", raw_archive_dir=tmp_path / "scrapy-raw",
        scrapy_enabled=True, scrapy_download_delay_seconds=0.0,
        scrapy_retry_max_attempts=1, scrapy_runner_timeout_seconds=30.0,
        _env_file=None,
    )


def _httpx_crawl(seed_url: str, settings: Settings, *, from_registry: bool = False):
    client = PipelineHTTPClient(m34.SOURCE_SYSTEM, settings=settings)
    try:
        return m34.crawl_icb((ICB_NAME, seed_url, from_registry, None), client)
    finally:
        client.close()


def _candidate_signature(crawl):
    return [
        (
            fetched.final_url or fetched.requested_url,
            link_text,
            from_index,
            method,
            fetched.status_code,
            fetched.payload_sha256,
        )
        for fetched, link_text, from_index, method in crawl.candidates
    ]


def test_m34_pilot_matches_httpx_discovery_and_provenance(
        fixture_server, httpx_settings, scrapy_settings):
    seed_url = fixture_server().replace("/board", "/")

    httpx_crawl = _httpx_crawl(seed_url, httpx_settings)
    pilot_crawl = fetch_m34_pilot(
        ICB_NAME, seed_url, from_registry=False, settings=scrapy_settings)

    assert not pilot_crawl.review_items, pilot_crawl.review_items
    assert _candidate_signature(httpx_crawl) == _candidate_signature(pilot_crawl)
    assert pilot_crawl.pages_fetched == httpx_crawl.pages_fetched
    assert pilot_crawl.board_url == httpx_crawl.board_url
    assert pilot_crawl.board_url_source == httpx_crawl.board_url_source
    assert pilot_crawl.review_items == httpx_crawl.review_items == []
    assert [item[1] for item in pilot_crawl.candidates] == [
        "Board pack", "Committee minutes"]
    for fetched, _text, _from_index, _method in pilot_crawl.candidates:
        fetched.require_provenance()
        assert fetched.raw_archive_ref is not None
    [(fetched, _text, _from_index, _method), _second] = pilot_crawl.candidates
    assert fetched.payload_sha256 == hashlib.sha256(PAPER_BYTES).hexdigest()
    assert (scrapy_settings.raw_archive_dir / m34.SOURCE_SYSTEM
            / f"{fetched.payload_sha256}.pdf").read_bytes() == PAPER_BYTES


def test_m34_pilot_disabled_by_default(tmp_path: Path):
    from pipeline.transports.scrapy_transport import ScrapyDisabled

    settings = Settings(
        contact_email="test@example.com", raw_archive_dir=tmp_path / "raw",
        _env_file=None,
    )
    with pytest.raises(ScrapyDisabled):
        fetch_m34_pilot(
            ICB_NAME, "https://example.invalid/board", from_registry=True,
            settings=settings,
        )


def test_m34_pilot_can_release_bodies_after_archiving(
        fixture_server, scrapy_settings):
    seed_url = fixture_server().replace("/board", "/")
    crawl = fetch_m34_pilot(
        ICB_NAME, seed_url, from_registry=False, settings=scrapy_settings,
        retain_bodies=False)

    archive = FilesystemArchive(scrapy_settings.raw_archive_dir)
    assert crawl.candidates
    for fetched, _text, _from_index, _method in crawl.candidates:
        assert fetched.body == b""
        stored = archive.lookup(fetched.source_system, fetched.payload_sha256)
        assert stored is not None
        assert hashlib.sha256(stored.read_bytes()).hexdigest() == fetched.payload_sha256
