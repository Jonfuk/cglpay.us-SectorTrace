"""scrapy.md Phase 2 parity: `crawl_board` (HTTPX) vs. the Scrapy pilot for
`m32_sab_site_reviews`.

Both paths call the exact same three functions — `sar_links_on_page`,
`sar_subpages_on_page`, `classify_document` — so a difference in output can
only come from the one thing that genuinely differs between them: how each
discovers and orders the fetches. These tests run both against the same
real, local fixture server (a socket, not `httpx_mock` — the Scrapy crawl
happens in a subprocess that cannot see a mock in this process) and assert
the candidate sets and classifications agree.

Skipped outright if the `scrapy` extra is not installed, same as
`test_transports_scrapy.py`.
"""
from __future__ import annotations

import hashlib
import http.server
import threading
from pathlib import Path
from urllib.parse import unquote

import pytest

pytest.importorskip("scrapy")

from pipeline.config import Settings
from pipeline.http import PipelineHTTPClient
from pipeline.modules import m32_sab_site_reviews as m32
from pipeline.transports.pilots.m32_sab_site_reviews_pilot import (
    _read_body_text,
    classify_pilot_documents,
    fetch_m32_pilot,
)

SAB_NAME = "Camden Safeguarding Adults Board"
PDF_BYTES = b"%PDF-1.4 fake camden review"


# --- a local, in-process fixture server --------------------------------------

def _make_handler(homepage_body: bytes, extra: dict[str, bytes]):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            # httpx and Scrapy disagree on whether a literal space in a path
            # (this fixture's document filenames have one, matching the real
            # boards m32 already crawls) gets percent-encoded before the
            # request is sent — httpx sends it literally, Scrapy encodes it.
            # Both are defensible; unquoting here is what makes one fixture
            # serve the right bytes to either.
            path = unquote(self.path)
            if path == "/robots.txt":
                body, status = b"User-agent: *\nAllow: /\n", 200
            elif path == "/":
                body, status = homepage_body, 200
            elif path in extra:
                body, status = extra[path], 200
            else:
                body, status = b"<p>nothing here</p>", 200
            self.send_response(status)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return Handler


@pytest.fixture
def board_server():
    """A factory fixture: call it with `(homepage_body, extra)` to start one
    server for the test. `extra` maps path -> body for every other URL the
    scenario needs (a document, a subpage). Each call gets its own server so
    a test using it more than once never shares state.
    """
    started: list[tuple[http.server.ThreadingHTTPServer, threading.Thread]] = []

    def make(homepage_body: bytes, extra: dict[str, bytes] | None = None) -> str:
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), _make_handler(homepage_body, extra or {}))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        started.append((server, thread))
        return f"http://127.0.0.1:{server.server_port}"

    yield make
    for server, thread in started:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture
def httpx_settings(tmp_path: Path) -> Settings:
    return Settings(contact_email="test@example.com", raw_archive_dir=tmp_path / "httpx-raw",
                     default_rate_limit_seconds=0.0, _env_file=None)


@pytest.fixture
def scrapy_settings(tmp_path: Path) -> Settings:
    return Settings(contact_email="test@example.com", raw_archive_dir=tmp_path / "scrapy-raw",
                     scrapy_enabled=True, scrapy_download_delay_seconds=0.0,
                     scrapy_retry_max_attempts=1, scrapy_runner_timeout_seconds=30.0,
                     _env_file=None)


def _run_httpx_crawl(base_url: str, settings: Settings):
    client = PipelineHTTPClient(m32.SOURCE_SYSTEM, settings=settings)
    try:
        return m32.crawl_board((SAB_NAME, base_url), client)
    finally:
        client.close()


def _classify_httpx_candidates(crawl, *, settings: Settings) -> dict[str, str]:
    """`document_url -> outcome`, extracting body text and classifying with
    the exact functions the pilot uses — see the module docstring for why
    comparing through the shared functions isolates what's actually being
    tested (discovery) from what is trivially identical either way
    (classification of the same body text).
    """
    outcomes: dict[str, str] = {}
    for fetched, link_text, from_index in crawl.candidates:
        document_url = fetched.final_url or fetched.url
        ext = m32.m28.document_extension(document_url)
        if ext is None:
            continue
        body_text, _source = _read_body_text(
            settings, ext, document_url, fetched.body, fetched.payload_sha256)
        classification = m32.classify_document(
            document_url=document_url, link_text=link_text, body_text=body_text,
            from_index=from_index, sab_name=SAB_NAME, sab_index={},
            duplicate_of_library=False)
        outcomes[document_url] = classification.outcome
    return outcomes


def _classify_pilot_crawl(crawl, *, settings: Settings) -> dict[str, str]:
    documents = classify_pilot_documents(crawl, settings=settings, sab_name=SAB_NAME)
    return {doc.document_url: doc.outcome for doc in documents}


