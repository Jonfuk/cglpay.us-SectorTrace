"""Regression coverage for the generated terminal UI entry point."""

from trogon.introspect import introspect_click_app
from trogon.trogon import Trogon
from trogon.widgets.command_tree import CommandTree
from trogon.widgets.form import CommandForm
from trogon.widgets.parameter_controls import ParameterControls
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


def test_trogon_headless_smoke_renders_nested_form() -> None:
    """Exercise the actual Textual mount path without a terminal or warehouse."""
    root = get_group(cli_module.app)

    async def autopilot(pilot) -> None:
        await pilot.pause()
        builder = pilot.app.screen
        tree = builder.query_one(CommandTree)

        def find_search(node):
            for child in node.children:
                if child.data is not None and child.data.name == "search":
                    return child
                found = find_search(child)
                if found is not None:
                    return found
            return None

        search_node = find_search(tree.root)
        assert search_node is not None
        await builder._refresh_command_form(search_node)
        await pilot.pause()
        form = builder.query_one(CommandForm)
        option_names = {
            name
            for control in form.query(ParameterControls)
            for name in (
                (control.schema.name,)
                if isinstance(control.schema.name, str)
                else control.schema.name
            )
        }
        assert "--limit" in option_names
        pilot.app.exit()

    Trogon(root, app_name="pipeline").run(
        headless=True, size=(120, 40), auto_pilot=autopilot
    )
