"""Terminal output: progress while a run is happening, and a legible summary
when it finishes.

This pipeline's runs are long — hours, historically — and until now they said
nothing between "--- running m10_committee_papers ---" and the end. A run that
looks identical whether it is working, rate-limited or hung is one people
interrupt and restart, which is the opposite of polite to the sources.

Three rules shape what is here:

  * **Never let the display change the data.** Progress reporting is
    write-only. A module that cannot report progress still runs, and
    `ctx.track()` degrades to a plain loop rather than raising.

  * **Plain output when nothing is watching.** Rich disables colour and
    animation when stdout is not a terminal, and this forces that decision
    rather than trusting the environment: these scripts are meant to be safe
    from cron, Task Scheduler and CI, where a spinner rewriting the same line
    produces thousands of lines of escape codes in a log file.

  * **Structured logs are unaffected.** structlog still writes the JSON record
    of what happened. The console is for the person watching; the log is the
    audit trail, and they are not the same artefact.
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import Iterable, Iterator, TypeVar

from rich.console import Console
from rich.progress import (
    BarColumn,
    ProgressColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

T = TypeVar("T")

# Named styles rather than colours at the call site, so the palette is one
# edit and the meaning is legible in the code that uses it.
THEME = Theme({
    "pipeline.heading": "bold cyan",
    "pipeline.module": "bold white",
    "pipeline.ok": "green",
    "pipeline.warn": "yellow",
    "pipeline.error": "bold red",
    "pipeline.muted": "dim",
    "pipeline.count": "bold",
    "pipeline.source": "cyan",
})


def _interactive() -> bool:
    """Whether to animate.

    NO_COLOR is honoured (https://no-color.org/), and CI is treated as
    non-interactive even when it hands us a pseudo-terminal.
    """
    if os.environ.get("NO_COLOR") or os.environ.get("PIPELINE_NO_PROGRESS"):
        return False
    if os.environ.get("CI"):
        return False
    return sys.stdout.isatty()


def unicode_safe() -> bool:
    """Whether the terminal can encode the characters Rich likes to use.

    Not cosmetic. Rich's default spinner is Braille (U+280B…) and its bars are
    box-drawing characters; on a Windows console running cp1252 — the default
    on this project's own development machine — writing one raises
    UnicodeEncodeError from inside the renderer and takes the whole run down
    with it. A progress display that can kill a four-hour crawl is worse than
    no progress display.
    """
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        "⠋━".encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


_console: Console | None = None


def console() -> Console:
    global _console
    if _console is None:
        # errors="replace" is the backstop: council names, committee titles and
        # coroners' text all arrive from the wild, and a stray character in a
        # progress label must never be able to end a run.
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError, OSError):
            pass
        _console = Console(theme=THEME, highlight=False,
                            force_terminal=True if _interactive() else None,
                            no_color=not _interactive(),
                            safe_box=True)
    return _console


def reset_console() -> None:
    """Drop the cached console. For tests, which change the environment."""
    global _console
    _console = None


def rule(text: str) -> None:
    console().rule(f"[pipeline.heading]{text}[/]", style="pipeline.muted")


def heading(text: str) -> None:
    console().print(f"\n[pipeline.heading]{text}[/]")


def info(text: str) -> None:
    console().print(text)


def muted(text: str) -> None:
    console().print(f"[pipeline.muted]{text}[/]")


def warn(text: str) -> None:
    console().print(f"[pipeline.warn]![/] {text}")


def error(text: str) -> None:
    console().print(f"[pipeline.error]error:[/] {text}")


def success(text: str) -> None:
    console().print(f"[pipeline.ok]ok[/] {text}")


class RequestCountColumn(ProgressColumn):
    """Live request total, rendered on every refresh.

    This is what replaced a line per HTTP request on the terminal. A crawl
    that is rate-limited rather than hung still visibly ticks over, which was
    the only thing the old firehose of `http.get` lines was really telling
    anyone.
    """

    def render(self, task) -> Text:
        from pipeline.http import REQUESTS

        total = REQUESTS.total
        if not total:
            return Text("", style="pipeline.muted")
        cached = REQUESTS.not_modified
        suffix = f" ({cached} cached)" if cached else ""
        return Text(f"{total:,} req{suffix}", style="pipeline.muted")


def _columns(show_rate: bool) -> list:
    # "line" is the ASCII spinner (-\|/). Chosen unconditionally rather than
    # only when the encoding forces it, so what the maintainer sees on Windows
    # is what CI and a Linux terminal see too.
    columns = [
        SpinnerColumn(spinner_name="line", style="pipeline.source"),
        TextColumn("[pipeline.module]{task.description}[/]"),
        BarColumn(bar_width=None, complete_style="pipeline.ok",
                   finished_style="pipeline.ok", pulse_style="pipeline.source"),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        RequestCountColumn(),
        TimeElapsedColumn(),
    ]
    if show_rate:
        # Remaining-time estimates are honest for a fixed list of councils and
        # actively misleading for anything paced by an external API's
        # Retry-After, so callers opt in.
        columns.append(TimeRemainingColumn())
    return columns


@contextmanager
def progress(show_rate: bool = True) -> Iterator[Progress]:
    """A progress display, or a silent stand-in when nothing is watching."""
    with Progress(*_columns(show_rate), console=console(),
                   disable=not _interactive(), transient=False,
                   refresh_per_second=8) as bar:
        yield bar


class ProgressReporter:
    """What a module is handed to report progress with.

    Deliberately tiny. A module should be able to add progress reporting with
    one wrapped loop, and removing the display should never change what the
    module collects.
    """

    def __init__(self, bar: Progress | None = None, parent_description: str = "") -> None:
        self._bar = bar
        self._parent = parent_description

    def track(self, items: Iterable[T], description: str,
               total: int | None = None) -> Iterator[T]:
        """Yield from `items`, advancing a bar if one is displayed.

        Falls back to a plain loop when there is no display, so a module's
        control flow is identical either way.
        """
        if self._bar is None:
            yield from items
            return

        if total is None:
            try:
                total = len(items)  # type: ignore[arg-type]
            except TypeError:
                total = None

        label = f"{self._parent} {description}".strip()
        task = self._bar.add_task(label, total=total)
        try:
            for item in items:
                yield item
                self._bar.advance(task)
        finally:
            self._bar.remove_task(task)

    def note(self, text: str) -> None:
        """A line that survives above the progress display."""
        if self._bar is not None:
            self._bar.console.print(f"[pipeline.muted]  {text}[/]")


NULL_REPORTER = ProgressReporter()


def run_summary(rows: list[dict]) -> Table:
    """The end-of-run table: what ran, how long it took, and what it wrote."""
    table = Table(title="Run summary", title_style="pipeline.heading",
                   header_style="pipeline.heading", border_style="pipeline.muted",
                   show_lines=False)
    # Wide enough for the longest module name (m11_public_health_grant), so
    # the one column a reader scans by is never the one that gets elided.
    table.add_column("Module", style="pipeline.module", min_width=23, no_wrap=True)
    table.add_column("Status")
    table.add_column("Elapsed", justify="right")
    table.add_column("Rows written", justify="right", style="pipeline.count")
    table.add_column("Review", justify="right")
    table.add_column("Parse failures", justify="right")

    for row in rows:
        status = row.get("status", "ok")
        styled = {
            "ok": "[pipeline.ok]ok[/]",
            "failed": "[pipeline.error]failed[/]",
            "skipped": "[pipeline.muted]skipped[/]",
        }.get(status, status)
        # Review items and parse failures are not errors — they are the
        # pipeline recording what it could not resolve, which is the output
        # working as intended. Shown, but not coloured as a problem.
        table.add_row(
            row["module"], styled, f"{row.get('elapsed', 0):.1f}s",
            f"{row.get('rows', 0):,}",
            f"{row.get('review', 0):,}", f"{row.get('failures', 0):,}")
    return table
