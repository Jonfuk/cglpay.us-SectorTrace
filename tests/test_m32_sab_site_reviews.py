"""Module 32: per-SAB website crawling.

The claim is "this board published this review on its own site". Most of
these tests are about the hybrid gate — a document is auto-ingested only
when the link is unambiguous AND the text names this board; everything else
is a review-queue candidate, and a document naming a different board is not
stored at all.
"""
from __future__ import annotations

import hashlib
import re

from pipeline.modules import m28_sar_reports as m28
from pipeline.modules import m32_sab_site_reviews as m32
from pipeline.registry import ModuleContext

ORIGIN = "https://camden.example.gov.uk"
PDF_BYTES = b"%PDF-1.4 fake camden review"


def _ctx(conn, settings):
    return ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)


def _add_board(conn, name, url, nation="England"):
    conn.execute(
        "INSERT INTO safeguarding_adults_boards (name, nation, website_url, "
        "source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?, ?, ?, 'https://dir', '2026-01-01T00:00:00Z', 200, 'test', 'h')",
        (name, nation, url))
    conn.commit()


def _mock_board_site(httpx_mock, *, links_html: str, origin: str = ORIGIN,
                      pdf: bytes = PDF_BYTES):
    httpx_mock.add_response(url=f"{origin}/robots.txt", status_code=404, text="",
                             is_reusable=True)
    for path in m32.SAR_PATHS:
        httpx_mock.add_response(url=f"{origin}{path}", status_code=200,
                                 text=f"<html><body>{links_html}</body></html>",
                                 is_reusable=True)
    if ".pdf" in links_html:
        httpx_mock.add_response(url=re.compile(rf"{re.escape(origin)}/.*\.pdf"),
                                 content=pdf, status_code=200, is_reusable=True)


# --- link discovery ---------------------------------------------------------

def test_sar_links_on_page_keeps_only_same_host_docs_with_sar_vocabulary():
    html = """
      <a href="/docs/Camden SAR Matthew Overview Report.pdf">Safeguarding Adults Review: Matthew</a>
      <a href="/docs/annual-report.pdf">Annual report 2024</a>
      <a href="https://other.example/x/SAR-report.pdf">SAR report</a>
      <a href="/safeguarding-policy">Our safeguarding policy</a>
    """
    links = m32.sar_links_on_page(html, f"{ORIGIN}/reviews", "camden.example.gov.uk")
    assert links == [(f"{ORIGIN}/docs/Camden SAR Matthew Overview Report.pdf",
                      "Safeguarding Adults Review: Matthew")]


def test_same_board_ignores_the_board_suffix_and_case():
    assert m32._same_board("Camden Safeguarding Adults Partnership Board",
                            "Camden Safeguarding Adults Board")
    assert not m32._same_board("Camden Safeguarding Adults Board",
                                "Islington Safeguarding Adults Board")


# --- the hybrid gate ------------------------------------------------------------

def test_run_auto_ingests_a_strong_link_whose_text_names_the_board(httpx_mock, settings, conn, monkeypatch):
    _add_board(conn, "Camden Safeguarding Adults Board", ORIGIN)
    _mock_board_site(httpx_mock, links_html=(
        '<a href="/d/Camden SAR Matthew 2021.pdf">Safeguarding Adults Review: Matthew</a>'))
    monkeypatch.setattr(m28.pdftext, "page_texts", lambda *a, **k: [
        "This Safeguarding Adults Review was commissioned by Camden Safeguarding "
        "Adults Board. Staffing pressures were noted."])

    m32.run(_ctx(conn, settings))

    row = conn.execute("SELECT * FROM sar_documents WHERE discovered_via = 'sab_website'").fetchone()
    assert row is not None
    assert row["sab_name"] == "Camden Safeguarding Adults Board"
    assert row["sab_name_source"] == "sab_website"
    assert row["library_year"] == 2021           # read from the filename
    assert row["has_body_text"] == 1
    crawl = conn.execute("SELECT * FROM sab_site_crawls").fetchone()
    assert crawl["status"] == "ok"
    assert crawl["docs_ingested"] == 1


