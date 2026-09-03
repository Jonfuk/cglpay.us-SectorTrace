"""Textual dashboard for the operator's first questions.

The generated Trogon screen is the complete command browser. This screen is
the complementary landing view: it makes the current review pressure,
warehouse state, and parse-failure backlog visible before someone chooses a
command. Review decisions are available here only through the existing
audited review path; pipeline runs and evidence promotion remain separate
operations.
"""
from __future__ import annotations

import json
from typing import Any

import structlog
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Static

from pipeline import db
from pipeline.config import Settings, get_settings
from pipeline.web import queries, review

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


class DecisionConfirmation(ModalScreen[bool]):
    """Require a deliberate confirmation before changing warehouse state."""

    CSS = """
    DecisionConfirmation { align: center middle; }
    #confirm-dialog { width: 72; height: auto; max-height: 80%; border: round $warning; background: $surface; padding: 2; }
    #confirm-text { height: auto; margin-bottom: 2; }
    #confirm-actions { height: auto; align-horizontal: right; }
    #confirm-actions Button { margin-left: 1; }
    """

    def __init__(self, item: dict[str, Any], decision: str, reviewer: str,
                 note: str | None) -> None:
        super().__init__()
        self.item = item
        self.decision = decision
        self.reviewer = reviewer
        self.note = note

    def compose(self) -> ComposeResult:
        label = {"approved": "Approve", "rejected": "Reject", "pending": "Reset to pending"}[self.decision]
        message = Text()
        message.append(f"{label} review item #{self.item['id']}?\n\n", style="bold")
        message.append(f"{_short(self.item['module'])} · {_short(self.item['item_type'])}\n")
        message.append(f"{_short(self.item['raw_value'], 180)}\n\n")
        message.append(f"Reviewer: {self.reviewer}\n", style="bold cyan")
        message.append(f"Decision: {self.decision}\n")
        message.append(f"Note: {_short(self.note, 180)}\n\n")
        message.append(
            "This records an auditable review decision. It does not promote "
            "evidence or edit a canonical table.", style="yellow")
        with Container(id="confirm-dialog"):
            yield Static(message, id="confirm-text")
            with Horizontal(id="confirm-actions"):
                yield Button("Cancel", id="cancel")
                yield Button(label, id="confirm", variant="warning")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")


