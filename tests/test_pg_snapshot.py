"""The PostgreSQL mirror's source snapshot contract."""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

try:
    from pipeline import pg
except ImportError:
    pytest.skip("psycopg has no usable libpq wrapper", allow_module_level=True)


class _Transaction:
    def __init__(self, events: list[str]):
        self.events = events

    def __enter__(self):
        self.events.append("begin")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.events.append("rollback" if exc_type else "commit")
        return False


class _Raw:
    def __init__(self):
        self.events: list[str] = []

    def transaction(self):
        return _Transaction(self.events)

    def execute(self, sql):
        self.events.append(sql)


class _Connection:
    def __init__(self):
        self.raw = _Raw()


def test_repeatable_read_starts_a_read_only_snapshot():
    connection = _Connection()

    with pg.repeatable_read(connection):
        connection.raw.events.append("read")

    assert connection.raw.events == [
        "begin",
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ",
        "SET TRANSACTION READ ONLY",
        "read",
        "commit",
    ]


def test_scratch_schema_keeps_database_extensions_visible():
    url = pg.with_schema("postgresql://localhost/warehouse", "bench_123")
    options = parse_qs(urlsplit(url).query)["options"][0]

    assert options == "-csearch_path=bench_123"
