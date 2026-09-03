"""The PostgreSQL backend used by the application.

`pipeline/db.py` stays the single database module and dispatches to this one.
Nothing outside `db.py` should import from here — call sites use psycopg's
native `%s` and `%(name)s` parameter styles directly.

**Read connections run in autocommit.** In PostgreSQL a failed statement
aborts the whole transaction, so every later statement on that connection
raises `InFailedSqlTransaction` until someone rolls back. SQLite does not do
this, and the read path relies on it: `web/health.py:freshness` catches an
error per table and carries on to the next one, and under a transaction the
first failure would truncate the panel silently rather than skip one table.
Autocommit makes each read its own transaction, which is what that loop
already assumes. Write connections keep real transactions — the per-unit
commit discipline depends on them.

**Read connections come from a pool; write connections do not.** Phase 1 left
pooling out on the grounds that it changes when connections are handed out and
when their transactions end, and that this repository's history says
concurrency changes do not travel with anything else. Phase 4 measured what
that cost: opening a reader to the LAN server is **68ms**, which is more than
most of the queries a request then runs, and the web layer opens one per HTTP
request. See `read_pool` for the shape and `Phase 4` in
docs/benchmarks/README.md for the numbers.

Writers stay unpooled, and that is not an omission. A module holds its
connection for the whole of its run — m13 for several minutes — so a pool of
eight would be eight modules deep and the ninth would wait for a crawl to
finish. The web layer's own writes are a person clicking Approve: they pay the
connection each time, which is 49ms nobody is measuring against a click.
"""
from __future__ import annotations

import atexit
import re
import threading
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg
from psycopg.rows import dict_row

# Statements that do not write, for the `total_changes` accounting in `_count`
# below. This lived in `pipeline/db.py` beside the SQLite write slot, which
# used the same read/write test to decide whether to take the slot. The slot is
# gone with SQLite; the change count is not — `runner.py` reports it per module
# and `--dry-run` depends on it — so the test moved here, its only remaining
# caller. Anything unrecognised is treated as a write: over-counting a read is
# a wrong number, under-counting a write is a dry run that looks like it did
# nothing, and only one of those hides a real change.
_READ_PREFIXES = ("select", "pragma", "explain", "analyze", "analyse")
_WRITE_IN_STATEMENT = re.compile(r"\b(insert|update|delete|replace)\b", re.IGNORECASE)


def _is_write(sql: str) -> bool:
    head = sql.lstrip()[:16].lower()
    if head.startswith("with"):
        # A CTE can end in either. `WITH x AS (...) SELECT` is a read;
        # `WITH x AS (...) INSERT` is not.
        return bool(_WRITE_IN_STATEMENT.search(sql))
    return not head.startswith(_READ_PREFIXES)

# How long a statement may run before the server cancels it. Only applied to
# read connections, where it replaces SQLite's progress-handler deadline in
# web/queries.py. Writers are not given one: a module committing 237,831
# budget rows is slow on purpose, and the cost of cancelling it part-way is a
# crawl that already made every one of its requests.
READ_STATEMENT_TIMEOUT_MS = 20_000