class OperatorDashboard(App[None]):
    """A compact operator landing screen with audited review decisions."""

    TITLE = "SectorTrace operator dashboard"
    SUB_TITLE = "Warehouse view · audited review decisions"

    CSS = """
    Screen { background: $surface; }
    #main { height: 1fr; padding: 0 1; }
    #status { height: auto; margin-bottom: 1; color: $text-muted; }
    #summary { height: auto; margin-bottom: 0; }
    .metric { width: 1fr; min-height: 3; border: round $primary; padding: 1; margin-right: 1; }
    .metric.last { margin-right: 0; }
    #content { height: 1fr; }
    .panel { height: 1fr; border: round $panel; padding: 1; }
    #queue-panel { width: 3fr; margin-right: 1; }
    #detail-panel { width: 2fr; }
    .panel-title { height: auto; margin-bottom: 1; text-style: bold; }
    #queue { height: 1fr; }
    #details { height: 1fr; min-height: 1; overflow-y: auto; }
    #reviewer, #note { height: 3; margin-top: 1; }
    #decision-buttons { height: auto; margin-top: 1; }
    #decision-buttons Button { margin-right: 1; }
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self.settings = settings or get_settings()
        self._items: dict[str, dict[str, Any]] = {}
        self._selected_item_id: int | None = None
        self._pending_decision: tuple[int, str, str, str | None] | None = None

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
                    yield Input(placeholder="Reviewer name (required)", id="reviewer",
                                disabled=True)
                    yield Input(placeholder="Optional note", id="note", max_length=2000,
                                disabled=True)
                    with Horizontal(id="decision-buttons"):
                        yield Button("Approve", id="approve", variant="success", disabled=True)
                        yield Button("Reject", id="reject", variant="error", disabled=True)
                        yield Button("Reset", id="reset", variant="warning", disabled=True)
                    yield Static(
                        "Select a row to inspect its stored context and provenance.",
                        id="details", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#queue", DataTable)
        table.add_columns("ID", "Module", "Type", "Value", "Created")
        self.action_refresh()

    def action_refresh(self) -> bool:
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
            return False

        self._show_snapshot(overview, review)
        return True

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
        self._selected_item_id = None
        self._set_decision_controls(enabled=False)
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
        self._set_decision_controls(enabled=False)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        item = self._items.get(str(event.row_key.value))
        if item is not None:
            self._selected_item_id = int(item["id"])
            self._set_decision_controls(enabled=True)
            self.query_one("#details", Static).update(self._item_text(item))

    def _set_decision_controls(self, *, enabled: bool) -> None:
        self.query_one("#reviewer", Input).disabled = not enabled
        self.query_one("#note", Input).disabled = not enabled
        for button_id in ("#approve", "#reject", "#reset"):
            self.query_one(button_id, Button).disabled = not enabled

    def on_button_pressed(self, event: Button.Pressed) -> None:
        decision_by_button = {
            "approve": "approved",
            "reject": "rejected",
            "reset": "pending",
        }
        decision = decision_by_button.get(event.button.id or "")
        if decision is not None:
            self._request_decision(decision)

    def _request_decision(self, decision: str) -> None:
        if self._selected_item_id is None:
            self._set_status("Select a review item first.", "yellow")
            return

        reviewer = self.query_one("#reviewer", Input).value.strip()
        note = self.query_one("#note", Input).value.strip() or None
        if not reviewer:
            self._set_status("Enter your reviewer name before recording a decision.", "yellow")
            self.query_one("#reviewer", Input).focus()
            return
        if len(reviewer) > 200:
            self._set_status("Reviewer name is limited to 200 characters.", "yellow")
            return
        if note and len(note) > review.MAX_NOTE_LENGTH:
            self._set_status(f"Note is limited to {review.MAX_NOTE_LENGTH} characters.", "yellow")
            return

        item = self._items[str(self._selected_item_id)]
        self._pending_decision = (self._selected_item_id, decision, reviewer, note)
        self.push_screen(
            DecisionConfirmation(item, decision, reviewer, note),
            self._on_decision_confirmed,
        )

    def _on_decision_confirmed(self, confirmed: bool | None) -> None:
        pending = self._pending_decision
        self._pending_decision = None
        if confirmed and pending is not None:
            self._record_decision(*pending)

    def _record_decision(self, item_id: int, decision: str, reviewer: str,
                         note: str | None) -> None:
        self._set_status("Recording audited decision…", "cyan")
        conn = None
        try:
            conn = db.get_connection(self.settings)
            result = review.decide(conn, [item_id], decision, reviewer, note)
        except review.DecisionError as exc:
            self._set_status(str(exc), "red")
            return
        except Exception as exc:  # noqa: BLE001 - the screen must explain a failed write
            log.exception("tui.review_decision_failed", item_id=item_id,
                          decision=decision, error=str(exc))
            self._set_status("Decision failed; no change was recorded. Check the logs.", "red")
            return
        finally:
            if conn is not None:
                conn.close()

        if not self.action_refresh():
            return
        updated = result["updated"]
        unchanged = result["unchanged"]
        missing = result["missing"]
        log.info("tui.review_decision", item_id=item_id, decision=decision,
                 decided_by=reviewer, updated=updated, unchanged=unchanged,
                 missing=missing)
        if updated:
            self._set_status(f"Recorded {decision} for review item #{item_id}.", "green")
        elif unchanged:
            self._set_status(f"Review item #{item_id} was already {decision}.", "yellow")
        else:
            self._set_status(f"Review item #{item_id} no longer exists.", "yellow")

    def _set_status(self, message: str, style: str) -> None:
        self.query_one("#status", Static).update(Text(message, style=style))

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
        text.append("\nAudited review decision controls are below this panel.", style="yellow")
        return text


def run(settings: Settings | None = None) -> None:
    """Launch the dashboard without importing Textual during CLI discovery."""
    OperatorDashboard(settings).run()
