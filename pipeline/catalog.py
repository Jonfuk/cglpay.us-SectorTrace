"""What the warehouse contains, asked the same way on either backend.

`sqlite_master` and `PRAGMA table_info` have no PostgreSQL equivalent, and
four places needed them: the migration ledger and restricted-table guard in
`db.py`, the table browser and SQL box in `web/queries.py`, the Health tab in
`web/health.py`, and the DATA_DICTIONARY generator in `exports/docs.py`. They
had four slightly different spellings of the same two questions, which is
three more than the number of places a schema-introspection bug should be
able to hide.

One helper each, here, dispatching on the backend.

A note on ordering. SQLite sorts NULLs first ascending and last descending;
PostgreSQL does the reverse. Nothing in this file orders by a nullable
column, and it stays that way — `name` and `ordinal_position` are both NOT
NULL — but the rule is written down here because the same trap is live in
`pipeline/exports/`, where the answer had to be explicit `NULLS` clauses.
"""
from __future__ import annotations

from pipeline import db

# The tables SQLite keeps for itself. PostgreSQL puts its equivalents in
# pg_catalog and information_schema, which are separate schemas and therefore
# never in `current_schema()` — no filter needed on that side.
_SQLITE_INTERNAL = "sqlite_%"


def list_objects(conn) -> list[dict]:
    """Every table and view, as `{"name": ..., "type": "table"|"view"}`.

    Ordered by name so two backends produce the same list in the same order —
    the migration-tree equivalence test compares them directly.
    """
    if db.backend_of(conn) == "postgres":
        # pg_catalog, NOT information_schema. The SQL-standard views are
        # filtered to objects the *current role* holds some privilege on, and
        # `sqlite_master` is not filtered at all — so the same call answered
        # differently depending on who was connected, which is a behavioural
        # difference this phase exists to prevent.
        #
        # It found itself: the read path connected as `sectortrace_reader`,
        # information_schema returned nothing, and the operator UI reported an
        # empty warehouse rather than a permissions problem. A missing grant
        # should look like a missing grant.
        #
        # It also matters for `db.restricted_tables`, which is built on this
        # and is a security boundary (settled decision 3). A guard that
        # enumerates fewer restricted_ tables when the connection holds fewer
        # privileges is a guard that quietly stops guarding.
        rows = conn.execute(
            "SELECT c.relname AS name, "
            "       CASE WHEN c.relkind = 'v' THEN 'view' ELSE 'table' END AS type "
            "FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = current_schema() "
            "  AND c.relkind IN ('r', 'p', 'v') "
            "ORDER BY c.relname"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT name, type FROM sqlite_master "
            "WHERE type IN ('table', 'view') AND name NOT LIKE ? "
            "ORDER BY name", (_SQLITE_INTERNAL,)
        ).fetchall()
    return [{"name": r["name"], "type": r["type"]} for r in rows]


def table_names(conn) -> list[str]:
    """Base tables only, views excluded."""
    return [o["name"] for o in list_objects(conn) if o["type"] == "table"]


def object_type(conn, name: str) -> str | None:
    """`"table"`, `"view"`, or None if there is no such object."""
    for obj in list_objects(conn):
        if obj["name"] == name:
            return obj["type"]
    return None


def columns_of(conn, name: str) -> list[dict]:
    """Columns in declaration order: `{name, type, notnull, pk}`.

    The shape is `PRAGMA table_info`'s, because that is what the table browser
    and the data dictionary were already written against. `type` is the
    declared type as the engine reports it, so it differs in spelling between
    backends (`INTEGER` vs `bigint`); nothing compares the two, and the
    schema-equivalence test maps them deliberately rather than by string
    equality.
    """
    if db.backend_of(conn) == "postgres":
        # pg_attribute rather than information_schema.columns, for the reason
        # in `list_objects`: the standard views are privilege-filtered and
        # `PRAGMA table_info` is not.
        rows = conn.execute(
            "SELECT a.attname AS name, "
            "       format_type(a.atttypid, a.atttypmod) AS type, "
            "       a.attnotnull AS notnull, "
            "       COALESCE(i.indisprimary, false) AS pk "
            "FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "LEFT JOIN pg_index i "
            "  ON i.indrelid = c.oid AND i.indisprimary "
            " AND a.attnum = ANY(i.indkey) "
            "WHERE n.nspname = current_schema() AND c.relname = ? "
            # attnum > 0 skips the system columns (ctid, xmin and friends);
            # attisdropped skips columns removed by ALTER TABLE, which
            # PostgreSQL keeps as tombstones in this catalog.
            "  AND a.attnum > 0 AND NOT a.attisdropped "
            "ORDER BY a.attnum", (name,)
        ).fetchall()
        return [
            {
                "name": r["name"],
                "type": r["type"] or "",
                "notnull": bool(r["notnull"]),
                "pk": bool(r["pk"]),
            }
            for r in rows
        ]

    from pipeline.web import queries

    rows = conn.execute(f"PRAGMA table_info({queries._quote(name)})").fetchall()
    return [
        {
            "name": r["name"],
            "type": r["type"] or "",
            "notnull": bool(r["notnull"]),
            "pk": bool(r["pk"]),
        }
        for r in rows
    ]


def primary_key(conn, name: str) -> list[str]:
    """The primary key columns, in key order, or `[]` if there is none.

    This is what replaces `ORDER BY rowid` as the table browser's default
    order. PostgreSQL has no stable per-row identifier to fall back on —
    `ctid` moves under VACUUM and UPDATE, so it is not a substitute — which
    means a table with no primary key has no default order at all, and the
    caller has to say so rather than return rows in whatever order the heap
    is in today.
    """
    if db.backend_of(conn) == "postgres":
        rows = conn.execute(
            "SELECT a.attname AS name "
            "FROM pg_index i "
            "JOIN pg_attribute a "
            "  ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
            "WHERE i.indrelid = to_regclass(?) AND i.indisprimary "
            "ORDER BY array_position(i.indkey, a.attnum)", (name,)
        ).fetchall()
        return [r["name"] for r in rows]

    return [c["name"] for c in columns_of(conn, name) if c["pk"]]


def tables_with_column(conn, column: str) -> list[str]:
    """Every table carrying `column`, ordered by name.

    The Health tab's freshness scan wants "tables with a `retrieved_at`". On
    SQLite that was a join against `pragma_table_info(m.name)` — a
    table-valued function, which is not a construct PostgreSQL has at all;
    `pg_attribute` answers it directly, and the SQLite side keeps the join it
    already had.
    """
    if db.backend_of(conn) == "postgres":
        rows = conn.execute(
            "SELECT c.relname AS name "
            "FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = current_schema() "
            "  AND c.relkind IN ('r', 'p') AND a.attname = ? "
            "  AND a.attnum > 0 AND NOT a.attisdropped "
            "ORDER BY c.relname", (column,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT m.name AS name FROM sqlite_master m "
            "JOIN pragma_table_info(m.name) p "
            "WHERE m.type = 'table' AND p.name = ? ORDER BY m.name", (column,)
        ).fetchall()
    return [r["name"] for r in rows]
