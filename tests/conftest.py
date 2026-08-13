from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from pipeline import db
from pipeline.config import Settings

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "pipeline" / "migrations"


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


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        contact_email="test@example.com",
        database_path=tmp_path / "warehouse.db",
        raw_archive_dir=tmp_path / "raw",
        migrations_dir=Path(__file__).resolve().parent.parent / "pipeline" / "migrations",
        logs_dir=tmp_path / "logs",
        export_output_dir=tmp_path / "exports" / "output",
        # Every writable path this fixture hands out points into tmp. A
        # default that reaches back into the repo is how the suite ends up
        # depositing its own output next to the operator's — which it has now
        # done twice, once into logs/ and once into data/backups/.
        backup_dir=tmp_path / "backups",
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
def conn(settings: Settings, _schema_template: Path) -> sqlite3.Connection:
    """A migrated warehouse, copied rather than built.

    Applying the migrations costs 0.31s and the suite did it once per test, so
    several hundred tests were each paying to build the same 30-migration
    schema from scratch. The template is built once per session and copied,
    which is a file copy of well under a megabyte.

    The copy is a real file on disk, not a shared connection: tests still get
    their own warehouse, and one that writes cannot be seen by another.
    """
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(_schema_template, settings.database_path)
    connection = db.get_connection(settings)
    yield connection
    connection.close()


@pytest.fixture(scope="session")
def _schema_template(tmp_path_factory) -> Path:
    """Every migration applied once, as a file to copy from."""
    path = tmp_path_factory.mktemp("schema") / "template.db"
    settings = Settings(contact_email="test@example.com", database_path=path,
                         migrations_dir=MIGRATIONS_DIR, _env_file=None)
    connection = db.get_connection(settings)
    try:
        db.apply_migrations(connection, MIGRATIONS_DIR)
        connection.commit()
        # Fold the WAL back into the database file before copying it. A copy
        # taken with pages still in the sidecar is a copy missing tables, and
        # it would be missing whichever ones the last migrations added.
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()
    return path
