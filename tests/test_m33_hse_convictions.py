"""Module 33 — HSE convictions, sibling to m33_hse_notices.

The fixture table below mirrors the real breach-list column set observed in
an archived capture of `resources.hse.gov.uk/convictions/breach/breach_list.asp`
(Wayback Machine, retrieved during preparation for this module): Case/Breach,
Defendant's Name, Hearing Date, Result, Fine £, Act or Regulation. These
tests pin: the header-keyed row parser, the breach-id/case-number split, the
individual exclusion and exact-match discipline shared with m33_hse_notices,
and the near-miss review item.
"""
from __future__ import annotations

import re

from pipeline.modules import m33_hse_convictions as m33c

LIST_HTML = """
<html><body>
<table class="breaches">
  <thead><tr>
    <th>Case/Breach</th><th>Defendant's&nbsp;Name</th><th>Hearing&nbsp;Date</th>
    <th>Result</th><th>Fine&nbsp;&pound;</th><th>Act&nbsp;or&nbsp;Regulation</th>
  </tr></thead>
  <tbody>
    <tr>
      <td><a title="Link to Breach ID 4740932001" href="breach_details.asp?SF=BID&amp;SV=4740932001">47409320/01</a></td>
      <td>Change Grow Live</td>
      <td>15/03/2024</td><td>Guilty-Fine</td><td>300,000.00</td>
      <td>Health and Safety At Work Act 1974 / 2 / 1</td>
    </tr>
    <tr>
      <td><a title="Link to Breach ID 4740932002" href="breach_details.asp?SF=BID&amp;SV=4740932002">47409320/02</a></td>
      <td>Change Grow Live Services Ltd</td>
      <td>15/03/2024</td><td>Guilty-No Sep Penalty</td><td>0.00</td>
      <td>Health and Safety At Work Act 1974 / 3 / 1</td>
    </tr>
    <tr>
      <td><a title="Link to Breach ID 4761340001" href="breach_details.asp?SF=BID&amp;SV=4761340001">47613400/01</a></td>
      <td>Mr John Smith</td>
      <td>06/03/2024</td><td>Guilty-Community</td><td>0.00</td>
      <td>Health and Safety At Work Act 1974 / 2 / 1</td>
    </tr>
    <tr>
      <td><a title="Link to Breach ID 4773861001" href="breach_details.asp?SF=BID&amp;SV=4773861001">47738610/01</a></td>
      <td>Change Grow Live Holdings Group</td>
      <td>12/03/2024</td><td>Guilty-Fine</td><td>28,000.00</td>
      <td>Work at Height Regulations 2005 / 4 / 1</td>
    </tr>
  </tbody>
</table>
</body></html>
"""


def test_parser_reads_rows_by_header_not_position():
    rows = m33c.parse_breach_list(LIST_HTML)
    assert len(rows) == 4
    first = next(r for r in rows if r["breach_id"] == "4740932001")
    assert first["defendant_name"] == "Change Grow Live"
    assert first["case_number"] == "47409320"
    assert first["breach_sequence"] == "01"
    assert first["hearing_date"] == "15/03/2024"
    assert first["result"] == "Guilty-Fine"
    assert first["fine_text"] == "300,000.00"
    assert "Health and Safety At Work Act" in first["legislation"]


def test_a_reordered_or_unknown_column_is_absent_not_misread():
    reordered = LIST_HTML.replace(
        "<th>Result</th><th>Fine&nbsp;&pound;</th>",
        "<th>Fine&nbsp;&pound;</th><th>Result</th>").replace(
        "<td>Guilty-Fine</td><td>300,000.00</td>",
        "<td>300,000.00</td><td>Guilty-Fine</td>")
    rows = m33c.parse_breach_list(reordered)
    first = next(r for r in rows if r["breach_id"] == "4740932001")
    assert first["result"] == "Guilty-Fine"
    assert first["fine_text"] == "300,000.00"


def test_breach_id_comes_from_the_link_not_the_displayed_text():
    # The displayed "Case/Breach" text and the link's SV id agree in this
    # fixture, as they do in the real register; the parser must use the
    # link, per its own docstring, rather than assume that always holds.
    rows = m33c.parse_breach_list(LIST_HTML)
    assert {r["breach_id"] for r in rows} == {
        "4740932001", "4740932002", "4761340001", "4773861001"}


def _mock_search(httpx_mock, body: str):
    httpx_mock.add_response(
        url="https://resources.hse.gov.uk/robots.txt", status_code=404,
        text="", is_reusable=True)
    httpx_mock.add_response(
        url=re.compile(
            r"https://resources\.hse\.gov\.uk/convictions/breach/breach_list\.asp.*"),
        text=body, is_reusable=True)


def test_run_stores_only_exact_org_matches_and_queues_a_near_miss(
        httpx_mock, settings, conn, monkeypatch):
    _mock_search(httpx_mock, LIST_HTML)
    monkeypatch.setattr(m33c, "SUPPLIER_NAME_VARIANTS", {
        "change_grow_live": ["Change Grow Live", "Change Grow Live Services Ltd"]})

    from pipeline.registry import ModuleContext
    m33c.run(ModuleContext(conn=conn, settings=settings, since=None,
                           dry_run=False, limit=None))

    stored = conn.execute(
        "SELECT breach_id, case_number, defendant_name, provider_key, result "
        "FROM hse_enforcement_convictions ORDER BY breach_id").fetchall()
    # 4740932001 (exact "Change Grow Live") and 4740932002 (exact
    # "…Services Ltd") are attributed; "Mr John Smith" is an individual,
    # dropped; "…Holdings Group" is an org but not an exact match.
    assert [r["breach_id"] for r in stored] == ["4740932001", "4740932002"]
    assert all(r["provider_key"] == "change_grow_live" for r in stored)
    assert {r["result"] for r in stored} == {"Guilty-Fine", "Guilty-No Sep Penalty"}

    near_miss = conn.execute(
        "SELECT COUNT(*) FROM review_queue "
        "WHERE item_type = 'hse_conviction_name_near_miss'"
    ).fetchone().values().__iter__().__next__()
    assert near_miss == 1