def _norm(url: str) -> str:
    """httpx and Scrapy disagree on percent-encoding a literal space in a
    path (see `_make_handler`) — comparisons below normalise both sides so
    that difference, which is not a difference in what was fetched, does not
    read as one.
    """
    return unquote(url)


# --- parity scenarios, mirroring tests/test_m32_sab_site_reviews.py's own --

def test_parity_strong_link_auto_ingests_on_both_paths(
        board_server, httpx_settings, scrapy_settings, monkeypatch):
    homepage = (b'<html><body><a href="/d/Camden SAR Matthew 2021.pdf">'
                b'Safeguarding Adults Review: Matthew</a></body></html>')
    base_url = board_server(homepage, {"/d/Camden SAR Matthew 2021.pdf": PDF_BYTES})
    monkeypatch.setattr(m32.m28.pdftext, "page_texts", lambda *a, **k: [
        "Commissioned by Camden Safeguarding Adults Board."])

    httpx_crawl = _run_httpx_crawl(base_url, httpx_settings)
    pilot_crawl = fetch_m32_pilot(SAB_NAME, base_url, settings=scrapy_settings)

    httpx_urls = {_norm(f.final_url or f.url) for f, _t, _i in httpx_crawl.candidates}
    pilot_urls = {_norm(r.result.final_url or r.result.requested_url) for r in pilot_crawl.documents}
    assert httpx_urls == pilot_urls == {f"{base_url}/d/Camden SAR Matthew 2021.pdf"}

    httpx_hashes = {f.payload_sha256 for f, _t, _i in httpx_crawl.candidates}
    pilot_hashes = {r.result.payload_sha256 for r in pilot_crawl.documents}
    assert httpx_hashes == pilot_hashes == {hashlib.sha256(PDF_BYTES).hexdigest()}

    httpx_outcomes = {_norm(u): o for u, o in
                       _classify_httpx_candidates(httpx_crawl, settings=httpx_settings).items()}
    pilot_outcomes = {_norm(u): o for u, o in
                       _classify_pilot_crawl(pilot_crawl, settings=scrapy_settings).items()}
    assert httpx_outcomes == pilot_outcomes == {
        f"{base_url}/d/Camden SAR Matthew 2021.pdf": "ingest"}


def test_parity_weak_link_off_index_is_a_candidate_on_both_paths(
        board_server, httpx_settings, scrapy_settings, monkeypatch):
    homepage = (b'<html><body><a href="/d/Matthew-learning-brief.pdf">'
                b'Learning brief: Matthew</a></body></html>')
    base_url = board_server(homepage, {"/d/Matthew-learning-brief.pdf": PDF_BYTES})
    monkeypatch.setattr(m32.m28.pdftext, "page_texts", lambda *a, **k: [
        "A learning brief from Camden Safeguarding Adults Board."])

    httpx_crawl = _run_httpx_crawl(base_url, httpx_settings)
    pilot_crawl = fetch_m32_pilot(SAB_NAME, base_url, settings=scrapy_settings)

    httpx_outcomes = {_norm(u): o for u, o in
                       _classify_httpx_candidates(httpx_crawl, settings=httpx_settings).items()}
    pilot_outcomes = {_norm(u): o for u, o in
                       _classify_pilot_crawl(pilot_crawl, settings=scrapy_settings).items()}
    expected = {f"{base_url}/d/Matthew-learning-brief.pdf": "candidate"}
    assert httpx_outcomes == expected
    assert pilot_outcomes == expected


def test_parity_board_mismatch_on_both_paths(
        board_server, httpx_settings, scrapy_settings, monkeypatch):
    homepage = (b'<html><body><a href="/d/Neighbour SAR.pdf">'
                b'Safeguarding Adults Review</a></body></html>')
    base_url = board_server(homepage, {"/d/Neighbour SAR.pdf": PDF_BYTES})
    monkeypatch.setattr(m32.m28.pdftext, "page_texts", lambda *a, **k: [
        "This Safeguarding Adults Review was commissioned by "
        "Islington Safeguarding Adults Board."])

    httpx_crawl = _run_httpx_crawl(base_url, httpx_settings)
    pilot_crawl = fetch_m32_pilot(SAB_NAME, base_url, settings=scrapy_settings)

    httpx_outcomes = {_norm(u): o for u, o in
                       _classify_httpx_candidates(httpx_crawl, settings=httpx_settings).items()}
    pilot_outcomes = {_norm(u): o for u, o in
                       _classify_pilot_crawl(pilot_crawl, settings=scrapy_settings).items()}
    expected = {f"{base_url}/d/Neighbour SAR.pdf": "board_mismatch"}
    assert httpx_outcomes == expected
    assert pilot_outcomes == expected


