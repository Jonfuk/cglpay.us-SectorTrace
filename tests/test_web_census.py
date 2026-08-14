"""The census verification screen over HTTP.

The rules themselves are tested in test_census_verify.py. What matters here is
that the routes do not offer a way around them: no bulk verify, no anonymous
verify, the same refusals, and every write behind the same content-type and
Origin guard as the rest of the operator UI.
"""
from __future__ import annotations

import threading

import httpx
import pytest

from pipeline import census_verify
from pipeline.web.server import build_server

PAGE_TEXT = (
    "Workforce summary\n"
    "8% vacancy rate in the delivery workforce\n"
    "a 19% turnover rate for all staff\n")


@pytest.fixture
def client(conn, settings):
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=10.0) as http:
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def seeded(conn):
    conn.execute(
        "INSERT INTO workforce_census_reports (census_year, report_title, "
        " document_url, page_count, publisher, source_url, retrieved_at, "
        " http_status, source_system, payload_sha256) "
        "VALUES (2024, 'Workforce Census 2024', 'https://nhsbn.example/c.pdf', "
        " 60, 'NHS Benchmarking Network', 'https://nhsbn.example/c.pdf', "
        " '2026-08-01T00:00:00Z', 200, 'm06_workforce_census', 'cen123')")
    conn.execute(
        "INSERT INTO workforce_census_page_text (census_year, page_number, "
        " page_text, source_url, retrieved_at, http_status, source_system, "
        " payload_sha256) VALUES (2024, 6, ?, 'https://nhsbn.example/c.pdf', "
        " '2026-08-01T00:00:00Z', 200, 'm06_workforce_census', 'cen123')",
        (PAGE_TEXT,))
    for metric, segment, value, line in (
            ("vacancy_rate", "delivery", 8.0,
             "8% vacancy rate in the delivery workforce"),
            ("turnover_rate", "all_staff", 19.0,
             "a 19% turnover rate for all staff")):
        conn.execute(
            "INSERT INTO workforce_census_metrics (census_year, metric, "
            " workforce_segment, value, unit, source_page, raw_text, verified, "
            " source_url, retrieved_at, http_status, source_system, "
            " payload_sha256) VALUES (2024, ?, ?, ?, 'percent', 6, ?, 0, "
            " 'https://nhsbn.example/c.pdf', '2026-08-01T00:00:00Z', 200, "
            " 'm06_workforce_census', 'cen123')",
            (metric, segment, value, line))
    conn.commit()
    return conn


def _key(client, metric: str) -> str:
    items = client.get("/api/admin/census").json()["items"]
    return next(item["key"] for item in items if item["metric"] == metric)


# --- reading -------------------------------------------------------------------


def test_counts_report_the_gap_this_screen_exists_to_close(client, seeded):
    payload = client.get("/api/admin/census/counts").json()

    assert (payload["total"], payload["unchecked"], payload["verified"]) == (2, 2, 0)
    assert payload["years"][0]["census_year"] == 2024
    assert payload["years"][0]["document_url"] == "https://nhsbn.example/c.pdf"
    assert payload["stale"] == []


def test_the_worklist_is_unchecked_by_default(client, seeded):
    payload = client.get("/api/admin/census").json()

    assert payload["status"] == "unchecked"
    assert payload["total"] == 2
    assert {item["metric"] for item in payload["items"]} == {
        "vacancy_rate", "turnover_rate"}


def test_a_figure_carries_the_line_it_was_parsed_from(client, seeded):
    item = next(i for i in client.get("/api/admin/census").json()["items"]
                 if i["metric"] == "vacancy_rate")

    assert item["raw_text"] == "8% vacancy rate in the delivery workforce"
    assert item["value"] == 8.0
    assert item["source_page"] == 6
    # The report m06 archived, which is what a verification is taken against.
    assert item["source"]["payload_sha256"] == "cen123"


def test_the_page_a_figure_was_read_from_is_served(client, seeded):
    """Not a link to the PDF -- the page. A parsed line can look right and
    still be a sentence about a different year; only the page says which."""
    payload = client.get("/api/admin/census/page?year=2024&page=6").json()

    assert payload["page_text"] == PAGE_TEXT
    assert payload["payload_sha256"] == "cen123"
    assert len(payload["metrics_on_page"]) == 2


def test_a_page_with_no_archived_text_is_a_404(client, seeded):
    assert client.get("/api/admin/census/page?year=2024&page=99").status_code == 404


def test_an_unknown_status_is_refused(client, seeded):
    assert client.get("/api/admin/census?status=promoted").status_code == 400


# --- writing -------------------------------------------------------------------


def test_verifying_needs_a_json_content_type(client, seeded):
    response = client.post("/api/admin/census/verify", content=b"key=abc",
                            headers={})
    assert response.status_code in (400, 415)


