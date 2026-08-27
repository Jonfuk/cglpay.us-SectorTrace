"""Module 24: council spend-transparency files.

The claim is actual money — "council X paid provider Y £Z in [period]" — so
most of these tests are about the NULL discipline: an unreadable file is a
parse_failure and a review item, never a zero; an unreadable amount is NULL
with the verbatim text kept; and a payee that matches no provider keeps its
name and a NULL key. The provider match is the same exact-normalised rule
m16 and m20 apply — a near-miss is never a match.
"""
from __future__ import annotations

import re

import pytest

from pipeline.modules import m24_council_spend as spend
from pipeline.registry import ModuleContext

ORIGIN = "https://www.testshire.gov.uk"


def _allow_robots(httpx_mock, host: str = ORIGIN) -> None:
    httpx_mock.add_response(url=f"{host}/robots.txt", status_code=200,
                            text="", is_reusable=True)


def _page(links: str) -> str:
    return f"<html><body>{links}</body></html>"


def _add_authority(conn, ons_code: str = "E99999001", name: str = "Testshire") -> None:
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, "
        "first_seen_vintage, last_seen_vintage, source_url, retrieved_at, "
        "http_status, source_system, payload_sha256) "
        "VALUES (?, ?, 'utla', '2023-01-01', '2023', '2026', "
        "'https://example.com/spine', '2026-01-01T00:00:00+00:00', 200, "
        "'test', 'abc')", (ons_code, name))
    conn.execute(
        "INSERT INTO authority_foi_profiles (ons_code, authority_name, "
        "home_page_url, source_url, retrieved_at, http_status, source_system, "
        "payload_sha256) VALUES (?, ?, ?, 'https://register.example', "
        "'2026-08-13T00:00:00Z', 200, 'm15', 'h')",
        (ons_code, name, ORIGIN))
    conn.commit()


def _spend_page_urls(html: str, origin: str = ORIGIN) -> list[str]:
    return spend._file_urls_on_page(html, f"{origin}/transparency", origin[8:])


# --- discovery ----------------------------------------------------------------


def test_a_spend_file_link_is_recognised():
    html = _page('<a href="/transparency/spend-2025.csv">Spend over £500</a>')
    urls = _spend_page_urls(html)
    assert urls == [f"{ORIGIN}/transparency/spend-2025.csv"]


def test_a_csv_without_spend_vocabulary_is_not_followed():
    html = _page('<a href="/data/dataset.csv">Open data</a>')
    assert _spend_page_urls(html) == []


def test_a_non_file_link_is_not_followed():
    html = _page('<a href="/transparency/spend-and-expenditure">Spend page</a>')
    assert _spend_page_urls(html) == []


@pytest.mark.parametrize("href,text", [
    ("/transparency/transparency-fraud-24-25.csv", "Fraud data 2024-25"),
    ("/transparency/senior-salary-2025-26.csv", "Senior salary information"),
    ("/transparency/community-grant-awards-over-5000.csv", "Grants to organisations"),
    ("/transparency/Land_and_Asset_data.xlsx", "Land and asset register"),
    ("/transparency/controlled-parking-spaces.csv", "Parking spaces"),
])
def test_other_transparency_code_datasets_are_not_followed_as_spend(href, text):
    """These publish under "transparency" too and so pass SPEND_WORDS, but
    they are not £500 supplier spend and only fail header detection."""
    assert _spend_page_urls(_page(f'<a href="{href}">{text}</a>')) == []


# --- the CSV parser -----------------------------------------------------------

CSV = (
    "Supplier,Amount,Period,Description\n"
    '"Turning Point","£12,345.67","2025-01","Substance misuse service"\n'
    '"A Local Builder Ltd","999.50","2025-01","Refurbishment"\n'
    '"Unreadable Co","n/a","2025-02","Could not be read"\n'
    ',"","2025-02","No supplier"\n'
)


def test_csv_lines_are_parsed_with_amount_null_discipline():
    rows, error = spend._parse_csv(CSV.encode(), "https://x/spend.csv")
    assert error is None
    assert len(rows) == 3
    assert rows[0]["payee"] == "Turning Point"
    assert rows[0]["amount"] == 12345.67
    assert rows[0]["amount_text"] == "£12,345.67"
    assert rows[0]["period"] == "2025-01"
    assert rows[0]["description"] == "Substance misuse service"
    assert rows[1]["amount"] == 999.5
    # n/a is unreadable: NULL amount, verbatim text survives
    assert rows[2]["amount"] is None
    assert rows[2]["amount_text"] == "n/a"


def test_csv_without_amount_column_is_an_error():
    rows, error = spend._parse_csv(b"Supplier,Description\nA,B\n", "https://x/s.csv")
    assert rows == []
    assert "amount column" in error


def test_csv_without_payee_column_is_an_error():
    rows, error = spend._parse_csv(b"Amount,Description\n1,B\n", "https://x/s.csv")
    assert rows == []
    assert "payee column" in error


def test_csv_with_no_rows_is_an_error():
    rows, error = spend._parse_csv(b"", "https://x/s.csv")
    assert rows == []
    assert "no rows" in error


