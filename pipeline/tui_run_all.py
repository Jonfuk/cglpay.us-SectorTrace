"""Textual operator screen for the complete dependency-ordered collection run."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Footer, Header, Input, RichLog, Select, Static

from pipeline import db, runner
from pipeline.config import Settings, get_settings
from pipeline.console import NULL_REPORTER
from pipeline.registry import discover_modules, resolve_run_order, resolve_run_waves


class RunAllConfirmation(ModalScreen[bool]):
    """Make a collection run and its write mode explicit."""

    CSS = """
    RunAllConfirmation { align: center middle; }
    #run-all-confirm-dialog { width: 88; height: auto; max-height: 80%; border: round $warning; background: $surface; padding: 2; }
    #run-all-confirm-text { height: auto; margin-bottom: 2; }
    #run-all-confirm-actions { height: auto; align-horizontal: right; }
    #run-all-confirm-actions Button { margin-left: 1; }
    """

    def __init__(self, details: str, dry_run: bool) -> None:
        super().__init__()
        self.details = details
        self.dry_run = dry_run

    def compose(self) -> ComposeResult:
        body = Text()
        body.append("Start the complete module run?\n\n", style="bold")
        body.append(self.details + "\n\n", style="cyan")
        if self.dry_run:
            body.append(
                "Dry run is selected: modules may fetch and parse, but database "
                "changes are rolled back.", style="green")
        else:
            body.append(
                "This run can fetch public sources and write candidates, evidence, "
                "review items, and parse failures to PostgreSQL.", style="yellow")
        with Container(id="run-all-confirm-dialog"):
            yield Static(body, id="run-all-confirm-text")
            with Horizontal(id="run-all-confirm-actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Start run", id="confirm", variant="warning")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")


class _RunAllObserver(runner.RunObserver):
    """Translate the runner's existing observer events into Textual messages."""

    def __init__(self, app: "RunAllApp") -> None:
        self.app = app

    def _log(self, message: str, style: str | None = None) -> None:
        self.app.call_from_thread(self.app._log, message, style)

    def run_starting(self, total_modules: int) -> None:
        self._log(f"Run started: {total_modules:,} modules")

    def wave_starting(self, names: list[str], width: int) -> None:
        self._log(f"Wave: {width} at a time · {', '.join(names)}", "cyan")

    @contextmanager
    def module_progress(self, name: str):
        self._log(f"Starting {name}…", "cyan")
        yield NULL_REPORTER

    def module_finished(self, row: dict) -> None:
        status = row.get("status", "unknown")
        style = "green" if status == "ok" else "red"
        self._log(
            f"{row.get('module', 'module')}: {status} · "
            f"{row.get('rows', 0):,} rows · "
            f"{row.get('review', 0):,} review · "
            f"{row.get('failures', 0):,} parse failures",
            style,
        )


