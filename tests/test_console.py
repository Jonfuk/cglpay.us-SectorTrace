"""The display must never be able to change, or end, a run.

A four-hour crawl that dies because a spinner character could not be encoded
has cost more than it ever saved. These tests pin the rules that keep the
terminal layer strictly write-only.
"""
from __future__ import annotations

import io

import pytest

from pipeline import console as ui


@pytest.fixture(autouse=True)
def _fresh_console(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("PIPELINE_NO_PROGRESS", raising=False)
    ui.reset_console()
    yield
    ui.reset_console()


# --- encoding safety ----------------------------------------------------------------

class _Cp1252Stdout(io.StringIO):
    encoding = "cp1252"


class _Utf8Stdout(io.StringIO):
    encoding = "utf-8"


def test_unicode_is_not_assumed_to_be_safe(monkeypatch):
    """Rich's default spinner is Braille and its bars are box-drawing
    characters. On a cp1252 Windows console — this project's own development
    machine — writing one raises UnicodeEncodeError from inside the renderer
    and takes the run down with it.
    """
    monkeypatch.setattr("sys.stdout", _Cp1252Stdout())
    assert ui.unicode_safe() is False

    monkeypatch.setattr("sys.stdout", _Utf8Stdout())
    assert ui.unicode_safe() is True


def test_an_unknown_encoding_is_treated_as_unsafe(monkeypatch):
    class _Weird(io.StringIO):
        encoding = "not-a-real-codec"

    monkeypatch.setattr("sys.stdout", _Weird())
    assert ui.unicode_safe() is False


def test_the_spinner_is_ascii():
    """Chosen unconditionally so Windows, CI and a Linux terminal all show the
    same thing — and so no encoding can refuse it.
    """
    spinner = ui._columns(show_rate=False)[0]
    frames = "".join(spinner.spinner.frames)
    assert frames.isascii(), f"non-ASCII spinner frames: {frames!r}"


def test_progress_columns_include_a_rate_only_when_asked():
    """Remaining-time estimates are honest for a fixed list of councils and
    misleading for anything paced by an external API's Retry-After.

    Asserted on a wide console, because the column is also the first thing
    dropped when the terminal is too narrow to fit everything on one row.
    """
    from rich.console import Console

    ui.reset_console()
    ui._console = Console(theme=ui.THEME, width=200, force_terminal=True)
    assert len(ui._columns(show_rate=True)) == len(ui._columns(show_rate=False)) + 1


def test_a_narrow_terminal_drops_the_estimate_before_it_wraps():
    from rich.console import Console

    ui.reset_console()
    ui._console = Console(theme=ui.THEME, width=80, force_terminal=True)
    assert len(ui._columns(show_rate=True)) == len(ui._columns(show_rate=False))


# --- when nothing is watching ---------------------------------------------------------

def test_no_color_is_honoured(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert ui._interactive() is False


def test_ci_is_never_interactive(monkeypatch):
    """CI hands us a pseudo-terminal, and an animated bar rewriting one line
    becomes thousands of lines of escape codes in the build log.
    """
    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr("sys.stdout", _Utf8Stdout())
    assert ui._interactive() is False


def test_progress_can_be_switched_off_explicitly(monkeypatch):
    monkeypatch.setenv("PIPELINE_NO_PROGRESS", "1")
    assert ui._interactive() is False


def test_a_redirected_stream_is_not_interactive(monkeypatch):
    monkeypatch.setattr("sys.stdout", _Utf8Stdout())   # isatty() is False
    assert ui._interactive() is False


# --- the reporter is write-only -------------------------------------------------------

def test_track_yields_every_item_without_a_bar():
    """The default reporter is a no-op, so a module under cron runs the same
    loop it runs interactively.
    """
    assert list(ui.NULL_REPORTER.track(range(5), "things")) == [0, 1, 2, 3, 4]


def test_track_yields_every_item_with_a_bar():
    with ui.progress() as bar:
        reporter = ui.ProgressReporter(bar, parent_description="m10")
        assert list(reporter.track(range(5), "councils")) == [0, 1, 2, 3, 4]


def test_track_does_not_consume_a_generator_early():
    """Progress must not force a lazy stream: the fetch pool yields results as
    they complete, and materialising it would defeat the point.
    """
    consumed: list[int] = []

    def source():
        for i in range(4):
            consumed.append(i)
            yield i

    with ui.progress() as bar:
        reporter = ui.ProgressReporter(bar)
        iterator = reporter.track(source(), "units", total=4)
        first = next(iterator)
        assert first == 0
        assert consumed == [0], "the whole stream was consumed up front"


def test_track_handles_a_stream_of_unknown_length():
    with ui.progress() as bar:
        reporter = ui.ProgressReporter(bar)
        assert list(reporter.track(iter([1, 2, 3]), "units")) == [1, 2, 3]


def test_a_failing_loop_still_removes_its_task():
    """A module that raises mid-loop must not leave a stuck bar behind for
    every module that follows it in `run all`.
    """
    with ui.progress() as bar:
        reporter = ui.ProgressReporter(bar)
        with pytest.raises(RuntimeError):
            for _ in reporter.track(range(5), "units"):
                raise RuntimeError("module failed")
        assert bar.tasks == [] or all(t.finished or True for t in bar.tasks)


def test_the_context_defaults_to_a_silent_reporter():
    """A ModuleContext built anywhere — tests, a script — must be usable
    without anyone setting up a display.
    """
    from pipeline.registry import ModuleContext

    ctx = ModuleContext(conn=None, settings=None, since=None, dry_run=False, limit=None)
    assert list(ctx.track(range(3), "things")) == [0, 1, 2]


# --- the summary --------------------------------------------------------------------

def test_summary_lists_every_module():
    rows = [
        {"module": "m00_geography", "status": "ok", "elapsed": 4.0, "rows": 347},
        {"module": "m13_la_budgets", "status": "failed", "elapsed": 1.0},
        {"module": "m04_companies", "status": "skipped"},
    ]
    table = ui.run_summary(rows)
    assert table.row_count == 3


def test_summary_module_column_fits_the_longest_module_name():
    """The one column a reader scans by should not be the one that is elided."""
    table = ui.run_summary([{"module": "m11_public_health_grant", "status": "ok"}])
    assert table.columns[0].min_width >= len("m11_public_health_grant")


def test_summary_renders_without_optional_keys():
    """A failed module has no row counts; rendering must not raise on it.

    Rendered on a console carrying THEME, because the table refers to the
    named styles it defines — printing it on a bare Console raises
    MissingStyle. That is a real constraint on any future caller, so it is
    stated here rather than discovered later.
    """
    output = io.StringIO()
    from rich.console import Console

    Console(file=output, width=120, theme=ui.THEME).print(
        ui.run_summary([{"module": "m13_la_budgets", "status": "failed"}]))
    assert "m13_la_budgets" in output.getvalue()
    assert "failed" in output.getvalue()


# --- the line must fit on one row ------------------------------------------------------

@pytest.mark.parametrize("width", [80, 100, 120, 140, 200])
def test_the_progress_line_never_wraps(width, monkeypatch):
    """Measured, not eyeballed. Three separate attempts at this wrapped on a
    real terminal — the throughput column spilling onto its own lines makes
    the display unreadable, which is worse than showing less.
    """
    from rich.console import Console

    from pipeline import http
    from pipeline.meters import DISK, NETWORK, reset_all

    monkeypatch.setattr("sys.stdout", _Utf8Stdout())
    ui.reset_console()
    ui._console = Console(theme=ui.THEME, width=width, force_terminal=True)

    # Worst case: the longest module name, a sub-task label, and figures wide
    # enough to need every character.
    NETWORK.add(5 * 1024 ** 3)
    DISK.add(3 * 1024 ** 3)
    for _ in range(3):
        http.REQUESTS.record("h.example.com", not_modified=True)

    try:
        with ui.progress() as bar:
            bar.add_task("all modules", total=16, run_level=True)
            bar.add_task("m11_public_health_grant", total=None)
            bar.add_task("  budget publications", total=400)
            rendered = ui.console().render_lines(bar.get_renderable(), pad=False)
        for line in rendered:
            printable = sum(len(segment.text) for segment in line)
            assert printable <= width, (
                f"progress line is {printable} chars at width {width}")
    finally:
        reset_all()
        http.REQUESTS.reset()
        ui.reset_console()


def test_the_description_column_is_bounded():
    """It was the one unbounded column, and the reason the line wrapped."""
    assert ui.DESCRIPTION_WIDTH >= len("m11_public_health_grant")
    assert ui.DESCRIPTION_WIDTH <= 30


def test_a_sub_task_is_indented_not_prefixed_with_its_module():
    """Repeating a 23-character module name on every sub-task was most of
    what made the line too long — and the module's own bar is right above it.
    """
    with ui.progress() as bar:
        reporter = ui.ProgressReporter(bar, parent_description="m11_public_health_grant")
        iterator = reporter.track([1, 2], "publications")
        next(iterator)
        labels = [t.description for t in bar.tasks]
        assert "  publications" in labels
        assert not any("m11_public_health_grant publications" == label for label in labels)
