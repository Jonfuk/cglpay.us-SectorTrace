"""Regression coverage for a real bug found while smoke-testing m00_geography
live: pipeline.cli.run never called conn.commit(), so every module's writes
were silently discarded on process exit. sqlite3 does not autocommit DML by
default and close() does not flush pending changes.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from pipeline import cli as cli_module
from pipeline.config import Settings
from pipeline.registry import ModuleContext, register_module

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "pipeline" / "migrations"


def _settings_for(tmp_path: Path) -> Settings:
    return Settings(
        contact_email="test@example.com",
        database_path=tmp_path / "warehouse.db",
        raw_archive_dir=tmp_path / "raw",
        migrations_dir=MIGRATIONS_DIR,
        logs_dir=tmp_path / "logs",
        _env_file=None,
    )


@register_module("fake_writer_for_tests")
def _fake_writer(ctx: ModuleContext) -> None:
    ctx.conn.execute("CREATE TABLE IF NOT EXISTS cli_test_rows (id INTEGER PRIMARY KEY)")
    ctx.conn.execute("INSERT INTO cli_test_rows DEFAULT VALUES")


# Note: sqlite3's implicit-transaction handling only wraps DML (INSERT/
# UPDATE/DELETE/REPLACE); CREATE TABLE runs and commits immediately outside
# any transaction. Real modules never hit this because schema DDL lives in
# migrations (applied and committed up front) — modules only ever do DML.
# So the dry-run test below pre-creates its table and only exercises INSERT,
# matching how a real module actually behaves.
@register_module("fake_insert_only_for_tests")
def _fake_insert_only(ctx: ModuleContext) -> None:
    ctx.conn.execute("INSERT INTO cli_test_rows DEFAULT VALUES")


def test_run_commits_module_writes(tmp_path, monkeypatch):
    settings = _settings_for(tmp_path)
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)

    result = CliRunner().invoke(cli_module.app, ["run", "fake_writer_for_tests"])
    assert result.exit_code == 0, result.output or repr(result.exception)

    conn = sqlite3.connect(settings.database_path)
    count = conn.execute("SELECT COUNT(*) FROM cli_test_rows").fetchone()[0]
    conn.close()
    assert count == 1


def test_run_dry_run_rolls_back(tmp_path, monkeypatch):
    settings = _settings_for(tmp_path)
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    setup_conn = sqlite3.connect(settings.database_path)
    setup_conn.execute("CREATE TABLE cli_test_rows (id INTEGER PRIMARY KEY)")
    setup_conn.commit()
    setup_conn.close()

    result = CliRunner().invoke(cli_module.app, ["run", "fake_insert_only_for_tests", "--dry-run"])
    assert result.exit_code == 0, result.output or repr(result.exception)

    conn = sqlite3.connect(settings.database_path)
    count = conn.execute("SELECT COUNT(*) FROM cli_test_rows").fetchone()[0]
    conn.close()
    assert count == 0


def test_backup_command_writes_a_verified_copy(tmp_path, monkeypatch):
    from pipeline import backup as backup_module
    from pipeline.config import Settings

    settings = Settings(
        contact_email="test@example.com",
        database_path=tmp_path / "warehouse.db",
        raw_archive_dir=tmp_path / "raw",
        migrations_dir=MIGRATIONS_DIR,
        logs_dir=tmp_path / "logs",
        backup_dir=tmp_path / "backups",
        _env_file=None)
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)

    from pipeline import db

    conn = db.get_connection(settings)
    db.apply_migrations(conn, settings.migrations_dir)
    conn.commit()
    conn.close()

    result = CliRunner().invoke(cli_module.app, ["backup"])
    assert result.exit_code == 0, result.output or repr(result.exception)
    assert "integrity ok" in result.output

    made = list((tmp_path / "backups").glob("warehouse-*.db"))
    assert len(made) == 1
    assert backup_module.listing(settings)[0]["rows"] is not None

    listed = CliRunner().invoke(cli_module.app, ["list-backups"])
    assert listed.exit_code == 0, listed.output
    assert made[0].name in listed.output


def test_restoring_over_a_warehouse_without_force_fails_cleanly(tmp_path, monkeypatch):
    """A traceback is not a refusal. The CLI has to say why and exit non-zero."""
    from pipeline.config import Settings

    settings = Settings(
        contact_email="test@example.com",
        database_path=tmp_path / "warehouse.db",
        raw_archive_dir=tmp_path / "raw",
        migrations_dir=MIGRATIONS_DIR,
        logs_dir=tmp_path / "logs",
        backup_dir=tmp_path / "backups",
        _env_file=None)
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)

    from pipeline import db

    conn = db.get_connection(settings)
    db.apply_migrations(conn, settings.migrations_dir)
    conn.commit()
    conn.close()

    CliRunner().invoke(cli_module.app, ["backup"])
    made = next((tmp_path / "backups").glob("warehouse-*.db"))

    result = CliRunner().invoke(cli_module.app, ["restore", str(made)])

    assert result.exit_code == 1
    assert "already exists" in result.output
    assert settings.database_path.is_file()