def test_run_routes_a_weak_link_to_a_candidate_review_item(httpx_mock, settings, conn, monkeypatch):
    _add_board(conn, "Camden Safeguarding Adults Board", ORIGIN)
    # "learning brief" is SAR vocabulary but not the unambiguous phrase.
    _mock_board_site(httpx_mock, links_html=(
        '<a href="/d/Matthew-learning-brief.pdf">Learning brief: Matthew</a>'))
    monkeypatch.setattr(m28.pdftext, "page_texts", lambda *a, **k: [
        "A learning brief from Camden Safeguarding Adults Board."])

    m32.run(_ctx(conn, settings))

    assert conn.execute(
        "SELECT COUNT(*) AS n FROM sar_documents WHERE discovered_via = 'sab_website'"
    ).fetchone()["n"] == 0
    item = conn.execute(
        "SELECT * FROM review_queue WHERE item_type = 'sab_site_sar_candidate'").fetchone()
    assert item is not None
    crawl = conn.execute("SELECT * FROM sab_site_crawls").fetchone()
    assert crawl["docs_candidate"] == 1


def test_run_does_not_store_a_document_that_names_a_different_board(httpx_mock, settings, conn, monkeypatch):
    _add_board(conn, "Camden Safeguarding Adults Board", ORIGIN)
    _mock_board_site(httpx_mock, links_html=(
        '<a href="/d/Neighbour SAR.pdf">Safeguarding Adults Review</a>'))
    monkeypatch.setattr(m28.pdftext, "page_texts", lambda *a, **k: [
        "This Safeguarding Adults Review was commissioned by Islington Safeguarding Adults Board."])

    m32.run(_ctx(conn, settings))

    assert conn.execute(
        "SELECT COUNT(*) AS n FROM sar_documents WHERE discovered_via = 'sab_website'"
    ).fetchone()["n"] == 0
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM review_queue WHERE item_type = 'sab_site_sar_board_mismatch'"
    ).fetchone()["n"] == 1


def test_run_skips_a_byte_identical_library_document(httpx_mock, settings, conn, monkeypatch):
    _add_board(conn, "Camden Safeguarding Adults Board", ORIGIN)
    sha = hashlib.sha256(PDF_BYTES).hexdigest()
    conn.execute(
        "INSERT INTO sar_documents (document_url, document_ext, library_year, "
        "sab_name, has_body_text, discovered_via, source_url, retrieved_at, "
        "http_status, source_system, payload_sha256) VALUES "
        "('https://nationalnetwork.org.uk/x.pdf', '.pdf', 2021, "
        "'Camden Safeguarding Adults Board', 1, 'national_library', 'https://x', "
        "'2026-01-01T00:00:00Z', 200, 'national_sar_library', ?)", (sha,))
    conn.commit()
    _mock_board_site(httpx_mock, links_html=(
        '<a href="/d/Camden SAR Matthew.pdf">Safeguarding Adults Review: Matthew</a>'))
    monkeypatch.setattr(m28.pdftext, "page_texts", lambda *a, **k: [
        "Commissioned by Camden Safeguarding Adults Board."])

    m32.run(_ctx(conn, settings))

    assert conn.execute(
        "SELECT COUNT(*) AS n FROM sar_documents WHERE discovered_via = 'sab_website'"
    ).fetchone()["n"] == 0
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM review_queue WHERE item_type = 'possible_duplicate_of_library_sar'"
    ).fetchone()["n"] == 1


def test_run_records_no_sars_found_with_a_crawl_row(httpx_mock, settings, conn):
    _add_board(conn, "Camden Safeguarding Adults Board", ORIGIN)
    _mock_board_site(httpx_mock, links_html='<a href="/about">About the board</a>')

    m32.run(_ctx(conn, settings))

    crawl = conn.execute("SELECT * FROM sab_site_crawls").fetchone()
    assert crawl["status"] == "no_sars_found"
    assert crawl["pages_fetched"] >= 1
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM review_queue WHERE item_type = 'sab_no_sars_found'"
    ).fetchone()["n"] == 1


def test_run_is_england_only(httpx_mock, settings, conn):
    _add_board(conn, "Cardiff and Vale Safeguarding Board", "https://cardiff.example.wales",
               nation="Wales")
    m32.run(_ctx(conn, settings))
    assert conn.execute("SELECT COUNT(*) AS n FROM sab_site_crawls").fetchone()["n"] == 0


def test_run_flags_a_board_with_no_website(httpx_mock, settings, conn):
    conn.execute(
        "INSERT INTO safeguarding_adults_boards (name, nation, website_url, "
        "source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('Nowhere Safeguarding Adults Board', 'England', '', "
        "'https://dir', '2026-01-01T00:00:00Z', 200, 'test', 'h')")
    conn.commit()
    m32.run(_ctx(conn, settings))
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM review_queue WHERE item_type = 'sab_website_unknown'"
    ).fetchone()["n"] == 1
