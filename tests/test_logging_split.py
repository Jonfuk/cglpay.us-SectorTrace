"""The log file and the terminal are two different artefacts.

They were the same one: `configure_logging` attached a StreamHandler at INFO,
so every `http.get` printed to stdout. At four hours of crawling that is not
information — it is a wall of text scrolling past faster than anyone can read,
and after the progress bars were added it scrolled those away too.

The split: the file keeps everything, because that is what makes a figure
defensible six months later. The terminal gets warnings and above, plus a
counter. Nothing is dropped, only moved.
"""
from __future__ import annotations

import logging

import pytest

from pipeline import http
from pipeline.logging_conf import configure_logging

pytestmark = pytest.mark.serial


@pytest.fixture
def configured(tmp_path, monkeypatch):
    from pipeline import config, logging_conf
    from pipeline.config import Settings

    settings = Settings(contact_email="t@example.com", logs_dir=tmp_path / "logs",
                         raw_archive_dir=tmp_path / "raw",
                         database_path=tmp_path / "w.db", _env_file=None)
    monkeypatch.setattr(logging_conf, "get_settings", lambda: settings)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    configure_logging("test_module")
    yield settings
    logging.getLogger().handlers.clear()


def _handlers_by_kind():
    from rich.logging import RichHandler

    root = logging.getLogger()
    console = [h for h in root.handlers if isinstance(h, RichHandler)]
    files = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
    return console, files


# --- the split ---------------------------------------------------------------------

def test_the_console_only_gets_warnings_and_above(configured):
    console, _ = _handlers_by_kind()
    assert console, "no console handler was attached"
    assert console[0].level == logging.WARNING


def test_the_log_file_still_gets_everything(configured):
    _, files = _handlers_by_kind()
    assert files, "no file handler was attached"
    assert files[0].level == logging.INFO
    assert logging.getLogger().level == logging.INFO


def test_a_per_request_log_line_never_reaches_the_terminal(configured):
    """The regression, stated directly."""
    console, _ = _handlers_by_kind()
    record = logging.LogRecord("x", logging.INFO, "", 0, "http.get", None, None)
    assert not console[0].filter(record) or record.levelno < console[0].level


def test_every_request_is_still_written_to_the_log_file(configured):
    import structlog

    structlog.get_logger().info("http.get", url="https://example.gov.uk/a")
    logging.getLogger().handlers[0].flush()

    written = (configured.logs_dir / "test_module.log").read_text(encoding="utf-8")
    assert "http.get" in written
    assert "https://example.gov.uk/a" in written


def test_a_warning_does_reach_the_terminal(configured):
    """Quieting the console must not silence the things worth interrupting
    for — a robots override, a blocked source, a failed module.
    """
    console, _ = _handlers_by_kind()
    assert logging.WARNING >= console[0].level
    assert logging.ERROR >= console[0].level


def test_the_console_handler_shares_the_progress_console(configured):
    """A plain StreamHandler interleaves with an active progress display
    mid-redraw; RichHandler on the same console prints above it.
    """
    from pipeline.console import console as ui_console

    handlers, _ = _handlers_by_kind()
    assert handlers[0].console is ui_console()


# --- the counter that replaced the noise ----------------------------------------------

def test_the_counter_records_requests_and_hosts():
    http.REQUESTS.reset()
    http.REQUESTS.record("a.example.com", not_modified=False)
    http.REQUESTS.record("a.example.com", not_modified=False)
    http.REQUESTS.record("b.example.com", not_modified=True)

    assert http.REQUESTS.total == 3
    assert http.REQUESTS.hosts == 2
    assert http.REQUESTS.not_modified == 1
    http.REQUESTS.reset()