@pytest.mark.parametrize("header", [
    "Supplier Name,Amount (£),Date",
    "Beneficiary,Transaction Amount,Payment Date",
    "Merchant Name,Amount GBP,Month",
    "Payee,Total Amount (net),Period",
])
def test_csv_headers_councils_actually_use_are_matched(header):
    body = (header + "\n\"Change Grow Live\",\"1,000.00\",\"2025-01\"\n").encode()
    rows, error = spend._parse_csv(body, "https://x/s.csv")
    assert error is None
    assert rows and rows[0]["payee"] == "Change Grow Live"
    assert rows[0]["amount"] == 1000.0


# --- the provider match -------------------------------------------------------


def test_payee_matches_a_provider_by_exact_normalised_name():
    lookups = spend._provider_lookups(None)
    assert lookups[spend._normalise_name("Turning Point")] == "turning_point"
    assert lookups[spend._normalise_name("Change Grow Live")] == "change_grow_live"
    # a near-miss is not a match
    assert spend._normalise_name("Turning Point Healthcare Ltd") not in lookups


# --- end to end ---------------------------------------------------------------

SAMPLE_CSV = (
    "Supplier,Amount,Period,Description\n"
    '"Turning Point","£12,345.67","2025-01","Substance misuse service"\n'
)


def _mock_site(httpx_mock, *, page_links: str | None = None,
               csv_body: bytes = SAMPLE_CSV.encode(), origin: str = ORIGIN):
    _allow_robots(httpx_mock, origin)
    for path in ("/", "/transparency", "/about-your-council/transparency",
                 "/your-council/transparency", "/finance-and-governance",
                 "/open-data", "/data", "/spend", "/expenditure",
                 "/payments-over-500", "/transparency-data"):
        httpx_mock.add_response(
            url=f"{origin}{path}",
            status_code=200,
            text=_page(page_links or ""), is_reusable=True)
    if page_links:
        httpx_mock.add_response(
            url=re.compile(rf"{re.escape(origin)}/transparency/.*\.csv"),
            content=csv_body, status_code=200, is_reusable=True)


def test_run_discovers_fetches_and_stores_lines(httpx_mock, settings, conn):
    _add_authority(conn)
    _mock_site(httpx_mock, page_links=(
        '<a href="/transparency/spend-2025.csv">Spend over £500</a>'))

    ctx = ModuleContext(conn=conn, settings=settings, since=None,
                        dry_run=False, limit=None)
    spend.run(ctx)

    files = conn.execute("SELECT * FROM council_spend_files").fetchall()
    assert len(files) == 1
    assert files[0]["parse_status"] == "parsed"
    assert files[0]["row_count"] == 1

    lines = conn.execute("SELECT * FROM council_spend").fetchall()
    assert len(lines) == 1
    assert lines[0]["payee"] == "Turning Point"
    assert lines[0]["amount"] == 12345.67
    assert lines[0]["provider_key"] == "turning_point", (
        "the payee matched a tracked provider by exact normalised name")
    assert lines[0]["source_url"].endswith("spend-2025.csv")


def test_run_records_an_unreadable_file(httpx_mock, settings, conn):
    _add_authority(conn)
    _mock_site(httpx_mock, page_links=(
        '<a href="/transparency/spend-2025.csv">Spend over £500</a>'),
        csv_body=b"not a csv at all")

    ctx = ModuleContext(conn=conn, settings=settings, since=None,
                        dry_run=False, limit=None)
    spend.run(ctx)

    files = conn.execute("SELECT * FROM council_spend_files").fetchall()
    assert files[0]["parse_status"] == "unreadable"
    assert conn.execute("SELECT COUNT(*) FROM parse_failures").fetchone()[0] == 1
    items = {r["item_type"] for r in conn.execute(
        "SELECT item_type FROM review_queue").fetchall()}
    assert "council_spend_unreadable" in items
    assert conn.execute("SELECT COUNT(*) FROM council_spend").fetchone()[0] == 0


def test_run_records_no_file_found(httpx_mock, settings, conn):
    _add_authority(conn)
    _mock_site(httpx_mock, page_links="")

    ctx = ModuleContext(conn=conn, settings=settings, since=None,
                        dry_run=False, limit=None)
    spend.run(ctx)

    items = {r["item_type"] for r in conn.execute(
        "SELECT item_type FROM review_queue").fetchall()}
    assert "council_spend_none_found" in items
    assert conn.execute("SELECT COUNT(*) FROM council_spend_files").fetchone()[0] == 0


def test_run_authority_without_a_website_is_a_review_item(httpx_mock, settings, conn):
    # An authority with no foi profile and no registry entry: nothing to
    # crawl, and the gap is a review item, never a silent skip.
    _add_authority(conn, ons_code="E99999002", name="Nowhere")
    conn.execute("DELETE FROM authority_foi_profiles WHERE ons_code = 'E99999002'")
    conn.commit()

    ctx = ModuleContext(conn=conn, settings=settings, since=None,
                        dry_run=False, limit=None)
    spend.run(ctx)

    items = {r["item_type"] for r in conn.execute(
        "SELECT item_type FROM review_queue").fetchall()}
    assert "authority_website_unknown" in items
