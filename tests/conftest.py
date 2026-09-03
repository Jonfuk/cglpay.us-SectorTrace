from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline import db
from pipeline.config import Settings

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "pipeline" / "migrations"
POSTGRES_MIGRATIONS_DIR = MIGRATIONS_DIR / "postgres"

# The offline suite runs on PostgreSQL (performance.md Phase 1 — PostgreSQL is
# the only application database). It reaches it through POSTGRES_TEST_URL, and
# deliberately not DATABASE_URL: keeping the two apart is what stops an
# ordinary `pytest` run from ever touching the working warehouse. The variable
# and the reasoning predate this change — tests/test_postgres_live.py has read
# it for the live suite all along — so the whole suite now shares it.
#
# A run needs its own database because the suite truncates between every test.
# Point it at the local dev container (deploy/docker-compose.postgres.yml) or a
# throwaway database on a shared server; never at the collection box's
# warehouse.
def _configured_url(name: str) -> str | None:
    """A test-database URL from the environment, or failing that from `.env`.

    The `.env` fallback matters: these are read with `os.environ.get`, and
    `.env` is only ever read by pydantic-settings, so putting `POSTGRES_TEST_URL`
    in `.env` — the obvious place, where the application's own database settings
    live — would otherwise do nothing and error out of every test silently. The
    variable names stay distinct from `DATABASE_URL`, so pointing the suite at a
    database is a deliberate act, never an inherited application configuration.
    """
    value = os.environ.get(name)
    if value and value.strip():
        return value.strip()
    from dotenv import dotenv_values

    from_file = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
    value = (from_file or {}).get(name)
    return value.strip() if value and value.strip() else None


POSTGRES_TEST_URL = _configured_url("POSTGRES_TEST_URL")
# Optional: a second role on the same test database for the read path. Left
# unset, reads use the owner role, which is what the suite did for its whole
# SQLite history — so nothing depends on it being present.
POSTGRES_TEST_RO_URL = _configured_url("POSTGRES_TEST_RO_URL")


