"""A dry run has to be recognisable afterwards.

`--dry-run` rolls back, so it leaves a warehouse byte-identical to the one it
started with. That is the point of it, and it also means the *only* difference
between "fetched and parsed 238,407 rows, wrote nothing on purpose" and "the
parser silently found nothing" is what got said at the time.

This was not hypothetical: m13_la_budgets logged `budgets.run_complete
documents=4 rows=238407` and left both its tables empty, and nothing in the
log, the summary or the warehouse could settle which of the two had happened.
"""
from __future__ import annotations

import json
import logging

import pytest

from pipeline import runner


@pytest.fixture
def module_log(settings, monkeypatch):
    """Logging configured the way the CLI configures it, into tmp.

    Returns a reader for the lines the run produced. The real
    `configure_logging` is used rather than a capture fixture because the file
    it writes *is* the artefact under test — it is the audit trail a person
    reads six months later.
    """
    from pipeline import logging_conf

    monkeypatch.setattr(logging_conf, "get_settings", lambda: settings)
    logging_conf.configure_logging("test-dry-run")
    path = settings.logs_dir / "test-dry-run.log"

    def events() -> list[dict]:
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                payload = json.loads(line)
            except ValueError:
                continue  # non-structlog lines from httpx and friends
            if isinstance(payload, dict) and "event" in payload:
                out.append(payload)
        return out

    yield events
    logging.getLogger().handlers.clear()


def a_writing_module(ctx):
    # REPLACE so the same module can be run twice in one test — a dry run
    # after a real one is exactly the comparison worth making.
    ctx.conn.execute(
        "INSERT OR REPLACE INTO module_cursors (module, cursor_value, updated_at) "
        "VALUES ('a_fake', '2026-01-01', '2026-01-01T00:00:00Z')")


def run_once(settings, dry_run: bool):
    return runner.execute_module("a_fake", a_writing_module, settings,
                                  since=None, dry_run=dry_run, limit=None,
                                  observer=runner.RunObserver())


def find(events, name):
    return [e for e in events if e["event"] == name]


def test_the_summary_row_says_which_kind_of_run_it_was(conn, settings):
    wet = run_once(settings, dry_run=False)
    dry = run_once(settings, dry_run=True)

    assert wet["dry_run"] is False
    assert dry["dry_run"] is True
    # Both did the same work, so both report rows. The flag is what separates
    # them, which is exactly why it has to be on the row.
    assert dry["rows"] > 0


def test_the_log_says_a_dry_run_wrote_nothing(conn, settings, module_log):
    run_once(settings, dry_run=True)
    events = module_log()

    starting = find(events, "module.starting")
    assert starting and starting[-1]["dry_run"] is True

    finished = find(events, "module.finished")
    assert finished, "a run must record how it ended, not only that it began"
    assert finished[-1]["dry_run"] is True
    assert finished[-1]["wrote"] is False
    assert finished[-1]["rows"] > 0, (
        "the count is worth keeping — it is what the run would have written")


def test_the_log_says_a_real_run_did_write(conn, settings, module_log):
    run_once(settings, dry_run=False)
    finished = find(module_log(), "module.finished")

    assert finished[-1]["wrote"] is True
    assert finished[-1]["dry_run"] is False


def test_the_arguments_are_recorded_before_the_work_starts(conn, settings, module_log):
    runner.execute_module("a_fake", a_writing_module, settings,
                           since="2024-01-01", dry_run=False, limit=5,
                           observer=runner.RunObserver())
    starting = find(module_log(), "module.starting")[-1]

    assert starting["since"] == "2024-01-01"
    assert starting["limit"] == 5


def test_a_failing_module_still_records_how_it_ended(conn, settings, module_log):
    def explodes(ctx):
        raise RuntimeError("the source changed shape")

    row = runner.execute_module("a_fake", explodes, settings, since=None,
                                 dry_run=False, limit=None,
                                 observer=runner.RunObserver())
    assert row["status"] == "failed"
    assert row["dry_run"] is False

    finished = find(module_log(), "module.finished")[-1]
    assert finished["status"] == "failed"
    assert "the source changed shape" in finished["error"]


def test_the_run_summary_table_says_nothing_was_written():
    from pipeline import console

    dry = console.run_summary([{"module": "a_fake", "status": "ok",
                                 "dry_run": True, "rows": 238407}])
    wet = console.run_summary([{"module": "a_fake", "status": "ok",
                                 "dry_run": False, "rows": 238407}])

    assert "dry run" in dry.title
    assert "nothing written" in dry.title
    assert dry.title != wet.title
    # The rows column has to disown the number it is showing, because the
    # table gets screenshotted and read back out of context.
    assert [column.header for column in dry.columns][3] == "Rows not written"
    assert [column.header for column in wet.columns][3] == "Rows written"
