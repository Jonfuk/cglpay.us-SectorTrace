"""Module 18: one lookup per provider against the Living Wage register.

The binary is the point: found, exactly, or not found — with the window
said out loud, a near-miss queued rather than stored, and a provider never
accredited on a name that merely resembles its own.
"""
from __future__ import annotations

import re
from pathlib import Path

from pipeline.modules import m18_living_wage as lw
from pipeline.registry import ModuleContext

FIXTURES = Path(__file__).parent / "fixtures"


def _allow_all_robots(httpx_mock, origin: str = "https://www.livingwage.org.uk") -> None:
    httpx_mock.add_response(url=f"{origin}/robots.txt", status_code=200, text="", is_reusable=True)


def _employers_page(*names: str, count: int | None = None) -> str:
    rows = []
    for index, name in enumerate(names, start=380000):
        rows.append(f"""
        <div class="views-row">
          <article data-history-node-id="{index}" about="/node/{index}" class="logo-teaser">
            <img class="logo-teaser__img" alt="{name}">
          </article>
          <div class="teaser-modal">
            <div class="teaser-modal__inner">
              <h3 class="teaser-modal__title">{name}</h3>
            </div>
          </div>
        </div>""")
    total = len(names) if count is None else count
    return (
        "<html><body><div class='employers-view__header-results'>"
        f"<strong>{total}</strong> Accredited Living Wage Employers found."
        "</div><div class='views-row'>" + "".join(rows) + "</div></body></html>")


# --- matching -----------------------------------------------------------------

def test_normalise_match_is_exact_and_case_insensitive():
    assert lw.normalise_match("Change Grow Live", "Change Grow Live")
    assert lw.normalise_match("change grow live", "Change Grow Live")
    assert not lw.normalise_match("Change Grow Live Services Ltd", "Change Grow Live")
    assert not lw.normalise_match("Some Other Charity", "Change Grow Live")


def test_parse_employer_list_extracts_names_and_node_ids():
    page = _employers_page("Change Grow Live", "Turning Point")
    employers, count = lw.parse_employer_list(page)
    assert count == 2
    assert employers == [
        {"node_id": "380000", "name": "Change Grow Live"},
        {"node_id": "380001", "name": "Turning Point"},
    ]


def test_parse_employer_list_reports_the_registers_own_count():
    page = _employers_page("One")
    assert "1" in page
    _, count = lw.parse_employer_list(page)
    assert count == 1


def test_parse_employer_list_handles_no_results():
    _, count = lw.parse_employer_list(
        "<html><body><strong>0</strong> Accredited Living Wage Employers found.</body></html>")
    assert count == 0


# --- end to end ---------------------------------------------------------------

def test_run_records_an_exact_accreditation(httpx_mock, settings, conn, monkeypatch):
    _allow_all_robots(httpx_mock)
    page = _employers_page("Change Grow Live")
    httpx_mock.add_response(
        url=re.compile(r"https://www\.livingwage\.org\.uk/accredited.*"), text=page,
        is_reusable=True)
    monkeypatch.setattr(lw, "SUPPLIER_NAME_VARIANTS",
                        {"change_grow_live": ["Change Grow Live"]})

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    lw.run(ctx)

    row = conn.execute("SELECT * FROM living_wage_accreditations").fetchone()
    assert row["provider_key"] == "change_grow_live"
    assert row["accredited"] == 1
    assert row["employer_name"] == "Change Grow Live"
    assert row["employer_node_id"] == "380000"
    assert row["match_basis"] == "exact"
    assert row["source_url"].startswith("https://www.livingwage.org.uk/accredited")
    assert conn.execute("SELECT COUNT(*) c FROM review_queue").fetchone()["c"] == 0


def test_run_records_not_found_as_not_found(httpx_mock, settings, conn, monkeypatch):
    """A provider not on the list is a real answer: accredited = 0 with the
    lookup's provenance, not a review item and not a stored match."""
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(
        url=re.compile(r"https://www\.livingwage\.org\.uk/accredited.*"),
        text="<html><body><strong>0</strong> Accredited Living Wage Employers found."
             "</body></html>", is_reusable=True)
    monkeypatch.setattr(lw, "SUPPLIER_NAME_VARIANTS",
                        {"change_grow_live": ["Change Grow Live"]})

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    lw.run(ctx)

    row = conn.execute("SELECT * FROM living_wage_accreditations").fetchone()
    assert row["accredited"] == 0
    assert row["employer_name"] is None
    assert row["match_basis"] is None
    assert conn.execute("SELECT COUNT(*) c FROM review_queue").fetchone()["c"] == 0


def test_run_queues_a_near_miss_instead_of_storing_it(httpx_mock, settings, conn, monkeypatch):
    """A differently-spelled name is the case the review queue exists for:
    the employer might be the provider, and it must never be recorded as
    accredited on that basis."""
    _allow_all_robots(httpx_mock)
    page = _employers_page("Change Grow Live Services Ltd")
    httpx_mock.add_response(
        url=re.compile(r"https://www\.livingwage\.org\.uk/accredited.*"), text=page,
        is_reusable=True)
    monkeypatch.setattr(lw, "SUPPLIER_NAME_VARIANTS",
                        {"change_grow_live": ["Change Grow Live"]})

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    lw.run(ctx)

    row = conn.execute("SELECT * FROM living_wage_accreditations").fetchone()
    assert row["accredited"] == 0
    review = conn.execute("SELECT * FROM review_queue").fetchall()
    assert [r["item_type"] for r in review] == ["unconfirmed_living_wage_name_match"]
    assert "Change Grow Live Services Ltd" in review[0]["context_json"]


def test_run_flags_a_truncated_search_window(httpx_mock, settings, conn, monkeypatch):
    """When the register's own count exceeds the checked window, 'not found'
    is not a complete answer and a review item must say so."""
    _allow_all_robots(httpx_mock)
    # the register says 40 matches; the module reads 3 pages and must say so
    page = _employers_page("Other Employer One", count=40)
    httpx_mock.add_response(
        url=re.compile(r"https://www\.livingwage\.org\.uk/accredited.*"), text=page,
        is_reusable=True)
    monkeypatch.setattr(lw, "SUPPLIER_NAME_VARIANTS",
                        {"change_grow_live": ["Change Grow Live"]})

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    lw.run(ctx)

    review = conn.execute("SELECT * FROM review_queue").fetchall()
    assert "living_wage_search_truncated" in [r["item_type"] for r in review]
    row = conn.execute("SELECT * FROM living_wage_accreditations").fetchone()
    assert row["accredited"] == 0
    assert row["pages_checked"] == 3


def test_run_is_idempotent(httpx_mock, settings, conn, monkeypatch):
    _allow_all_robots(httpx_mock)
    page = _employers_page("Change Grow Live")
    httpx_mock.add_response(
        url=re.compile(r"https://www\.livingwage\.org\.uk/accredited.*"), text=page,
        is_reusable=True)
    monkeypatch.setattr(lw, "SUPPLIER_NAME_VARIANTS",
                        {"change_grow_live": ["Change Grow Live"]})

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    lw.run(ctx)
    lw.run(ctx)

    assert conn.execute("SELECT COUNT(*) c FROM living_wage_accreditations").fetchone()["c"] == 1
