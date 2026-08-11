"""SQLite access: connection, migrations, and generic upsert/audit helpers.

Plain SQL throughout, no ORM, per the brief. Domain schemas live in numbered
files under pipeline/migrations/ (0001_core.sql is the infra layer this
module owns; 0002+ are added by m00_geography onward).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from pipeline.config import Settings, get_settings

RESTRICTED_PREFIX = "restricted_"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# A writer that has to wait for another writer should wait, not fail. The
# default 5s is not enough for this warehouse: a single m13 commit writes tens
# of thousands of budget rows, and anything queued behind it would raise
# "database is locked" part-way through a crawl that has already made the
# requests. Waiting costs time; failing costs the run.
BUSY_TIMEOUT_MS = 120_000


def get_connection(settings: Settings | None = None,
                    check_same_thread: bool = True) -> sqlite3.Connection:
    """A warehouse connection in WAL mode.

    WAL matters for two reasons, only one of which is about concurrency:

      * readers do not block the writer and the writer does not block
        readers, so a long m13 commit no longer stops everything else — under
        the default rollback journal a writer takes an exclusive lock on the
        whole file;
      * a crash mid-commit rolls back cleanly rather than leaving a hot
        journal beside the database.

    `check_same_thread=False` is for the fetch pools in the council-walking
    modules, whose worker threads read and write the HTTP cache. Pass it only
    where access is actually serialised — SQLite is safe across threads, but
    Python's cursor and transaction state is not.
    """
    settings = settings or get_settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_path, timeout=BUSY_TIMEOUT_MS / 1000,
                            check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row

    # WAL is a persistent property of the database file, so switching it is a
    # once-in-the-file's-life operation. Read the current mode first and only
    # write when it differs: changing journal_mode takes an exclusive lock and
    # returns SQLITE_BUSY *without consulting the busy handler*, so several
    # connections opening at once — which is exactly what the fetch pool
    # does — would race and some would fail outright. Reading is lock-free.
    #
    # It also cannot be set on some network filesystems. The mode is read back
    # rather than assumed, so a refusal is surfaced instead of silently
    # leaving the warehouse in a mode the caller did not ask for.
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    if mode.lower() != "wal":
        try:
            mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        except sqlite3.OperationalError:
            # Another connection is mid-switch. Re-read rather than fail: by
            # now it is very likely WAL, and if it is not, the check below
            # reports it.
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    if mode.lower() != "wal":
        import structlog

        structlog.get_logger().warning(
            "db.wal_unavailable", journal_mode=mode,
            database_path=str(settings.database_path),
            note="concurrent access will serialise on a whole-file lock")

    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def applied_migrations(conn: sqlite3.Connection) -> set[str]:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    )
    if cur.fetchone() is None:
        return set()
    return {row["filename"] for row in conn.execute("SELECT filename FROM schema_migrations")}


def apply_migrations(conn: sqlite3.Connection, migrations_dir: Path | None = None) -> list[str]:
    """Apply any .sql files in migrations_dir not yet recorded as applied,
    in filename order. Returns the list of filenames newly applied. Safe to
    call on every run — a no-op once the schema is current.
    """
    migrations_dir = migrations_dir or get_settings().migrations_dir
    already = applied_migrations(conn)
    newly_applied: list[str] = []

    for path in sorted(migrations_dir.glob("*.sql")):
        if path.name in already:
            continue
        sql = path.read_text(encoding="utf-8")
        with conn:
            conn.executescript(sql)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(filename TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT INTO schema_migrations (filename, applied_at) VALUES (?, ?)",
                (path.name, _utcnow()),
            )
        newly_applied.append(path.name)

    return newly_applied


def upsert(
    conn: sqlite3.Connection,
    table: str,
    row: dict,
    natural_key: list[str],
) -> None:
    """Insert row, or update all non-key columns on a natural-key conflict.

    table must have a UNIQUE constraint (or be the PRIMARY KEY) over exactly
    the natural_key columns — that's what makes re-runs idempotent.
    """
    columns = list(row.keys())
    placeholders = ", ".join(f":{c}" for c in columns)
    column_list = ", ".join(columns)
    update_columns = [c for c in columns if c not in natural_key]
    conflict_cols = ", ".join(natural_key)

    if update_columns:
        update_clause = ", ".join(f"{c} = excluded.{c}" for c in update_columns)
        sql = (
            f"INSERT INTO {table} ({column_list}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_cols}) DO UPDATE SET {update_clause}"
        )
    else:
        sql = (
            f"INSERT INTO {table} ({column_list}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_cols}) DO NOTHING"
        )

    conn.execute(sql, row)


def record_parse_failure(
    conn: sqlite3.Connection,
    module: str,
    field_name: str,
    raw_fragment: str,
    reason: str,
    source_url: str | None = None,
) -> None:
    """Idempotent: re-running a module must not append duplicate copies of
    the same failure (constraint 5). Uniqueness is on
    (module, source_url, field_name, raw_fragment) — see migration 0007.
    """
    conn.execute(
        "INSERT INTO parse_failures (module, source_url, field_name, raw_fragment, reason, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (module, COALESCE(source_url, ''), COALESCE(field_name, ''), COALESCE(raw_fragment, '')) "
        "DO UPDATE SET reason = excluded.reason",
        (module, source_url, field_name, raw_fragment, reason, _utcnow()),
    )


def record_review_item(
    conn: sqlite3.Connection,
    module: str,
    item_type: str,
    raw_value: str,
    context_json: str | None = None,
) -> None:
    """Idempotent: an unresolved item re-observed on a later run updates its
    context rather than being appended again, so "how many items need
    review?" stays answerable. A row already marked resolved is left alone.
    """
    conn.execute(
        "INSERT INTO review_queue (module, item_type, raw_value, context_json, status, created_at) "
        "VALUES (?, ?, ?, ?, 'pending', ?) "
        "ON CONFLICT (module, item_type, raw_value) DO UPDATE SET "
        "context_json = excluded.context_json "
        "WHERE review_queue.status = 'pending'",
        (module, item_type, raw_value, context_json, _utcnow()),
    )


def get_cursor(conn: sqlite3.Connection, module: str) -> str | None:
    row = conn.execute(
        "SELECT cursor_value FROM module_cursors WHERE module = ?", (module,)
    ).fetchone()
    return row["cursor_value"] if row else None


def set_cursor(conn: sqlite3.Connection, module: str, cursor_value: str) -> None:
    conn.execute(
        "INSERT INTO module_cursors (module, cursor_value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT (module) DO UPDATE SET cursor_value = excluded.cursor_value, "
        "updated_at = excluded.updated_at",
        (module, cursor_value, _utcnow()),
    )


def get_http_cache(conn: sqlite3.Connection, url: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM http_cache WHERE url = ?", (url,)).fetchone()


def set_http_cache(
    conn: sqlite3.Connection,
    url: str,
    host: str,
    etag: str | None,
    last_modified: str | None,
    payload_sha256: str | None,
) -> None:
    conn.execute(
        "INSERT INTO http_cache (url, host, etag, last_modified, payload_sha256, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (url) DO UPDATE SET etag = excluded.etag, "
        "last_modified = excluded.last_modified, payload_sha256 = excluded.payload_sha256, "
        "updated_at = excluded.updated_at",
        (url, host, etag, last_modified, payload_sha256, _utcnow()),
    )


def rows_missing_provenance(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    """Constraint 1: every row in every public (non-restricted) table must
    carry a non-null source_url and retrieved_at. Returns the offending rows
    (empty list if the table is clean). Assumes the table has those columns
    — call this only on tables that are supposed to carry provenance.
    """
    return conn.execute(
        f"SELECT * FROM {table} WHERE source_url IS NULL OR retrieved_at IS NULL"
    ).fetchall()


def restricted_tables(conn: sqlite3.Connection) -> list[str]:
    """Every restricted_ table AND view.

    Views matter as much as tables and were previously invisible here: this
    filtered on type='table', so a restricted_ view — a personal-data query
    saved under a name — would have passed assert_no_restricted_tables
    untouched. The entity graph is built from views, several of which name
    company officers, so the gap had to close before they landed.
    """
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name LIKE ?",
        (f"{RESTRICTED_PREFIX}%",),
    ).fetchall()
    return [r["name"] for r in rows]
