"""Module 34: Integrated Care Board governance documents.

The claim this module supports is only "this ICB published this document under
its governance area". Every governance document is captured; nothing is
evidence until a person promotes it, and the subject index only ranks the
review worklist. These tests pin that: all documents land as candidates, the
sector-relevant ones are indexed and surfaced, and icb_board_papers stays
empty.
"""
from __future__ import annotations

import re

from pipeline.modules import m28_sar_reports as m28
from pipeline.modules import m34_icb_board_papers as m34
from pipeline.registry import ModuleContext

DIRECTORY = m34.DIRECTORY_URL
ORIGIN = "https://notts.icb.nhs.uk"
BOARD_PATH = "/about-us/our-icb-board/"

SUBJECT_PDF = b"%PDF-1.4 notts subject pack"
PLAIN_PDF = b"%PDF-1.4 notts finance report"


def _ctx(conn, settings, since=None, limit=None):
    return ModuleContext(conn=conn, settings=settings, since=since,
                          dry_run=False, limit=limit)


def _directory_html(anchors: str) -> str:
    return f"<html><body><main>{anchors}</main></body></html>"


NOTTS_ANCHOR = (f'<a href="{ORIGIN}/">NHS Nottingham and Nottinghamshire '
                f'Integrated Care Board</a>')


def _mock_directory(httpx_mock, anchors: str = NOTTS_ANCHOR):
    httpx_mock.add_response(url="https://www.england.nhs.uk/robots.txt",
                             status_code=404, text="", is_reusable=True)
    httpx_mock.add_response(url=DIRECTORY, status_code=200,
                             text=_directory_html(anchors), is_reusable=True)


def _mock_icb_site(httpx_mock, *, board_html: str, origin: str = ORIGIN,
                    docs: list[str] | None = None):
    httpx_mock.add_response(url=f"{origin}/robots.txt", status_code=404, text="",
                             is_reusable=True)
    for path in dict.fromkeys([BOARD_PATH, *m34.MEETING_PATHS]):
        body = board_html if path == BOARD_PATH else "<p>nothing here</p>"
        httpx_mock.add_response(url=f"{origin}{path}", status_code=200,
                                 text=f"<html><body>{body}</body></html>",
                                 is_reusable=True)
    # Register only the document URLs actually fetched (docs override, else
    # every .pdf linked on the board page), so pytest-httpx's "every response
    # was requested" check stays meaningful.
    for href in (docs if docs is not None else re.findall(r'href="([^"]+\.pdf)"', board_html)):
        content = SUBJECT_PDF if "subject" in href else PLAIN_PDF
        httpx_mock.add_response(url=f"{origin}{href}", content=content,
                                 status_code=200, is_reusable=True)


def _text_by_body(*_args, **_kwargs):
    body = _args[3] if len(_args) > 3 else _kwargs.get("body", b"")
    if b"subject" in body:
        return ["Board pack. The Quality Committee noted drug and alcohol "
                "treatment pressures and that Change Grow Live reported staff "
                "vacancy and recruitment problems."]
    return ["Finance report. Month 6 position and capital programme update."]


# --- unit: parsers -----------------------------------------------------------


def test_parse_directory_keeps_only_icb_anchors():
    html = (
        '<a href="https://notts.icb.nhs.uk/">NHS Nottingham and Nottinghamshire '
        'Integrated Care Board</a>'
        '<a href="https://www.england.nhs.uk/about/">About NHS England</a>'
        '<a href="https://bsol.icb.nhs.uk/">Birmingham and Solihull ICB</a>'
    )
    rows = m34.parse_directory(html)
    names = sorted(r["name"] for r in rows)
    assert names == ["Birmingham and Solihull ICB",
                     "NHS Nottingham and Nottinghamshire Integrated Care Board"]


def test_parse_meeting_date_reads_written_and_numeric_dates():
    assert m34.parse_meeting_date("Board papers - 25 September 2025") == "2025-09-25"
    assert m34.parse_meeting_date("2025-09-25 agenda") == "2025-09-25"
    assert m34.parse_meeting_date("agenda 25/09/2025") == "2025-09-25"
    assert m34.parse_meeting_date("Board pack (no date)") is None


def test_classify_kind_and_committee_name():
    assert m34._classify_kind("/x/board-papers-sept.pdf", "Board papers") == "board_pack"
    assert m34._classify_kind("/x/agenda.pdf", "Agenda") == "agenda"
    assert m34._classify_kind("/x/thing.pdf", "Some enclosure") == "enclosure"
    assert m34._committee_name("/x.pdf", "Finance and Performance Committee pack") \
        == "Finance and Performance Committee"
    assert m34._committee_name("/board/x.pdf", "Board papers") is None


def test_subject_terms_counts_substance_and_workforce_vocab():
    terms = m34._subject_terms("drug and alcohol services; vacancy and recruitment; "
                                "recruitment again")
    assert terms.get("drug") == 1
    assert terms.get("alcohol") == 1
    assert terms.get("recruitment") == 2


