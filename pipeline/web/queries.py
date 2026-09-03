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

Read-only is not a permission boundary between people. It is a boundary between
*this tool* and the warehouse: reads go through a SELECT-only role
(DATABASE_RO_URL) so a viewer that can only view cannot corrupt the evidence
base through a mis-click, and that is what it is for.
"""
from __future__ import annotations

import json
import re
from contextlib import contextmanager
from typing import Any, Iterator

from pipeline import catalog, db
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

class QueryError(Exception):
    """A query that could not run, with a message meant for the person who
    typed it rather than a traceback."""


def readonly_connection(settings: Settings | None = None):
    """A connection to the warehouse that cannot write to it.

    Raises QueryError rather than a driver exception when the database is
    missing or unreachable — those are the states a fresh checkout and a
    stopped server are actually in ("you have not run anything yet", "the
    database is not answering"), and they deserve an answer rather than a
    stack trace.

    Read-only means something different on each backend, and on PostgreSQL it
    means something *better*:

      * SQLite — `mode=ro` on the URI plus `PRAGMA query_only`, both enforced
        by the driver rather than by inspecting the SQL, so neither can be
        talked around by a statement nobody anticipated.
      * PostgreSQL — `DATABASE_RO_URL`, a role holding `SELECT` and nothing
        else, plus `default_transaction_read_only` on the connection. The
        session setting is the belt; the role is the braces, and the role is
        the one that survives a bug in this file. A session setting is
        something this application *asks for*; a role without INSERT cannot be
        talked into one whatever the code does.

    With no `DATABASE_RO_URL` configured this falls back to `DATABASE_URL` —
    which works, and is weaker: reads then run as the role that owns the
    schema, so the only thing standing between the SQL box and a write is the
    session setting. That is a real difference from the SQLite path, not a
    tidiness point, so the fallback is logged rather than taken quietly. See
    pipeline/migrations/postgres/README.md for the role definitions.
    """
    settings = settings or get_settings()

    import structlog

    from pipeline import pg

    url = settings.database_ro_url or settings.database_url
    if not url:
        raise QueryError(
            "No DATABASE_URL configured. PostgreSQL is the only application "
            "database (performance.md Phase 1).")
    if not settings.database_ro_url:
        structlog.get_logger().warning(
            "web.readonly_without_a_reader_role",
            database=settings.redacted_database_url,
            note="reads are running as the schema owner; set DATABASE_RO_URL "
                 "to a SELECT-only role so a write is refused by the server "
                 "rather than by a session setting")
    try:
        # Borrowed, not opened: `close()` gives it back. Opening one to the LAN
        # server is 68ms, which the web layer was paying on every request —
        # more than most of the queries it then ran. See `pg.read_pool`.
        return pg.connect_pooled(
            url, application_name="sectortrace-web",
            statement_timeout_ms=int(QUERY_TIMEOUT_SECONDS * 1000))
    except db.Error as exc:
        raise QueryError(
            f"Could not reach the PostgreSQL warehouse at "
            f"{settings._redact(url)}: {exc}"
        ) from exc


@contextmanager
def deadline(conn, seconds: float = QUERY_TIMEOUT_SECONDS) -> Iterator[None]:
    """Abort statements on this connection that run longer than `seconds`.

    A no-op: the deadline is already in place and is not a context manager.
    `readonly_connection` sets `statement_timeout` on the session, so every
    statement carries it whether or not anyone remembered to wrap it. The
    server cancels and raises `QueryCanceled`, which `_run` turns into a
    timed-out message. `with deadline(conn):` stays at the call sites because
    it reads clearly and means the deadline is enforced; `seconds` is ignored
    because the session's timeout wins.
    """
    yield


def escape_like(term: str) -> str:
    """A search term as a literal, not a pattern.

    Someone searching for `100%` means that, not "anything starting 100", and
    `_` is a single-character wildcard that a person typing a column name will
    hit constantly. Callers wrap the result in `%...%` and must pair it with
    `ESCAPE '\\'` in the SQL.
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# A SQL identifier, quoted. Table and column names are never accepted from
# the caller directly — they are matched against the live schema first — but
# they still reach an f-string, and doubling embedded quotes keeps that true
# of names this schema does not happen to contain today.
#
# Moved to `pipeline/catalog.py` when the Phase 2 loader needed the same
# thing. The name stays here because eight call sites in this file and one in
# health.py use it, and a second spelling of a quoting rule is exactly what
# catalog.py exists to prevent.
_quote = catalog.quote


def is_restricted(name: str) -> bool:
    """Whether an object holds personal data, by the naming rule the whole
    pipeline uses (see pipeline/db.py and constraint 3)."""
    return name.startswith(RESTRICTED_PREFIX)


# What each backend says when it stops a statement for running too long.
# SQLite's progress handler produces "interrupted"; PostgreSQL's
# statement_timeout produces "canceling statement due to statement timeout".
# Matched on text rather than on exception class because sqlite3 has no
# distinct class for it, and one code path that reads the same on both
# backends is worth more here than catching psycopg's QueryCanceled precisely.
_TIMED_OUT = ("interrupted", "canceling statement")


def _timed_out(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in _TIMED_OUT)


@contextmanager
def _guarded(conn) -> Iterator[None]:
    """The deadline, and driver errors turned into something readable.

    A context manager rather than only `_run` below because `list_objects`
    reads its counts through `catalog.row_counts`, which does its own
    `execute` — and a second spelling of the timeout sentence is exactly the
    kind of drift that leaves one caller telling the operator what to do
    about a slow query and another handing them the raw driver message.
    """
    with deadline(conn):
        try:
            yield
        except db.OperationalError as exc:
            if _timed_out(exc):
                raise QueryError(
                    f"Query took longer than {QUERY_TIMEOUT_SECONDS:.0f}s and was "
                    "stopped. Narrow it with a WHERE clause, or sort on an "
                    "indexed column."
                ) from exc
            raise QueryError(str(exc)) from exc
        except db.Error as exc:
            if _timed_out(exc):
                # psycopg raises QueryCanceled, which descends from
                # DatabaseError rather than OperationalError — so without this
                # a timed-out query on PostgreSQL would reach the operator as
                # the raw server message instead of the sentence telling them
                # what to do about it.
                raise QueryError(
                    f"Query took longer than {QUERY_TIMEOUT_SECONDS:.0f}s and was "
                    "stopped. Narrow it with a WHERE clause, or sort on an "
                    "indexed column."
                ) from exc
            raise QueryError(str(exc)) from exc


def _run(conn, sql: str, params: Any = ()) -> list:
    with _guarded(conn):
        return conn.execute(sql, params).fetchall()


# --- schema ------------------------------------------------------------------


def list_objects(conn: db.Connection) -> list[dict]:
    """Every table and view, with row counts for tables.

    Views are listed uncounted. `v_fingertips_la_latest` is 20k rows over a
    window function and `v_la_public_health_budget` joins three tables; making
    the sidebar wait for all of them to be counted would put seconds on the
    first paint of every page load, to show a number nobody asked for yet.
    They are counted when one is opened.

    The counts are one statement, not one per table. This ran as a `COUNT(*)`
    per table until Phase 4, which is 82 cheap reads of a local file and 82
    round-trips to a server on the LAN — 39ms against 320ms, measured. The
    numbers are the same numbers; only the number of questions changed.
    """
    # Sorted by type then name, as the sidebar has always shown them:
    # `catalog.list_objects` orders by name alone, because its other callers
    # compare two backends' inventories and only need a stable order.
    objects = sorted(catalog.list_objects(conn), key=lambda o: (o["type"], o["name"]))
    with _guarded(conn):
        counts = catalog.row_counts(
            conn, [o["name"] for o in objects if o["type"] == "table"])
    return [
        {
            "name": obj["name"],
            "type": obj["type"],
            "restricted": is_restricted(obj["name"]),
            "rows": counts.get(obj["name"]),
        }
        for obj in objects
    ]


def object_type(conn, name: str) -> str | None:
    """'table', 'view', or None if no such object. This is what validates
    every caller-supplied object name before it reaches a query."""
    return catalog.object_type(conn, name)


# BETA-083: one-line descriptions for the tables an operator opens most. Not
# exhaustive — an undescribed table simply has no description line. Kept short
# and factual; the authoritative account of a source table is its migration
# comment and docs/SOURCES.md.
SCHEMA_DESCRIPTIONS = {
    "authorities": "One row per English local authority (ONS geography).",
    "providers": "Tracked provider organisations; `is_target` marks campaign subjects.",
    "provider_identifiers": "External ids (charity number, company number) per provider.",
    "contracts": "Procurement notices matched to the sector keyword set.",
    "council_spend": "Published council payment lines from spend-transparency files.",
    "public_health_grants": "Public health grant allocations per authority per year.",
    "la_revenue_budgets": "Local-authority budgeted spend, by section and line code.",
    "fingertips_indicators": "OHID Fingertips indicator catalogue.",
    "fingertips_la_values": "Per-authority Fingertips values with 95% intervals.",
    "ndtms_la_statistics": "NDTMS modelled local-authority estimates.",
    "cqc_locations": "CQC-registered locations for tracked providers.",
    "hse_enforcement_notices": "HSE enforcement notices matched to a provider.",
    "pfd_reports": "Coroners' Prevention of Future Deaths reports (metadata).",
    "pfd_provider_mentions": "A provider mentioned in a PFD report; `mention_type` distinguishes recipient from body text.",
    "sar_documents": "Safeguarding Adult Review documents from the National SAR Library.",
    "tribunal_cases": "Employment tribunal cases with a provider as a party.",
    "document_records": "Parsed documents (committee papers, CDP documents).",
    "document_elements": "One row per parsed element of a document version.",
    "document_versions": "Parse versions of a document; `is_active` is the current one.",
    "evidence_records": "The provenance envelope: source URL, retrieval time, payload hash.",
    "review_queue": "Candidates awaiting a human decision.",
    "run_ledger": "One durable row per run of the shared module runner.",
    "schema_migrations": "Which migration files have been applied.",
    "parse_failures": "Rows a module could not parse, with a logged reason.",
}


def schema_graph(conn: db.Connection) -> dict:
    """A read-only schema graph (BETA-083): every table and view with its
    columns, its foreign-key edges (table- and column-level) and a short
    description where one is registered.

    Composed from the existing catalogue helpers; no new SQL surface and no
    row reads. The table browser's own restricted-table gate, timeout and row
    caps are unchanged — this only describes the shape.
    """
    objects = sorted(catalog.list_objects(conn), key=lambda o: (o["type"], o["name"]))
    with _guarded(conn):
        counts = catalog.row_counts(
            conn, [o["name"] for o in objects if o["type"] == "table"])

    fk_cols = catalog.foreign_key_columns(conn)
    fk_by_child: dict[str, dict[str, dict]] = {}
    for edge in fk_cols:
        fk_by_child.setdefault(edge["child"], {})[edge["from_col"]] = {
            "table": edge["parent"], "column": edge["to_col"],
        }

    tables = []
    for obj in objects:
        name = obj["name"]
        cols = catalog.columns_of(conn, name)
        fks = fk_by_child.get(name, {})
        tables.append({
            "name": name,
            "type": obj["type"],
            "restricted": is_restricted(name),
            "rows": counts.get(name),
            "description": SCHEMA_DESCRIPTIONS.get(name),
            "columns": [
                {
                    "name": c["name"], "type": c["type"],
                    "notnull": c["notnull"], "pk": c["pk"],
                    "fk": fks.get(c["name"]),
                }
                for c in cols
            ],
        })

    return {
        "tables": tables,
        "edges": [list(pair) for pair in catalog.foreign_keys(conn)],
        "described": sum(1 for t in tables if t["description"]),
    }


def columns_of(conn, name: str) -> list[dict]:
    return catalog.columns_of(conn, name)


def _default_order(conn, name: str) -> str:
    """The ORDER BY that makes paging a table stable, or `""` if there is none.

    The primary key is the answer. PostgreSQL's `ctid` looks like a per-row
    identifier and is not: it is a physical location that moves when a row is
    updated and when VACUUM reclaims space, so paging by it would silently
    repeat and skip rows — the precise failure this function exists to prevent.
    A table without a primary key has no stable order to offer; the caller
    reports `ordered: False` and the UI says so, exactly as it does for a view.
    """
    key = catalog.primary_key(conn, name)
    if not key:
        return ""
    return " ORDER BY " + ", ".join(_quote(column) for column in key)


def read_table(
    conn: db.Connection,
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
    stable order, which a view's does not have to. Tables are ordered by their
    primary key by default for exactly that reason; for a view, or a table with
    no primary key, `ordered` comes back False and the UI says so rather than
    letting page 2 quietly overlap page 1.
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
        # URL fragment without the person having to say which column it is in.
        params["q"] = f"%{escape_like(search)}%"
        clauses = " OR ".join(
            f"CAST({_quote(c)} AS TEXT) LIKE :q ESCAPE '\\'" for c in column_names
        )
        where = f" WHERE ({clauses})"

    total = _run(conn, f"SELECT COUNT(*) AS n FROM {_quote(name)}{where}", params)[0]["n"]

    order_sql, ordered = "", False
    if order_by and order_by in column_names:
        # NULLS spelled out because the two engines disagree on the default:
        # SQLite sorts NULLs first ascending and last descending, PostgreSQL
        # the reverse. Sorting a nullable column in the table browser would
        # otherwise put the empty rows at opposite ends depending on which
        # database answered.
        direction = "DESC NULLS LAST" if descending else "ASC NULLS FIRST"
        order_sql = f" ORDER BY {_quote(order_by)} {direction}"
        ordered = True
    elif kind == "table":
        order_sql = _default_order(conn, name)
        ordered = bool(order_sql)

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


def _row_to_json(row, column_names: list[str]) -> list[Any]:
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


def run_select(conn: db.Connection, sql: str, limit: int = MAX_PAGE_SIZE) -> dict:
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
    if _has_statement_separator(sql):
        raise QueryError("Only one SQL statement may be run at a time.")

    limit = max(1, min(int(limit), MAX_PAGE_SIZE))
    with deadline(conn):
        try:
            cursor = conn.execute(sql)
            rows = cursor.fetchmany(limit)
            truncated = cursor.fetchone() is not None
            column_names = [d[0] for d in cursor.description or []]
            cursor.close()
        except db.OperationalError as exc:
            if "interrupted" in str(exc):
                raise QueryError(
                    f"Query took longer than {QUERY_TIMEOUT_SECONDS:.0f}s and was stopped."
                ) from exc
            raise QueryError(str(exc)) from exc
        except db.Warning as exc:
            # "You can only execute one statement at a time" arrives here.
            raise QueryError(str(exc)) from exc
        except db.Error as exc:
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


def _has_statement_separator(sql: str) -> bool:
    """Whether ``sql`` contains a semicolon outside quoted/commented text."""
    quote: str | None = None
    i = 0
    while i < len(sql):
        char = sql[i]
        if quote:
            if char == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if char in ("'", '"'):
            quote = char
        elif char == "-" and i + 1 < len(sql) and sql[i + 1] == "-":
            newline = sql.find("\n", i + 2)
            i = len(sql) if newline < 0 else newline
            continue
        elif char == ";":
            return True
        i += 1
    return False


# --- review queue -------------------------------------------------------------


# What a *person* may set an item to. 'pending' is the revert, and there is
# deliberately nothing else here: 'answered' is not a decision anyone makes.
REVIEW_STATUSES = ("pending", "approved", "rejected")

# Every status an item can hold, which is a different question. 'answered'
# means the pipeline went and got what the item was waiting for -- see
# pipeline/review_sweep.py. Counting only the decidable three would drop those
# items out of the totals silently, so the overview would show fewer items than
# the queue holds and never say why.
ALL_REVIEW_STATUSES = (*REVIEW_STATUSES, "answered")


def review_facets(conn: db.Connection) -> dict:
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
        "statuses": {status: by_status.get(status, 0)
                      for status in ALL_REVIEW_STATUSES},
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
        if status not in ALL_REVIEW_STATUSES:
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
        params["q"] = f"%{escape_like(search)}%"
        where.append(
            "(q.raw_value LIKE :q ESCAPE '\\' OR COALESCE(q.context_json, '') LIKE :q ESCAPE '\\')"
        )

    return (f" WHERE {' AND '.join(where)}" if where else ""), params


def review_items(
    conn: db.Connection,
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


# Context keys that identify the organisation / place a review item is about,
# tried in order. The first that is present becomes the cluster's org token.
_CLUSTER_ID_KEYS = (
    "provider_key", "ons_code", "authority_ons_code", "buyer_ons_code",
    "sab_name", "board", "authority", "register_name", "employer_name",
    "recipient_name", "notice_number",
)
_CLUSTER_URL_KEYS = ("source_url", "url", "page_url", "source_page", "notice_web_url")
_DOMAIN_RE = re.compile(r"https?://([^/]+)", re.IGNORECASE)


def _cluster_token(raw_value: str | None, context_json: str | None) -> str:
    """A deterministic organisation/source token for grouping.

    The same (module, item_type, token) always lands in the same cluster, and
    the token is derived only from stored fields — a context id key, else a
    URL's host, else the item's own short raw value. Grouping is a reading
    aid, never a judgement, so an unhelpful token ('(none)') is fine.
    """
    context: dict = {}
    if context_json:
        try:
            parsed = json.loads(context_json)
            if isinstance(parsed, dict):
                context = parsed
        except (TypeError, ValueError):
            context = {}
    for key in _CLUSTER_ID_KEYS:
        value = context.get(key)
        if value:
            return str(value).strip().lower()[:80]
    for key in _CLUSTER_URL_KEYS:
        value = context.get(key)
        if value:
            match = _DOMAIN_RE.search(str(value))
            if match:
                return match.group(1).lower()
    raw = (raw_value or "").strip().lower()
    return raw[:80] if raw else "(none)"


_CLUSTER_SCAN_CAP = 5000


def review_clusters(conn: db.Connection, *, status: str = "pending") -> dict:
    """Pending review items grouped by (module, item_type, org token).

    Display only: the cluster is a way to see 40 "unknown committee URL for
    Kent" items as one row instead of forty. Every bulk action still recounts
    its exact id set transactionally before it decides anything — grouping
    changes what a reviewer looks at, not what a decision touches.
    """
    rows = _run(
        conn,
        "SELECT id, module, item_type, raw_value, context_json FROM review_queue "
        "WHERE status = :status ORDER BY created_at, id LIMIT :cap",
        {"status": status, "cap": _CLUSTER_SCAN_CAP})

    buckets: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        token = _cluster_token(row["raw_value"], row["context_json"])
        key = (row["module"], row["item_type"], token)
        bucket = buckets.setdefault(key, {
            "module": row["module"], "item_type": row["item_type"],
            "token": token, "count": 0, "item_ids": [], "sample_raw": row["raw_value"],
        })
        bucket["count"] += 1
        if len(bucket["item_ids"]) < 200:
            bucket["item_ids"].append(row["id"])

    clusters = sorted(
        buckets.values(),
        key=lambda b: (-b["count"], b["module"], b["item_type"], b["token"]))
    return {
        "status": status,
        "scanned": len(rows),
        "truncated": len(rows) >= _CLUSTER_SCAN_CAP,
        "cluster_count": len(clusters),
        "clusters": clusters,
        "caveat": (
            "Grouping is a reading aid, not a judgement: items land in one "
            "cluster because they share a module, type and a token derived "
            "from stored fields, not because a decision on one applies to the "
            "rest. Every action still confirms its own id set."),
    }


def review_item(conn: db.Connection, item_id: int) -> dict | None:
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


def recent_decisions(conn: db.Connection, limit: int = 20) -> list[dict]:
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


def parse_failures(conn: db.Connection, limit: int = 200) -> list[dict]:
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


def overview(conn: db.Connection, settings: Settings | None = None) -> dict:
    """The landing screen: what is in the queue, what has been decided, and
    what the warehouse holds."""
    settings = settings or get_settings()
    facets = review_facets(conn)

    objects = catalog.list_objects(conn)
    tables = sum(1 for o in objects if o["type"] == "table")
    views = sum(1 for o in objects if o["type"] == "view")
    migrations = _run(
        conn, "SELECT COUNT(*) AS n FROM schema_migrations")[0]["n"]
    failures = _run(conn, "SELECT COUNT(*) AS n FROM parse_failures")[0]["n"]
    # The warehouse identity and size, PostgreSQL-side. `path` keeps its key so
    # the admin overview's shape is unchanged; it now carries the redacted
    # database URL rather than a file path, and the size is the whole database.
    size_bytes = _run(
        conn, "SELECT pg_database_size(current_database()) AS n")[0]["n"]

    return {
        "database": {
            "path": settings.redacted_database_url or "(DATABASE_URL unset)",
            "size_bytes": size_bytes,
            "tables": tables,
            "views": views,
            "migrations": migrations,
        },
        "review": facets,
        "parse_failures": {"total": failures, "groups": parse_failures(conn, limit=50)},
        "recent_decisions": recent_decisions(conn, limit=10),
    }
