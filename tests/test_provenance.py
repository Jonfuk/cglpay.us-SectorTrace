"""Constraint 1: every row in every public table has a non-null source_url
and retrieved_at. Exercises the checker itself against placeholder tables
(deliberately not named after real schema tables like 'contracts' or
'tribunal_cases' — those exist for real now/eventually and this fixture's
`conn` applies every real migration, so a same-named CREATE TABLE here
would collide). Once real tables exist, add one assertion per exportable
table calling db.rows_missing_provenance against the real table name.
"""
from __future__ import annotations

import sqlite3

from pipeline import db


def test_rows_missing_provenance_flags_null_source_url(conn: sqlite3.Connection):
    conn.execute(
        "CREATE TABLE example_public_table (id TEXT PRIMARY KEY, source_url TEXT, retrieved_at TEXT)"
    )
    conn.execute("INSERT INTO example_public_table (id, source_url, retrieved_at) VALUES ('row-1', NULL, '2024-01-01T00:00:00Z')")
    conn.execute("INSERT INTO example_public_table (id, source_url, retrieved_at) VALUES ('row-2', 'https://example.com', '2024-01-01T00:00:00Z')")

    offenders = db.rows_missing_provenance(conn, "example_public_table")
    assert [r["id"] for r in offenders] == ["row-1"]


def test_rows_missing_provenance_clean_table(conn: sqlite3.Connection):
    conn.execute(
        "CREATE TABLE example_clean_table (id TEXT PRIMARY KEY, source_url TEXT, retrieved_at TEXT)"
    )
    conn.execute("INSERT INTO example_clean_table (id, source_url, retrieved_at) VALUES ('row-1', 'https://example.com', '2024-01-01T00:00:00Z')")

    assert db.rows_missing_provenance(conn, "example_clean_table") == []
