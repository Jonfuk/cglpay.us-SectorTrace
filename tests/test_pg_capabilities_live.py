"""`pipeline pg-capabilities` against a real PostgreSQL server (BETA-063).

Skipped unless `POSTGRES_TEST_URL` is set — the same rule and the same
`scratch_schema` isolation as `test_postgres_live.py`. This is where the
"exercise the extension-enabled and the core PostgreSQL paths" half of
BETA-063 lives: run it against a disposable server with the optional
extensions installed and again without them, and the report must describe
each state correctly.

What it can assert without knowing which extensions the server carries: the
report's own invariants — `ready` iff nothing is on a fallback and every
warehouse extension is installed; an installed extension with its index
present is `healthy`; a missing extension produces exactly one fallback per
query path it backs.
"""
from __future__ import annotations

import os
from importlib.util import find_spec

import pytest

from pipeline import db, pg_capabilities

try:  # the same .env fallback the sibling suite documents
    from test_postgres_live import POSTGRES_TEST_URL
except Exception:  # pragma: no cover - import-time only
    POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL")

LIVE = bool(POSTGRES_TEST_URL) and find_spec("psycopg") is not None
pytestmark = pytest.mark.skipif(not LIVE, reason="POSTGRES_TEST_URL is not set")


@pytest.fixture
def pg_conn():
    from conftest import scratch_schema

    with scratch_schema(POSTGRES_TEST_URL) as made:
        yield made.conn


def test_the_report_applies_and_names_the_server(pg_conn):
    result = pg_capabilities.report(pg_conn)
    assert result["backend"] == "postgres"
    assert result["applies"] is True
    assert result["server_version"]
    assert {row["extension"] for row in result["indexes"]} <= set(db.WAREHOUSE_EXTENSIONS)


def test_ready_is_exactly_no_fallbacks_and_every_extension_installed(pg_conn):
    result = pg_capabilities.report(pg_conn)
    installed = {e["name"] for e in result["extensions"] if e["installed"]}
    expected_ready = (
        not result["active_fallbacks"]
        and installed == set(db.WAREHOUSE_EXTENSIONS))
    assert result["ready"] is expected_ready


def test_each_extension_state_is_described_correctly(pg_conn):
    result = pg_capabilities.report(pg_conn)
    installed = {e["name"] for e in result["extensions"] if e["installed"]}
    fallback_exts = {f["extension"] for f in result["active_fallbacks"]}

    for backed in pg_capabilities.BACKED_INDEXES:
        row = next(r for r in result["indexes"] if r["index"] == backed.index)
        if backed.extension not in installed:
            # A missing extension must surface as a fallback for its feature.
            assert backed.extension in fallback_exts
            assert row["healthy"] is False
        elif row["present"]:
            # Installed and the index exists: it must be judged healthy, and
            # its feature must not be listed as degraded.
            assert row["healthy"] is True
            assert all(f["feature"] != backed.feature
                       for f in result["active_fallbacks"])


def test_it_is_read_only(pg_conn):
    import inspect

    source = inspect.getsource(pg_capabilities)
    for forbidden in ("INSERT ", "UPDATE ", "DELETE ", "CREATE ", "ALTER ", "commit("):
        assert forbidden not in source
