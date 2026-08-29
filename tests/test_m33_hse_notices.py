"""Module 33 — HSE enforcement notices.

The register lists notices served on organisations and on named people; this
module keeps only the organisation-level ones, and attributes a notice to a
provider only on an exact name match. These tests pin: the header-keyed row
parser, the individual exclusion, the exact-match discipline, and the
near-miss review item.
"""
from __future__ import annotations

import re

from pipeline.modules import m33_hse_notices as m33

LIST_HTML = """
<html><body>
<table class="notices">
  <thead><tr>
    <th>Name</th><th>Notice Type</th><th>Notice Number</th>
    <th>Issuing Authority</th><th>Date of Issue</th><th>Compliance Date</th>
    <th>Result</th><th>Legislation</th>
  </tr></thead>
  <tbody>
    <tr>
      <td><a href="/notices/notices/notice_details.asp?SF=CN&amp;SV=1">Change Grow Live</a></td>
      <td>Improvement</td><td>301234567</td><td>HSE</td>
      <td>2024-05-02</td><td>2024-06-30</td><td>Complied</td>
      <td>Management of Health and Safety at Work Regulations 1999 / 3</td>
    </tr>
    <tr>
      <td>Change Grow Live Services Ltd</td>
      <td>Prohibition</td><td>309876543</td><td>HSE</td>
      <td>2023-11-14</td><td>Immediate</td><td>Under appeal</td>
      <td>Health and Safety at Work etc Act 1974 / 2(1)</td>
    </tr>
    <tr>
      <td>Mr John Smith</td>
      <td>Improvement</td><td>300000111</td><td>HSE</td>
      <td>2024-01-09</td><td>2024-02-01</td><td>Complied</td>
      <td>Work at Height Regulations 2005 / 6</td>
    </tr>
    <tr>
      <td>Change Grow Live Holdings Group</td>
      <td>Improvement</td><td>300000222</td><td>HSE</td>
      <td>2024-03-03</td><td>2024-04-01</td><td>Complied</td>
      <td>PUWER 1998 / 5</td>
    </tr>
  </tbody>
</table>
</body></html>
"""


def test_parser_reads_rows_by_header_not_position():
    rows = m33.parse_notice_list(LIST_HTML)
    assert len(rows) == 4
    first = next(r for r in rows if r["notice_number"] == "301234567")
    assert first["recipient_name"] == "Change Grow Live"
    assert first["notice_type"] == "Improvement"
    assert first["issue_date"] == "2024-05-02"
    assert first["result"] == "Complied"
    assert "Management of Health and Safety" in first["legislation"]


def test_a_reordered_or_unknown_column_is_absent_not_misread():
    reordered = LIST_HTML.replace(
        "<th>Notice Type</th><th>Notice Number</th>",
        "<th>Notice Number</th><th>Notice Type</th>").replace(
        "<td>Improvement</td><td>301234567</td>",
        "<td>301234567</td><td>Improvement</td>")
    rows = m33.parse_notice_list(reordered)
    first = next(r for r in rows if r["notice_number"] == "301234567")
    assert first["notice_type"] == "Improvement"


def test_is_organisation_excludes_a_bare_personal_name():
    tracked = {"Change Grow Live"}
    assert m33.is_organisation("Mr John Smith", tracked_variants=tracked) is False
    assert m33.is_organisation("John Smith", tracked_variants=tracked) is False
    assert m33.is_organisation("Acme Care Ltd", tracked_variants=tracked) is True
    # An exact tracked match is always an organisation, token or not.
    assert m33.is_organisation("Change Grow Live", tracked_variants=tracked) is True


def test_name_matches_is_an_exact_normalised_match():
    assert m33.name_matches("Change Grow Live", "Change Grow Live")
    assert m33.name_matches("Change Grow Live Services Ltd", "Change Grow Live Services Ltd")
    assert not m33.name_matches("Change Grow Live Holdings Group", "Change Grow Live")


def _mock_search(httpx_mock, body: str):
    httpx_mock.add_response(
        url="https://resources.hse.gov.uk/robots.txt", status_code=404,
        text="", is_reusable=True)
    httpx_mock.add_response(
        url=re.compile(r"https://resources\.hse\.gov\.uk/notices/notices/notice_list\.asp.*"),
        text=body, is_reusable=True)


def test_run_stores_only_exact_org_matches_and_queues_a_near_miss(
        httpx_mock, settings, conn, monkeypatch):
    _mock_search(httpx_mock, LIST_HTML)
    monkeypatch.setattr(m33, "SUPPLIER_NAME_VARIANTS", {
        "change_grow_live": ["Change Grow Live", "Change Grow Live Services Ltd"]})

    from pipeline.registry import ModuleContext
    m33.run(ModuleContext(conn=conn, settings=settings, since=None,
                          dry_run=False, limit=None))

    stored = conn.execute(
        "SELECT notice_number, recipient_name, provider_key, notice_type, result "
        "FROM hse_enforcement_notices ORDER BY notice_number").fetchall()
    # 301234567 (exact "Change Grow Live") and 309876543 (exact
    # "…Services Ltd") are attributed; "Mr John Smith" is an individual,
    # dropped; "…Holdings Group" is an org but not an exact match.
    assert [r["notice_number"] for r in stored] == ["301234567", "309876543"]
    assert all(r["provider_key"] == "change_grow_live" for r in stored)
    assert {r["result"] for r in stored} == {"Complied", "Under appeal"}

    near_miss = conn.execute(
        "SELECT COUNT(*) FROM review_queue WHERE item_type = 'hse_name_near_miss'"
    ).fetchone()[0]
    assert near_miss == 1