def test_verifying_from_another_origin_is_refused(client, seeded):
    response = client.post(
        "/api/admin/census/verify",
        json={"key": _key(client, "vacancy_rate"), "verified_by": "Jon"},
        headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_verifying_cannot_be_done_by_a_get(client, seeded):
    assert client.get("/api/admin/census/verify").status_code == 404


def test_verifying_anonymously_is_refused(client, seeded):
    response = client.post(
        "/api/admin/census/verify",
        json={"key": _key(client, "vacancy_rate"), "verified_by": ""})

    assert response.status_code == 400
    assert "attributed" in response.json()["error"]


def test_the_verify_route_takes_one_figure_and_not_a_list(client, seeded):
    """The census analogue of /api/admin/candidates/promote taking one URL.
    Not about the cost of the request -- about what a route accepting an array
    would make cheap to claim."""
    response = client.post(
        "/api/admin/census/verify",
        json={"keys": [_key(client, "vacancy_rate")], "verified_by": "Jon"})

    assert response.status_code == 400
    assert client.get("/api/admin/census/counts").json()["verified"] == 0


def test_verifying_one_figure_end_to_end(client, seeded):
    response = client.post(
        "/api/admin/census/verify",
        json={"key": _key(client, "vacancy_rate"), "verified_by": "Jon",
               "note": "read off page 6"})

    assert response.status_code == 200
    assert response.json()["decision"] == "verified"

    counts = client.get("/api/admin/census/counts").json()
    assert (counts["verified"], counts["unchecked"]) == (1, 1)
    assert counts["decisions"][0]["decided_by"] == "Jon"
    assert counts["decisions"][0]["note"] == "read off page 6"


def test_rejecting_is_bulk_and_verifying_is_not(client, seeded):
    keys = [item["key"] for item in client.get("/api/admin/census").json()["items"]]
    response = client.post(
        "/api/admin/census/reject",
        json={"keys": keys, "rejected_by": "Jon", "note": "wrong year"})

    assert response.status_code == 200
    assert response.json()["rejected"] == 2
    assert client.get("/api/admin/census/counts").json()["rejected"] == 2


def test_rejecting_refuses_anything_that_is_not_a_list_of_keys(client, seeded):
    response = client.post("/api/admin/census/reject",
                            json={"keys": "everything", "rejected_by": "Jon"})
    assert response.status_code == 400


def test_a_stale_verification_is_reported_by_the_counts_route(client, seeded, conn):
    """The flag stays up while the number underneath it moves. Surfaced where
    the operator will see it rather than in a query nobody runs."""
    client.post("/api/admin/census/verify",
                 json={"key": _key(client, "vacancy_rate"), "verified_by": "Jon"})
    conn.execute("UPDATE workforce_census_metrics SET value = 9.0 "
                  "WHERE metric = 'vacancy_rate'")
    conn.commit()

    stale = client.get("/api/admin/census/counts").json()["stale"]
    assert len(stale) == 1
    assert stale[0]["metric"] == "vacancy_rate"
    assert any("checked as 8.0" in why for why in stale[0]["why"])


def test_resetting_puts_a_figure_back_in_the_worklist(client, seeded):
    key = _key(client, "vacancy_rate")
    client.post("/api/admin/census/verify",
                 json={"key": key, "verified_by": "Jon"})
    assert client.post("/api/admin/census/reset",
                        json={"key": key}).status_code == 200

    counts = client.get("/api/admin/census/counts").json()
    assert (counts["verified"], counts["unchecked"]) == (0, 2)
    # The judgement is still on record.
    assert len(counts["decisions"]) == 1


# --- the operator asset the screen needs --------------------------------------


def test_the_census_module_is_served(client):
    """A module that 404s takes the whole import graph with it, and the page
    keeps working well enough that nobody notices the tab is empty."""
    response = client.get("/admin/js/census.js")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/javascript")


def test_the_screen_and_the_module_agree_on_their_element_ids(client):
    """The panel is markup in one file and behaviour in another, wired by id.
    A rename in either is invisible until somebody opens the tab."""
    html = client.get("/admin").text
    script = client.get("/admin/js/census.js").text

    for element_id in ("census-counts", "census-list", "census-pager",
                        "census-status", "census-status-filter",
                        "census-verify-read", "census-reject-selected",
                        "census-batch", "census-result", "census-stale",
                        "census-history", "census-pill"):
        assert f'id="{element_id}"' in html, f"{element_id} is not in the page"
        assert f"'{element_id}'" in script, f"{element_id} is not read by census.js"


def test_the_verification_key_is_not_a_rowid(client, seeded):
    """Stable across a rebuild, which a rowid is not. Checked from the outside:
    the key the UI holds must still name the same figure after the table has
    been rewritten."""
    key = _key(client, "vacancy_rate")
    assert key == census_verify.metric_key({
        "census_year": 2024, "metric": "vacancy_rate",
        "workforce_segment": "delivery",
        "raw_text": "8% vacancy rate in the delivery workforce"})
