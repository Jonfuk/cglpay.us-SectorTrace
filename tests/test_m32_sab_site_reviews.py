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
        "VALUES (%s, %s, %s, 'https://dir', '2026-01-01T00:00:00Z', 200, 'test', 'h')",
        (name, nation, url))
    conn.commit()


def _mock_board_site(httpx_mock, *, links_html: str, origin: str = ORIGIN,
                      pdf: bytes = PDF_BYTES, homepage_only: bool = False):
    httpx_mock.add_response(url=f"{origin}/robots.txt", status_code=404, text="",
                             is_reusable=True)
    for path in m32.SAR_PATHS:
        # "/" is not a SAR index path; the named ones are. homepage_only
        # serves the links on "/" alone so a candidate stays from_index=False.
        body = links_html if (path == "/" or not homepage_only) else "<p>nothing</p>"
        httpx_mock.add_response(url=f"{origin}{path}", status_code=200,
                                 text=f"<html><body>{body}</body></html>", is_reusable=True)
    if ".pdf" in links_html or ".docx" in links_html:
        httpx_mock.add_response(url=re.compile(rf"{re.escape(origin)}/.*\.(pdf|docx)"),
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


def test_sar_links_on_page_index_mode_keeps_every_document():
    """On a page reached via a SAR link, a document linked only as a
    pseudonym is still collected."""
    html = ('<a href="/d/anne-2023.pdf">Anne (2023)</a>'
            '<a href="/d/brian-overview.pdf">Brian</a>')
    plain = m32.sar_links_on_page(html, f"{ORIGIN}/x", "camden.example.gov.uk")
    indexed = m32.sar_links_on_page(html, f"{ORIGIN}/x", "camden.example.gov.uk",
                                     is_sar_index=True)
    assert plain == []
    assert len(indexed) == 2


def test_sar_links_on_page_treats_www_and_bare_host_as_the_same_site():
    html = '<a href="https://www.camden.example.gov.uk/d/SAR-x.pdf">SAR: X</a>'
    links = m32.sar_links_on_page(html, "https://camden.example.gov.uk/reviews",
                                   "camden.example.gov.uk")
    assert len(links) == 1


def test_run_follows_one_hop_to_a_reviews_page(httpx_mock, settings, conn, monkeypatch):
    """The reviews are behind a 'Safeguarding Adults Reviews' link on the
    homepage, not under any guessed path."""
    _add_board(conn, "Camden Safeguarding Adults Board", ORIGIN)
    httpx_mock.add_response(url=f"{ORIGIN}/robots.txt", status_code=404, text="",
                             is_reusable=True)
    for path in m32.SAR_PATHS:
        body = ('<a href="/our-work/adult-reviews-page">Safeguarding Adults Reviews</a>'
                if path == "/" else "<p>not here</p>")
        httpx_mock.add_response(url=f"{ORIGIN}{path}", status_code=200,
                                 text=f"<html><body>{body}</body></html>", is_reusable=True)
    httpx_mock.add_response(
        url=f"{ORIGIN}/our-work/adult-reviews-page", status_code=200, is_reusable=True,
        text='<html><body><a href="/d/Camden SAR Matthew 2021.pdf">'
             'Safeguarding Adults Review: Matthew</a></body></html>')
    httpx_mock.add_response(url=re.compile(rf"{re.escape(ORIGIN)}/d/.*\.pdf"),
                             content=PDF_BYTES, status_code=200, is_reusable=True)
    monkeypatch.setattr(m28.pdftext, "page_texts", lambda *a, **k: [
        "Commissioned by Camden Safeguarding Adults Board."])

    m32.run(_ctx(conn, settings))

    assert conn.execute(
        "SELECT COUNT(*) AS n FROM sar_documents WHERE discovered_via = 'sab_website'"
    ).fetchone()["n"] == 1


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


def test_run_routes_a_weak_link_not_on_an_index_page_to_a_candidate(httpx_mock, settings, conn, monkeypatch):
    _add_board(conn, "Camden Safeguarding Adults Board", ORIGIN)
    # A weak-vocabulary link ("learning brief"), found only on the homepage
    # — not on a confirmed SAR index page. Still needs a person.
    _mock_board_site(httpx_mock, homepage_only=True, links_html=(
        '<a href="/d/Matthew-learning-brief.pdf">Learning brief: Matthew</a>'))
    monkeypatch.setattr(m28.pdftext, "page_texts", lambda *a, **k: [
        "A learning brief from Camden Safeguarding Adults Board."])

    m32.run(_ctx(conn, settings))

    assert conn.execute(
        "SELECT COUNT(*) AS n FROM sar_documents WHERE discovered_via = 'sab_website'"
    ).fetchone()["n"] == 0
    crawl = conn.execute("SELECT * FROM sab_site_crawls").fetchone()
    assert crawl["docs_candidate"] == 1


def test_run_auto_ingests_from_a_confirmed_index_page_despite_a_pseudonym_link(
        httpx_mock, settings, conn, monkeypatch):
    """The loosening: a document linked only as a pseudonym, but sitting on
    the board's own SAR listing page, is auto-ingested — the page context
    plus the board-consistent text is enough."""
    _add_board(conn, "Camden Safeguarding Adults Board", ORIGIN)
    _mock_board_site(httpx_mock, links_html='<a href="/d/anne-2022.pdf">Anne (2022)</a>')
    monkeypatch.setattr(m28.pdftext, "page_texts", lambda *a, **k: [
        "A Safeguarding Adults Review commissioned by Camden Safeguarding Adults Board."])

    m32.run(_ctx(conn, settings))

    row = conn.execute(
        "SELECT * FROM sar_documents WHERE discovered_via = 'sab_website'").fetchone()
    assert row is not None and row["sab_name"] == "Camden Safeguarding Adults Board"


def test_run_never_auto_ingests_a_template_even_on_an_index_page(httpx_mock, settings, conn, monkeypatch):
    _add_board(conn, "Camden Safeguarding Adults Board", ORIGIN)
    _mock_board_site(httpx_mock, links_html=(
        '<a href="/d/SAR-referral-form.docx">SAR referral form</a>'))
    monkeypatch.setattr(m28.pdftext, "page_texts", lambda *a, **k: [""])

    m32.run(_ctx(conn, settings))

    assert conn.execute(
        "SELECT COUNT(*) AS n FROM sar_documents WHERE discovered_via = 'sab_website'"
    ).fetchone()["n"] == 0
    item = conn.execute(
        "SELECT context_json FROM review_queue WHERE item_type = 'sab_site_sar_candidate'"
    ).fetchone()
    assert "template or form" in item["context_json"]


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
        "'2026-01-01T00:00:00Z', 200, 'national_sar_library', %s)", (sha,))
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
