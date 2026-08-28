"""Moving the warehouse into PostgreSQL: the Phase 2 loader.

One direction only. `data/warehouse.db` is opened `mode=ro` and is never
written to, by this module or by anything it calls — SQLite stays the backend
of record until somebody decides otherwise, and the way back from a failed
migration is to stop using the URL, not to restore anything.

What this does *not* do, and why:

**It does not drop indexes before loading.** The plan proposed it, and for a
terabyte it would be right. This warehouse is 655,000 rows in 496 MiB, of
which two tables are 88% of it; the whole load takes minutes with the indexes
in place. Against that saving: a loader interrupted between the drop and the
recreate leaves a warehouse whose unique indexes are gone, and every
`ON CONFLICT` in the pipeline then either errors or — worse — silently stops
being a natural-key upsert. That is a correctness failure bought with a few
minutes, so the indexes stay.

**It does not disable the triggers.** The seven refusals from migrations 0030,
0033 and 0048 are the mechanism behind settled decision 4 (and its claims
registry sibling), and `COPY` fires
`BEFORE INSERT` triggers exactly as `INSERT` does. The obvious move is
`ALTER TABLE ... DISABLE TRIGGER USER` around the load, which suspends the
guarantee for the one operation that writes every evidence row this project
has. It is not needed: each of those triggers asks whether a row exists in
`evidence_promotions`, `census_verifications` or `claim_verifications`, so
loading those three tables
*first* makes every check pass on its own terms. The ordering below encodes
that, and `pipeline/pgverify.py` re-asks the triggers' own questions after the
load rather than trusting that they ran.

**It does not transform anything.** Values go across as the types they were
stored as, and a value whose storage type does not match its declared type is
a refusal naming the row, not a cast. SQLite is dynamically typed and will
hold `'12'` in an INTEGER column without complaint; PostgreSQL will not, and
the difference between those two facts is where a silent rewrite of the
evidence base would live.

The load is resumable because the alternative is an operator re-reading 477k
budget rows over the LAN to recover from a dropped connection. Each table is
one transaction and one line in the state file, so an interrupted run leaves
whole tables loaded and no partial ones.
"""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import structlog

from pipeline import catalog, db
from pipeline.config import Settings, get_settings

log = structlog.get_logger()


class LoadError(RuntimeError):
    """A migration that would produce a warehouse nobody should trust."""


# Tables the target keeps its own copy of, and which must not be overwritten
# with the source's.
#
# `schema_migrations` records which files were applied *to this database*.
# The two trees hold the same filenames, but the PostgreSQL warehouse applied
# the PostgreSQL ones, at its own times — and the SQLite warehouse may be a
# file behind, as the live one was when this was written (33 applied against
# the tree's 34). Copying the source's ledger over the target's would leave a
# database claiming it had run migrations it had not.
SOURCE_ONLY_TABLES = frozenset({"schema_migrations"})

# Columns present only in the PostgreSQL tree and derived there from a column
# both trees carry. They are not part of a cross-backend copy or schema
# comparison: SQLite has no matching type, and the value is rebuilt on the
# PostgreSQL side (pipeline/geo.py) rather than carried across.
#
# authorities.geom is a PostGIS MultiPolygon built from geometry_geojson by
# migration 0070 where PostGIS is present; absent otherwise, in which case
# filtering it out is a harmless no-op.
PG_DERIVED_COLUMNS: dict[str, frozenset[str]] = {
    "authorities": frozenset({"geom"}),
}


def portable_columns(conn, table: str) -> list[str]:
    """`table`'s column names, minus any PostgreSQL-only derived column.

    Use wherever a column list has to mean the same thing on both backends —
    a schema-parity check, or a row copy in either direction.
    """
    dropped = PG_DERIVED_COLUMNS.get(table, frozenset())
    return [c["name"] for c in catalog.columns_of(conn, table)
            if c["name"] not in dropped]


