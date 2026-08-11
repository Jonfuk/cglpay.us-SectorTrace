"""The review UI: what it may read, what it may write, and what it refuses.

The interesting assertions here are the negative ones. A tool that shows the
warehouse in a browser and writes decisions back is the first thing in this
pipeline that can damage the evidence base by accident, so the tests that
matter most are the ones fixing what it *cannot* do: write through the
browsing connection, resurrect a decided item's context on the next run, hand
out personal data without being asked twice, or take a write from another
origin.
"""
from __future__ import annotations

import json
import sqlite3
import threading

import httpx
import pytest

from pipeline import db
from pipeline.web import queries, review
from pipeline.web.server import build_server


@pytest.fixture
def seeded(conn: sqlite3.Connection) -> sqlite3.Connection:
    """A warehouse with a few review items and a restricted table."""
    db.record_review_item(conn, "m01_procurement", "unmatched_buyer_name",
                           "Barsetshire County Council", json.dumps({"contracts": 3}))
    db.record_review_item(conn, "m01_procurement", "unmatched_buyer_name", "Ambridge BC")
    db.record_review_item(conn, "m04_companies", "possible_group_company", "12345678",
                           json.dumps({"name": "Example Care Ltd"}))
    db.record_parse_failure(conn, "m03_charity_finance", "wages", "£not-a-number",
                             "could not parse currency amount")
    conn.execute("CREATE TABLE restricted_people (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO restricted_people (name) VALUES ('A Person')")
    conn.commit()
    return conn


def ids_for(conn: sqlite3.Connection, raw_value: str) -> int:
    return conn.execute(
        "SELECT id FROM review_queue WHERE raw_value = ?", (raw_value,)).fetchone()["id"]


# --- the browsing connection cannot write ------------------------------------


def test_browsing_connection_refuses_writes(seeded, settings):
    """mode=ro is the guard, not SQL inspection: a write is refused by the
    driver regardless of how it is phrased."""
    ro = queries.readonly_connection(settings)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        ro.execute("DELETE FROM review_queue")
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        ro.execute("UPDATE review_queue SET status = 'approved'")
    ro.close()


def test_sql_box_reports_a_write_attempt_rather_than_performing_it(seeded, settings):
    ro = queries.readonly_connection(settings)
    with pytest.raises(queries.QueryError):
        queries.run_select(ro, "DELETE FROM review_queue")
    ro.close()
    assert seeded.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0] == 3


def test_sql_box_refuses_more_than_one_statement(seeded, settings):
    ro = queries.readonly_connection(settings)
    with pytest.raises(queries.QueryError):
        queries.run_select(ro, "SELECT 1; SELECT 2")
    ro.close()


def test_sql_box_caps_the_number_of_rows_returned(seeded, settings):
    ro = queries.readonly_connection(settings)
    result = queries.run_select(
        ro,
        "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 100) SELECT i FROM n",
        limit=10,
    )
    assert len(result["rows"]) == 10
    assert result["truncated"] is True
    ro.close()


def test_missing_warehouse_is_a_message_not_a_traceback(settings, tmp_path):
    settings.database_path = tmp_path / "nope" / "warehouse.db"
    with pytest.raises(queries.QueryError, match="Run a module first"):
        queries.readonly_connection(settings)


# --- browsing ----------------------------------------------------------------


def test_list_objects_counts_tables_and_flags_restricted(seeded, settings):
    ro = queries.readonly_connection(settings)
    objects = {o["name"]: o for o in queries.list_objects(ro)}
    ro.close()

    assert objects["review_queue"]["rows"] == 3
    assert objects["review_queue"]["restricted"] is False
    assert objects["restricted_people"]["restricted"] is True
    assert "sqlite_sequence" not in objects


def test_read_table_pages_searches_and_sorts(seeded, settings):
    ro = queries.readonly_connection(settings)

    page = queries.read_table(ro, "review_queue", limit=2, offset=0)
    assert page["total"] == 3
    assert len(page["rows"]) == 2
    assert page["ordered"] is True

    found = queries.read_table(ro, "review_queue", search="Ambridge")
    assert found["total"] == 1

    # LIKE wildcards in the term are the user's literal text, not a pattern.
    assert queries.read_table(ro, "review_queue", search="%")["total"] == 0

    ordered = queries.read_table(ro, "review_queue", order_by="raw_value", descending=True)
    values = [row[3] for row in ordered["rows"]]
    assert values == sorted(values, reverse=True)
    ro.close()


def test_read_table_rejects_an_unknown_object(seeded, settings):
    ro = queries.readonly_connection(settings)
    with pytest.raises(queries.QueryError, match="No table or view"):
        queries.read_table(ro, "review_queue; DROP TABLE review_queue")
    ro.close()


# --- deciding ----------------------------------------------------------------


