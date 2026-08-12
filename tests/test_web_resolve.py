"""Resolving a review item into an answer the pipeline uses.

The test that matters here is not that a row lands in a table — it is that
`website_for()` returns the reviewer's URL afterwards, because that is the
only reason any of this is worth building. A resolution that writes a row no
module reads is a form that lies to whoever fills it in.
"""
from __future__ import annotations

import json
import sqlite3

import httpx
import pytest

from pipeline import db
from pipeline.authority_websites import AUTHORITY_WEBSITES, website_for
from pipeline.web import resolve


@pytest.fixture
def queued(conn: sqlite3.Connection) -> sqlite3.Connection:
    """The two resolvable item types, as the modules actually raise them."""
    db.record_review_item(
        conn, "m09_cdp_documents", "authority_website_unknown", "E09000002",
        json.dumps({"authority": "Barking and Dagenham",
                     "note": "add a verified entry to pipeline/authority_websites.py"}))
    db.record_review_item(
        conn, "m10_committee_papers", "committee_url_unknown", "E09000003",
        json.dumps({"authority": "Barnet"}))
    db.record_review_item(
        conn, "m01_procurement", "unmatched_buyer_name", "Some Trust")
    conn.commit()
    return conn


def item_for(conn: sqlite3.Connection, item_type: str) -> int:
    return conn.execute(
        "SELECT id FROM review_queue WHERE item_type = ?", (item_type,)).fetchone()["id"]


@pytest.fixture
def answering(monkeypatch):
    """A site that answers, with the ModernGov signature paths present."""
    seen: list[str] = []

    def fake_check(url, settings=None, conn=None):
        url = resolve.normalise_url(url)
        seen.append(url)
        return {"url": url, "status": 200, "ok": True,
                 "system": "moderngov", "signature": "/mgWhatsNew.aspx", "error": None}

    monkeypatch.setattr(resolve, "check_url", fake_check)
    return seen


# --- URL hygiene --------------------------------------------------------------


def test_a_url_without_a_scheme_is_accepted_not_rejected():
    """Typing a council domain without https:// is the common case."""
    assert resolve.normalise_url("www.kent.gov.uk") == "https://www.kent.gov.uk"
    assert resolve.normalise_url("https://democracy.kent.gov.uk/") == "https://democracy.kent.gov.uk"
    # A host and port is a host and port, not a scheme called
    # `democracy.kent.gov.uk`.
    assert resolve.normalise_url("democracy.kent.gov.uk:8443") == "https://democracy.kent.gov.uk:8443"


def test_unfetchable_schemes_are_refused_before_any_request():
    for bad in ["file:///etc/passwd", "javascript:alert(1)", "ftp://x.gov.uk"]:
        with pytest.raises(resolve.ResolveError, match="http"):
            resolve.normalise_url(bad)
    for bad in ["", "   ", "not a url"]:
        with pytest.raises(resolve.ResolveError):
            resolve.normalise_url(bad)


# --- resolving ----------------------------------------------------------------


def test_resolving_stores_the_url_and_approves_the_item(queued, answering):
    item_id = item_for(queued, "committee_url_unknown")
    result = resolve.resolve_authority_url(
        queued, item_id, "democracy.barnet.gov.uk", resolved_by="Jon")

    assert result["ons_code"] == "E09000003"
    assert result["url"] == "https://democracy.barnet.gov.uk"
    assert result["system"] == "moderngov"

    row = queued.execute(
        "SELECT * FROM authority_url_overrides WHERE ons_code = 'E09000003'").fetchone()
    assert row["committee_url"] == "https://democracy.barnet.gov.uk"
    assert row["committee_system"] == "moderngov"
    assert row["checked_status"] == 200
    assert row["verified_by"] == "Jon"
    assert row["review_item_id"] == item_id

    item = queued.execute("SELECT * FROM review_queue WHERE id = ?", (item_id,)).fetchone()
    assert item["status"] == "approved"

    # The decision records what was actually done, not just "approved".
    decision = queued.execute(
        "SELECT * FROM review_decisions WHERE review_item_id = ?", (item_id,)).fetchone()
    assert "democracy.barnet.gov.uk" in decision["note"]
    assert decision["decided_by"] == "Jon"


def test_a_resolved_url_is_what_the_modules_then_see(queued, answering):
    """The whole point. Before: nothing, which is why the item was raised."""
    assert website_for("E09000003", queued) is None

    resolve.resolve_authority_url(
        queued, item_for(queued, "committee_url_unknown"),
        "democracy.barnet.gov.uk", resolved_by="Jon")

    site = website_for("E09000003", queued)
    assert site is not None
    assert site.committee_url == "https://democracy.barnet.gov.uk"
    assert site.committee_system == "moderngov"
    # Labelled, so Module 10 does not record a human answer as a registry one.
    assert site.source == "human_verified"


def test_a_committee_answer_is_not_taken_as_a_website_answer(queued, answering):
    """The two questions are about different hosts.

    A reviewer answering `committee_url_unknown` has said where the committee
    system is, not where the council publishes documents. Module 9 searching
    a committee portal for its document paths finds nothing and records the
    authority as having published nothing — the silent failure this whole
    registry exists to avoid. So base_url stays empty and Module 9 keeps
    asking.
    """
    resolve.resolve_authority_url(
        queued, item_for(queued, "committee_url_unknown"),
        "democracy.barnet.gov.uk", resolved_by="Jon")

    site = website_for("E09000003", queued)
    assert site.committee_url == "https://democracy.barnet.gov.uk"
    assert not site.base_url, (
        "a committee URL was promoted to base_url; Module 9 would search the "
        "committee portal for council documents")


