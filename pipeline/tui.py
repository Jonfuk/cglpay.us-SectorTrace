"""Safety-aware Trogon launcher for the pipeline CLI.

Trogon is intentionally generic: its Close & Run binding can execute any
Click command it discovers. The pipeline has commands that write a warehouse,
rewrite an archive, or start a server with write endpoints, so the generated
form needs one small project-specific boundary before it hands control back to
the CLI.
"""
from __future__ import annotations

import shlex
from typing import Sequence

import click
import typer
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static
from trogon.trogon import CommandBuilder, Trogon

# An allowlist is safer than trying to predict every future command that may
# write. New commands therefore get a confirmation until somebody classifies
# them explicitly as a read-only inspection path.
READ_ONLY_ROOT_COMMANDS = frozenset({
    "coverage-report",
    "dashboard",
    "docs-check",
    "list-backups",
    "list-modules",
    "pg-capabilities",
})


def command_requires_confirmation(command_path: Sequence[str]) -> bool:
    """Return whether a discovered command needs an explicit run confirmation."""
    path = [str(part) for part in command_path if str(part) != "root"]
    return not path or path[0] not in READ_ONLY_ROOT_COMMANDS


class RunConfirmation(ModalScreen[bool]):
    """Make a potentially mutating command an intentional user action."""

    CSS = """
    RunConfirmation { align: center middle; }
    #run-confirm-dialog { width: 84; height: auto; max-height: 80%; border: round $warning; background: $surface; padding: 2; }
    #run-confirm-text { height: auto; margin-bottom: 2; }
    #run-confirm-actions { height: auto; align-horizontal: right; }
    #run-confirm-actions Button { margin-left: 1; }
    """

    def __init__(self, command: str) -> None:
        super().__init__()
        self.command = command

    def compose(self) -> ComposeResult:
        message = Text()
        message.append("Run this command?\n\n", style="bold")
        message.append(self.command + "\n\n", style="cyan")
        message.append(
            "This may write warehouse or archive state, or start a service. "
            "The command's normal validation and audit rules still apply.",
            style="yellow",
        )
        with Container(id="run-confirm-dialog"):
            yield Static(message, id="run-confirm-text")
            with Horizontal(id="run-confirm-actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Run command", id="confirm", variant="warning")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")


class SafeCommandBuilder(CommandBuilder):
    """Trogon's form with a confirmation boundary around command execution."""

    def action_close_and_run(self) -> None:
        command = self.app.post_run_command
        if not command:
            self.app.execute_on_exit = True
            self.app.exit()
            return

        schema = getattr(self, "selected_command_schema", None)
        command_path = [] if schema is None else [
            str(part.name) for part in schema.path_from_root
        ]
        if not command_requires_confirmation(command_path):
            self._exit_to_run()
            return

        command_text = shlex.join([self.app.app_name, *command])
        self.app.push_screen(RunConfirmation(command_text), self._run_confirmed)

    def _run_confirmed(self, confirmed: bool | None) -> None:
        if confirmed:
            self._exit_to_run()

    def _exit_to_run(self) -> None:
        self.app.execute_on_exit = True
        self.app.exit()


class SafeTrogon(Trogon):
    """Trogon with the pipeline's explicit execution confirmation screen."""

    def get_default_screen(self) -> SafeCommandBuilder:
        return SafeCommandBuilder(self.cli, self.app_name, self.command_name)


def init_tui(app: typer.Typer, name: str | None = None) -> typer.Typer:
    """Register the pipeline's safety-aware Trogon command on a Typer app."""

    def wrapped_tui() -> None:
        SafeTrogon(
            typer.main.get_group(app),
            app_name=name,
            click_context=click.get_current_context(),
        ).run()

    app.command("tui", help="Open Textual TUI.")(wrapped_tui)
    return app