def test_approving_sets_status_and_records_who_decided(seeded):
    item_id = ids_for(seeded, "Ambridge BC")
    result = review.decide(seeded, [item_id], "approved", decided_by="Jon", note="confirmed by hand")

    assert result["updated"] == [item_id]
    row = seeded.execute("SELECT * FROM review_queue WHERE id = ?", (item_id,)).fetchone()
    assert row["status"] == "approved"
    assert row["resolved_at"] is not None

    decision = seeded.execute(
        "SELECT * FROM review_decisions WHERE review_item_id = ?", (item_id,)).fetchone()
    assert decision["decision"] == "approved"
    assert decision["status_before"] == "pending"
    assert decision["decided_by"] == "Jon"
    assert decision["note"] == "confirmed by hand"


def test_reverting_to_pending_clears_resolved_at_and_is_itself_recorded(seeded):
    item_id = ids_for(seeded, "Ambridge BC")
    review.decide(seeded, [item_id], "rejected", decided_by="Jon")
    review.decide(seeded, [item_id], "pending", decided_by="Jon", note="rejected in error")

    row = seeded.execute("SELECT * FROM review_queue WHERE id = ?", (item_id,)).fetchone()
    assert row["status"] == "pending"
    assert row["resolved_at"] is None

    history = seeded.execute(
        "SELECT decision, status_before FROM review_decisions "
        "WHERE review_item_id = ? ORDER BY id", (item_id,)).fetchall()
    assert [(r["decision"], r["status_before"]) for r in history] == [
        ("rejected", "pending"), ("pending", "rejected")]


def test_repeating_a_decision_writes_no_second_audit_row(seeded):
    """A double-click is not a second judgement."""
    item_id = ids_for(seeded, "Ambridge BC")
    review.decide(seeded, [item_id], "approved", decided_by="Jon")
    result = review.decide(seeded, [item_id], "approved", decided_by="Jon")

    assert result["updated"] == []
    assert result["unchanged"] == [item_id]
    assert seeded.execute(
        "SELECT COUNT(*) FROM review_decisions WHERE review_item_id = ?",
        (item_id,)).fetchone()[0] == 1


def test_repeating_a_decision_with_a_note_does_record_it(seeded):
    item_id = ids_for(seeded, "Ambridge BC")
    review.decide(seeded, [item_id], "approved", decided_by="Jon")
    review.decide(seeded, [item_id], "approved", decided_by="Sam", note="checked again")

    assert seeded.execute(
        "SELECT COUNT(*) FROM review_decisions WHERE review_item_id = ?",
        (item_id,)).fetchone()[0] == 2


def test_bulk_decision_reports_missing_ids_rather_than_failing(seeded):
    item_id = ids_for(seeded, "Ambridge BC")
    result = review.decide(seeded, [item_id, 9999], "rejected", decided_by="Jon")
    assert result["updated"] == [item_id]
    assert result["missing"] == [9999]


def test_a_decision_needs_a_reviewer_and_a_known_decision(seeded):
    item_id = ids_for(seeded, "Ambridge BC")
    with pytest.raises(review.DecisionError, match="reviewer name"):
        review.decide(seeded, [item_id], "approved", decided_by="  ")
    with pytest.raises(review.DecisionError, match="Unknown decision"):
        review.decide(seeded, [item_id], "deleted", decided_by="Jon")
    with pytest.raises(review.DecisionError, match="No items selected"):
        review.decide(seeded, [], "approved", decided_by="Jon")
    with pytest.raises(review.DecisionError, match="more than"):
        review.decide(seeded, list(range(review.MAX_BATCH + 1)), "approved", decided_by="Jon")


def test_a_decided_item_is_not_reopened_by_a_later_run(seeded):
    """The guarantee that makes deciding worth doing at all.

    record_review_item() upserts on (module, item_type, raw_value) and every
    module calls it on every run. If a re-run reset a decided item to pending,
    or overwrote the context under a decision already taken, the queue could
    never be cleared — which is why that upsert is conditional on the row
    still being pending, and why this test guards it from here.
    """
    item_id = ids_for(seeded, "Ambridge BC")
    review.decide(seeded, [item_id], "rejected", decided_by="Jon", note="not a provider")

    db.record_review_item(seeded, "m01_procurement", "unmatched_buyer_name", "Ambridge BC",
                           json.dumps({"contracts": 99}))

    row = seeded.execute("SELECT * FROM review_queue WHERE id = ?", (item_id,)).fetchone()
    assert row["status"] == "rejected"
    assert row["context_json"] is None


def test_decisions_travel_with_the_items_they_belong_to(seeded, settings):
    item_id = ids_for(seeded, "Ambridge BC")
    review.decide(seeded, [item_id], "approved", decided_by="Jon", note="verified")

    ro = queries.readonly_connection(settings)
    listed = queries.review_items(ro, status="approved")
    assert listed["total"] == 1
    assert listed["items"][0]["last_decided_by"] == "Jon"
    assert listed["items"][0]["last_note"] == "verified"

    full = queries.review_item(ro, item_id)
    assert len(full["decisions"]) == 1

    facets = queries.review_facets(ro)
    assert facets["statuses"] == {"pending": 2, "approved": 1, "rejected": 0}
    ro.close()


