"""The PostgreSQL backend: connections that answer to the same API as the
SQLite ones.

`pipeline/db.py` stays the single database module and dispatches to this one
when `DATABASE_URL` is set. Nothing outside `db.py` should import from here —
call sites keep calling `db.get_connection()` and keep writing `?`/`:name`
SQL, and the difference arrives underneath them.

Three things in here are not obvious, and each of them is a bug that was
reasoned about rather than met:

**Rows answer to both protocols.** `sqlite3.Row` supports `row["column"]` and
`row[0]` and `dict(row)`, and this codebase uses all three — 16 call sites do
`fetchone()[0]`, `web/jobs.py` builds a `Job` from `row[0], row[1], row[2]`,
and 28 places call `dict(row)`. psycopg ships `dict_row` (no positional
access) and `tuple_row` (no names), and neither is a drop-in. `Row` below is.

**Read connections run in autocommit.** In PostgreSQL a failed statement
aborts the whole transaction, so every later statement on that connection
raises `InFailedSqlTransaction` until someone rolls back. SQLite does not do
this, and the read path relies on it: `web/health.py:freshness` catches an
error per table and carries on to the next one, and under a transaction the
first failure would truncate the panel silently rather than skip one table.
Autocommit makes each read its own transaction, which is what that loop
already assumes. Write connections keep real transactions — the per-unit
commit discipline depends on them.

**Statements are translated, not rewritten.** See `pipeline/sqldialect.py`.

There is deliberately no connection pool here yet. The plan puts pooling with
the Phase 4 concurrency work, and Phase 1 is a behavioural freeze: one
connection per module thread and one per HTTP request, opened and closed in
`finally`, exactly as the SQLite path does it today. A pool changes when
connections are handed out and when their transactions end, which is a
concurrency change, and this repository's history is explicit that
concurrency changes do not travel with anything else.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import psycopg

from pipeline.sqldialect import to_psycopg

# How long a statement may run before the server cancels it. Only applied to
# read connections, where it replaces SQLite's progress-handler deadline in
# web/queries.py. Writers are not given one: a module committing 237,831
# budget rows is slow on purpose, and the cost of cancelling it part-way is a
# crawl that already made every one of its requests.
READ_STATEMENT_TIMEOUT_MS = 20_000


class Row:
    """A result row addressable by name and by position.

    Matches `sqlite3.Row` where the codebase depends on it:

      * `row["name"]` and `row[0]` both work, as does `row[1:3]`;
      * iterating yields **values**, not column names, so `tuple(row)` and
        `list(row)` are the values — this is why it does not register as a
        `Mapping`, whose iteration protocol yields keys;
      * `keys()` returns the column names, which is what makes `dict(row)`
        work;
      * a duplicated column name resolves to the leftmost column, as SQLite
        does — `SELECT a.id, b.id` is answerable by position and ambiguous by
        name on both engines, and picking the same one matters more than
        picking the right one.
    """

    __slots__ = ("_names", "_index", "_values")

    def __init__(self, names: tuple[str, ...], index: Mapping[str, int],
                 values: tuple[Any, ...]) -> None:
        self._names = names
        self._index = index
        self._values = values

    def __getitem__(self, key):
        if isinstance(key, str):
            try:
                return self._values[self._index[key]]
            except KeyError:
                raise IndexError(f"no column named {key!r}") from None
        return self._values[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def keys(self) -> list[str]:
        return list(self._names)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Row):
            return self._names == other._names and self._values == other._values
        if isinstance(other, tuple):
            return self._values == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self._names, self._values))

    def __repr__(self) -> str:
        pairs = ", ".join(f"{n}={v!r}" for n, v in zip(self._names, self._values))
        return f"Row({pairs})"


def row_factory(cursor):
    """psycopg row factory producing `Row`. Set once on the connection."""
    description = cursor.description
    if description is None:
        # A statement with no result set (DDL, or an INSERT with no
        # RETURNING). psycopg still asks for a maker; it is never called.
        return lambda values: values

    names = tuple(d.name for d in description)
    index: dict[str, int] = {}
    for position, name in enumerate(names):
        index.setdefault(name, position)

    def make(values):
        return Row(names, index, tuple(values))

    return make


class PostgresConnection:
    """A psycopg connection wearing the parts of `sqlite3.Connection` that
    this codebase calls.

    Deliberately a wrapper and not a subclass: psycopg's `Connection` is not
    designed to be subclassed for this, and the wrapper is where statement
    translation and the write counter live.
    """

    def __init__(self, conn: psycopg.Connection, *, readonly: bool = False) -> None:
        self._conn = conn
        self._readonly = readonly
        self._total_changes = 0
        # Set by runner.py so a stuck writer can be named. Under SQLite it
        # also labelled the write-slot holder; there is no slot here, but it
        # is still what `application_name` reports to `pg_stat_activity`, so
        # an operator looking at the server sees which module is writing.
        self.write_label: str | None = None
        # Assigned by call sites that were written against sqlite3
        # (`conn.row_factory = sqlite3.Row`). The factory is fixed at connect
        # time; accepting the attribute keeps those lines working rather than
        # requiring every one of them to learn which backend it is on.
        self.row_factory = None

    # --- statement execution -------------------------------------------------

    def execute(self, sql: str, parameters: Sequence[Any] | Mapping[str, Any] = ()):
        translated, params = to_psycopg(sql, parameters)
        cursor = self._conn.execute(translated, params)
        self._count(sql, cursor)
        return cursor

    def executemany(self, sql: str, seq_of_parameters):
        rows = list(seq_of_parameters)
        if not rows:
            return self._conn.cursor()
        # Every row binds the same statement, so the translation is done once
        # against the first row purely to learn the parameter style.
        translated, _ = to_psycopg(sql, rows[0])
        cursor = self._conn.cursor()
        cursor.executemany(translated, rows)
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
        """Maintain the equivalent of `sqlite3.Connection.total_changes`.

        `runner.py` reports it per module and `--dry-run` accounting depends
        on it. psycopg reports `rowcount` for SELECT as well, so only
        statements that write are counted — the same `_is_write` test the
        SQLite path uses to decide about the write slot.
        """
        from pipeline.db import _is_write

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
        self._conn.close()

    def __enter__(self) -> PostgresConnection:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        # Matching sqlite3: commit on a clean exit, roll back on an exception,
        # and never swallow it. psycopg's own `with` block closes the
        # connection as well, which is not what any caller here expects.
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
        row_factory=row_factory,
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