# Load-order edges that are not foreign keys.
#
# Each of these is a trigger from 0030, 0033 or 0048 asking whether a decision
# row exists before it will accept the row that depends on it. A foreign key
# would have said the same thing to `catalog.foreign_keys`, but these
# deliberately are not foreign keys: `evidence_promotions` identifies its
# target by a `<authority>|<url>` key string rather than by a column
# reference, a census verification matches on four columns including a whole
# line of PDF text, and a claim verification names its claim by id but is
# written without an FK so that it can be loaded ahead of the claims it
# vouches for. So the dependency is real, is enforced on every insert, and is
# invisible to the FK graph — which is exactly the shape of thing that gets
# discovered at row 400,000 of a load.
TRIGGER_EDGES: dict[str, tuple[str, ...]] = {
    "cdp_documents": ("evidence_promotions",),
    "committee_papers": ("evidence_promotions",),
    "foi_requests": ("evidence_promotions",),
    "workforce_census_metrics": ("census_verifications",),
    "claims": ("claim_verifications",),
    # Migration 0049's `ai_promotion_requires_provenance` guards
    # evidence_promotions itself, but only against the row's own columns
    # (NEW.actor_id, NEW.model_id, ...) — it names no other table, so there is
    # no load-order dependency to add. Listed with an empty tuple anyway,
    # because the test below pins every trigger to an edge and a trigger that
    # needed nothing would otherwise look identical to one nobody had
    # accounted for yet.
    "evidence_promotions": (),
}

# What each PostgreSQL type accepts from SQLite, and nothing else.
#
# The whole schema is three types (687 text columns, 103 bigint, 46 double
# precision); the rest are here so that a column added in some later migration
# fails loudly rather than being coerced by a rule nobody wrote down.
_ACCEPTS: dict[str, tuple[type, ...]] = {
    "text": (str,),
    "varchar": (str,),
    "bpchar": (str,),
    "int8": (int,),
    "int4": (int,),
    "int2": (int,),
    "float8": (float, int),
    "float4": (float, int),
    "bool": (int,),
    "bytea": (bytes,),
}

# Exactly representable as a double. An INTEGER-stored value arriving in a
# `double precision` column above this would be rounded on the way in, and a
# rounded figure that reads as exact is the failure this project is built
# against.
_MAX_EXACT_DOUBLE = 2 ** 53


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def open_source(path: Path) -> sqlite3.Connection:
    """The SQLite warehouse, read-only.

    `mode=ro` at the driver level rather than a promise in a docstring: this
    module runs against the authoritative copy of several months of polite
    crawling, and the guarantee that it cannot write has to hold even if
    something in here is wrong.
    """
    if not path.is_file():
        raise LoadError(f"no SQLite warehouse at {path} to migrate from.")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_order(conn) -> list[str]:
    """Every table a load has to write, parents before children.

    Ties are broken by name so that two runs produce the same order and the
    state file from one is readable by the other. A cycle is raised on rather
    than resolved: this schema has none, and inventing an order for one would
    be choosing which foreign key to violate.
    """
    tables = [t for t in catalog.table_names(conn) if t not in SOURCE_ONLY_TABLES]
    known = set(tables)

    parents: dict[str, set[str]] = {t: set() for t in tables}
    for child, parent in catalog.foreign_keys(conn):
        if child in known and parent in known:
            parents[child].add(parent)
    for child, required in TRIGGER_EDGES.items():
        if child in known:
            parents[child].update(p for p in required if p in known)

    ordered: list[str] = []
    placed: set[str] = set()
    remaining = sorted(tables)
    while remaining:
        ready = [t for t in remaining if parents[t] <= placed]
        if not ready:
            raise LoadError(
                "the tables cannot be ordered for loading — these depend on "
                f"each other in a cycle: {', '.join(sorted(remaining))}")
        for table in ready:
            ordered.append(table)
            placed.add(table)
        remaining = [t for t in remaining if t not in placed]
    return ordered


def _column_types(target, table: str) -> dict[str, tuple[int, str]]:
    """`{column: (type oid, type name)}` in the target, in column order.

    The oid goes to `COPY`'s `set_types` so psycopg dumps each value as the
    column's own type rather than guessing from the Python object; the name
    decides what this module will accept for it.
    """
    rows = target.execute(
        "SELECT a.attname AS name, a.atttypid AS oid, t.typname AS typname "
        "FROM pg_attribute a "
        "JOIN pg_type t ON t.oid = a.atttypid "
        "WHERE a.attrelid = to_regclass(?) AND a.attnum > 0 "
        "  AND NOT a.attisdropped "
        "ORDER BY a.attnum", (table,)).fetchall()
    return {r["name"]: (int(r["oid"]), r["typname"]) for r in rows}


