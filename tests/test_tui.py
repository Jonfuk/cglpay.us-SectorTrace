"""Regression coverage for the generated and operator terminal UIs."""

import asyncio

from textual.widgets import Input, Select, Static
from trogon.introspect import introspect_click_app
from trogon.widgets.command_tree import CommandTree
from trogon.widgets.form import CommandForm
from trogon.widgets.parameter_controls import ParameterControls
from typer.main import get_group
from typer.testing import CliRunner

from pipeline import cli as cli_module
from pipeline.tui import RunConfirmation, SafeTrogon, command_requires_confirmation
from pipeline.tui_containers import ContainerManagerApp
from pipeline.tui_dashboard import InformationModal, OperatorDashboard
from pipeline.tui_run_all import RunAllApp
from pipeline.tui_sync import BackupSyncApp


def test_cli_exposes_tui_command() -> None:
    result = CliRunner().invoke(cli_module.app, ["--help"])

    assert result.exit_code == 0
    assert "tui" in result.stdout


def test_tui_schema_contains_nested_commands_and_options() -> None:
    schema = introspect_click_app(get_group(cli_module.app))["root"]

    assert {"dashboard", "sync", "containers", "run-all", "graph", "documents", "nlp", "analysis", "mirror"}.issubset(
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
        builder.app.post_run_command = ["documents", "search", "--limit", "2"]
        builder.action_close_and_run()
        await pilot.pause()
        assert isinstance(pilot.app.screen, RunConfirmation)
        assert "documents search --limit 2" in pilot.app.screen.command
        pilot.app.pop_screen()
        pilot.app.exit()

    SafeTrogon(root, app_name="pipeline").run(
        headless=True, size=(120, 40), auto_pilot=autopilot
    )


def test_tui_execution_policy_defaults_to_confirmation() -> None:
    assert not command_requires_confirmation(["root", "dashboard"])
    assert not command_requires_confirmation(["root", "list-modules"])
    assert command_requires_confirmation(["root", "run"])
    assert command_requires_confirmation(["root", "documents", "search"])
    assert command_requires_confirmation([])


def test_operator_dashboard_filters_queue_and_shows_reports(settings, monkeypatch) -> None:
    """Keep the backup cockpit's read-only triage path fixture-backed."""
    from pipeline.web import queries

    calls: list[dict] = []
    overview = {
        "database": {"path": "postgresql://redacted", "tables": 3,
                     "views": 1, "migrations": 2},
        "review": {"statuses": {"pending": 1}},
        "parse_failures": {
            "total": 2,
            "groups": [{"n": 2, "module": "m06", "field_name": "salary",
                         "reason": "bad value", "first_seen": "2026-01-01T00:00:00",
                         "last_seen": "2026-01-02T00:00:00"}],
        },
        "recent_decisions": [{
            "item_id": 7, "decision": "approved", "decided_by": "reviewer",
            "decided_at": "2026-01-02T00:00:00", "raw_value": "Provider A",
            "note": "checked source",
        }],
    }
    item = {"id": 7, "module": "m06", "item_type": "pay", "raw_value": "Provider A",
            "context_json": "{}", "status": "pending", "created_at": "2026-01-01T00:00:00"}

    class FakeConnection:
        def close(self) -> None:
            pass

    def fake_review_items(conn, **kwargs):
        calls.append(kwargs)
        return {"items": [item], "total": 1, "limit": 25, "offset": 0}

    monkeypatch.setattr(queries, "readonly_connection", lambda _: FakeConnection())
    monkeypatch.setattr(queries, "overview", lambda *_: overview)
    monkeypatch.setattr(queries, "review_items", fake_review_items)

    async def exercise() -> None:
        async with OperatorDashboard(settings).run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            assert calls[-1]["search"] is None

            filter_input = pilot.app.query_one("#filter", Input)
            filter_input.value = "m06"
            pilot.app.action_refresh()
            await pilot.pause()
            assert calls[-1]["search"] == "m06"
            assert "1 matching" in str(pilot.app.query_one("#queue-title", Static).render())

            pilot.app.action_show_decisions()
            await pilot.pause()
            assert isinstance(pilot.app.screen, InformationModal)
            assert "Provider A" in str(pilot.app.screen.query_one("#information-body", Static).render())
            pilot.app.pop_screen()

            pilot.app.action_show_failures()
            await pilot.pause()
            assert isinstance(pilot.app.screen, InformationModal)
            assert "bad value" in str(pilot.app.screen.query_one("#information-body", Static).render())

    asyncio.run(exercise())


def test_backup_sync_screen_mounts_without_starting_a_transfer(settings) -> None:
    """The transfer cockpit is safe to open before its endpoints are configured."""
    async def exercise() -> None:
        async with BackupSyncApp(settings).run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            assert "DATABASE_URL:" in str(pilot.app.query_one("#endpoints", Static).render())
            assert not pilot.app.query_one("#replace").display

    asyncio.run(exercise())


def test_container_screen_mounts_without_running_docker(settings) -> None:
    """Opening the container screen does not invoke Docker until refresh is chosen."""
    async def exercise() -> None:
        async with ContainerManagerApp(refresh_on_mount=False).run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            assert pilot.app.query_one("#action", Select).value == "status"
            assert "Volume deletion" in str(
                pilot.app.query_one("#guardrails", Static).render())

    asyncio.run(exercise())


def test_run_all_screen_defaults_to_fourteen_jobs(settings) -> None:
    """The dedicated run-all form exposes its intended concurrency visibly."""
    async def exercise() -> None:
        async with RunAllApp(settings).run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            assert pilot.app.query_one("#jobs", Input).value == "14"
            assert "waves" in str(pilot.app.query_one("#plan", Static).render())

    asyncio.run(exercise())