def test_a_website_answer_serves_module_9(queued, answering):
    resolve.resolve_authority_url(
        queued, item_for(queued, "authority_website_unknown"),
        "https://www.lbbd.gov.uk", resolved_by="Jon")

    site = website_for("E09000002", queued)
    assert site.base_url == "https://www.lbbd.gov.uk"


def test_answering_one_question_does_not_erase_the_other(queued, answering):
    """An authority can raise both item types. Two separate answers, one row."""
    resolve.resolve_authority_url(
        queued, item_for(queued, "authority_website_unknown"),
        "https://www.lbbd.gov.uk", resolved_by="Jon")

    db.record_review_item(queued, "m10_committee_papers", "committee_url_unknown",
                           "E09000002", None)
    second = queued.execute(
        "SELECT id FROM review_queue WHERE item_type = 'committee_url_unknown' "
        "AND raw_value = 'E09000002'").fetchone()["id"]
    resolve.resolve_authority_url(
        queued, second, "https://democracy.lbbd.gov.uk", resolved_by="Jon")

    site = website_for("E09000002", queued)
    assert site.base_url == "https://www.lbbd.gov.uk"
    assert site.committee_url == "https://democracy.lbbd.gov.uk"


def test_a_url_that_does_not_answer_is_not_stored(queued, monkeypatch):
    """The rule the whole module exists for.

    A wrong URL does not fail loudly at run time — it searches an unreachable
    site and finds nothing, which looks exactly like a council that publishes
    nothing. Storing one unchecked would put that failure into a table the
    modules treat as authoritative.
    """
    monkeypatch.setattr(resolve, "check_url", lambda url, settings=None, conn=None: {
        "url": resolve.normalise_url(url), "status": 404, "ok": False,
        "system": "unknown", "signature": None, "error": None})

    item_id = item_for(queued, "committee_url_unknown")
    with pytest.raises(resolve.ResolveError, match="did not answer"):
        resolve.resolve_authority_url(queued, item_id, "https://nope.example", resolved_by="Jon")

    assert queued.execute("SELECT COUNT(*) FROM authority_url_overrides").fetchone()[0] == 0
    assert queued.execute(
        "SELECT status FROM review_queue WHERE id = ?", (item_id,)).fetchone()[0] == "pending"


def test_robots_disallowed_is_reported_rather_than_ignored(queued, monkeypatch):
    monkeypatch.setattr(resolve, "check_url", lambda url, settings=None, conn=None: {
        "url": resolve.normalise_url(url), "status": None, "ok": False,
        "system": "unknown", "signature": None,
        "error": "That site's robots.txt disallows this path for automated clients"})

    with pytest.raises(resolve.ResolveError, match="robots.txt"):
        resolve.resolve_authority_url(
            queued, item_for(queued, "committee_url_unknown"),
            "https://blocked.example", resolved_by="Jon")


def test_only_resolvable_item_types_take_a_url(queued, answering):
    with pytest.raises(resolve.ResolveError, match="not resolvable"):
        resolve.resolve_authority_url(
            queued, item_for(queued, "unmatched_buyer_name"),
            "https://example.gov.uk", resolved_by="Jon")


def test_resolving_needs_a_reviewer(queued, answering):
    with pytest.raises(resolve.ResolveError, match="reviewer name"):
        resolve.resolve_authority_url(
            queued, item_for(queued, "committee_url_unknown"),
            "https://democracy.barnet.gov.uk", resolved_by="  ")


def test_an_unknown_item_is_refused(queued, answering):
    with pytest.raises(resolve.ResolveError, match="No review item"):
        resolve.resolve_authority_url(queued, 999999, "https://x.gov.uk", resolved_by="Jon")


# --- precedence ---------------------------------------------------------------


def test_the_code_registry_still_answers_for_authorities_nobody_reviewed(queued):
    """The registry is the seed, not a casualty. Anything nobody has been
    asked about still resolves exactly as before."""
    known = next(iter(AUTHORITY_WEBSITES))
    site = website_for(known, queued)
    assert site is not None
    assert site.source == "registry"


def test_a_warehouse_without_the_overrides_table_still_resolves(settings, monkeypatch):
    """These modules predate the reviewer. A missing table means "nobody has
    answered", not a crash on every authority."""
    conn = db.get_connection(settings)
    db.apply_migrations(conn, settings.migrations_dir)
    conn.execute("DROP TABLE authority_url_overrides")
    conn.commit()

    known = next(iter(AUTHORITY_WEBSITES))
    assert website_for(known, conn) is not None
    assert website_for("E09000003", conn) is None
    conn.close()


# --- over HTTP ----------------------------------------------------------------


@pytest.fixture
def client(queued, settings):
    import threading

    from pipeline.web.server import build_server

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


def test_the_ui_is_told_which_types_it_can_offer_a_form_for(client):
    facets = client.get("/api/review/facets").json()
    assert set(facets["resolvable"]) == {"authority_website_unknown", "committee_url_unknown"}
    assert facets["resolvable"]["committee_url_unknown"]["field"] == "committee_url"


def test_resolving_over_http(client, queued, answering):
    item_id = item_for(queued, "committee_url_unknown")
    response = client.post("/api/review/resolve", json={
        "id": item_id, "url": "democracy.barnet.gov.uk", "resolved_by": "Jon"})
    assert response.status_code == 200
    assert response.json()["url"] == "https://democracy.barnet.gov.uk"

    listed = client.get("/api/overrides").json()["overrides"]
    assert [o["ons_code"] for o in listed] == ["E09000003"]


def test_a_bad_resolution_is_a_400_with_a_readable_message(client, queued, answering):
    response = client.post("/api/review/resolve", json={
        "id": item_for(queued, "unmatched_buyer_name"),
        "url": "https://example.gov.uk", "resolved_by": "Jon"})
    assert response.status_code == 400
    assert "not resolvable" in response.json()["error"]
