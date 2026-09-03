"""Conditional requests, compression, and what the aggregates do to the disk.

The last of these is the point of the file. "Add an index" is the reflex when
a dashboard query is slow, and it is a cost paid by every module on every
insert forever to speed up a panel someone opens occasionally. So the queries
behind the admin views have their plans asserted here: the ones that must use
an index say so, and the one that cannot is documented as scanning rather than
quietly acquiring an index nobody weighed.
"""
from __future__ import annotations

import sqlite3
import threading

import httpx
import pytest

from pipeline.web import queries
from pipeline.web.server import GZIP_MIN_BYTES, build_server


@pytest.fixture
def client(conn, settings):
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # No automatic decompression, so the wire bytes can be inspected.
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=30.0, headers={"Accept-Encoding": "identity"}) as http:
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# --- conditional requests ---------------------------------------------------------


def test_a_static_asset_carries_an_etag(client):
    response = client.get("/admin/app.js")
    assert response.status_code == 200
    assert response.headers["ETag"].startswith('W/"')


def test_an_unchanged_asset_comes_back_as_304_with_no_body(client):
    first = client.get("/admin/app.js")
    again = client.get("/admin/app.js",
                        headers={"If-None-Match": first.headers["ETag"]})

    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["ETag"] == first.headers["ETag"]


def test_a_changed_asset_gets_a_new_etag_and_is_sent_again(client, tmp_path):
    from pipeline.web.server import STATIC_DIR

    target = STATIC_DIR / "app.js"
    original = target.read_bytes()
    first = client.get("/admin/app.js")
    try:
        target.write_bytes(original + b"\n// touched\n")
        again = client.get("/admin/app.js",
                            headers={"If-None-Match": first.headers["ETag"]})
        assert again.status_code == 200
        assert again.headers["ETag"] != first.headers["ETag"]
    finally:
        target.write_bytes(original)


def test_if_none_match_accepts_a_list_and_a_wildcard(client):
    etag = client.get("/admin/styles.css").headers["ETag"]

    listed = client.get("/admin/styles.css",
                         headers={"If-None-Match": f'W/"other", {etag}'})
    assert listed.status_code == 304
    assert client.get("/admin/styles.css",
                       headers={"If-None-Match": "*"}).status_code == 304
    assert client.get("/admin/styles.css",
                       headers={"If-None-Match": 'W/"nope"'}).status_code == 200


def test_warehouse_answers_are_never_conditional(client):
    """The review queue changes as it is worked on; a 304 there would show
    decisions that are not there."""
    response = client.get("/api/overview")
    assert response.headers["Cache-Control"] == "no-store"
    assert "ETag" not in response.headers


# --- compression -------------------------------------------------------------------


def test_a_large_text_response_is_compressed_when_asked(client):
    """Content-Length is what went over the wire; httpx has already decoded
    the body by the time it is readable, which is the round trip a browser
    makes and so the one worth asserting."""
    plain = client.get("/admin/app.js")
    zipped = client.get("/admin/app.js", headers={"Accept-Encoding": "gzip"})

    assert plain.headers.get("Content-Encoding") is None
    assert zipped.headers["Content-Encoding"] == "gzip"
    assert int(zipped.headers["Content-Length"]) < len(plain.content)
    assert zipped.content == plain.content, "it must decode back to the same script"


def test_compression_is_only_offered_to_clients_that_asked(client):
    response = client.get("/admin/app.js", headers={"Accept-Encoding": "identity"})
    assert response.headers.get("Content-Encoding") is None


def test_small_responses_are_left_alone(client):
    """Below the threshold the round trip through zlib costs more than the
    bytes it saves."""
    response = client.get("/api/schema", headers={"Accept-Encoding": "gzip"})
    if len(response.content) < GZIP_MIN_BYTES:
        assert response.headers.get("Content-Encoding") is None


def test_every_response_varies_on_accept_encoding(client):
    """A cache holding a compressed copy must not hand it to a client that
    cannot read it."""
    for path in ("/admin/app.js", "/api/overview"):
        assert client.get(path).headers["Vary"] == "Accept-Encoding"


def test_a_compressed_response_is_still_valid_json(client, conn):
    from pipeline import db

    for index in range(400):
        db.record_review_item(conn, "m01_procurement", "unmatched_buyer_name",
                               f"Authority number {index}")
    conn.commit()

    response = client.get("/api/review?limit=250", headers={"Accept-Encoding": "gzip"})
    assert response.headers["Content-Encoding"] == "gzip"
    assert int(response.headers["Content-Length"]) < len(response.content)
    assert response.json()["total"] == 400


