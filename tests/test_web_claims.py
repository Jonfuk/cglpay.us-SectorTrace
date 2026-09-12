"""The claims worklist over HTTP.

The rules themselves are tested in test_claims.py. What matters here is that
the routes do not offer a way around them: no anonymous decisions, no bulk
publishing, the same refusals, and every write behind the same content-type
and Origin guard as the rest of the operator UI. And the public side: the
"What we can say" page serves only published claims, with their citations
resolved.
"""
from __future__ import annotations

import threading

import httpx
import pytest

from pipeline import claims
from pipeline.web.server import build_server

RATE_KEY = claims.build_key(
    {"period_label": "April 2026", "band_label": "21 and over"},
    ("period_label", "band_label"))


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
        "INSERT INTO statutory_pay_rates (period_label, band_label, band_role, "
        "amount, value_text, source_url, retrieved_at, http_status, source_system, "
        "payload_sha256) VALUES ('April 2026', '21 and over', "
        "'national_living_wage', 12.71, '12.71', 'https://gov.uk/rates', "
        "'2026-01-01T00:00:00Z', 200, 'm17', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')")
    conn.commit()
    return conn


def _create(client, text="A claim.", by="Jon"):
    response = client.post("/api/admin/claims/create", json={
        "claim_text": text, "caveats": "Not a pay scale.",
        "created_by": by, "note": None})
    assert response.status_code == 200, response.text
    return response.json()


# --- reading -------------------------------------------------------------------


def test_the_worklist_is_all_by_default(client):
    payload = client.get("/api/admin/claims").json()

    assert payload["status"] == "all"
    assert payload["total"] == 0
    assert payload["items"] == []


def test_counts_and_the_status_filter(client, seeded):
    claim = _create(client)
    client.post("/api/admin/claims/decide", json={
        "claim_id": claim["id"], "decision": "published", "decided_by": "Ruth"})

    counts = client.get("/api/admin/claims/counts").json()
    assert (counts["draft"], counts["published"], counts["total"]) == (0, 1, 1)
    assert counts["decisions"][0]["decided_by"] == "Ruth"

    drafts = client.get("/api/admin/claims?status=draft").json()
    assert drafts["total"] == 0
    published = client.get("/api/admin/claims?status=published").json()
    assert published["total"] == 1


def test_an_unknown_status_is_refused(client):
    assert client.get("/api/admin/claims?status=promoted").status_code == 400


def test_the_citable_tables_list_answers_without_a_table(client):
    payload = client.get("/api/admin/claims/evidence").json()
    assert "statutory_pay_rates" in payload["tables"]
    assert "contracts" not in payload["tables"]


def test_the_evidence_search_returns_pickable_rows(client, seeded):
    payload = client.get(
        "/api/admin/claims/evidence?table=statutory_pay_rates&q=April").json()

    assert len(payload["rows"]) == 1
    assert payload["rows"][0]["key"] == RATE_KEY
    assert "£12.71" in payload["rows"][0]["label"]


def test_the_evidence_search_refuses_an_unknown_table(client):
    assert client.get(
        "/api/admin/claims/evidence?table=contracts&q=x").status_code == 400


# --- writing -------------------------------------------------------------------


def test_writing_needs_a_json_content_type(client):
    response = client.post("/api/admin/claims/create", content=b"claim_text=abc",
                            headers={})
    assert response.status_code in (400, 415)


