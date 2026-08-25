"""Which backend, and which migration tree, gets chosen.

Every one of these runs offline against SQLite. They are about the *choice*,
not about PostgreSQL working — that needs a server, and those tests live
behind their own marker.

The bug this file exists to prevent is the one that was found by reading
`cli.py` rather than by running anything: two commands passed
`settings.migrations_dir` explicitly, which is always the SQLite tree, so on a
PostgreSQL warehouse they would have applied SQLite DDL to PostgreSQL and
recorded it in `schema_migrations` as done.
"""
from __future__ import annotations

import inspect
import os
import sqlite3
from pathlib import Path

import pytest

from pipeline import db
from pipeline.config import Settings

PG_URL = "postgresql://app:secret@10.2.0.1:5433/sectortrace"
RAILWAY_SOURCE_URL = "postgresql://postgres:source-secret@altaria.proxy.rlwy.net:20580/railway"


def settings_for(url: str | None, tmp_path) -> Settings:
    return Settings(contact_email="t@e.com", database_url=url,
                    database_path=tmp_path / "warehouse.db")


class TestBackendResolution:
    def test_no_url_is_sqlite(self, tmp_path):
        assert settings_for(None, tmp_path).database_backend == "sqlite"

    def test_a_url_is_postgres(self, tmp_path):
        assert settings_for(PG_URL, tmp_path).database_backend == "postgres"

    def test_a_managed_postgres_source_url_is_accepted(self, tmp_path):
        settings = Settings(
            contact_email="t@e.com", database_url=PG_URL,
            database_source_url=RAILWAY_SOURCE_URL,
            database_path=tmp_path / "warehouse.db")
        assert settings.database_backend == "postgres"
        assert settings.database_source_url == RAILWAY_SOURCE_URL

    def test_an_empty_url_falls_back_to_sqlite(self, tmp_path):
        """`DATABASE_URL=` on a command line forces the file back on without
        anyone editing `.env`."""
        assert settings_for("", tmp_path).database_backend == "sqlite"
        assert settings_for("   ", tmp_path).database_backend == "sqlite"

    def test_a_non_postgres_url_is_refused_at_settings_time(self, tmp_path):
        """Not at the first connection — by then a run has applied migrations
        and fetched for an hour."""
        with pytest.raises(ValueError, match="must be a PostgreSQL URL"):
            settings_for("mysql://host/db", tmp_path)

    @pytest.mark.parametrize("url", [
        "postgresql://h/d", "postgres://h/d", "postgresql+psycopg://h/d"])
    def test_the_url_forms_a_platform_might_hand_out(self, url, tmp_path):
        assert settings_for(url, tmp_path).database_backend == "postgres"


class TestPasswordsDoNotLeak:
    def test_the_password_is_redacted(self, tmp_path):
        redacted = settings_for(PG_URL, tmp_path).redacted_database_url
        assert "secret" not in redacted
        assert "10.2.0.1:5433" in redacted
        assert redacted.startswith("postgresql://app:")

    def test_a_url_without_a_password_survives_intact(self, tmp_path):
        url = "postgresql://10.2.0.1:5433/sectortrace"
        assert settings_for(url, tmp_path).redacted_database_url == url

    def test_no_url_redacts_to_none(self, tmp_path):
        assert settings_for(None, tmp_path).redacted_database_url is None


class TestMigrationTreeSelection:
    def test_sqlite_gets_the_top_level_tree(self, tmp_path):
        chosen = db.migrations_dir_for(settings_for(None, tmp_path))
        assert chosen.name == "migrations"
        assert (chosen / "0001_core.sql").exists()

    def test_postgres_gets_the_postgres_tree(self, tmp_path):
        chosen = db.migrations_dir_for(settings_for(PG_URL, tmp_path))
        assert chosen.name == "postgres"
        assert (chosen / "0001_core.sql").exists()

    def test_no_cli_command_names_the_sqlite_tree_directly(self):
        """`settings.migrations_dir` is always SQLite's.

        Passing it to `apply_migrations` pins the tree regardless of backend,
        which on PostgreSQL means running SQLite DDL against it and then
        recording those filenames as applied — a schema that is wrong and a
        ledger that says it is fine. Two commands did exactly this.
        """
        from pipeline import cli

        source = inspect.getsource(cli)
        assert "apply_migrations(conn, settings.migrations_dir)" not in source

    def test_the_backend_comes_from_the_connection_not_the_settings(self, tmp_path,
                                                                     monkeypatch):
        """A test can hold a SQLite connection while DATABASE_URL is set.

        If `apply_migrations` trusted the settings instead of the connection it
        would send `information_schema` queries to a file, and the whole
        offline suite would depend on nobody having a PostgreSQL URL in their
        environment.
        """
        monkeypatch.setenv("DATABASE_URL", PG_URL)
        conn = sqlite3.connect(tmp_path / "w.db")
        try:
            assert db.backend_of(conn) == "sqlite"
        finally:
            conn.close()


class TestTheOfflineSuiteStaysOffline:
    """The suite must not find a PostgreSQL warehouse, whatever is configured.

    This is not hypothetical. The moment a `DATABASE_URL` went into this
    checkout's `.env`, a bare `Settings()` began resolving to postgres — and
    `db.get_connection()` and `queries.readonly_connection()` both fall back
    to `get_settings()` when handed nothing. Without the autouse fixture in
    conftest, tests that write would have written to a real warehouse over the
    LAN.
    """

    def test_a_bare_settings_object_is_sqlite(self):
        assert Settings(contact_email="t@e.com").database_backend == "sqlite"

    def test_get_settings_is_sqlite(self):
        from pipeline.config import get_settings

        assert get_settings().database_backend == "sqlite"

    def test_the_environment_is_neutralised_not_merely_absent(self):
        """Deleting the variable would not be enough — the value comes from
        the `.env` file, and an environment variable is what overrides it."""
        assert os.environ.get("DATABASE_URL") == ""
        assert os.environ.get("DATABASE_RO_URL") == ""

    def test_the_live_tests_use_a_different_variable(self):
        """So that pointing the suite at a database is a deliberate act and
        cannot happen by inheriting a working configuration."""
        source = (Path(__file__).parent / "test_postgres_live.py").read_text(encoding="utf-8")
        assert "POSTGRES_TEST_URL" in source
        assert 'environ.get("DATABASE_URL")' not in source


class TestExceptionTuples:
    """`except db.Error` has to catch whichever driver is connected."""

    @pytest.mark.parametrize("name", ["Error", "DatabaseError", "IntegrityError",
                                       "OperationalError", "Warning"])
    def test_each_tuple_includes_the_sqlite_class(self, name):
        tuple_ = getattr(db, name)
        assert isinstance(tuple_, tuple)
        assert getattr(sqlite3, name) in tuple_

    def test_a_trigger_refusal_is_an_integrity_error_on_both(self):
        """Settled decision 4's refusals must land in one exception class.

        SQLite's RAISE(ABORT) gives IntegrityError. plpgsql's bare RAISE gives
        RaiseException, which is not one — hence the explicit ERRCODE in the
        PostgreSQL trigger bodies, and hence RaiseException listed here too for
        the trigger somebody writes later without it.
        """
        psycopg = pytest.importorskip("psycopg")
        assert psycopg.IntegrityError in db.IntegrityError
        assert psycopg.errors.RaiseException in db.IntegrityError