def test_a_download_is_not_double_compressed(client, settings):
    """Exports are streamed straight from disk; gzip there would mean either
    buffering 23 MB or a second compression of already-compressed bytes."""
    root = settings.export_output_dir
    root.mkdir(parents=True, exist_ok=True)
    (root / "big.json").write_text("{" + '"a":1,' * 5000 + '"b":2}', encoding="utf-8")

    response = client.get("/api/admin/exports/file?path=big.json",
                           headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert response.headers.get("Content-Encoding") is None


# --- what the aggregates cost -------------------------------------------------------


def plan_for(conn: sqlite3.Connection, sql: str) -> str:
    return " ".join(row["QUERY PLAN"] for row in conn.execute(
        "EXPLAIN (FORMAT TEXT) " + sql))


@pytest.fixture
def ro(conn, settings):
    connection = queries.readonly_connection(settings)
    yield connection
    connection.close()


@pytest.mark.parametrize("table,column,index_name", [
    ("contracts", "buyer_ons_code", "idx_contracts_buyer_ons"),
    ("fingertips_la_values", "ons_code", "idx_fingertips_ons"),
    ("ndtms_la_statistics", "ons_code", "idx_ndtms_ons"),
    ("public_health_grants", "ons_code", "idx_phg_authority"),
])
def test_the_coverage_aggregates_have_the_supporting_index(
        ro, table, column, index_name):
    """These run on every visit to the Health tab, against the largest tables
    in the warehouse -- contracts alone is 98,588 rows in production. They are
    only affordable because the ons_code columns are already indexed, and a
    migration that dropped one would make the tab quietly slow."""
    # PostgreSQL quite correctly chooses a sequential scan for the tiny test
    # fixture. Verify the durable contract (the index exists); production's
    # planner can then choose it when the table is large enough to justify it.
    assert ro.execute(
        "SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() "
        "AND indexname = %s", (index_name,)).fetchone()


def test_the_portal_contract_list_uses_its_index(ro):
    """Migration 0044, and the ORDER BY that has to match it.

    The portal's contract list is `ORDER BY date_published DESC NULLS LAST,
    notice_id`, and 0044 indexes exactly that. The pairing is the fragile
    part: drop the `NULLS LAST`, or reverse either column, and the index stops
    being usable without anything failing — the page just goes back to sorting
    98,636 rows to show the first fifty. That was 6 seconds on SQLite and
    83ms on PostgreSQL before the index, and 1.9ms after.
    """
    assert ro.execute(
        "SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() "
        "AND indexname = %s", ("idx_contracts_date_published",)).fetchone()


def test_the_pending_queue_count_uses_an_index(ro):
    assert ro.execute(
        "SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() "
        "AND indexname = %s", ("idx_review_queue_status",)).fetchone()


def test_the_sidebar_asks_for_its_counts_once(ro):
    """The other half of "add an index" is "ask fewer times".

    This is the one case in the Phase 3 baseline where PostgreSQL was slower
    for a reason that had nothing to do with the query: a `COUNT(*)` per
    table, on every page load of the operator UI, is 82 cheap reads of a local
    file and 82 round-trips to a server on the LAN — 39ms against 320ms.

    Asserted by counting statements rather than by timing, because a timing
    test on a fixture database would pass either way.
    """
    statements: list[str] = []
    ro.set_trace_callback(statements.append)
    try:
        objects = queries.list_objects(ro)
    finally:
        ro.set_trace_callback(None)

    counted = [o for o in objects if o["rows"] is not None]
    assert len(counted) > 3, "too few tables here for this to be a test"

    counting = [s for s in statements if "COUNT(*)" in s]
    assert len(counting) == 1, (
        f"{len(counting)} counting statements for {len(counted)} tables. The "
        "sidebar counts every table in the warehouse on every page load; one "
        "statement per table is free on a file and 5-15ms each over a LAN.")


def test_freshness_scans_and_that_is_the_accepted_cost(ro):
    """Documented rather than fixed.

    SQLite answers MAX() or MIN() from an index in one seek, but only when it
    is the single aggregate in the query -- asking for COUNT, MAX and MIN
    together scans whatever indexes exist. Making this fast would mean a
    retrieved_at index on twenty tables, paid for on every insert by every
    module, to speed up one panel. It is served on its own route instead so
    nothing waits for it.
    """
    plan = plan_for(ro, "SELECT COUNT(*), MAX(retrieved_at), MIN(retrieved_at) "
                         "FROM contracts")
    assert "SCAN" in plan.upper(), (
        "freshness no longer scans -- if an index was added for it, weigh the "
        "write cost and update this test and health.freshness's docstring")


def test_freshness_is_not_on_the_health_route(client):
    """The tab renders its cards and its coverage without waiting seconds for
    a scan of every table."""
    payload = client.get("/api/admin/health").json()
    assert "freshness" not in payload
    assert "freshness" in client.get("/api/admin/freshness").json()
