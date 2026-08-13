from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pytest
from odf.opendocument import OpenDocumentSpreadsheet
from odf.table import Table, TableCell, TableRow
from odf.text import P

from pipeline.http import PipelineHTTPClient
from pipeline.modules import m11_public_health_grant as phg

FIXTURES = Path(__file__).parent / "fixtures"


def _allow_all_robots(httpx_mock, origin: str) -> None:
    httpx_mock.add_response(url=f"{origin}/robots.txt", status_code=200, text="")


def _cell(text: str) -> TableCell:
    c = TableCell(valuetype="string")
    c.addElement(P(text=text))
    return c


def _row(values: list[str]) -> TableRow:
    r = TableRow()
    for v in values:
        r.addElement(_cell(v))
    return r


def _build_test_ods() -> bytes:
    """A synthetic ODS mimicking DHSC's real shape: a title row before the
    header, an 'Ecode' + ONS-code + name header, a normal row, a non-English
    row that must be skipped, and a row with an unparseable amount.
    """
    doc = OpenDocumentSpreadsheet()
    table = Table(name="Test_PHG")
    table.addElement(_row(["Public health grant allocations: revised 2026 to 2027", ""]))
    table.addElement(_row([
        "Ecode", "ONS local authority code", "Local authority name",
        "Financial year 2026 to 2027: Total consolidated public health grant (£)*",
        "Of which is drug & alcohol ring-fenced funding total (£) *",
        "Financial year 2027 to 2028: Indicative total consolidated public health grant (£)*",
    ]))
    table.addElement(_row(["E0101", "E06000022", "Bath and North East Somerset", "12,739,369", "3,671,145", "13,045,525"]))
    table.addElement(_row(["W9999", "W06000001", "Cardiff", "1,000", "500", "1,100"]))
    table.addElement(_row(["E0202", "E06000055", "Bedford", "not-a-number", "524,114", "12,477,708"]))
    doc.spreadsheet.addElement(table)
    buf = io.BytesIO()
    doc.write(buf)
    return buf.getvalue()