def _coerce(value, typname: str, where: str):
    """One value, on its way from SQLite storage into a PostgreSQL column.

    Deliberately narrow. The only conversion performed is `int` into a
    floating-point column, and only where it is exact; everything else either
    goes across as it is or stops the migration. A loader that quietly casts
    is a loader that can change a figure, and the figures here are the point.
    """
    if value is None:
        return None

    accepted = _ACCEPTS.get(typname)
    if accepted is None:
        raise LoadError(
            f"{where}: no rule for loading into a {typname} column. Add one to "
            "pipeline/pgload.py._ACCEPTS, with the reasoning — an unlisted "
            "type is a type nobody has decided how to move.")
    if not isinstance(value, accepted) or isinstance(value, bool):
        raise LoadError(
            f"{where}: SQLite stored {type(value).__name__} "
            f"({value!r:.80}) in a {typname} column. Nothing here casts; "
            "the value has to be corrected in the source warehouse, or the "
            "column's type reconsidered.")

    if typname in ("float8", "float4") and isinstance(value, int):
        if abs(value) > _MAX_EXACT_DOUBLE:
            raise LoadError(
                f"{where}: {value} cannot be held exactly as a double, and "
                "loading it would round it.")
        return float(value)
    if typname == "text" and "\x00" in value:
        # PostgreSQL text cannot hold a NUL byte in any encoding or protocol.
        # Stripping it would alter archived source text — much of this column
        # family is extracted PDF prose — so this refuses instead. The live
        # warehouse has none; the check is here because the day it does, the
        # answer must not be a silent edit.
        raise LoadError(
            f"{where}: the text contains a NUL byte, which PostgreSQL cannot "
            "store. This has to be decided about, not stripped.")
    return value


def _coercer(table: str, column: str, typname: str):
    """`_coerce` with its column already bound. Built once per column rather
    than per value: the load calls it 655,000 times a table at the top end."""
    where = f"{table}.{column}"

    def coerce(value):
        return _coerce(value, typname, where)

    return coerce


def preflight(source: sqlite3.Connection, target) -> list[str]:
    """Everything checkable before a row is written. Returns the problems.

    Ordered cheapest-first only incidentally; the real ordering principle is
    that each of these has been the cause of a migration that half-succeeded
    somewhere, and the cost of finding out at row 400,000 is a full re-load.
    """
    problems: list[str] = []

    if db.backend_of(target) != "postgres":
        problems.append("the target is not a PostgreSQL connection.")
        return problems

    source_only = SOURCE_ONLY_TABLES | catalog.fts5_tables(source)
    source_tables = {t for t in catalog.table_names(source)
                      if t not in source_only}
    target_tables = {t for t in catalog.table_names(target)
                      if t not in SOURCE_ONLY_TABLES}
    missing = sorted(source_tables - target_tables)
    extra = sorted(target_tables - source_tables)
    if missing:
        problems.append(
            f"the target has no table {', '.join(missing)} — apply the "
            "PostgreSQL migrations first (any pipeline command does it).")
    if extra:
        problems.append(
            f"the target has tables the source does not: {', '.join(extra)}. "
            "The two schemas are not the same schema.")

    for table in sorted(source_tables & target_tables):
        in_source = portable_columns(source, table)
        in_target = portable_columns(target, table)
        if in_source != in_target:
            problems.append(
                f"{table}: columns differ. source {in_source}, "
                f"target {in_target}")

    source_fks = set(catalog.foreign_keys(source))
    target_fks = set(catalog.foreign_keys(target))
    if source_fks != target_fks:
        only_source = sorted(source_fks - target_fks)
        only_target = sorted(target_fks - source_fks)
        problems.append(
            "the foreign-key graphs differ, so the two databases do not "
            f"enforce the same references — only in source: {only_source}; "
            f"only in target: {only_target}")

    problems.extend(_storage_type_problems(source))
    problems.extend(null_key_problems(source))
    return problems


