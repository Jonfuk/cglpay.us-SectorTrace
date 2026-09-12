"""Textual Docker Compose management screen for local operators."""
from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, RichLog, Select, Static

from pipeline import docker_control


class ContainerConfirmation(ModalScreen[bool]):
    """Make stack lifecycle changes deliberate."""

    CSS = """
    ContainerConfirmation { align: center middle; }
    #container-confirm-dialog { width: 84; height: auto; max-height: 80%; border: round $warning; background: $surface; padding: 2; }
    #container-confirm-text { height: auto; margin-bottom: 2; }
    #container-confirm-actions { height: auto; align-horizontal: right; }
    #container-confirm-actions Button { margin-left: 1; }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        body = Text()
        body.append("Apply this Docker operation?\n\n", style="bold")
        body.append(self.message + "\n\n", style="cyan")
        body.append(
            "This changes running containers but does not remove volumes. "
            "The existing Compose file and Docker safety rules still apply.",
            style="yellow",
        )
        with Container(id="container-confirm-dialog"):
            yield Static(body, id="container-confirm-text")
            with Horizontal(id="container-confirm-actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Apply", id="confirm", variant="warning")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")


class ContainerManagerApp(App[None]):
    """Inspect and operate the concrete Compose stacks in this checkout."""

    TITLE = "SectorTrace containers"
    SUB_TITLE = "Docker Compose · no volume deletion"

    CSS = """
    Screen { background: $surface; }
    #main { height: 1fr; padding: 0 1; }
    #status { height: auto; margin-bottom: 1; }
    #configuration { height: auto; border: round $panel; padding: 1; }
    #form { width: 3fr; margin-right: 1; }
    #information { width: 2fr; }
    .panel-title { height: auto; margin-bottom: 1; text-style: bold; }
    #compose-file, #service, #tail { margin-bottom: 1; }
    #actions { height: auto; margin-top: 1; }
    #actions Button { margin-right: 1; }
    #log { height: 1fr; border: round $panel; padding: 1; margin-top: 1; }
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("x", "execute", "Apply"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, *, refresh_on_mount: bool = True) -> None:
        super().__init__()
        self.refresh_on_mount = refresh_on_mount
        self._busy = False
        self._pending: tuple[str, Path, str | None, int] | None = None

    def compose(self) -> ComposeResult:
        files = docker_control.default_compose_files()
        default = str(files[0].relative_to(docker_control.REPO_ROOT)) if files else ""
        yield Header()
        with Vertical(id="main"):
            yield Static("Ready", id="status", markup=False)
            with Horizontal(id="configuration"):
                with Vertical(id="form"):
                    yield Static("Compose operation", classes="panel-title", markup=False)
                    yield Input(value=default, placeholder="Path to docker-compose.yml",
                                id="compose-file")
                    yield Input(placeholder="Service (blank = entire stack)", id="service")
                    yield Select(
                        [(label, action) for action, label in docker_control.ACTION_LABELS.items()],
                        value="status", id="action", allow_blank=False)
                    yield Input(value="80", placeholder="Log lines", id="tail")
                    with Horizontal(id="actions"):
                        yield Button("Refresh status", id="refresh")
                        yield Button("Apply operation", id="execute", variant="warning")
                with Vertical(id="information"):
                    yield Static("Operator guardrails", classes="panel-title", markup=False)
                    yield Static(
                        "Status and logs are read-only. Start, stop, and restart require "
                        "confirmation. Volume deletion and `down -v` are not offered.",
                        id="guardrails",
                        markup=False)
            yield RichLog(id="log", highlight=False, markup=False)
        yield Footer()

    def on_mount(self) -> None:
        if self.refresh_on_mount:
            self.action_refresh()

    def action_refresh(self) -> None:
        self._start("status", confirmed=True)

    def action_execute(self) -> None:
        if self._busy:
            return
        action = self._selected_action()
        if action in docker_control.READ_ONLY_ACTIONS:
            self._start(action, confirmed=True)
            return
        pending = self._read_request(action)
        if pending is None:
            return
        self._pending = pending
        action_name, compose_file, service, tail = pending
        service_text = service or "entire stack"
        self.push_screen(
            ContainerConfirmation(
                f"{docker_control.ACTION_LABELS[action_name]}\n"
                f"Compose: {compose_file}\nService: {service_text}"),
            self._confirmed,
        )

    def _confirmed(self, confirmed: bool | None) -> None:
        pending = self._pending
        self._pending = None
        if confirmed and pending is not None:
            self._start(*pending, confirmed=True)

    def _selected_action(self) -> str:
        value = self.query_one("#action", Select).value
        return "status" if value == Select.BLANK else str(value)

    def _read_request(self, action: str) -> tuple[str, Path, str | None, int] | None:
        compose_text = self.query_one("#compose-file", Input).value.strip()
        if not compose_text:
            self._show_error("Enter a Compose file path first.")
            return None
        service = self.query_one("#service", Input).value.strip() or None
        try:
            tail = int(self.query_one("#tail", Input).value.strip() or "80")
            if tail < 1:
                raise ValueError
        except ValueError:
            self._show_error("Log lines must be a positive integer.")
            return None
        return action, Path(compose_text), service, tail

    def _start(self, action: str, compose_file: Path | None = None,
               service: str | None = None, tail: int = 80, *, confirmed: bool = False) -> None:
        if self._busy:
            return
        if compose_file is None:
            request = self._read_request(action)
            if request is None:
                return
            _, compose_file, service, tail = request
        self._busy = True
        self.query_one("#refresh", Button).disabled = True
        self.query_one("#execute", Button).disabled = True
        self._set_status(f"Running Docker Compose: {docker_control.ACTION_LABELS[action]}…", "cyan")
        self.run_worker(
            lambda: self._worker(action, compose_file, service, tail),
            name="docker-compose", group="docker-compose", exclusive=True, thread=True)

    def _worker(self, action: str, compose_file: Path, service: str | None, tail: int) -> None:
        try:
            output = docker_control.execute(action, compose_file, service=service, tail=tail)
            self.call_from_thread(self._finished, True, output)
        except Exception as exc:  # noqa: BLE001 - surface operator-facing failures in the screen
            self.call_from_thread(self._finished, False, str(exc))

    def _finished(self, ok: bool, output: str) -> None:
        self._busy = False
        self.query_one("#refresh", Button).disabled = False
        self.query_one("#execute", Button).disabled = False
        self._set_status("Docker operation completed." if ok else "Docker operation failed.",
                         "green" if ok else "red")
        self.query_one("#log", RichLog).write(Text(output, style="white" if ok else "red"))

    def _show_error(self, message: str) -> None:
        self._set_status(message, "yellow")
        self.query_one("#log", RichLog).write(Text(message, style="yellow"))

    def _set_status(self, message: str, style: str) -> None:
        self.query_one("#status", Static).update(Text(message, style=style))


def run() -> None:
    """Launch the Docker Compose management screen."""
    ContainerManagerApp().run()