def _worker_schema() -> str:
    """A schema name unique to this xdist worker.

    Isolation between parallel workers is by schema, not by database, because
    the test role has no CREATEDB (see pipeline/pg.py) and one migrated schema
    per worker costs the 94-migration build once rather than per test. Within a
    worker, tests are isolated from each other by truncation, not by a fresh
    schema — no migration in this project seeds data, so a truncated schema is
    byte-for-byte a freshly migrated one.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    return f"pgtest_{worker}"


@pytest.fixture(scope="session")
def _pg_warehouse() -> SimpleNamespace:
    """One migrated PostgreSQL schema for this worker, for the whole session.

    Built once and kept: the per-test `settings`/`conn` fixtures scope onto it
    and the truncation fixture empties it between tests. Dropped at session end.

    Errors rather than skips when POSTGRES_TEST_URL is unset: PostgreSQL is the
    only backend now, so a suite that cannot reach one has not run — silently
    skipping every test would report green on a run that measured nothing,
    which is the failure the live suite's `_configured_url` guard already warns
    against.
    """
    if POSTGRES_TEST_URL is None:
        raise RuntimeError(
            "POSTGRES_TEST_URL is not set. The offline suite runs on PostgreSQL "
            "(performance.md Phase 1). Start deploy/docker-compose.postgres.yml "
            "and set POSTGRES_TEST_URL to it — e.g. "
            "postgresql://sectortrace_app:sectortrace_app_dev@localhost:5432/sectortrace"
        )

    from pipeline import pg

    schema = _worker_schema()
    quoted = '"' + schema.replace('"', '""') + '"'
    admin = pg.connect(POSTGRES_TEST_URL, application_name="sectortrace-tests")
    try:
        # DROP first: a schema left behind by a crashed previous run would
        # otherwise fail CREATE, and re-migrating onto stale objects hides the
        # break rather than surfacing it.
        admin.execute(f"DROP SCHEMA IF EXISTS {quoted} CASCADE")
        admin.execute(f"CREATE SCHEMA {quoted}")
        admin.commit()

        url = pg.with_schema(POSTGRES_TEST_URL, schema)
        ro_url = pg.with_schema(POSTGRES_TEST_RO_URL, schema) if POSTGRES_TEST_RO_URL else None
        conn = pg.connect(url, application_name="sectortrace-tests")
        try:
            # ro_url passed so apply_migrations performs the reader grant the
            # way production does — see scratch_schema below for why the grant
            # belongs to the migration and not to the harness.
            settings = Settings(
                contact_email="test@example.com",
                database_url=POSTGRES_TEST_URL, database_ro_url=POSTGRES_TEST_RO_URL,
                _env_file=None) if ro_url else None
            db.apply_migrations(conn, POSTGRES_MIGRATIONS_DIR, settings=settings)
            conn.commit()
            tables = tuple(
                row["tablename"]
                for row in conn.execute(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = current_schema() ORDER BY tablename")
            )
        finally:
            conn.close()

        yield SimpleNamespace(base_url=POSTGRES_TEST_URL, base_ro_url=POSTGRES_TEST_RO_URL,
                              schema=schema, url=url, ro_url=ro_url, tables=tables)
    finally:
        try:
            admin.execute(f"DROP SCHEMA IF EXISTS {quoted} CASCADE")
            admin.commit()
        finally:
            admin.close()


@pytest.fixture(autouse=True)
def _empty_warehouse_between_tests(_pg_warehouse, request):
    """Truncate every table before each test so state cannot leak.

    Cheaper than a fresh schema per test by two orders of magnitude, and exact:
    no migration seeds data, so an empty migrated schema is what a test that
    wants "a fresh warehouse" means. `schema_migrations` is the one exception —
    it records what has been applied and must survive.

    Applied to tests that touch the database and harmless to those that do not.
    A test that manages its own scratch_schema is unaffected: this truncates the
    worker's shared schema, which those tests never write to.

    TRUNCATE, not DELETE: it resets identity sequences (so ids are stable
    between tests) and does not fire the row triggers behind settled decision 4
    — those are INSERT/UPDATE triggers, not TRUNCATE triggers. CASCADE handles
    the foreign-key graph in one statement.
    """
    from pipeline import pg

    warehouse = _pg_warehouse
    conn = pg.connect(warehouse.url, application_name="sectortrace-tests")
    try:
        rows = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = ? "
            "AND tablename <> 'schema_migrations'", (warehouse.schema,)).fetchall()
        names = [r["tablename"] for r in rows]
        if names:
            from pipeline.catalog import quote

            targets = ", ".join(f"{quote(warehouse.schema)}.{quote(n)}" for n in names)
            conn.execute(f"TRUNCATE {targets} RESTART IDENTITY CASCADE")
            conn.commit()
    finally:
        conn.close()
    yield

    # SQLite's old file-per-test fixture restored tables that a test dropped
    # while exercising graceful degradation. The shared PostgreSQL schema
    # keeps that speed advantage, but must restore DDL mutations before the
    # next test. Rebuild only when a table disappeared; ordinary tests still
    # pay only the TRUNCATE above.
    check = pg.connect(warehouse.url, application_name="sectortrace-tests")
    try:
        present = {
            row["tablename"] for row in check.execute(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = current_schema()")
        }
    finally:
        check.close()
    missing = set(warehouse.tables) - present
    if missing:
        admin = pg.connect(warehouse.base_url, application_name="sectortrace-tests")
        try:
            quoted = '"' + warehouse.schema.replace('"', '""') + '"'
            admin.execute(f"DROP SCHEMA IF EXISTS {quoted} CASCADE")
            admin.execute(f"CREATE SCHEMA {quoted}")
            admin.commit()
            rebuilt = pg.connect(warehouse.url, application_name="sectortrace-tests")
            try:
                db.apply_migrations(rebuilt, POSTGRES_MIGRATIONS_DIR)
                rebuilt.commit()
            finally:
                rebuilt.close()
        finally:
            admin.close()


@pytest.fixture(autouse=True)
def _reset_host_clock():
    """The per-host rate limiter is process-wide by design, so it would
    otherwise carry timing state from one test into the next.
    """
    from pipeline.http import HOST_CLOCK

    HOST_CLOCK.reset()
    yield
    HOST_CLOCK.reset()


@pytest.fixture(autouse=True)
def _contact_email_is_always_set(monkeypatch):
    """The one setting with no default, present for every test.

    `CONTACT_EMAIL` is required — the pipeline refuses to start without it,
    because it goes in the User-Agent of every request. Most code takes its
    settings from a fixture, but not all of it: `db.apply_migrations(conn)`
    with no directory falls back to `get_settings()`, and a bare `Settings()`
    reads the environment and `.env`.

    On a developer's machine `.env` exists, so this was invisible. On a fresh
    checkout — CI, a new contributor, a clean container — four tests failed
    with a pydantic validation error, and the suite was quietly depending on
    an untracked file. Setting it here is what makes the suite hermetic;
    tests that care about the value pass their own settings.
    """
    monkeypatch.setenv("CONTACT_EMAIL", "test@example.com")
    yield


@pytest.fixture(autouse=True)
def _the_suite_reaches_only_the_test_warehouse(_pg_warehouse, monkeypatch):
    """Every settings-resolving code path lands on this worker's test schema.

    The inverse of the fixture this replaces. Under SQLite the suite forced
    `DATABASE_URL` empty so no code path could reach a real PostgreSQL
    warehouse; PostgreSQL is now the only backend, so the hazard is the
    opposite one — a code path resolving `get_settings()` would read the
    operator's `.env` DATABASE_URL and open the working warehouse. Both
    variables are pinned to the schema-scoped test URL instead, so
    `db.get_connection()` and `queries.readonly_connection()` — which fall back
    to `get_settings()` — reach the schema this session owns and truncates, and
    nothing else.

    Set via the environment so it survives a bare `Settings(_env_file=None)`
    built deep in the code; the `settings` fixture below carries the same URLs
    for the code that does take its settings from a fixture.
    """
    monkeypatch.setenv("DATABASE_URL", _pg_warehouse.url)
    monkeypatch.setenv("DATABASE_RO_URL", _pg_warehouse.ro_url or "")
    yield


@pytest.fixture(autouse=True)
def _fresh_console():
    """The Rich console is cached process-wide and binds `sys.stdout` when it
    is built.

    Whatever stream it captured belongs to whichever test built it — a pytest
    capture buffer, or a CliRunner's. Reused by a later test, writes go to a
    stream that is no longer being read, or that is closed, and the failure
    surfaces as a command that produced no output for no visible reason.
    """
    from pipeline import console

    console.reset_console()
    yield
    console.reset_console()


@pytest.fixture(autouse=True)
def _names_resolve_somewhere_public(monkeypatch):
    """DNS, stubbed, so the destination guard runs without leaving the machine.

    `pipeline/netguard.py` refuses a fetch whose host resolves into private
    space, which means the guarded paths now do a lookup. The suite is offline
    and hermetic and must stay that way, so every name here resolves to one
    public address.

    Note this leaves the guard *switched on* for every test rather than
    disabling it: the code still resolves, still inspects, and still decides.
    Tests about refusal pass their own resolver, which takes precedence.
    """
    import socket

    from pipeline import netguard

    def fake(host, port, *args, **kwargs):
        # 93.184.216.34 — public, globally routable, and not a real target of
        # anything here: nothing in the suite actually opens a socket.
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                  ("93.184.216.34", port))]

    # netguard.DEFAULT_RESOLVER, never socket.getaddrinfo itself: patching
    # the socket module patches it for httpx too, and the test server the web
    # suites talk to lives on 127.0.0.1.
    monkeypatch.setattr(netguard, "DEFAULT_RESOLVER", fake)
    yield


@pytest.fixture(autouse=True)
def _get_settings_returns_the_test_settings(settings: Settings, monkeypatch):
    """`get_settings()` anywhere in the codebase resolves to this test's tmp.

    Three times now the suite has written into the repository because a
    function took `settings: Settings | None = None`, a test did not pass one,
    and the default reached back into the checkout: 5 MB of fake module logs
    into `logs/`, 7.7 MB of backups into `data/backups/`, and a
    `verified_websites.json` full of Barnet.

    Patching the fixtures one at a time treats the symptom. The cause is that
    the default is the operator's real configuration, so this makes the
    default safe instead. Tests that exercise settings resolution itself build
    their own `Settings` and are unaffected.
    """
    import sys

    from pipeline import config

    stub = lambda: settings  # noqa: E731 - a fixture-local alias, not a def
    monkeypatch.setattr(config, "get_settings", stub)
    # And every module that did `from pipeline.config import get_settings`,
    # because that binds the function into the importing module's namespace
    # and patching `config` alone leaves ten copies of the original behind.
    # Discovered rather than listed: a new module importing it that way would
    # otherwise quietly reopen this hole.
    for name, module in list(sys.modules.items()):
        if name.startswith("pipeline") and getattr(module, "get_settings", None) is not None:
            monkeypatch.setattr(module, "get_settings", stub, raising=False)
    yield


@pytest.fixture(autouse=True)
def _logs_stay_out_of_the_repo(tmp_path: Path, monkeypatch):
    """No test writes into the operator's `logs/`.

    `configure_logging` resolves its own settings rather than being handed
    them, so anything that runs the CLI or the server for real -- which is
    most of the web and CLI suites -- opened a file handler on the repo's
    logs/ and left it there. The suite was depositing a 5 MB
    `fake_insert_only_for_tests.log` next to the audit trail of real crawls,
    which is a good way to stop trusting the directory.

    Tests that need to read what was logged patch this themselves afterwards
    and are unaffected; this only moves the default.
    """
    from pipeline import logging_conf

    monkeypatch.setattr(
        logging_conf, "get_settings",
        lambda: Settings(contact_email="test@example.com",
                          logs_dir=tmp_path / "logs", _env_file=None))
    yield


@contextmanager
def scratch_schema(url: str, ro_url: str | None = None):
    """A migrated PostgreSQL warehouse of its own, dropped on the way out.

    Every live PostgreSQL suite here writes, and some truncate. The first
    version of them said "point `POSTGRES_TEST_URL` at a database kept for the
    tests" and trusted that — which lasted until the operator pointed it at
    the same database as `DATABASE_URL`, the obvious thing to do when the
    server holds one database and `sectortrace_app` has no CREATEDB. An
    ordinary `pytest` run would then have truncated the working warehouse.

    A schema is the isolation that is actually available here. Everything in
    this codebase asks `current_schema()` rather than naming `public`, so a
    warehouse in a schema of its own is the same warehouse; and the scoping
    rides on the URL (see `pg.with_schema`) so connections opened by fetch
    pools and by module code land in it too.

    The reader role is granted what it holds on `public`, because several
    tests check the read path through a role that cannot write, and a grant
    on a schema that is about to be dropped is narrower than the alternative
    of pointing those tests at the working warehouse.

    The grant is `apply_migrations`' own, not one this fixture performs
    afterwards. It used to be the latter, and that is precisely why the live
    suite never noticed the working warehouse's reader losing sight of
    thirteen tables: the fixture granted after every migration and the server
    did not. A harness that repairs what production leaves broken tests the
    harness.
    """
    from uuid import uuid4

    from pipeline import pg

    name = f"pgtest_{uuid4().hex[:12]}"
    quoted = '"' + name.replace('"', '""') + '"'
    admin = pg.connect(url, application_name="sectortrace-tests")
    try:
        admin.execute(f"CREATE SCHEMA {quoted}")
        admin.commit()
        conn = pg.connect(pg.with_schema(url, name),
                           application_name="sectortrace-tests")
        try:
            from pipeline.config import Settings

            db.apply_migrations(
                conn, POSTGRES_MIGRATIONS_DIR,
                settings=Settings(contact_email="test@example.com",
                                   database_url=url, database_ro_url=ro_url,
                                   _env_file=None) if ro_url else None)
            conn.commit()
            yield SimpleNamespace(conn=conn, schema=name,
                                   url=pg.with_schema(url, name),
                                   ro_url=pg.with_schema(ro_url, name) if ro_url else None)
        finally:
            conn.close()
    finally:
        try:
            admin.execute(f"DROP SCHEMA {quoted} CASCADE")
            admin.commit()
        finally:
            admin.close()


@pytest.fixture
def settings(tmp_path: Path, _pg_warehouse) -> Settings:
    """Test settings pointed at this worker's PostgreSQL schema.

    Every *writable filesystem* path still points into tmp — a default that
    reaches back into the repo is how the suite ended up depositing its own
    output next to the operator's, three times (logs/, data/backups/,
    data/derived/). The database is the worker's schema-scoped test URL, shared
    across the session and emptied between tests by
    `_empty_warehouse_between_tests`.
    """
    return Settings(
        contact_email="test@example.com",
        database_url=_pg_warehouse.url,
        database_ro_url=_pg_warehouse.ro_url,
        raw_archive_dir=tmp_path / "raw",
        migrations_dir=POSTGRES_MIGRATIONS_DIR,
        logs_dir=tmp_path / "logs",
        export_output_dir=tmp_path / "exports" / "output",
        backup_dir=tmp_path / "backups",
        derived_archive_dir=tmp_path / "derived",
        mirror_state_dir=tmp_path / "mirror-state",
        mirror_inbox_dir=tmp_path / "mirror-inbox",
        verified_websites_path=tmp_path / "verified_websites.json",
        # No politeness delay against mocked transports — the rate limiter is
        # exercised directly in test_http.py with its own explicit override.
        default_rate_limit_seconds=0.0,
        # Dummy credentials so modules that require a key can be exercised.
        # Never real values: every outbound call in the suite is mocked.
        charity_commission_api_key="test-charity-key",
        companies_house_api_key="test-companies-house-key",
        cqc_subscription_key="test-cqc-key",
        _env_file=None,
    )


@pytest.fixture
def conn(settings: Settings):
    """A connection to this worker's migrated warehouse schema.

    Emptied before the test by `_empty_warehouse_between_tests`, so it opens on
    a clean migrated schema. A real connection, not a transaction wrapper:
    tests that commit, that open a second connection, or that exercise the
    write path see exactly what production sees.
    """
    connection = db.get_connection(settings)
    try:
        yield connection
    finally:
        connection.close()
