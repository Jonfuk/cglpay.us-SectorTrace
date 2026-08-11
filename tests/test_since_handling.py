"""`--since` must either work or say it doesn't.

Before this, only m01 read ctx.since while the CLI advertised the flag for all
13 modules, so `run m07_ndtms --since 2024-01-01` processed everything and
reported success — the failure mode that looks like an answer.
"""
from __future__ import annotations

from datetime import date

import pytest
from typer.testing import CliRunner

from pipeline import cli as cli_module
from pipeline.modules import m08_pfd_reports as pfd
from pipeline.registry import (
    MODULE_META,
    MODULE_REGISTRY,
    ModuleContext,
    discover_modules,
    module_meta,
)

MODULES_HONOURING_SINCE = {
    "m01_procurement", "m02_tribunals", "m03_charity_finance",
    "m06_workforce_census", "m07_ndtms", "m08_pfd_reports",
    "m11_public_health_grant", "m13_la_budgets",
}


@pytest.fixture(scope="module", autouse=True)
def _discovered():
    discover_modules()


def _ctx(since, settings=None):
    return ModuleContext(conn=None, settings=settings, since=since, dry_run=False, limit=None)


# --- context helpers -------------------------------------------------------------

def test_since_date_parses_iso():
    assert _ctx("2024-01-01").since_date() == date(2024, 1, 1)
    assert _ctx("2024-01-01").since_year() == 2024


def test_since_date_is_none_when_absent():
    assert _ctx(None).since_date() is None
    assert _ctx(None).since_year() is None


def test_unparseable_since_raises_rather_than_processing_everything():
    with pytest.raises(ValueError, match="ISO date"):
        _ctx("last tuesday").since_date()


@pytest.mark.parametrize("value,expected", [
    ("2023-06-01", True),
    ("2024-01-01", False),
    ("2025-01-01", False),
    ("2023-06-01T09:00:00Z", True),
])
def test_is_before_since(value, expected):
    assert _ctx("2024-01-01").is_before_since(value) is expected


def test_unreadable_dates_are_never_skipped():
    """Dropping a record because its date could not be parsed would be a
    silent loss; keeping it surfaces the record for a human instead.
    """
    ctx = _ctx("2024-01-01")
    assert ctx.is_before_since("not a date") is False
    assert ctx.is_before_since(None) is False
    assert ctx.is_before_since("") is False


def test_no_since_means_nothing_is_filtered():
    assert _ctx(None).is_before_since("1999-01-01") is False


# --- capability declaration ---------------------------------------------------------

def test_every_module_declares_since_support():
    real = {n for n in MODULE_REGISTRY if n.startswith("m") and n[1:3].isdigit()}
    undeclared = sorted(n for n in real if n not in MODULE_META)
    assert undeclared == []


def test_declared_support_matches_the_intended_set():
    real = {n for n in MODULE_REGISTRY if n.startswith("m") and n[1:3].isdigit()}
    supporting = {n for n in real if module_meta(n).supports_since}
    assert supporting == MODULES_HONOURING_SINCE


def test_modules_that_ignore_since_explain_why():
    """An unexplained 'not supported' is not much better than silence."""
    real = {n for n in MODULE_REGISTRY if n.startswith("m") and n[1:3].isdigit()}
    for name in real:
        meta = module_meta(name)
        if not meta.supports_since:
            assert meta.since_note.strip(), f"{name} gives no reason for ignoring --since"


def test_every_supporting_module_actually_reads_since():
    """Declaring support without implementing it would be the original bug
    wearing a label.
    """
    import inspect

    for name in MODULES_HONOURING_SINCE:
        source = inspect.getsource(MODULE_REGISTRY[name])
        assert ("ctx.since" in source or "since_year" in source
                or "is_before_since" in source or "_is_before_since_ddmmyyyy" in source), \
            f"{name} declares supports_since but never reads it"


# --- CLI behaviour ---------------------------------------------------------------------

def test_cli_rejects_an_unparseable_since(tmp_path, monkeypatch):
    from pipeline.config import Settings

    settings = Settings(
        contact_email="t@example.com", database_path=tmp_path / "w.db",
        raw_archive_dir=tmp_path / "raw", logs_dir=tmp_path / "logs",
        migrations_dir=__import__("pathlib").Path(__file__).resolve().parent.parent
            / "pipeline" / "migrations",
        _env_file=None)
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)

    result = CliRunner().invoke(cli_module.app, ["run", "m00_geography", "--since", "not-a-date"])
    assert result.exit_code == 1
    assert "ISO date" in result.output


def test_cli_warns_when_since_has_no_effect(tmp_path, monkeypatch):
    from pipeline.config import Settings

    settings = Settings(
        contact_email="t@example.com", database_path=tmp_path / "w.db",
        raw_archive_dir=tmp_path / "raw", logs_dir=tmp_path / "logs",
        migrations_dir=__import__("pathlib").Path(__file__).resolve().parent.parent
            / "pipeline" / "migrations",
        _env_file=None)
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    # m05_cqc does not filter by date; the CLI must say so before running.
    monkeypatch.setitem(MODULE_REGISTRY, "m05_cqc", lambda ctx: None)

    result = CliRunner().invoke(cli_module.app, ["run", "m05_cqc", "--since", "2024-01-01"])
    assert "has no effect on m05_cqc" in result.output


# --- module-level date handling ----------------------------------------------------------

@pytest.mark.parametrize("report_date,expected", [
    ("27/04/2023", True),    # before
    ("27/04/2026", False),   # after
    ("01/01/2024", False),   # on the boundary
])
def test_pfd_uses_ddmmyyyy_not_iso(report_date, expected):
    """PFD headers give DD/MM/YYYY. Feeding that to the ISO helper would never
    parse, so --since would silently filter nothing.
    """
    assert pfd._is_before_since_ddmmyyyy(_ctx("2024-01-01"), report_date) is expected


def test_pfd_keeps_reports_with_unreadable_dates():
    assert pfd._is_before_since_ddmmyyyy(_ctx("2024-01-01"), "sometime in 2023") is False
    assert pfd._is_before_since_ddmmyyyy(_ctx("2024-01-01"), None) is False


def test_iso_helper_would_have_silently_failed_on_pfd_dates():
    """Documents why PFD needs its own comparison — a regression guard against
    someone 'simplifying' it back to the shared helper.
    """
    assert _ctx("2024-01-01").is_before_since("27/04/2023") is False
