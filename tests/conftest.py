from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pipeline import db
from pipeline.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        contact_email="test@example.com",
        database_path=tmp_path / "warehouse.db",
        raw_archive_dir=tmp_path / "raw",
        migrations_dir=Path(__file__).resolve().parent.parent / "pipeline" / "migrations",
        logs_dir=tmp_path / "logs",
        _env_file=None,
    )


@pytest.fixture
def conn(settings: Settings) -> sqlite3.Connection:
    connection = db.get_connection(settings)
    db.apply_migrations(connection, settings.migrations_dir)
    yield connection
    connection.close()
