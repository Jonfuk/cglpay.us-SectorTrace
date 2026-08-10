"""Constraint 1: every row in every public table has a non-null source_url
and retrieved_at. No domain tables exist yet (those land with Module 0
onward) so this exercises the checker itself; once real tables exist, add
one assertion per exportable table calling db.rows_missing_provenance.
"""
from __future__ import annotations

import sqlite3

from pipeline import db


def test_rows_missing_provenance_flags_null_source_url(conn: sqlite3.Connection):
    conn.execute(
        "CREATE TABLE contracts (ocid TEXT PRIMARY KEY, source_url TEXT, retrieved_at TEXT)"
    )
    conn.execute("INSERT INTO contracts (ocid, source_url, retrieved_at) VALUES ('ocid-1', NULL, '2024-01-01T00:00:00Z')")
    conn.execute("INSERT INTO contracts (ocid, source_url, retrieved_at) VALUES ('ocid-2', 'https://example.com', '2024-01-01T00:00:00Z')")

    offenders = db.rows_missing_provenance(conn, "contracts")
    assert [r["ocid"] for r in offenders] == ["ocid-1"]


def test_rows_missing_provenance_clean_table(conn: sqlite3.Connection):
    conn.execute(
        "CREATE TABLE tribunal_cases (case_number TEXT PRIMARY KEY, source_url TEXT, retrieved_at TEXT)"
    )
    conn.execute("INSERT INTO tribunal_cases (case_number, source_url, retrieved_at) VALUES ('c1', 'https://example.com', '2024-01-01T00:00:00Z')")

    assert db.rows_missing_provenance(conn, "tribunal_cases") == []
