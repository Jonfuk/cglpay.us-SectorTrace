from __future__ import annotations

import sqlite3

from pipeline import db


def test_apply_migrations_is_idempotent(settings):
    conn = db.get_connection(settings)
    first = db.apply_migrations(conn, settings.migrations_dir)
    second = db.apply_migrations(conn, settings.migrations_dir)
    assert "0001_core.sql" in first
    assert second == []
    conn.close()


def test_core_infra_tables_exist(conn: sqlite3.Connection):
    tables = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"parse_failures", "review_queue", "module_cursors", "http_cache", "schema_migrations"} <= tables


def test_upsert_dedupes_on_natural_key(conn: sqlite3.Connection):
    conn.execute(
        "CREATE TABLE widgets (ons_code TEXT PRIMARY KEY, name TEXT NOT NULL)"
    )
    db.upsert(conn, "widgets", {"ons_code": "E01", "name": "First"}, natural_key=["ons_code"])
    db.upsert(conn, "widgets", {"ons_code": "E01", "name": "Updated"}, natural_key=["ons_code"])
    rows = conn.execute("SELECT * FROM widgets").fetchall()
    assert len(rows) == 1
    assert rows[0]["name"] == "Updated"


def test_record_parse_failure_and_review_item(conn: sqlite3.Connection):
    db.record_parse_failure(conn, "m01_procurement", "value_core", "£not-a-number", "could not parse currency amount")
    db.record_review_item(conn, "m01_procurement", "buyer_name", "Some Unmatched Council")

    failures = conn.execute("SELECT * FROM parse_failures").fetchall()
    review = conn.execute("SELECT * FROM review_queue").fetchall()
    assert len(failures) == 1
    assert failures[0]["raw_fragment"] == "£not-a-number"
    assert len(review) == 1
    assert review[0]["status"] == "pending"


def test_cursor_round_trip(conn: sqlite3.Connection):
    assert db.get_cursor(conn, "m01_procurement") is None
    db.set_cursor(conn, "m01_procurement", "2024-01-01")
    assert db.get_cursor(conn, "m01_procurement") == "2024-01-01"
    db.set_cursor(conn, "m01_procurement", "2024-02-01")
    assert db.get_cursor(conn, "m01_procurement") == "2024-02-01"


def test_restricted_tables_are_discoverable(conn: sqlite3.Connection):
    conn.execute("CREATE TABLE restricted_tribunal_parties (case_number TEXT PRIMARY KEY, claimant_name_raw TEXT)")
    conn.execute("CREATE TABLE tribunal_cases (case_number TEXT PRIMARY KEY)")
    assert db.restricted_tables(conn) == ["restricted_tribunal_parties"]
