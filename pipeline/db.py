"""SQLite access: connection, migrations, and generic upsert/audit helpers.

Plain SQL throughout, no ORM, per the brief. Domain schemas live in numbered
files under pipeline/migrations/ (0001_core.sql is the infra layer this
module owns; 0002+ are added by m00_geography onward).
"""
from __future__ import annotations

import re
import sqlite3
import threading
from collections import deque
from collections.abc import Sequence
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

# How long a module will queue for the write slot before giving up. Generous:
# the legitimate worst case is one module committing a very large batch (m13
# writes 237,831 budget rows), and the cost of waiting is time, where the cost
# of giving up is a crawl that already made every one of its requests. It is
# not None only because a deadlock should surface as an error naming the
# holder rather than as a run that never ends.
WRITE_SLOT_TIMEOUT_SECONDS = 900


class _FairWriteLock:
    """A strictly FIFO lock over the warehouse's single write slot.

    SQLite allows one writer, and its busy handler is a backoff rather than a
    queue: a blocked writer sleeps, retries, and finds the lock taken again by
    whichever thread happened to ask at the right moment. Nothing gives the
    loser a turn. Measured on this codebase, four modules committing every
    50ms starved a fifth for the whole of its timeout — no single holder held
    the lock for more than a fiftieth of a second, and the latecomer still
    failed with "database is locked".

    That is what took m13 out of wave 2 while m05, m07, m12 and m15 wrote
    around it, and it is made *more* likely by the incremental-commit
    discipline the modules now follow, because more commits mean more races to
    lose.

    Handing off in arrival order removes the failure mode rather than making
    it rarer: every waiter is served, in order, and no module can be passed
    over twice. Every module in a run is a thread in one process, so a
    process-wide lock is sufficient — this is not a cross-process guarantee
    and does not need to be one.
    """

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._waiters: deque[threading.Event] = deque()
        self._held = False
        self._owner: int | None = None
        self.holder: str | None = None

    def acquire(self, holder: str | None = None,
                 timeout: float = WRITE_SLOT_TIMEOUT_SECONDS) -> None:
        me = threading.get_ident()
        with self._guard:
            if self._held and self._owner == me:
                # Two connections writing in one thread. Each is its own
                # transaction, so this cannot be satisfied by re-entering —
                # the thread would queue behind itself and neither
                # transaction would ever commit. Better a stack trace naming
                # the thread than a run that stops with no output.
                raise sqlite3.OperationalError(
                    f"{holder or 'this thread'} cannot take the write slot: the "
                    f"same thread already holds it on another connection "
                    f"(as {self.holder!r}). Two write transactions in one "
                    "thread cannot both proceed — use one connection per "
                    "module, and make sure the first one committed.")
            if not self._held and not self._waiters:
                self._held = True
                self._owner = me
                self.holder = holder
                return
            ticket = threading.Event()
            self._waiters.append(ticket)

        if not ticket.wait(timeout):
            with self._guard:
                # Give up our place, or everyone behind it waits on a ticket
                # that will never be served.
                try:
                    self._waiters.remove(ticket)
                except ValueError:
                    # Handed the slot between the timeout and this lock; take
                    # it rather than losing it.
                    self._owner = me
                    self.holder = holder
                    return
            raise sqlite3.OperationalError(
                f"waited {timeout:.0f}s for the warehouse write slot, held by "
                f"{self.holder or 'another module'}. That is long enough to be "
                "a stuck writer rather than a busy one.")

        # Handed off directly: the releasing thread left _held set for us.
        with self._guard:
            self._owner = me
            self.holder = holder

    def release(self) -> None:
        with self._guard:
            if self._waiters:
                # Hand the slot to the next in line rather than dropping it,
                # so an arriving thread cannot barge past a waiter. _owner is
                # set by the waiter when it wakes.
                self._owner = None
                self._waiters.popleft().set()
            else:
                self._held = False
                self._owner = None
                self.holder = None


WRITE_SLOT = _FairWriteLock()

# Statements that do not need the write slot. Anything unrecognised is treated
# as a write: over-acquiring costs concurrency, under-acquiring costs the
# guarantee, and only one of those is a bug.
_READ_PREFIXES = ("select", "pragma", "explain", "analyze", "analyse")
_WRITE_IN_STATEMENT = re.compile(r"\b(insert|update|delete|replace)\b", re.IGNORECASE)


def _is_write(sql: str) -> bool:
    head = sql.lstrip()[:16].lower()
    if head.startswith("with"):
        # A CTE can end in either. `WITH x AS (...) SELECT` is a read;
        # `WITH x AS (...) INSERT` is not.
        return bool(_WRITE_IN_STATEMENT.search(sql))
    return not head.startswith(_READ_PREFIXES)


