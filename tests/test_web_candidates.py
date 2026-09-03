"""The candidate screens over HTTP.

The promotion rules themselves are tested in test_promote.py. What matters
here is that the routes do not offer a way around them: no bulk promote, no
anonymous promote, the same refusals, and every write behind the same
content-type and Origin guard as the rest of the operator UI.
"""
from __future__ import annotations

import threading

import httpx
import pytest

from pipeline.web.server import build_server


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
        "INSERT INTO authorities (ons_code, name, type, active_from, "
        "first_seen_vintage, last_seen_vintage, source_url, retrieved_at, "
        "http_status, source_system, payload_sha256) VALUES "
        "('E10000016', 'Kent', 'CTY', '2013-04-01', '2024', '2024', "
        "'https://example.org/a', '2026-08-01T00:00:00Z', 200, 'ons', 'abc')")
    for i in range(3):
        conn.execute(
            "INSERT INTO cdp_document_candidates (authority_ons_code, candidate_url, "
            "title, document_type_guess, confidence, discovered_at, discovery_method, "
            "verified, rejected, source_url, retrieved_at, http_status, source_system, "
            "payload_sha256) VALUES ('E10000016', %s, %s, 'strategy', 0.5, "
            "'2026-08-01T00:00:00Z', 'link', 0, 0, 'https://kent.gov.uk/list', "
            "'2026-08-01T00:00:00Z', 200, 'm09', 'listing-hash')",
            (f"https://kent.gov.uk/doc{i}.pdf", f"Kent document {i}"))
    conn.commit()
    return conn


# --- reading -------------------------------------------------------------------


def test_counts_report_the_gap_this_screen_exists_to_close(client, seeded):
    payload = client.get("/api/admin/candidates/counts").json()

    cdp = payload["kinds"]["cdp_document"]
    assert cdp["undecided"] == 3
    assert cdp["evidence_rows"] == 0
    assert set(payload["kinds"]) == {"cdp_document", "committee_paper", "foi_request"}


def test_the_listing_is_undecided_by_default(client, seeded):
    payload = client.get("/api/admin/candidates?kind=cdp_document").json()

    assert payload["total"] == 3
    assert len(payload["items"]) == 3
    assert payload["requires"] == ["document_type"], (
        "the UI builds its confirm field from this")


def test_a_candidate_shows_where_it_was_found_not_where_it_leads(client, seeded):
    """The candidate's provenance is the listing page. Labelling it as such is
    the difference between a link and a citation."""
    item = client.get("/api/admin/candidates?kind=cdp_document").json()["items"][0]

    assert item["url"] == "https://kent.gov.uk/doc0.pdf"
    assert item["discovered"]["source_url"] == "https://kent.gov.uk/list"


def test_the_listing_can_be_searched_and_filtered(client, seeded):
    assert client.get(
        "/api/admin/candidates?kind=cdp_document&q=document 1").json()["total"] == 1
    assert client.get(
        "/api/admin/candidates?kind=cdp_document&authority=E10000016").json()["total"] == 3
    assert client.get(
        "/api/admin/candidates?kind=cdp_document&authority=E09000001").json()["total"] == 0


def test_a_percent_sign_is_searched_for_literally(client, seeded):
    assert client.get("/api/admin/candidates?kind=cdp_document&q=%25").json()["total"] == 0


def test_authorities_are_listed_for_the_filter(client, seeded):
    payload = client.get(
        "/api/admin/candidates/authorities?kind=cdp_document").json()

    assert payload["authorities"] == [
        {"ons_code": "E10000016", "name": "Kent", "candidates": 3}]


def test_an_unknown_kind_is_a_400(client, seeded):
    response = client.get("/api/admin/candidates?kind=spreadsheets")

    assert response.status_code == 400
    assert "unknown candidate kind" in response.json()["error"]


def test_an_unknown_status_is_a_400(client, seeded):
    assert client.get(
        "/api/admin/candidates?kind=cdp_document&status=maybe").status_code == 400


def test_a_missing_candidate_detail_is_a_404(client, seeded):
    assert client.get(
        "/api/admin/candidates/detail?kind=cdp_document&url=nope").status_code == 404


# --- writing -------------------------------------------------------------------


def test_promoting_needs_a_json_content_type(client, seeded):
    response = client.post("/api/admin/candidates/promote",
                            content=b"kind=cdp_document", headers={})
    assert response.status_code in (400, 415)


def test_promoting_from_another_origin_is_refused(client, seeded):
    response = client.post(
        "/api/admin/candidates/promote",
        json={"kind": "cdp_document", "url": "https://kent.gov.uk/doc0.pdf",
               "promoted_by": "Jon", "fields": {"document_type": "strategy"}},
        headers={"Origin": "https://evil.example"})

    assert response.status_code == 403


def test_promoting_cannot_be_done_by_a_get(client, seeded):
    assert client.get("/api/admin/candidates/promote").status_code == 404


def test_promoting_anonymously_is_refused_before_any_fetch(client, seeded):
    """No network call is made: the refusal is about the request, and a fetch
    would be a request made to a public source on nobody's behalf."""
    response = client.post(
        "/api/admin/candidates/promote",
        json={"kind": "cdp_document", "url": "https://kent.gov.uk/doc0.pdf",
               "promoted_by": "", "fields": {"document_type": "strategy"}})

    assert response.status_code == 400
    assert "attributed" in response.json()["error"]


