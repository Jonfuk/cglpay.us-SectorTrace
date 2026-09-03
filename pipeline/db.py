"""Warehouse access: connection, migrations, and generic upsert/audit helpers.

Plain SQL throughout, no ORM, per the brief. Domain schemas live in numbered
files under pipeline/migrations/ (0001_core.sql is the infra layer this
module owns; 0002+ are added by m00_geography onward).

PostgreSQL 18 is the only application database (performance.md Phase 1). What
a caller relies on:

  * `get_connection()` for writes, closed in `finally`;
  * `?` and `:name` parameters — the style this codebase writes, translated to
    psycopg's `%s` / `%(name)s` at the connection boundary by
    `pipeline/sqldialect.py`. One SQL string per query, in one style; the
    translation is a scanner, not a regex, and is the only place the two
    styles meet;
  * rows addressable by name and by position (`row["x"]`, `row[0]`) — see
    `pipeline/pg.py`'s row factory;
  * `db.IntegrityError` and friends in `except` clauses.

There is no write slot: SQLite allowed one writer at a time and needed a fair
queue to serialise them; PostgreSQL's MVCC lets writers interleave, so the
apparatus is gone. The one-overlapping-pipeline-run rule it used to also carry
moves to a PostgreSQL advisory lock in the Phase 5 worker cutover.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import psycopg as _psycopg

from pipeline.config import Settings, get_settings

RESTRICTED_PREFIX = "restricted_"

# What a warehouse connection is. Written as a name rather than spelled out at
# eighty call sites: there is no type checker in this project — ruff's selected
# rules do not include one — so an annotation here is documentation, and
# `db.Connection` says "a warehouse connection". `object` at runtime because
# annotations are never evaluated (`from __future__ import annotations`).
if TYPE_CHECKING:
    from pipeline.pg import PostgresConnection

    Connection = PostgresConnection
else:
    Connection = object

# Exception classes to catch, so `except db.Error:` names the warehouse's
# errors rather than psycopg's directly.
#
# The one that needed thought is `IntegrityError`. plpgsql's `RAISE EXCEPTION`
# surfaces as `psycopg.errors.RaiseException`, which is *not* a
# `psycopg.IntegrityError` — so the triggers behind settled decision 4 raise
# with `ERRCODE = 'integrity_constraint_violation'` to land in the right class,
# and `RaiseException` is listed here anyway for the case where someone writes
# a new trigger and forgets.
Error: tuple[type[BaseException], ...] = (_psycopg.Error,)
DatabaseError: tuple[type[BaseException], ...] = (_psycopg.DatabaseError,)
IntegrityError: tuple[type[BaseException], ...] = (
    _psycopg.IntegrityError, _psycopg.errors.RaiseException)
OperationalError: tuple[type[BaseException], ...] = (
    _psycopg.OperationalError, _psycopg.errors.ReadOnlySqlTransaction)
Warning: tuple[type[BaseException], ...] = (_psycopg.Warning,)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection(settings: Settings | None = None,
                    check_same_thread: bool = True):
    """A warehouse connection.

    `check_same_thread` is a SQLite concept with no meaning on PostgreSQL — a
    connection is not bound to the thread that opened it — but it stays in the
    signature and is ignored, because the fetch pools pass it and rewriting
    those call sites is not this change's job.
    """
    settings = settings or get_settings()
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. PostgreSQL is the only application "
            "database (performance.md Phase 1); there is no file backend to "
            "fall back to.")
    from pipeline import pg

    return pg.connect(settings.database_url)


def backend_of(conn) -> str:
    """Always `"postgres"`.

    Retained as a function rather than removed at 60-odd call sites: it now has
    one answer, but the sites that ask `backend_of(conn) == "postgres"` still
    read clearly and cost nothing. They are simplified where they are touched
    for other reasons; there is no value in a mechanical sweep that changes
    nothing.
    """
    return "postgres"


def migrations_dir_for(settings: Settings | None = None) -> Path:
    """The migration tree — one tree now, under `postgres/`.

    Recorded in `schema_migrations` in filename order. The former SQLite tree
    beside it is gone with the SQLite backend.
    """
    settings = settings or get_settings()
    return (settings.migrations_dir if settings.migrations_dir.name == "postgres"
            else settings.migrations_dir / "postgres")


def applied_migrations(conn) -> set[str]:
    exists = conn.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = current_schema() AND table_name = ?",
        ("schema_migrations",)).fetchone()
    if exists is None:
        return set()
    return {row["filename"] for row in conn.execute("SELECT filename FROM schema_migrations")}


# The PostgreSQL extensions the warehouse requires. Each backs a plan that is
# now the only implementation, its SQLite/Python fallback removed with the
# SQLite backend (performance.md Phase 1):
#
#   * vector   — pgvector/HNSW is the only semantic-search path (pipeline/nlp).
#   * pg_trgm  — the operator's fuzzy-name search and the portal's contract
#                text filter, through GIN indexes.
#   * postgis  — a geometry column and spatial index on `authorities`.
#
# They are mandatory: `ensure_extensions` fails the migrate clearly if the
# server cannot provide one, rather than degrading silently to a path that no
# longer exists.
WAREHOUSE_EXTENSIONS = ("vector", "pg_trgm", "postgis")


def has_extension(conn, name: str) -> bool:
    """True when `name` is installed in the connected database.

    Queried each call rather than cached: it is one indexed catalog lookup, and
    `ensure_extensions` can change the answer within a single process run.
    """
    return conn.execute(
        "SELECT 1 FROM pg_extension WHERE extname = ?", (name,)).fetchone() is not None


def ensure_extensions(conn, names: Sequence[str] = WAREHOUSE_EXTENSIONS) -> list[str]:
    """`CREATE EXTENSION IF NOT EXISTS` for each of `names`, then require it.

    The extensions are mandatory now that their fallbacks are gone, so absence
    is fatal. But a `CREATE EXTENSION` that *fails* is not the same as an
    absent extension: a managed server (Railway) may forbid the role from
    creating one that is already installed, and that is fine. So each name is
    created best-effort — the refusal swallowed, the transaction rolled back —
    and then checked with `has_extension`. Only a name that is genuinely not
    present afterwards raises, and it raises naming all of them together rather
    than failing on the first.

    Each statement runs in its own transaction (`with conn:`) so one refusal
    does not poison the next.
    """
    from pipeline.catalog import quote

    for name in names:
        try:
            with conn:
                conn.execute(f"CREATE EXTENSION IF NOT EXISTS {quote(name)}")
        except Exception:  # noqa: BLE001 - a refusal is not absence; has_extension decides
            conn.rollback()

    missing = [name for name in names if not has_extension(conn, name)]
    if missing:
        raise RuntimeError(
            "required PostgreSQL extension(s) not available: "
            f"{', '.join(missing)}. pgvector (vector), pg_trgm and PostGIS are "
            "mandatory — install them on the server or use the image in "
            "deploy/postgres/Dockerfile (performance.md Phase 1).")
    return list(names)


def reader_role(settings: Settings | None = None) -> str | None:
    """The role `DATABASE_RO_URL` connects as, or None if reads use the owner.

    Parsed out of the URL rather than configured separately because there is
    only one right answer and two settings would be two things to keep in
    agreement.
    """
    settings = settings or get_settings()
    if not settings.database_ro_url or settings.database_ro_url == settings.database_url:
        return None
    from urllib.parse import unquote, urlsplit

    username = urlsplit(settings.database_ro_url).username
    return unquote(username) if username else None


def grant_reader_access(conn, settings: Settings | None = None) -> str | None:
    """Let the reader role see the tables that now exist. Returns the role
    granted to, or None if there is nothing to do.

    This exists because of a defect Phase 4 found rather than a design: the
    reader role was created with one `GRANT SELECT ON ALL TABLES`, which
    grants on the tables existing *at that moment*. Nine migrations later,
    thirteen tables were invisible to every read the portal and the operator
    UI make — and invisible is the exact word, because `information_schema`
    is privilege-filtered. The sidebar listed 69 of 82 objects with no gap in
    it, `object_type()` reported the other thirteen as not existing, and a
    portal query on one got a permission error. Nothing was wrong-looking.

    So the grant travels with the thing that caused it. A migration that adds
    a table is what makes the grant stale, and this runs when one does.

    `ALTER DEFAULT PRIVILEGES` as well, for the table created by some route
    other than a migration: it applies to future tables only, which is why it
    cannot replace the catch-up grant beside it.

    Restricted tables are granted along with the rest, which is deliberate and
    is how the role was already set up: the personal-data boundary is
    `guard_columns()` and the reveal gate (settled decision 3), and the reveal
    gate reads through this very connection. A role that could not see
    `restricted_*` would not tighten that boundary — it would break the one
    path that is allowed to cross it, and leave the boundary where it already
    is.
    """
    role = reader_role(settings)
    if role is None:
        return None

    # Deferred: `catalog` imports this module, and its `quote` is the one
    # spelling of the quoting rule the project keeps.
    from pipeline.catalog import quote

    if conn.execute("SELECT 1 FROM pg_roles WHERE rolname = ?", (role,)).fetchone() is None:
        # Named in the settings and absent from the server. Not fatal here —
        # the read path will fail to connect at all and say so — but silence
        # is what produced the defect this function exists for.
        import structlog

        structlog.get_logger().warning(
            "db.reader_role_missing", role=role,
            note="DATABASE_RO_URL names a role this server does not have; "
                 "tables added by these migrations were not granted to it")
        return None

    grantee = quote(role)
    schema = quote(conn.execute("SELECT current_schema()").fetchone()[0])
    with conn:
        conn.execute(f"GRANT USAGE ON SCHEMA {schema} TO {grantee}")
        conn.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO {grantee}")
        conn.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
                      f"GRANT SELECT ON TABLES TO {grantee}")
    return role


def apply_migrations(conn, migrations_dir: Path | None = None, *,
                      settings: Settings | None = None) -> list[str]:
    """Apply any .sql files in migrations_dir not yet recorded as applied,
    in filename order. Returns the list of filenames newly applied. Safe to
    call on every run — a no-op once the schema is current.

    The directory defaults to the migration tree under `postgres/`.

    Applying anything re-grants the reader role — see `grant_reader_access`,
    and the defect that made it necessary. `settings` is where the reader's
    name comes from; it is a parameter rather than always the process-wide
    settings so that a caller working against a warehouse other than the
    configured one (the live suite's scratch schemas, `migrate-data`) grants to
    the role it is actually using.
    """
    if migrations_dir is None:
        migrations_dir = (settings or get_settings()).migrations_dir / "postgres"

    # Before any migration that references an extension can run. The three
    # required extensions are created (or confirmed present) here, and a server
    # that cannot provide one fails the migrate clearly rather than running on
    # into DDL that assumes it.
    ensure_extensions(conn)

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

    if newly_applied:
        granted = grant_reader_access(conn, settings)
        if granted:
            import structlog

            structlog.get_logger().info("db.reader_granted", role=granted,
                                         after=len(newly_applied))

        # Keep authorities.geom in step with geometry_geojson after a schema
        # change — migration 0070's own backfill runs before any rows exist on
        # the migrate-then-collect path. A no-op unless PostgreSQL + PostGIS.
        # Deferred import: pipeline.geo imports this module.
        from pipeline import geo

        geo.refresh_authority_geometry(conn)

        # NB: document_embeddings.embedding_vec is *not* backfilled here. It was,
        # once — and on a populated warehouse the first 0071 apply then filled
        # 167k rows into a fresh HNSW index inside `pipeline migrate`, which the
        # app runs before it binds its port. That blocked the deploy's health
        # gate long enough to fail it (and, before the serial-build fix, crashed
        # outright on a small /dev/shm). Migration 0071 creates the empty index;
        # embeddings.run keeps it current inline; the one-time catch-up of
        # pre-existing rows is a post-health deploy step (`nlp backfill-vectors`,
        # ansible) and the mirror sync's rebuild — never the request-serving
        # startup path. `backfill_vectors` stays idempotent for those callers.

    return newly_applied


# The columns that carry a *person's* decision about a row — set by promotion,
# by rejection, or by a hand-run UPDATE off a verification worklist, and never
# by collection. Pass them as `preserve` from any module that re-upserts a row
# a reviewer may already have decided on; see the note on `preserve` below for
# what happens when you don't.
DECISION_COLUMNS = ("verified", "verified_at", "rejected")


def upsert(
    conn: Connection,
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


def upsert_many(
    conn: Connection,
    table: str,
    rows: Sequence[dict],
    natural_key: Sequence[str],
    preserve: Sequence[str] = (),
) -> int:
    """Batch :func:`upsert` using one cached statement shape.

    All rows must have the same columns; accepting a ragged batch would make
    the statement shape depend on row order and quietly turn a bulk write back
    into a collection of special cases. ``IS DISTINCT FROM`` suppresses a
    pointless conflict update on both supported SQL engines while still
    updating provenance, hashes, timestamps, or canonical values that changed.
    """
    if not rows:
        return 0
    columns = list(rows[0].keys())
    if not columns or any(set(row) != set(columns) for row in rows):
        raise ValueError("upsert_many rows must share one column shape")
    missing = set(natural_key) - set(columns)
    if missing:
        raise ValueError(f"natural key columns are missing from rows: {sorted(missing)}")
    protected = set(preserve)
    updates = [c for c in columns if c not in natural_key and c not in protected]
    key_sql = ", ".join(natural_key)
    column_sql = ", ".join(columns)
    placeholders = ", ".join(f":{column}" for column in columns)
    if updates:
        assignments = ", ".join(f"{c} = excluded.{c}" for c in updates)
        changed = " OR ".join(f"{table}.{c} IS DISTINCT FROM excluded.{c}" for c in updates)
        sql = (f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) "
               f"ON CONFLICT ({key_sql}) DO UPDATE SET {assignments} "
               f"WHERE {changed}")
    else:
        sql = (f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) "
               f"ON CONFLICT ({key_sql}) DO NOTHING")
    # Normalise insertion order once so callers may construct equivalent
    # dictionaries in different orders while the prepared statement remains
    # one stable shape.
    conn.executemany(sql, [{column: row[column] for column in columns} for row in rows])
    return len(rows)


def record_parse_failure(
    conn: Connection,
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
    conn: Connection,
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


def get_cursor(conn: Connection, module: str) -> str | None:
    row = conn.execute(
        "SELECT cursor_value FROM module_cursors WHERE module = ?", (module,)
    ).fetchone()
    return row["cursor_value"] if row else None


def set_cursor(conn: Connection, module: str, cursor_value: str) -> None:
    conn.execute(
        "INSERT INTO module_cursors (module, cursor_value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT (module) DO UPDATE SET cursor_value = excluded.cursor_value, "
        "updated_at = excluded.updated_at",
        (module, cursor_value, _utcnow()),
    )


def get_http_cache(conn: Connection, url: str):
    return conn.execute("SELECT * FROM http_cache WHERE url = ?", (url,)).fetchone()


def set_http_cache(
    conn: Connection,
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


def rows_missing_provenance(conn: Connection, table: str) -> list:
    """Constraint 1: every row in every public (non-restricted) table must
    carry a non-null source_url and retrieved_at. Returns the offending rows
    (empty list if the table is clean). Assumes the table has those columns
    — call this only on tables that are supposed to carry provenance.
    """
    return conn.execute(
        f"SELECT * FROM {table} WHERE source_url IS NULL OR retrieved_at IS NULL"
    ).fetchall()


def restricted_tables(conn) -> list[str]:
    """Every restricted_ table AND view.

    Views matter as much as tables and were previously invisible here: this
    filtered on type='table', so a restricted_ view — a personal-data query
    saved under a name — would have passed assert_no_restricted_tables
    untouched. The entity graph is built from views, several of which name
    company officers, so the gap had to close before they landed.

    Filtered in Python rather than by `LIKE` now that it goes through the
    catalog helper. The prefix contains no wildcard, the object list is 77
    rows, and one code path that behaves identically on both backends is
    worth more here than a predicate the server evaluates — this function is
    what `guard_columns()` and the reveal gate stand on.
    """
    from pipeline import catalog

    return [o["name"] for o in catalog.list_objects(conn)
            if o["name"].startswith(RESTRICTED_PREFIX)]
