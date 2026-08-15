"""The dual-protocol result row.

`sqlite3.Row` answers to both a mapping and a sequence, and this codebase uses
both — `row["column"]` in most places, `row[0]` in sixteen, `dict(row)` in
twenty-eight, and `Job(id=row[0], kind=row[1], …)` in `web/jobs.py`. psycopg
ships `dict_row` and `tuple_row` and neither does both, so `pg.Row` exists.

These tests run against `sqlite3.Row` too, as the specification: where the
two disagree, sqlite3 is right by definition, because it is what the rest of
the codebase was written against.
"""
from __future__ import annotations

import sqlite3

import pytest

# `pipeline/pg.py` imports psycopg at module level, and psycopg is an extra.
# pyproject is explicit that a checkout with no driver must still work — "a
# fresh checkout, CI, and every test that does not name a backend open a file,
# and none of them should need a database driver on the machine" — and without
# this line that claim was false of the test suite itself: collection aborted
# with ModuleNotFoundError before a single test ran, taking the whole offline
# suite with it. CI installs the extra (see .github/workflows/tests.yml) so
# these do run there; this is what keeps the driverless case honest.
pytest.importorskip("psycopg", reason="the postgres extra is not installed")

from pipeline.pg import Row, row_factory  # noqa: E402 - after the guard above


def make_row(names, values):
    index = {}
    for position, name in enumerate(names):
        index.setdefault(name, position)
    return Row(tuple(names), index, tuple(values))


@pytest.fixture
def sqlite_row():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT 1 AS id, 'x' AS name, NULL AS note").fetchone()
    yield row
    conn.close()


@pytest.fixture
def pg_row():
    return make_row(["id", "name", "note"], [1, "x", None])


class TestMatchesSqlite:
    """Both fixtures answer the same question the same way."""

    def test_by_name(self, sqlite_row, pg_row):
        assert sqlite_row["name"] == pg_row["name"] == "x"

    def test_by_position(self, sqlite_row, pg_row):
        assert sqlite_row[0] == pg_row[0] == 1
        assert sqlite_row[1] == pg_row[1] == "x"

    def test_negative_index(self, sqlite_row, pg_row):
        assert sqlite_row[-1] is pg_row[-1] is None

    def test_null_is_none_not_missing(self, sqlite_row, pg_row):
        assert sqlite_row["note"] is pg_row["note"] is None

    def test_len(self, sqlite_row, pg_row):
        assert len(sqlite_row) == len(pg_row) == 3

    def test_keys(self, sqlite_row, pg_row):
        assert sqlite_row.keys() == pg_row.keys() == ["id", "name", "note"]

    def test_dict_conversion(self, sqlite_row, pg_row):
        expected = {"id": 1, "name": "x", "note": None}
        assert dict(sqlite_row) == dict(pg_row) == expected

    def test_iteration_yields_values_not_keys(self, sqlite_row, pg_row):
        """The trap that makes a Mapping the wrong base class.

        A `Mapping` iterates keys. `sqlite3.Row` iterates values, so
        `tuple(row)` is the values, and anything here that unpacks a row
        depends on it.
        """
        assert tuple(sqlite_row) == tuple(pg_row) == (1, "x", None)
        assert list(sqlite_row) == list(pg_row)

    def test_unpacking(self, sqlite_row, pg_row):
        a, b, c = sqlite_row
        x, y, z = pg_row
        assert (a, b, c) == (x, y, z)

    def test_slicing(self, sqlite_row, pg_row):
        assert tuple(sqlite_row[0:2]) == tuple(pg_row[0:2]) == (1, "x")


class TestRowSpecifics:
    def test_missing_column_raises_index_error(self, pg_row):
        # sqlite3.Row raises IndexError for an unknown name, not KeyError.
        with pytest.raises(IndexError):
            pg_row["nope"]

    def test_missing_column_matches_sqlite(self, sqlite_row):
        with pytest.raises(IndexError):
            sqlite_row["nope"]

    def test_duplicate_names_resolve_leftmost(self):
        """`SELECT a.id, b.id` is ambiguous by name on both engines.

        Which one you get matters less than getting the same one, so that a
        query behaving oddly behaves oddly identically on both backends.
        """
        row = make_row(["id", "id"], [1, 2])
        assert row["id"] == 1
        assert row[1] == 2

    def test_equality_against_a_tuple_of_values(self, pg_row):
        assert pg_row == (1, "x", None)

    def test_repr_names_the_columns(self, pg_row):
        assert "id=1" in repr(pg_row)
        assert "name='x'" in repr(pg_row)


class TestRowFactory:
    class _FakeDescription:
        def __init__(self, name):
            self.name = name

    class _FakeCursor:
        def __init__(self, names):
            self.description = ([TestRowFactory._FakeDescription(n) for n in names]
                                 if names is not None else None)

    def test_builds_rows_from_the_cursor_description(self):
        make = row_factory(self._FakeCursor(["a", "b"]))
        row = make([10, 20])
        assert row["a"] == 10 and row[1] == 20
        assert dict(row) == {"a": 10, "b": 20}

    def test_statement_with_no_result_set(self):
        """DDL and a parameterless INSERT have `description is None`.

        psycopg still asks for a row maker; it must not blow up building one.
        """
        make = row_factory(self._FakeCursor(None))
        assert make([1]) == [1]
