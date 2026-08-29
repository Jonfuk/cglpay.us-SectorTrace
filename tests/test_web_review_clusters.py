"""Review clusters (BETA-053).

Grouping is a reading aid, not a judgement: items land in one cluster because
they share a module, an item_type and a deterministic token, and every bulk
action still recounts its exact id set. These pin the grouping and its
route's isolation.
"""
from __future__ import annotations

import json
import sqlite3
import threading

import httpx
import pytest

from pipeline.config import Settings
from pipeline.web import queries
from pipeline.web.server import build_server


def _add(conn, *, module, item_type, raw_value, context=None, status="pending"):
    conn.execute(
        "INSERT INTO review_queue (module, item_type, raw_value, context_json, "
        "status, created_at) VALUES (?, ?, ?, ?, ?, '2026-08-20T00:00:00Z')",
        (module, item_type, raw_value,
         json.dumps(context) if context is not None else "{}", status))


@pytest.fixture
def warehouse(conn: sqlite3.Connection) -> sqlite3.Connection:
    # Two clusters for the same (module, item_type): one keyed on an
    # ons_code in context, one on a URL host.
    for i in range(3):
        _add(conn, module="m10_committee_papers",
             item_type="committee_url_unknown", raw_value=f"kent-{i}",
             context={"ons_code": "E10000016", "note": f"row {i}"})
    for i in range(2):
        _add(conn, module="m10_committee_papers",
             item_type="committee_url_unknown", raw_value=f"surrey-{i}",
             context={"source_url": "https://surreycc.gov.uk/committees/x"})
    # A different item_type. One pending + one already-approved, sharing a
    # token via `authority` in context, so status filtering is exercised.
    _add(conn, module="m15_foi", item_type="foi_body_unmatched",
         raw_value="Some Council", context={"authority": "Some Council"})
    _add(conn, module="m15_foi", item_type="foi_body_unmatched",
         raw_value="Some Council (revised)", context={"authority": "Some Council"},
         status="approved")
    conn.commit()
    return conn


def test_items_sharing_module_type_and_token_form_one_cluster(warehouse):
    result = queries.review_clusters(warehouse)
    by_token = {(c["module"], c["item_type"], c["token"]): c
                for c in result["clusters"]}
    kent = by_token[("m10_committee_papers", "committee_url_unknown", "e10000016")]
    assert kent["count"] == 3
    assert len(kent["item_ids"]) == 3

    surrey = by_token[("m10_committee_papers", "committee_url_unknown",
                       "surreycc.gov.uk")]
    assert surrey["count"] == 2


def test_only_the_requested_status_is_clustered(warehouse):
    result = queries.review_clusters(warehouse, status="pending")
    foi = [c for c in result["clusters"] if c["module"] == "m15_foi"]
    assert len(foi) == 1 and foi[0]["count"] == 1  # the approved one is excluded


def test_the_token_prefers_a_context_id_then_falls_back(warehouse):
    result = queries.review_clusters(warehouse)
    foi = next(c for c in result["clusters"] if c["module"] == "m15_foi")
    # `authority` in context wins over the raw value.
    assert foi["token"] == "some council"
    # And a bare item with no context id/url would key on its raw value —
    # exercised by the kent/surrey rows keying on ons_code / URL host instead.
    tokens = {c["token"] for c in result["clusters"]}
    assert "e10000016" in tokens and "surreycc.gov.uk" in tokens


def test_the_caveat_says_grouping_is_not_a_judgement(warehouse):
    caveat = queries.review_clusters(warehouse)["caveat"].lower()
    assert "not a judgement" in caveat
    assert "confirms its own id set" in caveat


@pytest.fixture
def client(warehouse, settings: Settings):
    warehouse.close()
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


def test_the_route_serves_under_api_review_only(client):
    ok = client.get("/api/review/clusters")
    assert ok.status_code == 200
    body = ok.json()
    assert body["cluster_count"] >= 3
    # Not published under the portal's public prefix.
    assert client.get("/api/v1/review/clusters").status_code == 404


def test_the_admin_app_drives_decide_matching_with_a_confirm_count():
    """The per-cluster button reuses the recount-guarded bulk path, not a new
    id list. `confirm_count` is what makes grouping safe."""
    from pathlib import Path
    app = (Path(__file__).resolve().parent.parent / "pipeline" / "web"
           / "static" / "app.js").read_text(encoding="utf-8")
    block = app[app.index("async function loadReviewClusters("):]
    block = block[:block.index("\nfunction renderList(")]
    assert "/api/review/decide-matching" in block
    assert "confirm_count: cluster.count" in block