# --- integration: the run --------------------------------------------------------


def test_run_captures_every_document_and_indexes_the_sector_relevant_one(
        httpx_mock, settings, conn, monkeypatch):
    _mock_directory(httpx_mock)
    _mock_icb_site(httpx_mock, board_html=(
        '<a href="/board/2025/subject-board-pack-25-september-2025.pdf">'
        'Board papers - 25 September 2025</a>'
        '<a href="/board/2025/finance-report-m6.pdf">Finance report Month 6</a>'))
    monkeypatch.setattr(m28.pdftext, "page_texts", _text_by_body)

    m34.run(_ctx(conn, settings))

    rows = conn.execute(
        "SELECT document_url, has_body_text, subject_hits, provider_mentions, "
        "document_kind, meeting_date FROM icb_board_paper_candidates "
        "ORDER BY document_url").fetchall()
    assert len(rows) == 2, "every governance document is captured, not just the relevant one"
    by_url = {r["document_url"].rsplit("/", 1)[-1]: r for r in rows}

    subject = by_url["subject-board-pack-25-september-2025.pdf"]
    assert subject["has_body_text"] == 1
    assert subject["subject_hits"] > 0
    assert subject["provider_mentions"] == 1
    assert subject["meeting_date"] == "2025-09-25"
    assert subject["document_kind"] == "board_pack"

    plain = by_url["finance-report-m6.pdf"]
    assert plain["has_body_text"] == 1
    assert plain["subject_hits"] == 0
    assert plain["provider_mentions"] == 0

    crawl = conn.execute("SELECT * FROM icb_site_crawls").fetchone()
    assert crawl["status"] == "ok"
    assert crawl["docs_found"] == 2
    assert crawl["docs_with_subject"] == 1

    assert conn.execute(
        "SELECT COUNT(*) AS n FROM icb_paper_provider_mentions "
        "WHERE provider_key = 'change_grow_live'").fetchone()["n"] == 1
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM restricted_icb_paper_snippets").fetchone()["n"] >= 1


def test_run_seeds_the_icb_reference_table_with_provenance(httpx_mock, settings, conn,
                                                            monkeypatch):
    _mock_directory(httpx_mock)
    _mock_icb_site(httpx_mock, board_html="<p>no papers</p>")
    monkeypatch.setattr(m28.pdftext, "page_texts", _text_by_body)

    m34.run(_ctx(conn, settings))

    row = conn.execute("SELECT * FROM integrated_care_boards").fetchone()
    assert row["name"] == "NHS Nottingham and Nottinghamshire Integrated Care Board"
    assert row["board_url"] == "https://notts.icb.nhs.uk/about-us/our-icb-board/"
    assert row["board_url_source"] == "registry"
    assert row["payload_sha256"] and row["source_system"] == m34.SOURCE_DIRECTORY


def test_run_never_writes_to_the_evidence_table(httpx_mock, settings, conn, monkeypatch):
    _mock_directory(httpx_mock)
    _mock_icb_site(httpx_mock, board_html=(
        '<a href="/board/subject-pack.pdf">Safeguarding and drug treatment board pack</a>'))
    monkeypatch.setattr(m28.pdftext, "page_texts", _text_by_body)

    m34.run(_ctx(conn, settings))

    assert conn.execute("SELECT COUNT(*) AS n FROM icb_board_papers").fetchone()["n"] == 0


def test_run_records_no_documents_found_with_a_crawl_row(httpx_mock, settings, conn,
                                                          monkeypatch):
    _mock_directory(httpx_mock)
    _mock_icb_site(httpx_mock, board_html='<a href="/about">About the board</a>')
    monkeypatch.setattr(m28.pdftext, "page_texts", _text_by_body)

    m34.run(_ctx(conn, settings))

    crawl = conn.execute("SELECT * FROM icb_site_crawls").fetchone()
    assert crawl["status"] == "no_documents_found"
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM review_queue WHERE item_type = 'icb_no_documents_found'"
    ).fetchone()["n"] == 1


def test_run_since_skips_an_older_meeting(httpx_mock, settings, conn, monkeypatch):
    _mock_directory(httpx_mock)
    _mock_icb_site(httpx_mock, board_html=(
        '<a href="/board/subject-pack-10-january-2021.pdf">Board papers 10 January 2021</a>'
        '<a href="/board/subject-pack-25-september-2025.pdf">Board papers 25 September 2025</a>'),
        docs=["/board/subject-pack-25-september-2025.pdf"])   # the 2021 one is --since-skipped
    monkeypatch.setattr(m28.pdftext, "page_texts", _text_by_body)

    m34.run(_ctx(conn, settings, since="2024-01-01"))

    urls = [r["document_url"].rsplit("/", 1)[-1] for r in conn.execute(
        "SELECT document_url FROM icb_board_paper_candidates").fetchall()]
    assert urls == ["subject-pack-25-september-2025.pdf"]
