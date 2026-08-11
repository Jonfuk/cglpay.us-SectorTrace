"""Everything the UI reads, on a connection that cannot write.

The browser is a general database viewer — it will run a table scan, a sort on
an unindexed column, and whatever SQL someone types into the query box. Two
guards make that safe to expose rather than merely convenient:

  * **`mode=ro` plus `query_only`.** The read-only URI stops writes to the
    warehouse at the driver level, and `query_only` extends that to anything
    the connection later attaches. Neither depends on inspecting the SQL, so
    neither can be talked around by a statement nobody anticipated.

  * **A deadline on every statement.** SQLite's progress handler aborts a
    query that outstays it. `la_revenue_budgets` has 237k rows and the
    Fingertips views join across two more, so an ordinary-looking sort can run
    for minutes; the alternative to a deadline is a page that hangs with no
    way to cancel and a thread stuck behind it.

Read-only is not a permission boundary between people. Anyone who can reach
this server can already open the file with `sqlite3`. It is a boundary between
*this tool* and the warehouse: a viewer that can only view cannot corrupt the
evidence base through a mis-click, and that is what it is for.
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from pipeline.config import Settings, get_settings
from pipeline.db import RESTRICTED_PREFIX

# Page sizes. The maximum is a real limit and not a formality: a page of rows
# is serialised to JSON in memory and rendered as DOM nodes, and tables here
# reach six figures.
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500

# Long enough for a sort over the largest table on a cold cache, short enough
# that a mistake is a message rather than a hang.
QUERY_TIMEOUT_SECONDS = 20.0

# How often SQLite consults the progress handler, in VM instructions. Small
# enough to notice a deadline promptly, large enough that the callback is not
# itself a cost.
_PROGRESS_INSTRUCTIONS = 10_000


class QueryError(Exception):
    """A query that could not run, with a message meant for the person who
    typed it rather than a traceback."""


def readonly_connection(settings: Settings | None = None) -> sqlite3.Connection:
    """A connection to the warehouse that cannot write to it.

    Raises QueryError rather than sqlite3.OperationalError when the database
    is missing or unreadable — those are the two states a fresh checkout is
    actually in ("you have not run anything yet"), and they deserve an answer
    rather than a stack trace.
    """
    settings = settings or get_settings()
    path = Path(settings.database_path).resolve()
    if not path.exists():
        raise QueryError(
            f"No warehouse at {path}. Run a module first — e.g. "
            "`./start.sh run m00_geography` — and the database will be created."
        )

    # SQLite's URI form wants forward slashes on every platform, and an
    # absolute Windows path (C:/...) needs the extra leading slash to sit in
    # the authority-less form the parser expects.
    as_posix = path.as_posix()
    uri = f"file:{as_posix}?mode=ro" if as_posix.startswith("/") else f"file:/{as_posix}?mode=ro"

    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    except sqlite3.OperationalError as exc:
        # The usual cause is a WAL database whose -shm file is missing and
        # cannot be created by a read-only connection: SQLite needs shared
        # memory to read a WAL, and read-only cannot make it. Any pipeline
        # command re-creates it.
        raise QueryError(
            f"Could not open {path} for reading: {exc}. If the database is in "
            "WAL mode and was left without its -shm file, run any pipeline "
            "command (e.g. `./start.sh list-modules`) to restore it."
        ) from exc

    conn.row_factory = sqlite3.Row
    # Belt and braces over mode=ro: query_only also covers databases ATTACHed
    # later, which the read-only flag on the main database does not.
    conn.execute("PRAGMA query_only = ON")
    return conn


@contextmanager
def deadline(conn: sqlite3.Connection, seconds: float = QUERY_TIMEOUT_SECONDS) -> Iterator[None]:
    """Abort statements on this connection that run longer than `seconds`."""
    expires_at = time.monotonic() + seconds

    def _abort_if_late() -> int:
        return 1 if time.monotonic() > expires_at else 0

    conn.set_progress_handler(_abort_if_late, _PROGRESS_INSTRUCTIONS)
    try:
        yield
    finally:
        conn.set_progress_handler(None, 0)


def _quote(identifier: str) -> str:
    """A SQL identifier, quoted. Table and column names are never accepted
    from the caller directly — they are matched against the live schema first
    — but they still reach an f-string, and doubling embedded quotes keeps
    that true of names this schema does not happen to contain today.
    """
    return '"' + identifier.replace('"', '""') + '"'


def is_restricted(name: str) -> bool:
    """Whether an object holds personal data, by the naming rule the whole
    pipeline uses (see pipeline/db.py and constraint 3)."""
    return name.startswith(RESTRICTED_PREFIX)


def _run(conn: sqlite3.Connection, sql: str, params: Any = ()) -> list[sqlite3.Row]:
    with deadline(conn):
        try:
            return conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc):
                raise QueryError(
                    f"Query took longer than {QUERY_TIMEOUT_SECONDS:.0f}s and was "
                    "stopped. Narrow it with a WHERE clause, or sort on an "
                    "indexed column."
                ) from exc
            raise QueryError(str(exc)) from exc
        except sqlite3.Error as exc:
            raise QueryError(str(exc)) from exc


# --- schema ------------------------------------------------------------------


def list_objects(conn: sqlite3.Connection) -> list[dict]:
    """Every table and view, with row counts for tables.

    Views are listed uncounted. `v_fingertips_la_latest` is 20k rows over a
    window function and `v_la_public_health_budget` joins three tables; making
    the sidebar wait for all of them to be counted would put seconds on the
    first paint of every page load, to show a number nobody asked for yet.
    They are counted when one is opened.
    """
    rows = _run(
        conn,
        "SELECT name, type FROM sqlite_master "
        "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' "
        "ORDER BY type, name",
    )

    objects: list[dict] = []
    for row in rows:
        entry = {
            "name": row["name"],
            "type": row["type"],
            "restricted": is_restricted(row["name"]),
            "rows": None,
        }
        if row["type"] == "table":
            entry["rows"] = _run(conn, f"SELECT COUNT(*) AS n FROM {_quote(row['name'])}")[0]["n"]
        objects.append(entry)
    return objects


def object_type(conn: sqlite3.Connection, name: str) -> str | None:
    """'table', 'view', or None if no such object. This is what validates
    every caller-supplied object name before it reaches a query."""
    rows = _run(
        conn,
        "SELECT type FROM sqlite_master "
        "WHERE name = ? AND type IN ('table', 'view')",
        (name,),
    )
    return rows[0]["type"] if rows else None


def columns_of(conn: sqlite3.Connection, name: str) -> list[dict]:
    rows = _run(conn, f"PRAGMA table_info({_quote(name)})")
    return [
        {
            "name": row["name"],
            "type": row["type"] or "",
            "notnull": bool(row["notnull"]),
            "pk": bool(row["pk"]),
        }
        for row in rows
    ]


def _has_rowid(conn: sqlite3.Connection, name: str) -> bool:
    try:
        with deadline(conn, 2.0):
            conn.execute(f"SELECT rowid FROM {_quote(name)} LIMIT 0")
        return True
    except sqlite3.Error:
        return False


def read_table(
    conn: sqlite3.Connection,
    name: str,
    *,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
    order_by: str | None = None,
    descending: bool = False,
    search: str | None = None,
) -> dict:
    """One page of a table or view, with the columns and the matching count.

    Paging without an ORDER BY is only stable if the underlying query has a
    stable order, which a view's does not have to. Tables are ordered by rowid
    by default for exactly that reason; for a view, `ordered` comes back False
    and the UI says so rather than letting page 2 quietly overlap page 1.
    """
    kind = object_type(conn, name)
    if kind is None:
        raise QueryError(f"No table or view named {name!r}.")

    limit = max(1, min(int(limit), MAX_PAGE_SIZE))
    offset = max(0, int(offset))
    columns = columns_of(conn, name)
    column_names = [c["name"] for c in columns]
    if not column_names:
        raise QueryError(f"{name} has no readable columns.")

    where, params = "", {}
    if search:
        # Every column as text, so a search box finds a number, a date or a
        # URL fragment without the person having to say which column it is
        # in. LIKE wildcards in the term are escaped: someone searching for a
        # literal `100%` means that, not "anything starting 100".
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params["q"] = f"%{escaped}%"
        clauses = " OR ".join(
            f"CAST({_quote(c)} AS TEXT) LIKE :q ESCAPE '\\'" for c in column_names
        )
        where = f" WHERE ({clauses})"

    total = _run(conn, f"SELECT COUNT(*) AS n FROM {_quote(name)}{where}", params)[0]["n"]

    order_sql, ordered = "", False
    if order_by and order_by in column_names:
        order_sql = f" ORDER BY {_quote(order_by)} {'DESC' if descending else 'ASC'}"
        ordered = True
    elif kind == "table" and _has_rowid(conn, name):
        order_sql = " ORDER BY rowid"
        ordered = True

    params = {**params, "limit": limit, "offset": offset}
    rows = _run(
        conn,
        f"SELECT * FROM {_quote(name)}{where}{order_sql} LIMIT :limit OFFSET :offset",
        params,
    )

    return {
        "name": name,
        "type": kind,
        "restricted": is_restricted(name),
        "columns": columns,
        "rows": [_row_to_json(row, column_names) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "order_by": order_by if ordered and order_by in column_names else None,
        "descending": descending,
        "ordered": ordered,
        "search": search or "",
    }


def _row_to_json(row: sqlite3.Row, column_names: list[str]) -> list[Any]:
    """A row as a list of JSON-safe values, positionally.

    Positional rather than a dict because several views repeat a column name
    across joined tables, and a dict would silently drop one of them.
    """
    values: list[Any] = []
    for index in range(len(column_names)):
        value = row[index]
        if isinstance(value, bytes):
            # BLOBs are archived payloads, not display material. Say what it
            # is rather than mangling it through a decode that may not hold.
            value = f"<{len(value)} bytes>"
        values.append(value)
    return values


def run_select(conn: sqlite3.Connection, sql: str, limit: int = MAX_PAGE_SIZE) -> dict:
    """Run one statement typed by the user and return up to `limit` rows.

    Nothing inspects the SQL for danger. The connection is read-only, which
    covers writes far more reliably than a keyword blocklist, and sqlite3
    refuses more than one statement per execute() of its own accord. What is
    checked is the size of the answer: `fetchmany` stops pulling rows at the
    limit rather than materialising a table scan's worth of results.
    """
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        raise QueryError("Nothing to run.")

    limit = max(1, min(int(limit), MAX_PAGE_SIZE))
    with deadline(conn):
        try:
            cursor = conn.execute(sql)
            rows = cursor.fetchmany(limit)
            truncated = cursor.fetchone() is not None
            column_names = [d[0] for d in cursor.description or []]
            cursor.close()
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc):
                raise QueryError(
                    f"Query took longer than {QUERY_TIMEOUT_SECONDS:.0f}s and was stopped."
                ) from exc
            raise QueryError(str(exc)) from exc
        except sqlite3.Warning as exc:
            # "You can only execute one statement at a time" arrives here.
            raise QueryError(str(exc)) from exc
        except sqlite3.Error as exc:
            raise QueryError(str(exc)) from exc

    if not column_names:
        raise QueryError(
            "That statement returned no columns. This connection is read-only, "
            "so only SELECT (and PRAGMA/EXPLAIN) can do anything here."
        )

    return {
        "columns": [{"name": name, "type": "", "notnull": False, "pk": False}
                    for name in column_names],
        "rows": [_row_to_json(row, column_names) for row in rows],
        "limit": limit,
        "truncated": truncated,
    }


# --- review queue -------------------------------------------------------------


REVIEW_STATUSES = ("pending", "approved", "rejected")


def review_facets(conn: sqlite3.Connection) -> dict:
    """The values worth filtering on, with counts, so the UI's dropdowns are
    built from what is actually in the queue rather than a hardcoded list that
    goes stale the next time a module invents an item type."""
    by_status = {row["status"]: row["n"] for row in _run(
        conn, "SELECT status, COUNT(*) AS n FROM review_queue GROUP BY status")}

    modules = _run(
        conn,
        "SELECT module, COUNT(*) AS total, "
        "SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending "
        "FROM review_queue GROUP BY module ORDER BY module",
    )
    item_types = _run(
        conn,
        "SELECT module, item_type, COUNT(*) AS total, "
        "SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending "
        "FROM review_queue GROUP BY module, item_type ORDER BY pending DESC, module, item_type",
    )
    return {
        "statuses": {status: by_status.get(status, 0) for status in REVIEW_STATUSES},
        "total": sum(by_status.values()),
        "modules": [dict(row) for row in modules],
        "item_types": [dict(row) for row in item_types],
    }


def review_filter_sql(
    status: str | None = "pending",
    module: str | None = None,
    item_type: str | None = None,
    search: str | None = None,
) -> tuple[str, dict]:
    """The WHERE clause behind every review-queue screen, as (clause, params).

    Extracted rather than repeated because "approve everything matching this
    filter" and "show me everything matching this filter" have to mean the
    same set of rows. Two copies of this predicate that drift apart is a bulk
    action deciding items the reviewer was never shown — the one bug in this
    whole feature that would be silent, unbounded and unrecoverable.

    Rows are aliased `q`, matching the queries that join decisions onto them.
    """
    where, params = [], {}
    if status and status != "all":
        if status not in REVIEW_STATUSES:
            raise QueryError(f"Unknown status {status!r}.")
        where.append("q.status = :status")
        params["status"] = status
    if module:
        where.append("q.module = :module")
        params["module"] = module
    if item_type:
        where.append("q.item_type = :item_type")
        params["item_type"] = item_type
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params["q"] = f"%{escaped}%"
        where.append(
            "(q.raw_value LIKE :q ESCAPE '\\' OR COALESCE(q.context_json, '') LIKE :q ESCAPE '\\')"
        )

    return (f" WHERE {' AND '.join(where)}" if where else ""), params


def review_items(
    conn: sqlite3.Connection,
    *,
    status: str | None = "pending",
    module: str | None = None,
    item_type: str | None = None,
    search: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
    oldest_first: bool = True,
) -> dict:
    """A page of the queue, each item carrying its latest decision.

    The latest decision travels with the item because a queue that shows only
    a status cannot answer the question that follows every status: on what
    grounds? Showing "rejected — Jon, 'duplicate of E06000001'" in the list is
    the difference between an audit trail and a flag.
    """
    clause, params = review_filter_sql(status, module, item_type, search)
    total = _run(conn, f"SELECT COUNT(*) AS n FROM review_queue q{clause}", params)[0]["n"]

    limit = max(1, min(int(limit), MAX_PAGE_SIZE))
    offset = max(0, int(offset))
    params = {**params, "limit": limit, "offset": offset}
    direction = "ASC" if oldest_first else "DESC"

    rows = _run(
        conn,
        "SELECT q.id, q.module, q.item_type, q.raw_value, q.context_json, q.status, "
        "       q.created_at, q.resolved_at, "
        "       d.decision AS last_decision, d.note AS last_note, "
        "       d.decided_by AS last_decided_by, d.decided_at AS last_decided_at, "
        "       (SELECT COUNT(*) FROM review_decisions x WHERE x.review_item_id = q.id) "
        "           AS decision_count "
        "FROM review_queue q "
        # The latest decision only. A correlated MAX(id) rather than a window
        # function: this runs against whatever SQLite ships with the reader's
        # Python, and the subquery is indexed by (review_item_id, decided_at).
        "LEFT JOIN review_decisions d ON d.id = ("
        "    SELECT MAX(id) FROM review_decisions e WHERE e.review_item_id = q.id)"
        f"{clause} "
        f"ORDER BY q.created_at {direction}, q.id {direction} "
        "LIMIT :limit OFFSET :offset",
        params,
    )

    return {
        "items": [dict(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "status": status or "all",
        "module": module or "",
        "item_type": item_type or "",
        "search": search or "",
    }


def review_item(conn: sqlite3.Connection, item_id: int) -> dict | None:
    """One item with its full decision history, newest first."""
    rows = _run(conn, "SELECT * FROM review_queue WHERE id = ?", (item_id,))
    if not rows:
        return None

    item = dict(rows[0])
    item["decisions"] = [
        dict(row)
        for row in _run(
            conn,
            "SELECT id, decision, status_before, note, decided_by, decided_at, context_json "
            "FROM review_decisions WHERE review_item_id = ? "
            "ORDER BY decided_at DESC, id DESC",
            (item_id,),
        )
    ]
    return item


def recent_decisions(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    return [
        dict(row)
        for row in _run(
            conn,
            "SELECT d.id, d.decision, d.note, d.decided_by, d.decided_at, "
            "       q.id AS item_id, q.module, q.item_type, q.raw_value "
            "FROM review_decisions d JOIN review_queue q ON q.id = d.review_item_id "
            "ORDER BY d.decided_at DESC, d.id DESC LIMIT ?",
            (max(1, min(int(limit), 200)),),
        )
    ]


def parse_failures(conn: sqlite3.Connection, limit: int = 200) -> list[dict]:
    """Parse failures, grouped the way they are read: by module and reason.

    Read-only and never decidable. A parse failure is a bug report about this
    pipeline's parsers, not a judgement call for a reviewer, so it appears in
    the UI beside the queue and has no buttons.
    """
    return [
        dict(row)
        for row in _run(
            conn,
            "SELECT module, reason, field_name, COUNT(*) AS n, "
            "       MIN(created_at) AS first_seen, MAX(created_at) AS last_seen "
            "FROM parse_failures GROUP BY module, reason, field_name "
            "ORDER BY n DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        )
    ]


def overview(conn: sqlite3.Connection, settings: Settings | None = None) -> dict:
    """The landing screen: what is in the queue, what has been decided, and
    what the warehouse holds."""
    settings = settings or get_settings()
    path = Path(settings.database_path)
    facets = review_facets(conn)

    tables = _run(
        conn,
        "SELECT COUNT(*) AS n FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'",
    )[0]["n"]
    views = _run(conn, "SELECT COUNT(*) AS n FROM sqlite_master WHERE type = 'view'")[0]["n"]
    migrations = _run(
        conn, "SELECT COUNT(*) AS n FROM schema_migrations")[0]["n"]
    failures = _run(conn, "SELECT COUNT(*) AS n FROM parse_failures")[0]["n"]

    return {
        "database": {
            "path": str(path),
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "tables": tables,
            "views": views,
            "migrations": migrations,
        },
        "review": facets,
        "parse_failures": {"total": failures, "groups": parse_failures(conn, limit=50)},
        "recent_decisions": recent_decisions(conn, limit=10),
    }
