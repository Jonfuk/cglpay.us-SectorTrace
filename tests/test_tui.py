"""Regression coverage for the generated terminal UI entry point."""

from trogon.introspect import introspect_click_app
from typer.main import get_group
from typer.testing import CliRunner

from pipeline import cli as cli_module


def test_cli_exposes_tui_command() -> None:
    result = CliRunner().invoke(cli_module.app, ["--help"])

    assert result.exit_code == 0
    assert "tui" in result.stdout


def test_tui_schema_contains_nested_commands_and_options() -> None:
    schema = introspect_click_app(get_group(cli_module.app))["root"]

    assert {"dashboard", "graph", "documents", "nlp", "analysis", "mirror"}.issubset(
        schema.subcommands
    )
    assert "search" in schema.subcommands["documents"].subcommands

    run_options = {
        name
        for option in schema.subcommands["run"].options
        for name in option.name
    }
    search_options = {
        name
        for option in schema.subcommands["documents"].subcommands["search"].options
        for name in option.name
    }
    assert "--jobs" in run_options
    assert "--limit" in search_options
