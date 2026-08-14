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


def quote(identifier: str) -> str:
    """A SQL identifier, quoted, for the places a name reaches an f-string.

    Table and column names are never taken from a caller directly — they are
    matched against the live schema first — but they are still interpolated,
    and doubling an embedded quote keeps that safe for names this schema does
    not happen to contain today.

    Here rather than in `web/queries.py`, where it was, because the Phase 2
    loader needs it too and `catalog.py` is where the schema vocabulary lives.
    Double quotes mean the same thing to both engines, so one spelling
    serves both — which is the whole argument of this module.
    """
    return '"' + identifier.replace('"', '""') + '"'


def list_objects(conn) -> list[dict]:
    """Every table and view, as `{"name": ..., "type": "table"|"view"}`.

    Ordered by name so two backends produce the same list in the same order —
    the migration-tree equivalence test compares them directly.
    """
    if db.backend_of(conn) == "postgres":
        rows = conn.execute(
            "SELECT table_name AS name, "
            "       CASE WHEN table_type = 'VIEW' THEN 'view' ELSE 'table' END AS type "
            "FROM information_schema.tables "
            "WHERE table_schema = current_schema() "
            "ORDER BY table_name"
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
        rows = conn.execute(
            "SELECT c.column_name AS name, c.data_type AS type, "
            "       c.is_nullable AS is_nullable, "
            "       COALESCE(k.is_pk, 0) AS pk "
            "FROM information_schema.columns c "
            "LEFT JOIN ( "
            "    SELECT a.attname AS column_name, 1 AS is_pk "
            "    FROM pg_index i "
            "    JOIN pg_attribute a "
            "      ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
            "    WHERE i.indrelid = to_regclass(?) AND i.indisprimary "
            ") k ON k.column_name = c.column_name "
            "WHERE c.table_schema = current_schema() AND c.table_name = ? "
            "ORDER BY c.ordinal_position", (name, name)
        ).fetchall()
        return [
            {
                "name": r["name"],
                "type": r["type"] or "",
                "notnull": r["is_nullable"] == "NO",
                "pk": bool(r["pk"]),
            }
            for r in rows
        ]

    rows = conn.execute(f"PRAGMA table_info({quote(name)})").fetchall()
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


def foreign_keys(conn) -> list[tuple[str, str]]:
    """Every `(child, parent)` foreign-key edge, deduplicated and sorted.

    What the Phase 2 loader orders its tables by: a child row cannot be
    inserted before the parent it references exists. Composite keys and two
    columns of one table pointing at the same parent are one edge here,
    because the only question being asked is which table goes first.

    Self-references are dropped. A table whose rows point at other rows of the
    same table (none do today) would otherwise be its own predecessor and make
    the graph unsortable, when in fact it just needs its rows in the right
    order within one load — a different problem, and not one this warehouse
    has.
    """
    edges: set[tuple[str, str]] = set()
    if db.backend_of(conn) == "postgres":
        rows = conn.execute(
            "SELECT c.conrelid::regclass::text AS child, "
            "       c.confrelid::regclass::text AS parent "
            "FROM pg_constraint c "
            "JOIN pg_class r ON r.oid = c.conrelid "
            "WHERE c.contype = 'f' "
            "  AND r.relnamespace = current_schema()::regnamespace"
        ).fetchall()
        edges = {(r["child"], r["parent"]) for r in rows}
    else:
        for child in table_names(conn):
            for row in conn.execute(
                    f"PRAGMA foreign_key_list({quote(child)})").fetchall():
                edges.add((child, row["table"]))
    return sorted((child, parent) for child, parent in edges if child != parent)


def tables_with_column(conn, column: str) -> list[str]:
    """Every table carrying `column`, ordered by name.

    The Health tab's freshness scan wants "tables with a `retrieved_at`". On
    SQLite that was a join against `pragma_table_info(m.name)` — a
    table-valued function, which is not a construct PostgreSQL has at all;
    `information_schema.columns` answers it directly, and the SQLite side
    keeps the join it already had.
    """
    if db.backend_of(conn) == "postgres":
        rows = conn.execute(
            "SELECT DISTINCT c.table_name AS name "
            "FROM information_schema.columns c "
            "JOIN information_schema.tables t "
            "  ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
            "WHERE c.table_schema = current_schema() "
            "  AND t.table_type = 'BASE TABLE' AND c.column_name = ? "
            "ORDER BY c.table_name", (column,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT m.name AS name FROM sqlite_master m "
            "JOIN pragma_table_info(m.name) p "
            "WHERE m.type = 'table' AND p.name = ? ORDER BY m.name", (column,)
        ).fetchall()
    return [r["name"] for r in rows]
