from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pipeline import db
from pipeline.config import Settings


@pytest.fixture(autouse=True)
def _reset_host_clock():
    """The per-host rate limiter is process-wide by design, so it would
    otherwise carry timing state from one test into the next.
    """
    from pipeline.http import HOST_CLOCK

    HOST_CLOCK.reset()
    yield
    HOST_CLOCK.reset()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        contact_email="test@example.com",
        database_path=tmp_path / "warehouse.db",
        raw_archive_dir=tmp_path / "raw",
        migrations_dir=Path(__file__).resolve().parent.parent / "pipeline" / "migrations",
        logs_dir=tmp_path / "logs",
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
def conn(settings: Settings) -> sqlite3.Connection:
    connection = db.get_connection(settings)
    db.apply_migrations(connection, settings.migrations_dir)
    yield connection
    connection.close()
