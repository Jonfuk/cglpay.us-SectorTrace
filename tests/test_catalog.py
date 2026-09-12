"""The schema questions, asked once.

`pipeline/catalog.py` is where the two backends' introspection lives, and the
one thing that is not obvious about it from reading it is how many statements
each helper costs. On a file that is a curiosity. Over a LAN it is the whole
difference between the operator sidebar taking 39ms and taking 320ms, which is
what Phase 3 measured and Phase 4 fixed — so the count is asserted here rather
than left to whoever next edits the loop.
"""
from __future__ import annotations

import sqlite3

import pytest

from pipeline import catalog, db


@pytest.fixture
def counted(conn: sqlite3.Connection):
    """The connection, plus the statements it was asked to run.

    SQLite's trace callback is the real thing: it fires per statement actually
    executed, so a test built on it cannot be satisfied by a loop that looks
    like one query.
    """
    statements: list[str] = []
    conn.set_trace_callback(statements.append)
    try:
        yield conn, statements
    finally:
        conn.set_trace_callback(None)


def _some_tables(conn: sqlite3.Connection) -> list[str]:
    return [name for name in catalog.table_names(conn)
            if not name.startswith("sqlite_")][:8]


def test_row_counts_agrees_with_asking_one_table_at_a_time(conn):
    db.record_review_item(conn, "m00_geography", "thing", "one", "{}")
    db.record_review_item(conn, "m00_geography", "thing", "two", "{}")
    tables = sorted(set(_some_tables(conn)) | {"review_queue", "parse_failures"})

    one_at_a_time = {
        name: conn.execute(
            f"SELECT COUNT(*) FROM {catalog.quote(name)}").fetchone().values().__iter__().__next__()
        for name in tables
    }
    assert catalog.row_counts(conn, tables) == one_at_a_time
    assert one_at_a_time["review_queue"] == 2


def test_row_counts_costs_one_statement_however_many_tables(counted):
    conn, statements = counted
    tables = _some_tables(conn)
    assert len(tables) > 3, "the fixture schema is too small to be a test of this"

    statements.clear()
    catalog.row_counts(conn, tables)

    assert len(statements) == 1, (
        f"{len(statements)} statements for {len(tables)} tables. This is the "
        "regression Phase 4 removed: one round-trip per table is free on a "
        "file and 5-15ms each over a LAN.")


def test_row_counts_of_nothing_asks_nothing(counted):
    conn, statements = counted
    statements.clear()
    assert catalog.row_counts(conn, []) == {}
    assert statements == []


def test_row_counts_keeps_names_and_counts_together(conn):
    """The results are matched back to names by position, so a table with no
    rows — which contributes a row to the result like any other — must not
    shift the ones after it."""
    conn.execute("CREATE TABLE empty_one (a TEXT)")
    conn.execute("CREATE TABLE has_two (a TEXT)")
    conn.execute("INSERT INTO has_two VALUES ('x'), ('y')")

    assert catalog.row_counts(conn, ["empty_one", "has_two"]) == {
        "empty_one": 0, "has_two": 2}
    # Same tables, other way round.
    assert catalog.row_counts(conn, ["has_two", "empty_one"]) == {
        "empty_one": 0, "has_two": 2}


def test_row_counts_quotes_a_name_that_needs_it(conn):
    """Names reach an f-string here. They are matched against the live schema
    by every caller first, but the quoting is what makes that a second line of
    defence rather than the only one."""
    conn.execute('CREATE TABLE "select" (a TEXT)')
    conn.execute('INSERT INTO "select" VALUES (\'x\')')

    assert catalog.row_counts(conn, ["select"]) == {"select": 1}