class PostgresConnection:
    """A small application connection facade over psycopg.

    Deliberately a wrapper and not a subclass: psycopg's `Connection` is not
    designed to be subclassed for this, and the wrapper is where the write
    counter and application lifecycle semantics live.
    """

    def __init__(self, conn: psycopg.Connection, *, readonly: bool = False,
                  pool: Any = None) -> None:
        self._conn = conn
        self._readonly = readonly
        # Set when this connection was borrowed rather than opened: `close()`
        # then returns it instead of dropping it. See `connect_pooled`.
        self._pool = pool
        self._total_changes = 0
        self._trace_callback = None
        # Set by runner.py so a stuck writer can be named. Under SQLite it
        # also labelled the write-slot holder; there is no slot here, but it
        # is still what `application_name` reports to `pg_stat_activity`, so
        # an operator looking at the server sees which module is writing.
        self.write_label: str | None = None
        # Retained as a harmless compatibility attribute for callers that set
        # it while constructing a connection. Result rows are always created
        # by psycopg's named `dict_row` factory at connect time.
        self.row_factory = dict_row

    # --- statement execution -------------------------------------------------

    def _live(self) -> psycopg.Connection:
        """The underlying connection, or a message rather than an
        `AttributeError` if this one has already been closed or returned."""
        if self._conn is None:
            raise psycopg.ProgrammingError(
                "this connection has been closed; a pooled one has been "
                "returned to the pool and belongs to whoever borrows it next")
        return self._conn

    def execute(self, sql: str, parameters: Sequence[Any] | Mapping[str, Any] = ()):
        cursor = self._live().execute(sql, parameters or None)
        if self._trace_callback is not None:
            self._trace_callback(sql)
        self._count(sql, cursor)
        return cursor

    def set_trace_callback(self, callback) -> None:
        """Record statements executed through this compatibility wrapper.

        The catalog performance tests use this to assert round-trip counts.
        Keeping it at the wrapper boundary makes the assertion independent of
        psycopg cursor details.
        """
        self._trace_callback = callback

    def executemany(self, sql: str, seq_of_parameters):
        rows = list(seq_of_parameters)
        if not rows:
            return self._conn.cursor()
        cursor = self._conn.cursor()
        cursor.executemany(sql, rows)
        self._count(sql, cursor)
        return cursor

    def executescript(self, sql_script: str):
        """Run a multi-statement script, as the migration runner does.

        psycopg sends a parameterless statement over the simple query
        protocol, which is the one that permits several statements in a single
        message — see `_cursor_base.py`, where its own comment says so. That
        also means the whole script is one implicit transaction on the server
        and no statement in it can be individually recovered from, which
        matches `executescript`'s contract closely enough for the migration
        runner, the only caller.
        """
        cursor = self._conn.execute(sql_script)
        self._total_changes += max(cursor.rowcount, 0)
        return cursor

    def cursor(self):
        return self._conn.cursor()

    def _count(self, sql: str, cursor) -> None:
        """Maintain the write count used by runner diagnostics.

        `runner.py` reports it per module and `--dry-run` accounting depends
        on it. psycopg reports `rowcount` for SELECT as well, so only
        statements that write are counted — see `_is_write` above.
        """
        if _is_write(sql) and cursor.rowcount and cursor.rowcount > 0:
            self._total_changes += cursor.rowcount

    @property
    def total_changes(self) -> int:
        return self._total_changes

    # --- transactions --------------------------------------------------------

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        """Close, or give back — and either way, only once.

        Idempotent because closing twice is legal and harmless. Returning a
        pooled connection
        twice is not: the second `putconn` puts a connection into the pool
        that another request is already using, and the failure surfaces later
        as two requests interleaving statements on one connection.
        """
        conn, pool, self._conn, self._pool = self._conn, self._pool, None, None
        if conn is None:
            return
        if pool is not None:
            pool.putconn(conn)
        else:
            conn.close()

    def __enter__(self) -> PostgresConnection:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        # Commit on a clean exit, roll back on an exception, and never swallow
        # it. psycopg's own `with` block closes the connection as well, which
        # is not what any caller here expects.
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False

    # --- passthrough ---------------------------------------------------------

    @property
    def autocommit(self) -> bool:
        return self._conn.autocommit

    @property
    def readonly(self) -> bool:
        return self._readonly

    @property
    def raw(self) -> psycopg.Connection:
        """The psycopg connection, for the few places that need a real one —
        `COPY`, and the backup tooling."""
        return self._conn


def with_schema(url: str, schema: str) -> str:
    """The same URL, with every connection made from it landing in `schema`.

    Carried in the URL as a libpq `options` parameter rather than issued as a
    `SET search_path` on one connection, and that difference is the whole
    point: the council-walking modules open their own connections in
    fetch-pool threads (`pipeline/parallel.py`), and the backup and export
    paths open their own too. A setting on the connection this function's
    caller happens to hold would leave all of those writing somewhere else.

    What it is for: giving a test run a warehouse of its own on a server where
    creating a database is not available — `sectortrace_app` has no CREATEDB,
    and a suite that writes has to write somewhere that is not the warehouse.
    Nothing in the pipeline itself calls this.

    No space after `-c`. `urlencode` renders one as `+`, and libpq then reads
    the parameter as `+search_path` and refuses the connection outright —
    which at least fails loudly, unlike most ways of getting this wrong.
    """
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query["options"] = f"-csearch_path={schema}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                        urlencode(query), parts.fragment))


def connect(url: str, *, readonly: bool = False,
            application_name: str = "sectortrace",
            statement_timeout_ms: int | None = None) -> PostgresConnection:
    """A warehouse connection.

    `readonly` gives autocommit plus a read-only transaction default — see the
    module docstring for why autocommit is the read path's semantics and not
    an optimisation. It is a second line of defence rather than the first: the
    enforcement that matters is the `sectortrace_reader` role, which cannot
    write whatever the connection asks for.
    """
    conn = psycopg.connect(
        url,
        autocommit=readonly,
        row_factory=dict_row,
        application_name=application_name,
    )
    try:
        if readonly:
            conn.execute("SET default_transaction_read_only = on")
            timeout = (READ_STATEMENT_TIMEOUT_MS if statement_timeout_ms is None
                        else statement_timeout_ms)
            conn.execute(f"SET statement_timeout = {int(timeout)}")
        elif statement_timeout_ms is not None:
            conn.execute(f"SET statement_timeout = {int(statement_timeout_ms)}")
            conn.commit()
    except Exception:
        conn.close()
        raise
    return PostgresConnection(conn, readonly=readonly)