class WriteSerialisedConnection(sqlite3.Connection):
    """A connection that takes the process-wide write slot for the life of a
    write transaction.

    The slot is acquired before the first write of a transaction and released
    on commit, rollback or close, so two modules are never inside a write
    transaction at the same time and SQLite's unfair busy handler is never
    consulted. Reads are untouched: WAL readers do not block and do not need
    the slot.

    This does not shorten how long a module holds the database — a module that
    writes and then fetches still blocks everything behind it, which is what
    the per-unit commits in each module are for. It changes who waits and for
    how long into something predictable, and turns "database is locked" from
    an outcome into a queue.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._holds_write_slot = False
        self.write_label: str | None = None

    def _acquire_for(self, sql: str, assume_write: bool = False) -> None:
        if self._holds_write_slot:
            return
        if not assume_write and not _is_write(sql):
            return
        WRITE_SLOT.acquire(self.write_label or threading.current_thread().name)
        self._holds_write_slot = True

    def _release_slot(self) -> None:
        if self._holds_write_slot:
            self._holds_write_slot = False
            WRITE_SLOT.release()

    def execute(self, sql, parameters=(), /):  # type: ignore[override]
        self._acquire_for(sql)
        return super().execute(sql, parameters)

    def executemany(self, sql, parameters, /):  # type: ignore[override]
        self._acquire_for(sql)
        return super().executemany(sql, parameters)

    def executescript(self, sql_script, /):  # type: ignore[override]
        # A script commits implicitly before it runs and can contain anything.
        self._acquire_for(sql_script, assume_write=True)
        return super().executescript(sql_script)

    def commit(self):
        try:
            super().commit()
        finally:
            self._release_slot()

    def rollback(self):
        try:
            super().rollback()
        finally:
            self._release_slot()

    # `with conn:` has to go through the methods above.
    #
    # sqlite3.Connection.__exit__ is implemented in C and commits the
    # transaction directly, without calling the Python-level commit(). An
    # override of commit() alone is therefore bypassed by every `with conn:`
    # block in the codebase — apply_migrations uses one per migration file,
    # and so does every review decision — which committed the data and left
    # the write slot held for the life of the connection. The next writer in
    # that thread then queued behind a transaction that had already finished.
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False        # never swallow, matching sqlite3's own behaviour

    def close(self):
        try:
            super().close()
        finally:
            # A connection closed mid-transaction rolls back, and the slot has
            # to come back either way or the run stops.
            self._release_slot()


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
                            check_same_thread=check_same_thread,
                            factory=WriteSerialisedConnection)
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

    # `synchronous` is deliberately left at SQLite's default of FULL.
    #
    # It looks like the obvious lever: every module commits per unit of work,
    # so the pipeline does a lot of small commits, and each one under FULL is
    # an fsync. Measured on this machine, 200 commits of 10 rows take 0.189s
    # under FULL and 0.020s under NORMAL — 9.5x, or about 0.85ms a commit.
    #
    # And it does not matter. Commits happen per fetched unit — a page, a
    # council, a document — so a full collection is on the order of 10,000 of
    # them, which is about 8 seconds. That same collection makes ~6,300
    # requests at one per two seconds per host, which is three and a half
    # hours of deliberate waiting. The saving is 0.07% of a run, bought by
    # giving up the guarantee that a committed row survives the power going
    # out mid-crawl.
    #
    # Left alone on purpose, and written down so the next person measuring it
    # gets to the same place faster.
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


# The columns that carry a *person's* decision about a row — set by promotion,
# by rejection, or by a hand-run UPDATE off a verification worklist, and never
# by collection. Pass them as `preserve` from any module that re-upserts a row
# a reviewer may already have decided on; see the note on `preserve` below for
# what happens when you don't.
DECISION_COLUMNS = ("verified", "verified_at", "rejected")


def upsert(
    conn: sqlite3.Connection,
    table: str,
    row: dict,
    natural_key: list[str],
    preserve: Sequence[str] = (),
) -> None:
    """Insert row, or update all non-key columns on a natural-key conflict.

    table must have a UNIQUE constraint (or be the PRIMARY KEY) over exactly
    the natural_key columns — that's what makes re-runs idempotent.

    `preserve` names columns written when the row is new and left alone on
    conflict. It exists for one specific failure: the candidate modules
    re-upsert every link they find on every run, carrying `verified = 0`, so a
    link re-found after somebody had opened the document and promoted it had
    that decision silently reset and reappeared in the review worklist. The
    evidence row and its `evidence_promotions` record survived — only the
    candidate's flag was lost, which is the part the worklist reads. Same
    protection `record_review_item` gives a decided review item.

    Provenance columns are deliberately *not* preservable this way: a
    re-observation is a real new fetch and the row should carry its hash and
    its time, not the first run's.
    """
    columns = list(row.keys())
    placeholders = ", ".join(f":{c}" for c in columns)
    column_list = ", ".join(columns)
    protected = set(preserve)
    update_columns = [c for c in columns
                       if c not in natural_key and c not in protected]
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