def test_discover_publications_filters_to_exact_title_pattern(httpx_mock, settings):
    _allow_all_robots(httpx_mock, "https://www.gov.uk")
    fixture = json.loads((FIXTURES / "govuk_search_ph_grants.json").read_text())
    httpx_mock.add_response(url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"), json=fixture)

    with PipelineHTTPClient("test", settings=settings) as client:
        publications = phg._discover_publications(client)

    years = [p["year_start"] for p in publications]
    assert years == sorted(years)
    assert 2026 in years
    # the "and social care charging: local authority circulars" decoy, and
    # the "from 2013 to 2016" title (different phrasing) must be excluded
    assert all("circular" not in p["title"].lower() for p in publications)
    assert all(re.match(r"^Public health grants to local authorities: \d{4} to \d{4}$", p["title"]) for p in publications)


def test_sheet_rows_and_header_detection():
    ods_bytes = _build_test_ods()
    rows = phg._sheet_rows(ods_bytes)
    header_idx = phg._find_header_row(rows)
    assert rows[header_idx][0] == "Ecode"
    assert header_idx == 1  # row 0 is the title row


def test_classify_columns_extracts_year_spans_and_slugs():
    ods_bytes = _build_test_ods()
    rows = phg._sheet_rows(ods_bytes)
    header_idx = phg._find_header_row(rows)
    ons_idx, name_idx, year_columns = phg._classify_columns(rows[header_idx])

    assert rows[header_idx][ons_idx] == "ONS local authority code"
    assert rows[header_idx][name_idx] == "Local authority name"
    assert len(year_columns) == 3

    total_col = next(c for c in year_columns if c["grant_type"] == "total_consolidated_public_health_grant")
    assert total_col["financial_year"] == "2026-27"
    assert total_col["allocation_status"] == "confirmed"
    assert total_col["unit"] == "gbp"

    da_col = next(c for c in year_columns if "drug" in c["grant_type"])
    assert da_col["financial_year"] == "2026-27"

    indicative_col = next(c for c in year_columns if c["financial_year"] == "2027-28")
    assert indicative_col["allocation_status"] == "indicative"


@pytest.mark.parametrize("raw,expected", [
    ("12,739,369", 12739369.0),
    ("84.4", 84.4),
    (" 1,000 ", 1000.0),
])
def test_parse_amount_handles_formatted_numbers(raw, expected):
    assert phg._parse_amount(raw) == expected


def test_parse_amount_raises_on_garbage():
    with pytest.raises(ValueError):
        phg._parse_amount("not-a-number")


def test_run_end_to_end(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock, "https://www.gov.uk")
    _allow_all_robots(httpx_mock, "https://assets.publishing.service.gov.uk")

    search_fixture = {"results": [{
        "title": "Public health grants to local authorities: 2026 to 2027",
        "link": "/government/publications/public-health-grants-to-local-authorities-2026-to-2027",
        "public_timestamp": "2026-05-13T10:41:36Z",
    }]}
    httpx_mock.add_response(url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"), json=search_fixture)

    content_fixture = {
        "title": "Public health grants to local authorities: 2026 to 2027",
        "details": {"attachments": [
            {"title": "circular", "content_type": None,
             "url": "/government/publications/x/circular"},
            {"title": "Annex E: public health grant allocations",
             "content_type": phg.ODS_MIME,
             "url": "https://assets.publishing.service.gov.uk/media/x/annex-e.ods"},
        ]},
    }
    httpx_mock.add_response(
        url="https://www.gov.uk/api/content/government/publications/public-health-grants-to-local-authorities-2026-to-2027",
        json=content_fixture,
    )
    httpx_mock.add_response(
        url="https://assets.publishing.service.gov.uk/media/x/annex-e.ods",
        content=_build_test_ods(),
        headers={"content-type": phg.ODS_MIME},
    )

    from pipeline.registry import ModuleContext
    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    phg.run(ctx)

    rows = conn.execute("SELECT * FROM public_health_grants ORDER BY ons_code, grant_type").fetchall()
    ons_codes = {r["ons_code"] for r in rows}
    # Cardiff (W-code) excluded entirely; Bedford keeps its 2 parseable
    # columns, only its unparseable 'total' cell is dropped (see below).
    assert ons_codes == {"E06000022", "E06000055"}

    bath = [r for r in rows if r["ons_code"] == "E06000022"]
    assert len(bath) == 3  # all three year columns parsed for Bath
    total = next(r for r in bath if r["grant_type"] == "total_consolidated_public_health_grant")
    assert total["amount"] == 12739369.0
    assert total["financial_year"] == "2026-27"
    assert total["source_url"] == "https://assets.publishing.service.gov.uk/media/x/annex-e.ods"
    assert total["retrieved_at"] is not None

    # Bedford's drug & alcohol and 2027-28 columns should still have parsed,
    # only its unparseable 'total' cell should be missing + logged.
    bedford_rows = conn.execute("SELECT * FROM public_health_grants WHERE ons_code = 'E06000055'").fetchall()
    assert len(bedford_rows) == 2
    failures = conn.execute("SELECT * FROM parse_failures WHERE module = 'm11_public_health_grant'").fetchall()
    assert len(failures) == 1
    assert failures[0]["raw_fragment"] == "not-a-number"


def test_run_upsert_is_idempotent(httpx_mock, settings, conn):
    search_fixture = {"results": [{
        "title": "Public health grants to local authorities: 2026 to 2027",
        "link": "/government/publications/public-health-grants-to-local-authorities-2026-to-2027",
        "public_timestamp": "2026-05-13T10:41:36Z",
    }]}
    content_fixture = {
        "title": "t",
        "details": {"attachments": [{"title": "Annex E allocations", "content_type": phg.ODS_MIME,
                                      "url": "https://assets.publishing.service.gov.uk/media/x/annex-e.ods"}]},
    }
    ods_bytes = _build_test_ods()
    for _ in range(2):
        _allow_all_robots(httpx_mock, "https://www.gov.uk")
        _allow_all_robots(httpx_mock, "https://assets.publishing.service.gov.uk")
        httpx_mock.add_response(url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"), json=search_fixture)
        httpx_mock.add_response(
            url="https://www.gov.uk/api/content/government/publications/public-health-grants-to-local-authorities-2026-to-2027",
            json=content_fixture,
        )
        httpx_mock.add_response(
            url="https://assets.publishing.service.gov.uk/media/x/annex-e.ods",
            content=ods_bytes, headers={"content-type": phg.ODS_MIME},
        )

    from pipeline.registry import ModuleContext
    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    phg.run(ctx)
    phg.run(ctx)

    count = conn.execute("SELECT COUNT(*) c FROM public_health_grants").fetchone()["c"]
    assert count == 5  # not 10 — second run upserts onto the same natural keys