def test_review_items_filter_by_module_type_and_text(seeded, settings):
    ro = queries.readonly_connection(settings)
    assert queries.review_items(ro, module="m04_companies")["total"] == 1
    assert queries.review_items(ro, item_type="unmatched_buyer_name")["total"] == 2
    assert queries.review_items(ro, search="Barsetshire")["total"] == 1
    # Context is searched as well as the raw value.
    assert queries.review_items(ro, search="Example Care")["total"] == 1
    assert queries.review_items(ro, status="all")["total"] == 3
    with pytest.raises(queries.QueryError):
        queries.review_items(ro, status="banished")
    ro.close()


# --- the HTTP layer -----------------------------------------------------------


@pytest.fixture
def client(seeded, settings):
    """A live server on an ephemeral port, and a client pointed at it."""
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with httpx.Client(base_url=base, timeout=10.0) as http:
            http.base = base
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_serves_the_page_and_its_assets(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert client.get("/app.js").status_code == 200
    assert client.get("/styles.css").status_code == 200


def test_unknown_paths_and_traversal_are_refused(client):
    assert client.get("/../../.env").status_code == 404
    assert client.get("/secrets/key.pem").status_code == 404
    assert client.get("/api/nonsense").status_code == 404


def test_overview_and_review_endpoints(client):
    overview = client.get("/api/overview").json()
    assert overview["review"]["statuses"]["pending"] == 3
    assert overview["parse_failures"]["total"] == 1
    assert overview["database"]["tables"] > 0

    listed = client.get("/api/review", params={"status": "pending", "limit": 2}).json()
    assert listed["total"] == 3
    assert len(listed["items"]) == 2

    assert client.get("/api/schema").json()["objects"]
    assert client.get("/api/review/999999").status_code == 404


def test_restricted_tables_need_a_second_ask(client):
    blocked = client.get("/api/table/restricted_people")
    assert blocked.status_code == 403
    assert "personal data" in blocked.json()["error"]

    revealed = client.get("/api/table/restricted_people", params={"reveal": "1"})
    assert revealed.status_code == 200
    assert revealed.json()["restricted"] is True

    # An ordinary table is never gated.
    assert client.get("/api/table/review_queue").status_code == 200


def test_deciding_over_http(client, seeded):
    item_id = ids_for(seeded, "Ambridge BC")
    response = client.post("/api/review/decide", json={
        "ids": [item_id], "decision": "approved", "decided_by": "Jon", "note": "ok"})
    assert response.status_code == 200
    assert response.json()["updated"] == [item_id]

    assert seeded.execute(
        "SELECT status FROM review_queue WHERE id = ?", (item_id,)).fetchone()[0] == "approved"


def test_a_bad_decision_is_a_400_with_a_readable_message(client, seeded):
    item_id = ids_for(seeded, "Ambridge BC")
    response = client.post("/api/review/decide", json={
        "ids": [item_id], "decision": "approved", "decided_by": ""})
    assert response.status_code == 400
    assert "reviewer name" in response.json()["error"]


def test_writes_require_a_json_content_type(client, seeded):
    """The CSRF guard. A form POST from another site cannot set this header,
    and a fetch that does triggers a preflight the browser will not pass."""
    item_id = ids_for(seeded, "Ambridge BC")
    response = client.post(
        "/api/review/decide",
        content=json.dumps({"ids": [item_id], "decision": "approved", "decided_by": "Jon"}),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 415
    assert seeded.execute(
        "SELECT status FROM review_queue WHERE id = ?", (item_id,)).fetchone()[0] == "pending"


def test_writes_from_another_origin_are_refused(client, seeded):
    item_id = ids_for(seeded, "Ambridge BC")
    response = client.post(
        "/api/review/decide",
        json={"ids": [item_id], "decision": "approved", "decided_by": "Jon"},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    assert seeded.execute(
        "SELECT status FROM review_queue WHERE id = ?", (item_id,)).fetchone()[0] == "pending"


def test_a_refused_write_leaves_the_connection_usable(client, seeded):
    """A refusal must consume the body it refused.

    httpx keeps the connection alive between these two calls. If the rejected
    POST's body were left sitting in the socket, this GET would be parsed out
    of those leftover bytes rather than read from the wire — the failure mode
    is a UI that breaks some actions *after* the one that went wrong.
    """
    item_id = ids_for(seeded, "Ambridge BC")
    refused = client.post(
        "/api/review/decide",
        content=json.dumps({"ids": [item_id], "decision": "approved", "decided_by": "Jon"}),
        headers={"Content-Type": "text/plain"},
    )
    assert refused.status_code == 415

    following = client.get("/api/review", params={"status": "pending"})
    assert following.status_code == 200
    assert following.json()["total"] == 3


def test_the_sql_endpoint_reads_but_cannot_write(client, seeded):
    ok = client.post("/api/query", json={"sql": "SELECT COUNT(*) AS n FROM review_queue"})
    assert ok.status_code == 200
    assert ok.json()["rows"] == [[3]]

    refused = client.post("/api/query", json={"sql": "DROP TABLE review_queue"})
    assert refused.status_code == 400
    assert seeded.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name = 'review_queue'").fetchone()[0] == 1