def test_the_counter_is_thread_safe():
    """Modules and fetch pools both increment it concurrently."""
    import threading

    http.REQUESTS.reset()
    ready = threading.Barrier(8)

    def bump():
        ready.wait(timeout=10)
        for _ in range(50):
            http.REQUESTS.record("h.example.com", not_modified=False)

    threads = [threading.Thread(target=bump) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert http.REQUESTS.total == 400
    http.REQUESTS.reset()


class _RunLevelTask:
    """The one bar that carries whole-run figures; every other renders empty."""

    fields = {"run_level": True}


def test_the_column_renders_the_live_total():
    from pipeline.console import RequestCountColumn

    http.REQUESTS.reset()
    column = RequestCountColumn()
    task = _RunLevelTask()
    assert column.render(task).plain == "", "an idle run should not show a zero"

    http.REQUESTS.record("h.example.com", not_modified=False)
    assert "1 req" in column.render(task).plain

    http.REQUESTS.record("h.example.com", not_modified=True)
    rendered = column.render(task).plain
    assert "2 req" in rendered
    assert "1 cached" in rendered, "conditional requests are worth showing"
    http.REQUESTS.reset()


# --- rotation (O-03) ------------------------------------------------------------------
#
# Nothing ever pruned these files. The half of the finding that closed in
# Phase 2 was tests writing into the operator's logs/; this is the other half.


def test_the_log_file_is_bounded_and_keeps_generations(configured):
    from logging.handlers import RotatingFileHandler

    _, files = _handlers_by_kind()
    handler = files[0]

    assert isinstance(handler, RotatingFileHandler)
    assert handler.maxBytes == configured.log_max_bytes > 0
    assert handler.backupCount == configured.log_backup_count > 0


def test_a_log_that_passes_the_ceiling_rolls_over_rather_than_growing(
        tmp_path, monkeypatch):
    """Written small enough to roll in a test, because the real ceiling is
    10 MB and asserting on it would mean writing 10 MB."""
    import logging as logging_module

    from pipeline import config, logging_conf
    from pipeline.config import Settings

    settings = Settings(contact_email="t@example.com", logs_dir=tmp_path / "logs",
                         raw_archive_dir=tmp_path / "raw",
                         database_path=tmp_path / "w.db",
                         log_max_bytes=2_000, log_backup_count=2, _env_file=None)
    monkeypatch.setattr(logging_conf, "get_settings", lambda: settings)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    logging_conf.configure_logging("rolling_module")

    try:
        log = logging_module.getLogger("rolling")
        for index in range(400):
            log.info("x" * 100 + str(index))
        for handler in logging_module.getLogger().handlers:
            handler.flush()

        directory = settings.logs_dir
        assert (directory / "rolling_module.log").stat().st_size <= 2_200
        assert (directory / "rolling_module.log.1").is_file()
        # Bounded: the ceiling is the point, so the generation past the count
        # must be gone rather than merely old.
        assert not (directory / "rolling_module.log.3").exists()
        assert sum(p.stat().st_size for p in directory.glob("rolling_module.log*")) \
            <= 2_200 * 3
    finally:
        logging_module.getLogger().handlers.clear()


def test_configuring_logging_does_not_create_a_file_for_a_module_that_never_ran(
        tmp_path, monkeypatch):
    """Several commands configure logging as a matter of course. An empty file
    per module name they passed is how a log directory stops being readable."""
    from pipeline import config, logging_conf
    from pipeline.config import Settings

    settings = Settings(contact_email="t@example.com", logs_dir=tmp_path / "logs",
                         raw_archive_dir=tmp_path / "raw",
                         database_path=tmp_path / "w.db", _env_file=None)
    monkeypatch.setattr(logging_conf, "get_settings", lambda: settings)
    monkeypatch.setattr(config, "get_settings", lambda: settings)

    try:
        logging_conf.configure_logging("quiet_module")
        assert not (settings.logs_dir / "quiet_module.log").exists()
    finally:
        import logging as logging_module

        logging_module.getLogger().handlers.clear()


def test_the_suite_does_not_write_into_the_repos_log_directory(tmp_path):
    """The conftest autouse fixture, asserted rather than assumed.

    Without it, every test that invokes the CLI or builds a server opens a
    handler on the operator's real logs/ — where the audit trail of actual
    crawls lives — and leaves a file named after a fake module in it.
    """
    from pipeline import logging_conf
    from pipeline.config import REPO_ROOT

    resolved = logging_conf.get_settings().logs_dir.resolve()

    assert resolved != (REPO_ROOT / "logs").resolve()
    assert not resolved.is_relative_to(REPO_ROOT.resolve())
