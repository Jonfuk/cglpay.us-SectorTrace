"""What changed? evidence feed (BETA-090).

A derived, filterable chronology of what the warehouse recorded changing.
There is no persisted change-event table and this adds none. Collection,
parser and human-review changes are distinct kinds and their counts are never
added together.
"""
from __future__ import annotations

import sqlite3

import pytest

from pipeline.web import public_queries as pq
from pipeline.web.queries import QueryError


def test_events_are_typed_and_counts_are_kept_apart(conn: sqlite3.Connection) -> None:
    out = pq.change_feed(conn)
    assert set(out["counts"]) == {"by_kind"}      # no `total` key
    assert "total" not in out["counts"]
    assert set(out["kinds"]) == {"release", "refreshed", "reparsed",
                                  "superseded", "verified"}
    for event in out["events"]:
        assert event["kind"] in out["kinds"]
    assert "never added" in out["note"].lower()
    # the caveat says it is not a record of what a source published
    assert "not a record of what a source published" in out["caveat"].lower()


def test_a_run_is_a_release_event(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO run_ledger (run_id, origin, revision, environment, "
        " module_selector, dry_run, started_at, finished_at, status, "
        " modules_total, modules_ok, modules_failed, results_json) VALUES "
        "('r9', 'cli', 'abc', 'test', 'all', 0, '2026-08-05T00:00:00Z', "
        " '2026-08-05T01:00:00Z', 'ok', 3, 3, 0, '[]')")
    conn.commit()
    out = pq.change_feed(conn, kind="release")
    assert out["events"], "no release event for a recorded run"
    ev = out["events"][0]
    assert ev["kind"] == "release" and ev["release"] == "r9"
    assert "ok" in ev["detail"]


def test_a_reparsed_document_is_its_own_kind(conn: sqlite3.Connection, settings) -> None:
    n = "2026-08-01T00:00:00Z"
    conn.execute(
        "INSERT INTO evidence_records (evidence_id, source_system, source_url, "
        " retrieved_at, http_status, payload_sha256, raw_object_path, mime_type, "
        " content_length, source_table, source_key, created_at) VALUES "
        "('ev1', 'committee_paper_promotion', 'https://x/1', %s, 200, 's1', "
        " 'r/x.pdf', 'application/pdf', 10, 'committee_papers', 'k1', %s)", (n, n))
    conn.execute(
        "INSERT INTO document_records (document_id, evidence_id, source_table, "
        " source_key, document_type, mime_type, title, created_at, updated_at) "
        "VALUES ('d1', 'ev1', 'committee_papers', 'k1', 'committee_paper', "
        " 'application/pdf', 'Paper', %s, %s)", (n, n))
    for vid, ver, active, at in [("v1", "1.0.0", 0, "2026-06-01T00:00:00Z"),
                                  ("v2", "2.0.0", 1, "2026-08-01T00:00:00Z")]:
        conn.execute(
            "INSERT INTO document_versions (document_version_id, document_id, "
            " parser_name, parser_version, parse_schema_version, config_hash, "
            " text_sha256, status, is_active, created_at) VALUES "
            "(%s, 'd1', 'docling', %s, '1', 'c', 't', 'parsed', %s, %s)",
            (vid, ver, active, at))
    conn.commit()

    out = pq.change_feed(conn, kind="reparsed")
    assert out["events"], "no reparsed event for a superseded parse version"
    ev = out["events"][0]
    assert ev["kind"] == "reparsed" and ev["evidence_type"] == "document"
    assert "2.0.0" in ev["detail"]
    # it is not counted with the release events
    both = pq.change_feed(conn)["counts"]["by_kind"]
    assert both.get("reparsed", 0) >= 1


def test_filters_and_a_bad_kind(conn: sqlite3.Connection) -> None:
    with pytest.raises(QueryError):
        pq.change_feed(conn, kind="not-a-kind")
    # since keeps only dated events on/after it
    since = pq.change_feed(conn, since="2099-01-01")
    assert all(e["at"] is None or e["at"][:10] >= "2099-01-01" for e in since["events"])


def test_the_route_is_in_the_openapi_document() -> None:
    from pipeline.web import openapi
    assert "/api/v1/changes" in openapi.document()["paths"]