def test_writing_from_another_origin_is_refused(client):
    response = client.post(
        "/api/admin/claims/create",
        json={"claim_text": "A claim.", "created_by": "Jon"},
        headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_creating_anonymously_is_refused(client):
    response = client.post("/api/admin/claims/create", json={
        "claim_text": "A claim.", "created_by": ""})
    assert response.status_code == 400
    assert "attributed" in response.json()["error"]


def test_the_create_route_takes_one_claim_and_not_a_list(client):
    response = client.post("/api/admin/claims/create", json={
        "claims": [{"claim_text": "A claim."}], "created_by": "Jon"})
    assert response.status_code == 400


def test_cite_and_uncite_over_http(client, seeded):
    claim = _create(client)
    response = client.post("/api/admin/claims/cite", json={
        "claim_id": claim["id"], "evidence_table": "statutory_pay_rates",
        "evidence_key": RATE_KEY, "cited_by": "Jon"})
    assert response.status_code == 200
    assert len(response.json()["citations"]) == 1

    response = client.post("/api/admin/claims/uncite", json={
        "claim_id": claim["id"], "evidence_table": "statutory_pay_rates",
        "evidence_key": RATE_KEY})
    assert response.status_code == 200
    assert len(response.json()["citations"]) == 0


def test_citing_something_that_does_not_resolve_is_refused(client, seeded):
    claim = _create(client)
    response = client.post("/api/admin/claims/cite", json={
        "claim_id": claim["id"], "evidence_table": "statutory_pay_rates",
        "evidence_key": "nope\x1fnope", "cited_by": "Jon"})
    assert response.status_code == 400
    assert "No citable row" in response.json()["error"]


def test_deciding_anonymously_is_refused(client):
    claim = _create(client)
    response = client.post("/api/admin/claims/decide", json={
        "claim_id": claim["id"], "decision": "published", "decided_by": ""})
    assert response.status_code == 400


def test_the_decide_route_takes_one_claim_and_not_a_list(client):
    response = client.post("/api/admin/claims/decide", json={
        "claims": [1], "decision": "published", "decided_by": "Ruth"})
    assert response.status_code == 400


def test_an_unknown_decision_is_refused(client):
    claim = _create(client)
    response = client.post("/api/admin/claims/decide", json={
        "claim_id": claim["id"], "decision": "verified", "decided_by": "Ruth"})
    assert response.status_code == 400


def test_deciding_end_to_end(client):
    claim = _create(client)
    response = client.post("/api/admin/claims/decide", json={
        "claim_id": claim["id"], "decision": "published", "decided_by": "Ruth",
        "note": "reviewed"})
    assert response.status_code == 200
    assert response.json()["status"] == "published"
    assert response.json()["decisions"][-1]["decided_by"] == "Ruth"


def test_resetting_puts_a_claim_back_in_the_worklist(client):
    claim = _create(client)
    client.post("/api/admin/claims/decide", json={
        "claim_id": claim["id"], "decision": "published", "decided_by": "Ruth"})
    response = client.post("/api/admin/claims/reset", json={
        "claim_id": claim["id"]})
    assert response.status_code == 200
    assert response.json()["status"] == "draft"
    assert len(response.json()["decisions"]) == 1, "the judgement is still on record"


def test_editing_a_published_claim_is_refused(client):
    claim = _create(client)
    client.post("/api/admin/claims/decide", json={
        "claim_id": claim["id"], "decision": "published", "decided_by": "Ruth"})
    response = client.post("/api/admin/claims/update", json={
        "claim_id": claim["id"], "claim_text": "Rewritten."})
    assert response.status_code == 400
    assert "Reset it before editing" in response.json()["error"]


# --- the public side -----------------------------------------------------------


def _published(client, text="The floor is £12.71."):
    claim = _create(client, text=text)
    client.post("/api/admin/claims/cite", json={
        "claim_id": claim["id"], "evidence_table": "statutory_pay_rates",
        "evidence_key": RATE_KEY, "cited_by": "Jon"})
    client.post("/api/admin/claims/decide", json={
        "claim_id": claim["id"], "decision": "published", "decided_by": "Ruth"})
    return claim


def test_the_portal_serves_published_claims_with_their_citations(client, seeded):
    _published(client)

    payload = client.get("/api/v1/claims").json()
    assert len(payload["claims"]) == 1
    claim = payload["claims"][0]
    assert claim["claim_text"] == "The floor is £12.71."
    assert claim["caveats"] == ["Not a pay scale."]
    assert claim["published_by"] == "Ruth"
    assert claim["citations"][0]["table"] == "statutory_pay_rates"
    resolved = claim["citations"][0]["resolved"]
    assert "£12.71" in resolved["label"]
    assert resolved["url"] == "https://gov.uk/rates"


def test_the_portal_never_serves_drafts_rejections_or_retractions(client, seeded):
    claim = _create(client)
    client.post("/api/admin/claims/decide", json={
        "claim_id": claim["id"], "decision": "rejected", "decided_by": "Ruth"})
    claim = _create(client, text="A second claim.")
    client.post("/api/admin/claims/decide", json={
        "claim_id": claim["id"], "decision": "published", "decided_by": "Ruth"})
    client.post("/api/admin/claims/decide", json={
        "claim_id": claim["id"], "decision": "retracted", "decided_by": "Ruth"})

    payload = client.get("/api/v1/claims").json()
    assert payload["claims"] == []


def test_the_portal_renders_an_unresolvable_citation_honestly(client, seeded, conn):
    _published(client)
    conn.execute("DELETE FROM statutory_pay_rates")
    conn.commit()

    payload = client.get("/api/v1/claims").json()
    citation = payload["claims"][0]["citations"][0]
    assert citation["resolved"] is None


def test_the_claims_page_and_module_are_served(client):
    assert client.get("/js/pages/claims.js").status_code == 200
    html = client.get("/").text
    assert 'data-route="claims"' in html
    api = client.get("/api").text
    assert 'data-route="claims"' in api
    assert "/api/v1/claims" in api


# --- the operator asset the screen needs ---------------------------------------


def test_the_claims_module_is_served(client):
    response = client.get("/admin/js/claims.js")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/javascript")


def test_the_screen_and_the_module_agree_on_their_element_ids(client):
    """The panel is markup in one file and behaviour in another, wired by id.
    A rename in either is invisible until somebody opens the tab."""
    html = client.get("/admin").text
    script = client.get("/admin/js/claims.js").text

    for element_id in ("claim-counts", "claim-list", "claim-pager",
                        "claim-status", "claim-status-filter", "claim-create",
                        "claim-new-text", "claim-new-caveats", "claim-new-note",
                        "claim-history", "claim-pill", "tab-claims"):
        assert f'id="{element_id}"' in html, f"{element_id} is not in the page"
        assert f"'{element_id}'" in script or element_id == "tab-claims", (
            f"{element_id} is not read by claims.js")


def test_the_router_knows_the_claims_tab(client):
    """The tab button, the panel and the module can all exist while the tab
    never loads: app.js's TABS list is the router, and a tab it does not know
    falls back to overview when clicked. This is exactly how the Claims tab
    shipped broken — the button rendered and the panel stayed empty."""
    app = client.get("/admin/app.js").text
    assert "'claims'" in app, "app.js's TABS list does not name the claims tab"
    assert "'census'" in app, "app.js's TABS list has lost the census tab"