def _storage_type_problems(source: sqlite3.Connection) -> list[str]:
    """Columns where SQLite is holding something other than what it declared.

    SQLite's type affinity is a suggestion: an INTEGER column accepts `'n/a'`
    and keeps it as text. PostgreSQL's is not, so such a row stops the load —
    and it should stop it here, five seconds in, rather than after the two
    large tables have already gone across.

    Whole-warehouse scan, measured at 4.5 seconds on the 496 MiB live
    warehouse, because `typeof()` reads the storage class off each value
    without decoding it.
    """
    problems = []
    expected = {"TEXT": {"text"}, "INTEGER": {"integer"}, "REAL": {"real"},
                 "BLOB": {"blob"}}
    skip = SOURCE_ONLY_TABLES | catalog.fts5_tables(source)
    for table in catalog.table_names(source):
        if table in skip:
            continue
        columns = catalog.columns_of(source, table)
        if not columns:
            continue
        selects = ", ".join(
            f"group_concat(DISTINCT typeof({catalog.quote(c['name'])}))"
            for c in columns)
        row = source.execute(
            f"SELECT {selects} FROM {catalog.quote(table)}").fetchone()
        for column, found in zip(columns, row):
            if found is None:            # no rows
                continue
            declared = column["type"].upper().split("(")[0]
            allowed = expected.get(declared)
            kinds = set(found.split(","))
            if allowed is None:
                problems.append(
                    f"{table}.{column['name']}: declared {column['type']!r}, "
                    "which this loader has no rule for.")
            elif not kinds <= (allowed | {"null"}):
                problems.append(
                    f"{table}.{column['name']}: declared {declared} but "
                    f"holding {sorted(kinds - allowed - {'null'})}. "
                    "PostgreSQL will refuse it, and this will not cast it.")
    return problems


def null_key_problems(source: sqlite3.Connection) -> list[str]:
    """Rows whose primary key contains a NULL.

    SQLite permits it — a documented legacy quirk, kept for compatibility, and
    live: only `INTEGER PRIMARY KEY` is exempt. PostgreSQL makes every key
    column NOT NULL, so such a row cannot be loaded at all.
    `tests/test_postgres_live.py` pins the schema-level difference and says in
    as many words that the loader has to check the data rather than assume it.
    This is that check.
    """
    problems = []
    for table in catalog.table_names(source):
        if table in SOURCE_ONLY_TABLES:
            continue
        key = catalog.primary_key(source, table)
        if not key:
            continue
        predicate = " OR ".join(f"{catalog.quote(c)} IS NULL" for c in key)
        count = source.execute(
            f"SELECT COUNT(*) FROM {catalog.quote(table)} "
            f"WHERE {predicate}").fetchone()[0]
        if count:
            problems.append(
                f"{table}: {count:,} row(s) have a NULL in the primary key "
                f"({', '.join(key)}). PostgreSQL cannot hold them.")
    return problems


def copy_table(source: sqlite3.Connection, target, table: str) -> int:
    """One table, streamed through `COPY FROM STDIN`. Returns rows written.

    Streamed rather than batched: the rows are read straight off a SQLite
    cursor and written to the socket, so the 477,199-row table costs the same
    memory as the 13-row one. The caller commits — one transaction per table
    is what makes an interrupted run leave whole tables rather than partial
    ones.
    """
    # `portable_columns` drops any PostgreSQL-only derived column (authorities.geom):
    # SQLite has no value to send for it, and it is rebuilt afterwards by
    # pipeline/geo.py. COPY names the remaining columns explicitly, so PostgreSQL
    # fills the skipped one with its default.
    columns = portable_columns(target, table)
    types = _column_types(target, table)
    missing = [c for c in columns if c not in types]
    if missing:
        raise LoadError(f"{table}: no type for column(s) {missing}")

    coercers = [_coercer(table, c, types[c][1]) for c in columns]
    oids = [types[c][0] for c in columns]
    # Named explicitly on both sides rather than `SELECT *` into `COPY table`:
    # the two orders are checked by preflight, and depending on that check
    # from here as well would make a column added to one side a silent
    # off-by-one across every row of the table.
    column_list = ", ".join(catalog.quote(c) for c in columns)
    key = catalog.primary_key(source, table)
    key_positions = [columns.index(c) for c in key if c in columns]

    written = 0
    with target.raw.cursor() as cursor:
        with cursor.copy(
                f"COPY {catalog.quote(table)} ({column_list}) "
                "FROM STDIN") as copy:
            copy.set_types(oids)
            for row in source.execute(
                    f"SELECT {column_list} FROM {catalog.quote(table)}"):
                try:
                    copy.write_row([coerce(value) for coerce, value
                                     in zip(coercers, row)])
                except LoadError as exc:
                    identity = ", ".join(
                        f"{columns[p]}={row[p]!r}" for p in key_positions)
                    raise LoadError(
                        f"{exc} (row {written + 1:,}"
                        f"{', ' + identity if identity else ''})") from None
                written += 1
    return written