@contextmanager
def repeatable_read(connection: PostgresConnection):
    """Hold one repeatable-read, read-only snapshot for a sequence of reads.

    The mirror copies many tables over several minutes. Autocommit reads can
    therefore observe different committed versions of the source while the
    copy is in progress, making a correct copy fail its later verification.
    psycopg's transaction context starts one transaction on the normally
    autocommit source connection and commits or rolls it back on exit.
    """
    raw = connection.raw
    with raw.transaction():
        raw.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        raw.execute("SET TRANSACTION READ ONLY")
        yield connection


# --- the read pool -------------------------------------------------------------
#
# Sizes. `max_size` is 8 because that is the width of a fetch wave
# (`parallel.DEFAULT_MAX_WORKERS`) and the number of browser tabs an operator
# plausibly has open; `min_size` is 1 so an idle server holds one connection
# rather than eight. Beyond `max_size` a request waits for a connection
# instead of opening a ninth, which is the behaviour worth having: the
# unbounded alternative is what the server sees as a connection storm.
#
# The wait is bounded by `POOL_TIMEOUT_SECONDS`, and it is longer than the
# 20-second statement timeout on purpose — a request queueing behind two slow
# ones should wait, and a request that waits longer than any statement is
# allowed to run has hit something that is not congestion.
POOL_MIN_SIZE = 1
POOL_MAX_SIZE = 8
POOL_TIMEOUT_SECONDS = 45.0

_pools: dict[tuple, Any] = {}
_pools_lock = threading.Lock()


def read_pool(url: str, *, application_name: str, statement_timeout_ms: int):
    """The process-wide pool of read connections for `url`, made on demand.

    One pool per distinct (url, application_name, timeout), because those are
    exactly what `configure` bakes into a connection and a connection
    configured for one caller must not be handed to another.

    `check` costs a round-trip on checkout and buys the case this deployment
    actually has: the warehouse is on another machine, and a server restart or
    a dropped link leaves connections that look open and fail on use. 4ms
    against 68ms is still the trade worth taking, and the alternative is a
    page that errors once for reasons no operator can act on.
    """
    from psycopg_pool import ConnectionPool

    key = (url, application_name, statement_timeout_ms)
    with _pools_lock:
        pool = _pools.get(key)
        if pool is not None and not pool.closed:
            return pool

        def configure(conn: psycopg.Connection) -> None:
            # Once per connection, not once per request — which is the other
            # half of what the pool is for. Three round-trips became one
            # checkout.
            conn.execute("SET default_transaction_read_only = on")
            conn.execute(f"SET statement_timeout = {int(statement_timeout_ms)}")

        pool = ConnectionPool(
            url,
            min_size=POOL_MIN_SIZE,
            max_size=POOL_MAX_SIZE,
            timeout=POOL_TIMEOUT_SECONDS,
        kwargs={"autocommit": True, "row_factory": dict_row,
                     "application_name": application_name},
            configure=configure,
            check=ConnectionPool.check_connection,
            open=True,
        )
        _pools[key] = pool
        return pool


def close_pools() -> None:
    """Shut every pool down. Registered with `atexit` and called by the web
    server on shutdown.

    Without it a process that opened a pool does not exit: the pool runs
    worker threads of its own, and a CLI command that read one row would hang
    on the way out — the kind of failure that gets attributed to everything
    except the thing that caused it.
    """
    with _pools_lock:
        pools = list(_pools.values())
        _pools.clear()
    for pool in pools:
        try:
            pool.close()
        except Exception:  # noqa: BLE001 - shutdown is not a place to raise
            pass


atexit.register(close_pools)


def connect_pooled(url: str, *, application_name: str = "sectortrace",
                    statement_timeout_ms: int | None = None) -> PostgresConnection:
    """A read connection borrowed from the pool, returned by `.close()`.

    The same object the callers already had, with the same lifecycle: they
    open one per request and close it in a `finally`, and that `finally` now
    returns it rather than dropping it. Nothing above this line changes shape.
    """
    timeout = (READ_STATEMENT_TIMEOUT_MS if statement_timeout_ms is None
                else int(statement_timeout_ms))
    pool = read_pool(url, application_name=application_name,
                      statement_timeout_ms=timeout)
    conn = pool.getconn()
    return PostgresConnection(conn, readonly=True, pool=pool)
