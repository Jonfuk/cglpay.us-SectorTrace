"""Regression coverage for the generated terminal UI entry point."""

from typer.testing import CliRunner

from pipeline import cli as cli_module


def test_cli_exposes_tui_command() -> None:
    result = CliRunner().invoke(cli_module.app, ["--help"])

    assert result.exit_code == 0
    assert "tui" in result.stdout