def reset_sequences(target) -> list[dict]:
    """Point every identity sequence past the ids that were just loaded.

    The ids are copied verbatim so that every foreign key and every recorded
    `evidence_promotions.id` still points where it did — see the note in
    `pipeline/migrations/postgres/README.md` on why the columns are
    `GENERATED BY DEFAULT`. A sequence left at 1 afterwards would hand the
    next insert an id that is already taken, and the failure would arrive as a
    unique-violation on the first review decision somebody made.
    """
    rows = target.execute(
        "SELECT table_name AS tbl, column_name AS col "
        "FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND is_identity = 'YES' "
        "ORDER BY table_name, column_name").fetchall()

    out = []
    for row in rows:
        table, column = row["tbl"], row["col"]
        # `+ 1, false` rather than `max, true`: an empty table has no maximum,
        # and `setval(seq, 0)` is below the sequence's minimum value and
        # raises. This spelling gives "the next value is max + 1" in both
        # cases.
        nxt = target.execute(
            f"SELECT setval(pg_get_serial_sequence(?, ?), "
            f"COALESCE(MAX({catalog.quote(column)}), 0) + 1, false) "
            f"FROM {catalog.quote(table)}", (table, column)).fetchone()[0]
        out.append({"table": table, "column": column, "next_value": int(nxt)})
    return out


def truncate_all(target, tables: list[str]) -> None:
    """Empty the target's data tables, keeping its migration ledger.

    One statement listing every table, so the foreign keys between them are
    satisfied at the end of it without `CASCADE` — which would reach tables
    not on the list, and the one table not on the list is the ledger that
    records what schema this database is.
    """
    if not tables:
        return
    listed = ", ".join(catalog.quote(t) for t in tables)
    target.execute(f"TRUNCATE {listed} RESTART IDENTITY")
    target.commit()


def state_path_for(settings: Settings | None = None) -> Path:
    """Where an interrupted migration leaves its place.

    Beside the warehouse it is reading, because that is what the state is
    about: a state file next to one warehouse and describing another is how a
    resume loads half of the wrong database.
    """
    settings = settings or get_settings()
    return settings.database_path.with_name("pg-migration-state.json")