def test_promoting_without_confirming_the_type_is_refused(client, seeded):
    response = client.post(
        "/api/admin/candidates/promote",
        json={"kind": "cdp_document", "url": "https://kent.gov.uk/doc0.pdf",
               "promoted_by": "Jon", "fields": {}})

    assert response.status_code == 400
    assert "document_type" in response.json()["error"]


def test_there_is_no_bulk_promote_route(client, seeded):
    """The act recorded is that somebody opened the document. A route taking a
    list would make pretending cheap."""
    for path in ("/api/admin/candidates/promote-many",
                  "/api/admin/candidates/promote-all"):
        assert client.post(path, json={}).status_code == 404

    response = client.post(
        "/api/admin/candidates/promote",
        json={"kind": "cdp_document",
               "urls": ["https://kent.gov.uk/doc0.pdf",
                         "https://kent.gov.uk/doc1.pdf"],
               "promoted_by": "Jon", "fields": {"document_type": "strategy"}})
    assert response.status_code == 400, "a list of urls is not a url"


def test_rejecting_is_bulk_and_attributed(client, seeded):
    response = client.post(
        "/api/admin/candidates/reject",
        json={"kind": "cdp_document",
               "urls": ["https://kent.gov.uk/doc0.pdf",
                         "https://kent.gov.uk/doc1.pdf"],
               "rejected_by": "Jon"})

    assert response.status_code == 200
    assert response.json() == {"rejected": 2}
    assert client.get(
        "/api/admin/candidates?kind=cdp_document").json()["total"] == 1


def test_rejecting_anonymously_is_refused(client, seeded):
    response = client.post(
        "/api/admin/candidates/reject",
        json={"kind": "cdp_document", "urls": ["https://kent.gov.uk/doc0.pdf"],
               "rejected_by": " "})

    assert response.status_code == 400


def test_rejecting_needs_a_list_of_strings(client, seeded):
    response = client.post(
        "/api/admin/candidates/reject",
        json={"kind": "cdp_document", "urls": "everything", "rejected_by": "Jon"})

    assert response.status_code == 400


def test_a_rejected_candidate_can_be_reset(client, seeded):
    client.post("/api/admin/candidates/reject",
                 json={"kind": "cdp_document",
                        "urls": ["https://kent.gov.uk/doc0.pdf"],
                        "rejected_by": "Jon"})

    response = client.post("/api/admin/candidates/reset",
                            json={"kind": "cdp_document",
                                   "url": "https://kent.gov.uk/doc0.pdf"})

    assert response.status_code == 200
    assert client.get(
        "/api/admin/candidates?kind=cdp_document").json()["total"] == 3


# --- the batch path ------------------------------------------------------------
#
# The gate that makes a batch promote acceptable lives in the browser: only
# candidates the operator opened in this session can be sent. That cannot be
# exercised from here, so what these pin is the pair of properties that keep
# it meaningful -- the shipped script still sends one URL per request, and the
# gate is not something a later edit can quietly drop while leaving the button.


def _candidates_js() -> str:
    from pipeline.web.server import STATIC_DIR

    return (STATIC_DIR / "js" / "candidates.js").read_text(encoding="utf-8")


def test_the_batch_promotes_through_the_single_url_route():
    """One request per candidate. A body carrying `urls` to the promote route
    would be a bulk promote whatever the button said."""
    source = _candidates_js()
    promote_calls = source.count("'/api/admin/candidates/promote'")
    assert promote_calls == 2, (
        "expected exactly two callers of the promote route -- the single-row "
        "button and the batch loop -- found "
        f"{promote_calls}")
    assert "urls," not in source.split("candidates/promote'")[1][:400], (
        "the promote route is being sent a list")


def test_the_batch_cannot_send_a_candidate_nobody_opened():
    """`partitionSelection` is the gate. If it stops naming `opened`, a
    selection promotes documents nobody looked at."""
    source = _candidates_js()
    assert "state.opened.has(url)" in source, (
        "the opened-in-this-session check is gone from partitionSelection")
    assert "blocked.push" in source, (
        "excluded candidates are no longer reported to the operator")


def test_the_batch_runs_one_at_a_time():
    """Parallel promotion would fight the per-host rate limit and the
    process-wide write slot, and would make the progress line a lie."""
    source = _candidates_js()
    body = source.split("async function promoteOpened()")[1]
    assert "for (const [index, item] of ready.entries())" in body

    # The loop itself, not the refresh after it -- reloading the counts and
    # the list together is fine and is not what this is about.
    loop = body.split("for (const [index, item] of ready.entries())")[1]
    loop = loop.split("state.busy = false;")[0]
    assert "Promise.all" not in loop, "the batch is promoting in parallel"


# --- the isolation contract ----------------------------------------------------


def test_none_of_this_is_reachable_from_the_portal(client, seeded):
    for route in ("candidates", "candidates/counts", "candidates/promote"):
        assert client.get(f"/api/v1/{route}").status_code == 404
