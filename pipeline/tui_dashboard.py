"""Read-only Textual dashboard for the operator's first questions.

The generated Trogon screen is the complete command browser. This screen is
the complementary landing view: it makes the current review pressure,
warehouse state, and parse-failure backlog visible before someone chooses a
command. It deliberately has no decision or pipeline-run buttons; actions
continue through the existing audited CLI and web paths.
"""
from __future__ import annotations

import json
from typing import Any

import structlog
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Static

from pipeline.config import Settings, get_settings
from pipeline.web import queries

log = structlog.get_logger()

_PROVENANCE_KEYS = (
    "source_url", "url", "page_url", "source_page", "notice_web_url",
    "raw_object_path", "payload_sha256", "retrieved_at", "http_status",
)


def _short(value: Any, limit: int = 80) -> str:
    text = "—" if value is None or value == "" else str(value)
    text = text.replace("\r", " ").replace("\n", " ")
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _when(value: Any) -> str:
    return _short(value, 19).replace("T", " ")


def _context(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _metric(label: str, value: Any, detail: str) -> Text:
    text = Text()
    text.append(label + "\n", style="bold")
    text.append(f"{value}\n", style="bold cyan")
    text.append(detail, style="dim")
    return text


class OperatorDashboard(App[None]):
    """A compact, read-only operator landing screen."""

    TITLE = "SectorTrace operator dashboard"
    SUB_TITLE = "Read-only warehouse view"

    CSS = """
    Screen { background: $surface; }
    #main { height: 1fr; padding: 1 2; }
    #status { height: auto; margin-bottom: 1; color: $text-muted; }
    #summary { height: auto; margin-bottom: 1; }
    .metric { width: 1fr; min-height: 4; border: round $primary; padding: 1; margin-right: 1; }
    .metric.last { margin-right: 0; }
    #content { height: 1fr; }
    .panel { height: 1fr; border: round $panel; padding: 1; }
    #queue-panel { width: 3fr; margin-right: 1; }
    #detail-panel { width: 2fr; }
    .panel-title { height: auto; margin-bottom: 1; text-style: bold; }
    #queue { height: 1fr; }
    #details { height: 1fr; overflow-y: auto; }
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self.settings = settings or get_settings()
        self._items: dict[str, dict[str, Any]] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main"):
            yield Static("Loading warehouse…", id="status", markup=False)
            with Horizontal(id="summary"):
                yield Static("", id="pending", classes="metric", markup=False)
                yield Static("", id="failures", classes="metric", markup=False)
                yield Static("", id="warehouse", classes="metric last", markup=False)
            with Horizontal(id="content"):
                with Vertical(id="queue-panel", classes="panel"):
                    yield Static("Pending review items", classes="panel-title", markup=False)
                    yield DataTable(id="queue", cursor_type="row")
                with Vertical(id="detail-panel", classes="panel"):
                    yield Static("Selected item", classes="panel-title", markup=False)
                    yield Static(
                        "Select a row to inspect its stored context and provenance.",
                        id="details", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#queue", DataTable)
        table.add_columns("ID", "Module", "Type", "Value", "Created")
        self.action_refresh()

    def action_refresh(self) -> None:
        self.query_one("#status", Static).update("Reading the PostgreSQL warehouse…")
        try:
            conn = queries.readonly_connection(self.settings)
            try:
                overview = queries.overview(conn, self.settings)
                review = queries.review_items(conn, status="pending", limit=25,
                                              oldest_first=True)
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001 - the screen must explain an unavailable warehouse
            log.warning("tui.dashboard_unavailable", error=str(exc))
            self._show_error(exc)
            return

        self._show_snapshot(overview, review)

    def _show_snapshot(self, overview: dict, review: dict) -> None:
        facets = overview["review"]
        pending = facets["statuses"].get("pending", 0)
        failures = overview["parse_failures"]["total"]
        database = overview["database"]

        self.query_one("#pending", Static).update(
            _metric("Pending review", f"{pending:,}",
                    "oldest-first worklist"))
        self.query_one("#failures", Static).update(
            _metric("Parse failures", f"{failures:,}",
                    "grouped below the queue in the CLI"))
        self.query_one("#warehouse", Static).update(
            _metric("Warehouse", f"{database['tables']:,} tables",
                    f"{database['views']:,} views · {database['migrations']:,} migrations"))
        self.query_one("#status", Static).update(
            Text(f"Connected to {database['path']} · refreshed now", style="dim"))

        table = self.query_one("#queue", DataTable)
        table.clear()
        self._items = {str(item["id"]): item for item in review["items"]}
        for item in review["items"]:
            table.add_row(
                Text(str(item["id"])),
                Text(_short(item["module"], 22)),
                Text(_short(item["item_type"], 28)),
                Text(_short(item["raw_value"], 54)),
                Text(_when(item["created_at"])),
                key=str(item["id"]),
            )
        if not review["items"]:
            self.query_one("#details", Static).update(
                Text("The pending review queue is empty.", style="green"))
        else:
            self.query_one("#details", Static).update(
                Text("Select a row to inspect its stored context and provenance.",
                     style="dim"))

    def _show_error(self, exc: Exception) -> None:
        message = Text()
        message.append("Warehouse unavailable\n", style="bold red")
        message.append(str(exc), style="red")
        message.append("\n\nCheck DATABASE_URL / DATABASE_RO_URL and migrations.",
                       style="dim")
        self.query_one("#status", Static).update(Text("Refresh failed", style="red"))
        self.query_one("#details", Static).update(message)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        item = self._items.get(str(event.row_key.value))
        if item is not None:
            self.query_one("#details", Static).update(self._item_text(item))

    @staticmethod
    def _item_text(item: dict[str, Any]) -> Text:
        text = Text()
        text.append(f"Review item #{item['id']}\n", style="bold cyan")
        text.append(f"{item['module']} · {item['item_type']}\n", style="bold")
        text.append(f"Status: {item['status']}\n", style="dim")
        text.append(f"\n{item['raw_value'] or '—'}\n", style="white")

        context = _context(item.get("context_json"))
        provenance = [(key, context[key]) for key in _PROVENANCE_KEYS if context.get(key)]
        if provenance:
            text.append("\nStored provenance\n", style="bold")
            for key, value in provenance:
                text.append(f"{key}: ", style="dim")
                text.append(str(value) + "\n")
        if item.get("last_decision"):
            text.append("\nLatest decision\n", style="bold")
            text.append(f"{item['last_decision']} by {item.get('last_decided_by') or '—'}\n")
            if item.get("last_note"):
                text.append(str(item["last_note"]) + "\n", style="dim")
        text.append("\nRead-only: decisions are made through the audited review workflow.",
                     style="yellow")
        return text


def run(settings: Settings | None = None) -> None:
    """Launch the dashboard without importing Textual during CLI discovery."""
    OperatorDashboard(settings).run()
