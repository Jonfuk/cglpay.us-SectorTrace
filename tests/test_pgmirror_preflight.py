"""Schema compatibility rules for PostgreSQL-to-PostgreSQL mirrors."""
from __future__ import annotations

from pipeline import pgmirror


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Target:
    def __init__(self, count):
        self.count = count

    def execute(self, sql):
        assert "COUNT(*)" in sql
        return _Cursor([{"i": 0, "n": self.count}])


def _patch_schema(monkeypatch, extra_tables, count):
    source = object()
    target = _Target(count)
    monkeypatch.setattr(
        pgmirror, "_tables",
        lambda connection: {"source_table"} if connection is source
        else {"source_table", *extra_tables})
    monkeypatch.setattr(pgmirror, "_server_identity", lambda connection: connection)
    monkeypatch.setattr(pgmirror.catalog, "foreign_keys", lambda connection: set())
    monkeypatch.setattr(pgmirror.catalog, "columns_of", lambda connection, table: [])
    return source, target


def test_empty_beta_only_table_is_allowed(monkeypatch):
    source, target = _patch_schema(monkeypatch, {"beta_only"}, 0)

    assert pgmirror.preflight(source, target) == []


def test_populated_beta_only_table_is_refused(monkeypatch):
    source, target = _patch_schema(monkeypatch, {"beta_only"}, 3)

    problems = pgmirror.preflight(source, target)

    assert problems == [
        "target has unexpected populated table(s): beta_only (3 rows)"
    ]
