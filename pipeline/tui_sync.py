"""Textual backup and sync cockpit for operators.

This is deliberately separate from the review dashboard. It makes the two
endpoints visible, keeps archive transfers additive, and puts a confirmation
step in front of PostgreSQL replacement. The actual bytes still move through
the verified archive and restore implementations.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Footer, Header, RichLog, Select, Static

from pipeline import archive_sync, pgsync, snapshot_sync
from pipeline.config import Settings, get_settings
from pipeline.meters import human_bytes

LOCAL_TO_S3 = "local-to-s3"
S3_TO_LOCAL = "s3-to-local"
CURRENT_TO_OTHER = "current-to-other"
OTHER_TO_CURRENT = "other-to-current"
SNAPSHOTS_TO_S3 = "snapshots-to-s3"
S3_TO_SNAPSHOTS = "s3-to-snapshots"

OPERATIONS = {
    LOCAL_TO_S3: {
        "label": "Raw archive: local → S3 (additive)",
        "description": "Upload local content-addressed objects missing from S3.",
    },
    S3_TO_LOCAL: {
        "label": "Raw archive: S3 → local (additive)",
        "description": "Download S3 objects missing from the local raw archive.",
    },
    CURRENT_TO_OTHER: {
        "label": "PostgreSQL: configured → alternate (replace target)",
        "description": "Snapshot DATABASE_URL, then restore it into DATABASE_SOURCE_URL.",
    },
    OTHER_TO_CURRENT: {
        "label": "PostgreSQL: alternate → configured (replace target)",
        "description": "Snapshot DATABASE_SOURCE_URL, then restore it into DATABASE_URL.",
    },
    SNAPSHOTS_TO_S3: {
        "label": "Warehouse backups: local → S3 (additive)",
        "description": "Upload verified .sql.gz snapshots and companions missing from S3.",
    },
    S3_TO_SNAPSHOTS: {
        "label": "Warehouse backups: S3 → local (additive)",
        "description": "Download snapshot files missing from the local backup directory.",
    },
}


def _operation_label(operation: str) -> str:
    return OPERATIONS[operation]["label"]


class SyncConfirmation(ModalScreen[bool]):
    """Make an archive transfer or warehouse replacement deliberate."""

    CSS = """
    SyncConfirmation { align: center middle; }
    #sync-confirm-dialog { width: 88; height: auto; max-height: 80%; border: round $warning; background: $surface; padding: 2; }
    #sync-confirm-text { height: auto; margin-bottom: 2; }
    #sync-confirm-actions { height: auto; align-horizontal: right; }
    #sync-confirm-actions Button { margin-left: 1; }
    """

    def __init__(self, operation: str, details: str, replace: bool) -> None:
        super().__init__()
        self.operation = operation
        self.details = details
        self.replace = replace

    def compose(self) -> ComposeResult:
        message = Text()
        message.append("Start this backup / sync?\n\n", style="bold")
        message.append(_operation_label(self.operation) + "\n", style="cyan")
        message.append(self.details + "\n\n")
        if self.operation in {CURRENT_TO_OTHER, OTHER_TO_CURRENT} and self.replace:
            message.append(
                "The target will be replaced. The existing target is backed up "
                "before restore, but this can take time and disk space.", style="yellow")
        else:
            message.append(
                "Archive transfers are additive. PostgreSQL sync refuses a "
                "populated target unless Replace target is checked.", style="dim")
        with Container(id="sync-confirm-dialog"):
            yield Static(message, id="sync-confirm-text")
            with Horizontal(id="sync-confirm-actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Start", id="confirm", variant="warning")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")


class BackupSyncApp(App[None]):
    """A focused operator screen for moving verified copies between endpoints."""

    TITLE = "SectorTrace backup and sync"
    SUB_TITLE = "Explicit transfers · verified copies · no merge semantics"

    CSS = """
    Screen { background: $surface; }
    #main { height: 1fr; padding: 0 1; }
    #status { height: auto; margin-bottom: 1; color: $text-muted; }
    #configuration { height: auto; border: round $panel; padding: 1; margin-bottom: 1; }
    #operation-panel { width: 2fr; margin-right: 1; }
    #endpoint-panel { width: 3fr; }
    .panel-title { height: auto; margin-bottom: 1; text-style: bold; }
    #operation { width: 1fr; }
    #description { height: auto; margin-top: 1; color: $text-muted; }
    #replace { margin-top: 1; }
    #actions { height: auto; margin-top: 1; }
    #actions Button { margin-right: 1; }
    #log { height: 1fr; border: round $panel; padding: 1; }
    """

    BINDINGS = [
        Binding("p", "preview", "Preview"),
        Binding("x", "execute", "Start"),
        Binding("r", "refresh_config", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self.settings = settings or get_settings()
        self._busy = False
        self._last_operation: str | None = None
        self._replace_target = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main"):
            yield Static("Ready", id="status", markup=False)
            with Horizontal(id="configuration"):
                with Vertical(id="operation-panel"):
                    yield Static("Transfer", classes="panel-title", markup=False)
                    yield Select(
                        [(meta["label"], key) for key, meta in OPERATIONS.items()],
                        value=LOCAL_TO_S3, id="operation", allow_blank=False)
                    yield Static(OPERATIONS[LOCAL_TO_S3]["description"], id="description",
                                 markup=False)
                    yield Checkbox("Replace target PostgreSQL warehouse", id="replace")
                with Vertical(id="endpoint-panel"):
                    yield Static("Configured endpoints", classes="panel-title", markup=False)
                    yield Static("", id="endpoints", markup=False)
                    with Horizontal(id="actions"):
                        yield Button("Preview", id="preview")
                        yield Button("Start transfer", id="execute", variant="warning")
                        yield Button("Refresh config", id="refresh")
            yield RichLog(id="log", highlight=False, markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self._update_selection()
        self._write_configuration()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "operation" and event.value != Select.BLANK:
            self._update_selection()

    def _selected_operation(self) -> str:
        value = self.query_one("#operation", Select).value
        if value == Select.BLANK:
            return LOCAL_TO_S3
        return str(value)

    def _update_selection(self) -> None:
        operation = self._selected_operation()
        self.query_one("#description", Static).update(OPERATIONS[operation]["description"])
        self.query_one("#replace", Checkbox).display = operation in {
            CURRENT_TO_OTHER, OTHER_TO_CURRENT}

    def _write_configuration(self) -> None:
        archive = (f"S3 bucket: s3://{self.settings.archive_s3_bucket}/"
                   if self.settings.archive_s3_bucket else "S3 bucket: not configured")
        backups = (f"Backup S3: s3://{self.settings.backup_s3_bucket}/"
                   f"{self.settings.backup_s3_prefix.strip('/')}/"
                   if self.settings.backup_s3_bucket else "Backup S3: not configured")
        local_archive = f"Local raw archive: {self.settings.raw_archive_dir}"
        local_backups = f"Local backups: {self.settings.backup_dir}"
        configured = self.settings.redacted_database_url or "not configured"
        alternate = self.settings.redacted_database_source_url or "not configured"
        self.query_one("#endpoints", Static).update(
            f"{local_archive}\n{archive}\n{local_backups}\n{backups}\n\n"
            f"DATABASE_URL: {configured}\n"
            f"DATABASE_SOURCE_URL: {alternate}")

    def action_refresh_config(self) -> None:
        self._write_configuration()
        self._set_status("Configuration refreshed.", "green")

    def action_preview(self) -> None:
        self._start("preview")

    def action_execute(self) -> None:
        if self._busy:
            return
        operation = self._selected_operation()
        replace = self.query_one("#replace", Checkbox).value
        details = self._operation_details(operation)
        self.push_screen(SyncConfirmation(operation, details, replace), self._confirmed)

    def _confirmed(self, confirmed: bool | None) -> None:
        if confirmed:
            self._start("execute")

    def _operation_details(self, operation: str) -> str:
        if operation == LOCAL_TO_S3:
            return f"Source: {self.settings.raw_archive_dir}\nTarget: configured S3 archive"
        if operation == S3_TO_LOCAL:
            return f"Source: configured S3 archive\nTarget: {self.settings.raw_archive_dir}"
        if operation == SNAPSHOTS_TO_S3:
            return f"Source: {self.settings.backup_dir}\nTarget: configured backup S3 prefix"
        if operation == S3_TO_SNAPSHOTS:
            return f"Source: configured backup S3 prefix\nTarget: {self.settings.backup_dir}"
        source, target = self._postgres_urls(operation)
        return f"Source: {self.settings._redact(source) or 'not configured'}\nTarget: {self.settings._redact(target) or 'not configured'}"

    def _postgres_urls(self, operation: str) -> tuple[str | None, str | None]:
        if operation == CURRENT_TO_OTHER:
            return self.settings.database_url, self.settings.database_source_url
        return self.settings.database_source_url, self.settings.database_url

    def _start(self, mode: str) -> None:
        if self._busy:
            return
        self._busy = True
        self._last_operation = self._selected_operation()
        self._replace_target = self.query_one("#replace", Checkbox).value
        self.query_one("#preview", Button).disabled = True
        self.query_one("#execute", Button).disabled = True
        self.query_one("#refresh", Button).disabled = True
        self._set_status("Working…", "cyan")
        self._log(f"{mode.title()}: {_operation_label(self._last_operation)}")
        self.run_worker(lambda: self._worker(mode, self._last_operation, self._replace_target),
                        name="backup-sync", group="backup-sync", exclusive=True, thread=True)

    def _worker(self, mode: str, operation: str, replace: bool) -> None:
        try:
            if operation == LOCAL_TO_S3:
                result = (archive_sync.plan_local_to_s3(self.settings)
                          if mode == "preview" else archive_sync.local_to_s3(
                              self.settings, on_progress=self._archive_progress))
                summary = (f"{result['objects']:,} object(s), "
                           f"{human_bytes(result['bytes'])} to transfer")
            elif operation == S3_TO_LOCAL:
                result = (archive_sync.plan_s3_to_local(self.settings)
                          if mode == "preview" else archive_sync.s3_to_local(
                              self.settings, on_progress=self._archive_progress))
                summary = (f"{result['objects']:,} object(s), "
                           f"{human_bytes(result['bytes'])} to transfer")
            elif operation == SNAPSHOTS_TO_S3:
                result = (snapshot_sync.plan_local_to_s3(self.settings)
                          if mode == "preview" else snapshot_sync.local_to_s3(
                              self.settings, on_progress=self._archive_progress))
                summary = (f"{result['objects']:,} backup file(s), "
                           f"{human_bytes(result['bytes'])} to transfer")
            elif operation == S3_TO_SNAPSHOTS:
                result = (snapshot_sync.plan_s3_to_local(self.settings)
                          if mode == "preview" else snapshot_sync.s3_to_local(
                              self.settings, on_progress=self._archive_progress))
                summary = (f"{result['objects']:,} backup file(s), "
                           f"{human_bytes(result['bytes'])} to transfer")
            else:
                source, target = self._postgres_urls(operation)
                if mode == "preview":
                    result = pgsync.preflight(source, target)
                    summary = ("Preflight passed: " if result["ok"] else "Preflight failed: ") + \
                        ("schema and endpoints are compatible" if result["ok"]
                         else "; ".join(result["problems"]))
                else:
                    result = pgsync.transfer(
                        self.settings, source_url=source, target_url=target,
                        replace=replace,
                        on_step=lambda message: self._call_from_thread_log(message))
                    summary = (f"{result['rows']:,} rows in {result['tables']:,} tables "
                               "transferred and verified")
            self.call_from_thread(self._finished, True, summary)
        except Exception as exc:  # noqa: BLE001 - report operational failure in the screen
            self.call_from_thread(self._finished, False, str(exc))

    def _archive_progress(self, completed: int, total: int) -> None:
        self._call_from_thread_log(f"transferred {completed:,}/{total:,} archive objects")

    def _call_from_thread_log(self, message: str) -> None:
        self.call_from_thread(self._log, message)

    def _finished(self, ok: bool, message: str) -> None:
        self._busy = False
        self.query_one("#preview", Button).disabled = False
        self.query_one("#execute", Button).disabled = False
        self.query_one("#refresh", Button).disabled = False
        self._set_status(message, "green" if ok else "red")
        self._log(("Done: " if ok else "Failed: ") + message)

    def _set_status(self, message: str, style: str) -> None:
        self.query_one("#status", Static).update(Text(message, style=style))

    def _log(self, message: str) -> None:
        self.query_one("#log", RichLog).write(Text(message))


def run(settings: Settings | None = None) -> None:
    """Launch the backup/sync screen."""
    BackupSyncApp(settings).run()