def _load_state(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise LoadError(
            f"{path} is not readable as a migration state file ({exc}). "
            "Delete it to start again, having first decided what is already "
            "in the target.") from exc


def _write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def migrate(source: sqlite3.Connection, target, *, settings: Settings | None = None,
             state_path: Path | None = None, resume: bool = False,
             truncate: bool = False, only: list[str] | None = None,
             skip_preflight: bool = False, on_table=None) -> dict:
    """Load the SQLite warehouse into PostgreSQL. Returns the run's summary.

    `only` runs a named subset, for a table that failed on its own; it skips
    the empty-target check for the tables it is not touching, which makes it
    the one option here that can produce a half-loaded warehouse. It is for
    recovering a load, not for performing one.
    """
    settings = settings or get_settings()
    path = state_path or state_path_for(settings)
    started = time.monotonic()

    if not skip_preflight:
        problems = preflight(source, target)
        if problems:
            raise LoadError(
                "the migration was refused before writing anything:\n  - "
                + "\n  - ".join(problems))

    order = load_order(target)
    if only:
        unknown = [t for t in only if t not in order]
        if unknown:
            raise LoadError(f"no such table to load: {', '.join(unknown)}")
        wanted = [t for t in order if t in set(only)]
    else:
        wanted = list(order)

    source_path = Path(
        source.execute("PRAGMA database_list").fetchone()["file"] or "")
    state = _load_state(path)
    done: dict[str, dict] = {}

    if state is not None and not resume:
        if state.get("finished_at"):
            raise LoadError(
                f"{path} records a migration that finished at "
                f"{state['finished_at']}. Delete it to run another one, so "
                "that starting over is a deliberate act.")
        raise LoadError(
            f"{path} records a migration that did not finish. Re-run with "
            "resume to carry on from where it stopped, or delete the file "
            "and start again — but decide what is in the target first.")
    if state is not None and resume:
        if state.get("source") != str(source_path):
            raise LoadError(
                f"{path} is the state of a migration from {state.get('source')}, "
                f"not from {source_path}. Two different sources are two "
                "different migrations.")
        done = dict(state.get("tables", {}))
        for table, record in sorted(done.items()):
            count = target.execute(
                f"SELECT COUNT(*) FROM {catalog.quote(table)}").fetchone()[0]
            if count != record["rows"]:
                raise LoadError(
                    f"resume refused: {table} holds {count:,} rows in the "
                    f"target and the state file says {record['rows']:,}. "
                    "Something else has written to this database since.")

    remaining = [t for t in wanted if t not in done]

    if truncate:
        truncate_all(target, [t for t in order if t not in done] if resume
                      else list(order))
    elif not resume:
        occupied = []
        for table in remaining:
            count = target.execute(
                f"SELECT COUNT(*) FROM {catalog.quote(table)}").fetchone()[0]
            if count:
                occupied.append(f"{table} ({count:,})")
        if occupied:
            raise LoadError(
                "the target already holds rows in: " + ", ".join(occupied)
                + ". Pass truncate to empty it first, which will discard "
                "them, or point this at an empty database.")

    if state is None:
        state = {
            "version": 1,
            "started_at": _utcnow(),
            "source": str(source_path),
            "source_bytes": source_path.stat().st_size if source_path.is_file() else None,
            "target": settings.redacted_database_url,
            "order": order,
            "tables": {},
            "finished_at": None,
        }
    state["tables"] = done
    _write_state(path, state)

    log.info("pgload.starting", tables=len(remaining),
              already_done=len(done), source=str(source_path))

    for table in remaining:
        table_started = time.monotonic()
        expected = source.execute(
            f"SELECT COUNT(*) FROM {catalog.quote(table)}").fetchone()[0]
        if on_table:
            on_table(table, expected, None)
        try:
            written = copy_table(source, target, table)
        except Exception:
            # The table's own transaction is what is being abandoned, and it
            # holds only this table's rows: the ones before it are committed
            # and recorded, and this one is as if it had not started. Rolling
            # back explicitly rather than leaving the connection in a failed
            # transaction, so that the caller can still read counts out of it
            # while deciding what to do.
            target.rollback()
            _write_state(path, state)
            raise
        target.commit()
        elapsed = time.monotonic() - table_started
        if written != expected:
            raise LoadError(
                f"{table}: read {expected:,} rows from the source and wrote "
                f"{written:,}. The source is being written to, or something "
                "is wrong with this loader; either way the target is not a "
                "copy of anything.")
        done[table] = {"rows": written, "seconds": round(elapsed, 2),
                        "finished_at": _utcnow()}
        _write_state(path, state)
        log.info("pgload.table", table=table, rows=written,
                  seconds=round(elapsed, 2))
        if on_table:
            on_table(table, expected, written)

    sequences = reset_sequences(target)
    target.commit()

    # authorities.geom is derived, not copied (portable_columns drops it), so
    # rebuild it from the geometry_geojson that just landed. No-op unless the
    # target is PostgreSQL with PostGIS.
    from pipeline import geo

    geo.refresh_authority_geometry(target)
    target.commit()

    # A run that was told to load some of the tables has not finished the
    # migration, whatever it finished. Marking it done would make the next
    # ordinary run refuse with "that one finished" and offer deleting the
    # state file as the way on, which is how a warehouse ends up missing the
    # tables nobody thought to name.
    if only is None:
        state["finished_at"] = _utcnow()
    state["sequences"] = sequences
    state["elapsed_seconds"] = round(time.monotonic() - started, 1)
    _write_state(path, state)

    summary = {
        "tables": len(done),
        "loaded_now": len(remaining),
        "rows": sum(r["rows"] for r in done.values()),
        "sequences": sequences,
        "elapsed_seconds": state["elapsed_seconds"],
        "state_path": str(path),
        "counts": {t: r["rows"] for t, r in done.items()},
    }
    log.info("pgload.complete", rows=summary["rows"], tables=summary["tables"],
              seconds=summary["elapsed_seconds"])
    return summary


def plan(source: sqlite3.Connection, target) -> list[dict]:
    """What a load would do, in the order it would do it."""
    return [{"table": table,
              "rows": source.execute(
                  f"SELECT COUNT(*) FROM {catalog.quote(table)}").fetchone()[0]}
             for table in load_order(target)]
