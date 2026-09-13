"""Module 36: GOV.UK Search API / Content API publication discovery.

Discovery, not extraction, same shape as m09: every attachment is a
candidate, none is evidence, and the two honest limits (a paged query says
when it hit its cap; an attachment with no bytes to archive is never stored)
are exercised directly rather than trusted by inspection.
"""
from __future__ import annotations

import re
from pathlib import Path

from pipeline.modules import m36_govuk_publications as govuk
from pipeline.registry import ModuleContext

FIXTURES = Path(__file__).parent / "fixtures"

CONTENT_URL = ("https://www.gov.uk/api/content/government/publications/"
               "dhsc-drug-strategy")


def _allow_all_robots(httpx_mock, origin: str = "https://www.gov.uk") -> None:
    httpx_mock.add_response(url=f"{origin}/robots.txt", status_code=200, text="", is_reusable=True)


def _hit(**overrides) -> dict:
    hit = {
        "content_id": "11111111-1111-1111-1111-111111111111",
        "title": "DHSC drug strategy",
        "link": "/government/publications/dhsc-drug-strategy",
        "public_timestamp": "2024-05-01T00:00:00.000+00:00",
        "format": "policy_paper",
    }
    hit.update(overrides)
    return hit


def _search_response(*hits, total: int | None = None) -> dict:
    hits = list(hits)
    return {"results": hits, "total": total if total is not None else len(hits)}


def _attachment(**overrides) -> dict:
    attachment = {
        "attachment_type": "file",
        "url": "https://assets.publishing.service.gov.uk/dhsc.pdf",
        "title": "Full strategy (PDF)",
        "content_type": "application/pdf",
        "id": "att-1",
    }
    attachment.update(overrides)
    return attachment


def _content_detail(*attachments, **overrides) -> dict:
    detail = {
        "content_id": "11111111-1111-1111-1111-111111111111",
        "title": "DHSC drug strategy",
        "base_path": "/government/publications/dhsc-drug-strategy",
        "document_type": "policy_paper",
        "public_updated_at": "2024-05-01T00:00:00.000+00:00",
        "first_published_at": "2024-04-01T00:00:00.000+00:00",
        "details": {"attachments": list(attachments) or [_attachment()]},
        "links": {"organisations": [
            {"title": "Department of Health and Social Care",
             "base_path": "/government/organisations/department-of-health-and-social-care"},
        ]},
    }
    detail.update(overrides)
    return detail


# --- confidence -----------------------------------------------------------

def test_confidence_counts_every_signal():
    assert govuk.confidence("policy_paper", "department-of-health-and-social-care",
                             "application/pdf") == 1.0


def test_confidence_drops_for_an_unhelpful_type():
    assert govuk.confidence("press_release", "some-other-organisation",
                             "text/html") == 0.25


# --- end to end -------------------------------------------------------------

def test_run_stores_one_candidate_per_content_item_across_keywords(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(
        url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"),
        json=_search_response(_hit()), is_reusable=True)
    httpx_mock.add_response(
        url=CONTENT_URL, json=_content_detail(), is_reusable=True)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    govuk.run(ctx)

    rows = conn.execute("SELECT * FROM govuk_document_candidates").fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["publishing_organisation"] == "department-of-health-and-social-care"
    assert row["candidate_url"] == "https://assets.publishing.service.gov.uk/dhsc.pdf"
    assert row["content_id"] == "11111111-1111-1111-1111-111111111111"
    assert row["document_type_guess"] == "policy_paper"
    assert row["confidence"] == 1.0
    # Found under every keyword, across both organisation searches, but
    # de-duplicated -- the row says everything this pipeline found it under,
    # once each.
    assert set(row["matched_terms"].split(",")) == set(govuk.SUBSTANCE_MISUSE_KEYWORDS)

    content_calls = [r for r in httpx_mock.get_requests() if "api/content" in str(r.url)]
    assert len(content_calls) == 1, (
        "the same content item must be fetched once per run, not once per keyword hit")


def test_run_writes_the_review_markdown(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(
        url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"),
        json=_search_response(_hit()), is_reusable=True)
    httpx_mock.add_response(
        url=CONTENT_URL, json=_content_detail(), is_reusable=True)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    govuk.run(ctx)

    out_path = (Path(settings.logs_dir).parent / "docs" / "verification"
                / "govuk_publication_candidates.md")
    text = out_path.read_text(encoding="utf-8")
    assert "department-of-health-and-social-care" in text
    assert "Full strategy (PDF)" in text  # the attachment's own title, not the page's


def test_an_external_attachment_is_not_a_candidate(httpx_mock, settings, conn):
    """No bytes to archive on promotion, so it is never stored -- not even at
    zero confidence."""
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(
        url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"),
        json=_search_response(_hit()), is_reusable=True)
    httpx_mock.add_response(
        url=CONTENT_URL,
        json=_content_detail(_attachment(attachment_type="external",
                                          url="https://example.com/report",
                                          content_type=None)),
        is_reusable=True)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    govuk.run(ctx)

    assert conn.execute("SELECT COUNT(*) c FROM govuk_document_candidates").fetchone()["c"] == 0


def test_run_raises_a_review_item_when_a_query_is_capped(httpx_mock, settings, conn):
    """The catalogue says a huge number of results; the module reads
    MAX_PAGES worth and says so. One hit per mocked page is enough to prove
    the cap fires -- the search response's own declared `total` is what
    drives it, not how many results happen to be on any one page."""
    _allow_all_robots(httpx_mock)
    page = _search_response(_hit(), total=1_000_000)
    httpx_mock.add_response(
        url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"),
        json=page, is_reusable=True)
    httpx_mock.add_response(
        url=CONTENT_URL, json=_content_detail(), is_reusable=True)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    govuk.run(ctx)

    review = conn.execute(
        "SELECT * FROM review_queue WHERE item_type='govuk_search_capped'").fetchall()
    assert review, "the cap must be said out loud, never silent"


def test_a_failed_search_is_recorded_and_nothing_crashes(httpx_mock, settings, conn):
    """A permanent (non-retryable) failure -- 404, not 5xx/429, which the
    shared HTTP client retries with real backoff before re-raising rather
    than returning a FetchResult; see pipeline/http.py's `_is_retryable`."""
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(
        url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"),
        status_code=404, is_reusable=True)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    govuk.run(ctx)

    review = conn.execute(
        "SELECT * FROM review_queue WHERE item_type='govuk_search_failed'").fetchall()
    assert review
    assert conn.execute("SELECT COUNT(*) c FROM govuk_document_candidates").fetchone()["c"] == 0


def test_an_unavailable_content_item_is_recorded_and_skipped(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(
        url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"),
        json=_search_response(_hit()), is_reusable=True)
    httpx_mock.add_response(url=CONTENT_URL, status_code=404, is_reusable=True)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    govuk.run(ctx)

    review = conn.execute(
        "SELECT * FROM review_queue WHERE item_type='govuk_content_unavailable'").fetchall()
    assert review
    assert conn.execute("SELECT COUNT(*) c FROM govuk_document_candidates").fetchone()["c"] == 0