class RunAllApp(App[None]):
    """Run all registered modules in dependency order, defaulting to 14 jobs."""

    TITLE = "SectorTrace run all"
    SUB_TITLE = "Dependency waves · default concurrency 14"

    CSS = """
    Screen { background: $surface; }
    #main { height: 1fr; padding: 0 1; }
    #status { height: auto; margin-bottom: 1; }
    #configuration { height: auto; border: round $panel; padding: 1; }
    #form { width: 3fr; margin-right: 1; }
    #plan-panel { width: 3fr; }
    .panel-title { height: auto; margin-bottom: 1; text-style: bold; }
    #jobs, #since, #limit, #source { margin-bottom: 1; }
    #dry-run { margin-bottom: 1; }
    #actions { height: auto; margin-top: 1; }
    #actions Button { margin-right: 1; }
    #plan { height: 1fr; overflow-y: auto; }
    #log { height: 1fr; border: round $panel; padding: 1; margin-top: 1; }
    """

    BINDINGS = [
        Binding("p", "preview", "Preview"),
        Binding("x", "execute", "Start"),
        Binding("r", "refresh_plan", "Refresh plan"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self.settings = settings or get_settings()
        self._busy = False
        self._pending: tuple[int, str | None, int | None, bool, str] | None = None
        self._order: list[str] = []
        self._waves: list[list[str]] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main"):
            yield Static("Ready", id="status", markup=False)
            with Horizontal(id="configuration"):
                with Vertical(id="form"):
                    yield Static("Run controls", classes="panel-title", markup=False)
                    yield Input(value="14", placeholder="Concurrent modules", id="jobs")
                    yield Input(placeholder="Since date (YYYY-MM-DD)", id="since")
                    yield Input(placeholder="Limit records per module (optional)", id="limit")
                    yield Select(
                        [("CSV channels (default)", "csv"), ("Live API channels", "api"),
                         ("All contract channels", "all"), ("Kaggle cross-check", "kag")],
                        value="csv", id="source", allow_blank=False)
                    yield Checkbox("Dry run (roll back database changes)", id="dry-run")
                    with Horizontal(id="actions"):
                        yield Button("Preview", id="preview")
                        yield Button("Start run", id="execute", variant="warning")
                        yield Button("Refresh plan", id="refresh")
                with Vertical(id="plan-panel"):
                    yield Static("Dependency plan", classes="panel-title", markup=False)
                    yield Static("Loading module plan…", id="plan", markup=False)
            yield RichLog(id="log", highlight=False, markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.action_refresh_plan()

    def action_refresh_plan(self) -> None:
        try:
            discover_modules()
            self._order = resolve_run_order()
            self._waves = resolve_run_waves(self._order)
        except Exception as exc:  # noqa: BLE001 - show registry failures in the screen
            self._set_status("Could not build dependency plan.", "red")
            self._log(str(exc), "red")
            return
        lines = [
            f"{len(self._order):,} modules · {len(self._waves):,} waves · "
            "each wave waits for the previous one",
            "",
        ]
        for index, wave in enumerate(self._waves, start=1):
            lines.append(f"Wave {index}: {', '.join(wave)}")
        self.query_one("#plan", Static).update("\n".join(lines))
        self._set_status(
            f"Plan ready: {len(self._order):,} modules in {len(self._waves):,} waves; "
            "default --jobs is 14.", "green")

    def action_preview(self) -> None:
        self._start("preview")

    def action_execute(self) -> None:
        if self._busy:
            return
        request = self._read_request()
        if request is None:
            return
        jobs, since, limit, dry_run, source = request
        self._pending = request
        self.push_screen(
            RunAllConfirmation(self._details(jobs, since, limit, dry_run, source), dry_run),
            self._confirmed,
        )

    def _confirmed(self, confirmed: bool | None) -> None:
        request = self._pending
        self._pending = None
        if confirmed and request is not None:
            self._start("execute", request)

    def _read_request(self) -> tuple[int, str | None, int | None, bool, str] | None:
        try:
            jobs = int(self.query_one("#jobs", Input).value.strip() or "14")
            if jobs < 1:
                raise ValueError("jobs must be positive")
        except ValueError as exc:
            self._show_error(f"Concurrent modules must be a positive integer: {exc}")
            return None
        since = self.query_one("#since", Input).value.strip() or None
        if since:
            try:
                date.fromisoformat(since)
            except ValueError:
                self._show_error("Since date must be an ISO date in YYYY-MM-DD form.")
                return None
        limit_text = self.query_one("#limit", Input).value.strip()
        try:
            limit = int(limit_text) if limit_text else None
            if limit is not None and limit < 1:
                raise ValueError
        except ValueError:
            self._show_error("Record limit must be a positive integer.")
            return None
        source_value = self.query_one("#source", Select).value
        source = "csv" if source_value == Select.BLANK else str(source_value)
        return jobs, since, limit, self.query_one("#dry-run", Checkbox).value, source

    @staticmethod
    def _details(jobs: int, since: str | None, limit: int | None,
                 dry_run: bool, source: str) -> str:
        return (
            f"Modules: all ({len(resolve_run_order()):,})\n"
            f"Concurrency: --jobs {jobs}\n"
            f"Source channel: --{source}\n"
            f"Since: {since or 'not set'}\n"
            f"Limit: {limit or 'not set'}\n"
            f"Mode: {'dry run' if dry_run else 'write run'}"
        )

    def _start(self, mode: str, request: tuple[int, str | None, int | None, bool, str] | None = None) -> None:
        if self._busy:
            return
        request = request or self._read_request()
        if request is None:
            return
        if not self._order:
            self.action_refresh_plan()
        self._busy = True
        self.query_one("#preview", Button).disabled = True
        self.query_one("#execute", Button).disabled = True
        self.query_one("#refresh", Button).disabled = True
        self._set_status("Preparing the run…", "cyan")
        self._log(
            f"{mode.title()}: run all · --jobs {request[0]} · "
            f"--{request[4]}" + (" · --dry-run" if request[3] else ""))
        self.run_worker(
            lambda: self._worker(mode, request),
            name="run-all", group="run-all", exclusive=True, thread=True)

    def _worker(self, mode: str, request: tuple[int, str | None, int | None, bool, str]) -> None:
        jobs, since, limit, dry_run, source = request
        try:
            if since:
                date.fromisoformat(since)
            if mode == "preview":
                self.call_from_thread(
                    self._finished,
                    True,
                    f"Plan preview: {len(self._order):,} modules in {len(self._waves):,} waves; "
                    f"--jobs {jobs} would use up to {jobs} concurrent modules.",
                )
                return
            conn = db.get_connection(self.settings)
            try:
                applied = db.apply_migrations(conn, db.migrations_dir_for(self.settings))
            finally:
                conn.close()
            if applied:
                self.call_from_thread(
                    self._log, f"Applied migrations: {', '.join(applied)}", "cyan")
            summary = runner.run_waves(
                self._waves, jobs, self.settings, since, dry_run, limit,
                _RunAllObserver(self), source=source, origin="admin")
            failed = sum(row.get("status") == "failed" for row in summary)
            written = sum(row.get("rows", 0) for row in summary)
            self.call_from_thread(
                self._finished,
                failed == 0,
                f"Run finished: {len(summary):,} modules, {written:,} "
                f"{'would-be ' if dry_run else ''}rows, {failed:,} failed.",
            )
        except Exception as exc:  # noqa: BLE001 - explain operator failures in the screen
            self.call_from_thread(self._finished, False, str(exc))

    def _finished(self, ok: bool, message: str) -> None:
        self._busy = False
        self.query_one("#preview", Button).disabled = False
        self.query_one("#execute", Button).disabled = False
        self.query_one("#refresh", Button).disabled = False
        self._set_status(message, "green" if ok else "red")
        self._log(("Done: " if ok else "Failed: ") + message,
                  "green" if ok else "red")

    def _show_error(self, message: str) -> None:
        self._set_status(message, "yellow")
        self._log(message, "yellow")

    def _set_status(self, message: str, style: str) -> None:
        self.query_one("#status", Static).update(Text(message, style=style))

    def _log(self, message: str, style: str | None = None) -> None:
        self.query_one("#log", RichLog).write(Text(message, style=style))


def run(settings: Settings | None = None) -> None:
    """Launch the complete-run operator screen."""
    RunAllApp(settings).run()