def test_parity_follows_one_hop_to_a_reviews_subpage(
        board_server, httpx_settings, scrapy_settings, monkeypatch):
    """The reviews are behind a 'Safeguarding Adults Reviews' link on the
    homepage, not under any guessed SAR_PATHS path — the same scenario
    tests/test_m32_sab_site_reviews.py's own subpage test exercises.
    """
    homepage = (b'<html><body><a href="/our-work/adult-reviews-page">'
                b'Safeguarding Adults Reviews</a></body></html>')
    subpage = (b'<html><body><a href="/d/Camden SAR Matthew 2021.pdf">'
               b'Safeguarding Adults Review: Matthew</a></body></html>')
    base_url = board_server(homepage, {
        "/our-work/adult-reviews-page": subpage,
        "/d/Camden SAR Matthew 2021.pdf": PDF_BYTES,
    })
    monkeypatch.setattr(m32.m28.pdftext, "page_texts", lambda *a, **k: [
        "Commissioned by Camden Safeguarding Adults Board."])

    httpx_crawl = _run_httpx_crawl(base_url, httpx_settings)
    pilot_crawl = fetch_m32_pilot(SAB_NAME, base_url, settings=scrapy_settings)

    expected_url = f"{base_url}/d/Camden SAR Matthew 2021.pdf"
    httpx_urls = {_norm(f.final_url or f.url) for f, _t, _i in httpx_crawl.candidates}
    pilot_urls = {_norm(r.result.final_url or r.result.requested_url) for r in pilot_crawl.documents}
    assert httpx_urls == pilot_urls == {expected_url}

    # Found via the subpage, so from_index is True on both paths — which is
    # what lets the "loosening" auto-ingest a pseudonym-only link elsewhere;
    # here it corroborates the already-strong link.
    httpx_from_index = {t for _f, _txt, t in httpx_crawl.candidates}
    pilot_from_index = {r.from_index for r in pilot_crawl.documents}
    assert httpx_from_index == pilot_from_index == {True}

    httpx_outcomes = {_norm(u): o for u, o in
                       _classify_httpx_candidates(httpx_crawl, settings=httpx_settings).items()}
    pilot_outcomes = {_norm(u): o for u, o in
                       _classify_pilot_crawl(pilot_crawl, settings=scrapy_settings).items()}
    assert httpx_outcomes == pilot_outcomes == {expected_url: "ingest"}


def test_parity_robots_disallowed_on_both_paths(board_server, httpx_settings, scrapy_settings):
    class DisallowingHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/robots.txt":
                body, status = b"User-agent: *\nDisallow: /\n", 200
            else:
                body, status = b"should never be fetched", 200
            self.send_response(status)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), DisallowingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"

        httpx_crawl = _run_httpx_crawl(base_url, httpx_settings)
        pilot_crawl = fetch_m32_pilot(SAB_NAME, base_url, settings=scrapy_settings)

        assert httpx_crawl.robots_blocked is True
        assert pilot_crawl.robots_blocked is True
        assert httpx_crawl.candidates == []
        assert pilot_crawl.documents == ()
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_parity_no_sars_found_on_both_paths(board_server, httpx_settings, scrapy_settings):
    base_url = board_server(b'<html><body><a href="/about">About the board</a></body></html>')

    httpx_crawl = _run_httpx_crawl(base_url, httpx_settings)
    pilot_crawl = fetch_m32_pilot(SAB_NAME, base_url, settings=scrapy_settings)

    assert httpx_crawl.candidates == []
    assert pilot_crawl.documents == ()
    assert httpx_crawl.pages_fetched >= 1
    assert pilot_crawl.pages_fetched >= 1
    assert httpx_crawl.robots_blocked is False
    assert pilot_crawl.robots_blocked is False


# --- pilot-specific behaviour, no HTTPX counterpart needed -------------------

def test_pilot_provenance_is_complete_for_every_document(
        board_server, scrapy_settings, monkeypatch):
    homepage = (b'<html><body><a href="/d/Camden SAR Matthew 2021.pdf">'
                b'Safeguarding Adults Review: Matthew</a></body></html>')
    base_url = board_server(homepage, {"/d/Camden SAR Matthew 2021.pdf": PDF_BYTES})

    crawl = fetch_m32_pilot(SAB_NAME, base_url, settings=scrapy_settings)
    assert len(crawl.documents) == 1
    [record] = crawl.documents
    record.result.require_provenance()  # must not raise
    assert record.result.payload_sha256 == hashlib.sha256(PDF_BYTES).hexdigest()
    assert record.result.raw_archive_ref is not None

    archived = (scrapy_settings.raw_archive_dir / "sab_website_pilot"
                / f"{record.result.payload_sha256}.html")
    assert archived.read_bytes() == PDF_BYTES


def test_pilot_disabled_by_default(tmp_path):
    from pipeline.transports.scrapy_transport import ScrapyDisabled

    settings = Settings(contact_email="test@example.com",
                         raw_archive_dir=tmp_path / "raw", _env_file=None)
    with pytest.raises(ScrapyDisabled):
        fetch_m32_pilot(SAB_NAME, "https://example.invalid/", settings=settings)
