"""Evidence sidecar for a review item (BETA-054).

Beside the decision form: the item's own source excerpt, and — for the
name-match types — ranked candidates relabelled as a similarity percentage.
An aid, never a verdict: nothing is preselected, generic false-match names
are suppressed, and approving the item still writes nothing canonical.
"""
from __future__ import annotations

import json
import sqlite3
import threading

import httpx
import pytest

from pipeline.config import Settings
from pipeline.web import sidecar as sidecar_mod
from pipeline.web.queries import QueryError
from pipeline.web.server import build_server


def _authority(conn, ons_code, name):
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, active_to, "
        " first_seen_vintage, last_seen_vintage, source_url, retrieved_at, "
        " http_status, source_system, payload_sha256) VALUES (%s, %s, 'unitary', "
        " '2021-04-01', NULL, '2024', '2026', 'https://ons.example', "
        " '2026-08-01T00:00:00Z', 200, 'ons', 'x')",
        (ons_code, name))


def _item(conn, item_type, raw_value, context=None):
    cur = conn.execute(
        "INSERT INTO review_queue (module, item_type, raw_value, context_json, "
        "created_at) VALUES ('m01_procurement', %s, %s, %s, '2026-08-01T00:00:00Z') RETURNING id",
        (item_type, raw_value, json.dumps(context) if context else "{}"))
    return cur.fetchone().values().__iter__().__next__()


@pytest.fixture
def warehouse(conn: sqlite3.Connection) -> sqlite3.Connection:
    _authority(conn, "E06000019", "Herefordshire, County of")
    _authority(conn, "E08000025", "Birmingham City Council")
    _authority(conn, "E10000000", "Council")  # a generic false match
    conn.commit()
    return conn


def test_the_sidecar_ranks_candidates_and_labels_them_as_similarity(warehouse):
    item_id = _item(warehouse, "unmatched_buyer_name", "Herefordshire Council")
    result = sidecar_mod.sidecar(warehouse, item_id)

    assert result["candidates"]["supported"] is True
    ranking = result["candidates"]["ranking"]
    assert ranking, "expected at least one candidate"
    top = ranking[0]
    assert top["name"] == "Herefordshire, County of"
    assert "similarity_percent" in top and top["preselected"] is False
    assert "score" not in top  # relabelled, not the raw name_matches field


def test_generic_false_match_names_are_suppressed(warehouse):
    item_id = _item(warehouse, "unmatched_buyer_name", "The Council")
    result = sidecar_mod.sidecar(warehouse, item_id)
    ranking_names = {m["name"] for m in result["candidates"]["ranking"]}
    suppressed_names = {m["name"] for m in result["candidates"]["suppressed"]}
    assert "Council" not in ranking_names
    assert "Council" in suppressed_names


def test_the_source_excerpt_comes_from_the_items_own_context(warehouse):
    item_id = _item(warehouse, "semantic_claim_candidate", "cc-1", context={
        "sentence": "The provider is struggling to recruit.",
        "source_url": "https://example.org/paper", "retrieved_at": "2026-08-01T00:00:00Z",
        "payload_sha256": "abc123def456"})
    result = sidecar_mod.sidecar(warehouse, item_id)
    assert result["source"]["excerpt"] == "The provider is struggling to recruit."
    assert result["source"]["url"] == "https://example.org/paper"
    # Not a name-match type — no candidate ranking, and that is stated.
    assert result["candidates"]["supported"] is False


def test_an_item_with_no_excerpt_says_so(warehouse):
    item_id = _item(warehouse, "some_other_type", "raw", context={})
    result = sidecar_mod.sidecar(warehouse, item_id)
    assert result["source"]["excerpt"] is None
    assert "no source excerpt" in result["source"]["note"].lower()


def test_an_unknown_item_is_a_query_error(warehouse):
    with pytest.raises(QueryError):
        sidecar_mod.sidecar(warehouse, 999999)


def test_the_caveat_says_nothing_is_preselected(warehouse):
    item_id = _item(warehouse, "unmatched_buyer_name", "Herefordshire Council")
    caveat = sidecar_mod.sidecar(warehouse, item_id)["caveat"].lower()
    assert "does not pick one" in caveat and "preselected" in caveat


@pytest.fixture
def client(warehouse, settings: Settings):
    item_id = _item(warehouse, "unmatched_buyer_name", "Herefordshire Council")
    warehouse.commit()
    warehouse.close()
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=10.0) as http:
            http.item_id = item_id
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_the_route_serves_under_api_review_only(client):
    ok = client.get(f"/api/review/{client.item_id}/sidecar")
    assert ok.status_code == 200
    assert ok.json()["item_id"] == client.item_id
    assert client.get(f"/api/v1/review/{client.item_id}/sidecar").status_code == 404
    assert client.get("/api/review/999999/sidecar").status_code == 400
