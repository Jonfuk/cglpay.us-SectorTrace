"""Is the warehouse fresh, complete, and honest about its gaps?

Three questions the operator UI could not previously answer without writing
SQL, and one of them has a wrong answer that is very easy to publish.

**Coverage.** England has 347 local authorities in this warehouse and only 159
of them are responsible for public health: the other 188 are non-metropolitan
districts, which have no drug and alcohol treatment role at all. Counting
grant coverage against 347 gives "155 of 347, 45%", which is both arithmetic
and nonsense -- the missing 188 are not gaps, they are authorities that should
never have had a row. Against the tier that is actually responsible it is 155
of 159. So the tier is the default here and the denominator travels with every
number, because a coverage figure without its denominator is the kind of thing
that ends up in a campaign document.

**Freshness.** Not "when did a module last run" -- a module that ran this
morning and fetched nothing new is not fresh evidence -- but when the rows
themselves were retrieved, per table, and when each source host was last
spoken to.

**Failures.** parse_failures is a bug list about this pipeline's own parsers,
grouped by the thing that actually distinguishes them: the reason. Twenty-two
failures with three distinct reasons is three problems, not twenty-two.

Everything here reads. The only write is the integrity check, which is a job
because it can take a while on a 230 MB file.
"""
from __future__ import annotations

from pathlib import Path

from pipeline import catalog, db, operational_snapshots
from pipeline.web import queries

# Authorities responsible for public health, and therefore the ones any
# treatment-sector evidence should exist for. Non-metropolitan districts are
# deliberately not here: see the module docstring.
UPPER_TIER = ("county", "unitary", "london_borough", "metropolitan_district")

# The evidence a responsible authority could have, and where it lives. An
# explicit list rather than a scan of the schema: this is a statement about
# what the pipeline is *for*, and a new table appearing should not silently
# change what "covered" means. Table and column names come from here and never
# from a request, so they are safe to interpolate.
#
# `candidates` tables are shown beside their confirmed counterparts rather than
# folded into them. m09 and m10 currently hold hundreds of candidates and zero
# confirmed documents, and a matrix that hid that would be reporting the
# pipeline as more finished than it is.
COVERAGE_COLUMNS: tuple[tuple[str, str, str, str], ...] = (
    ("Grant", "public_health_grants", "ons_code", "m11_public_health_grant"),
    ("Budget", "la_revenue_budgets", "ons_code", "m13_la_budgets"),
    ("Contracts", "contracts", "buyer_ons_code", "m01_procurement"),
    ("NDTMS", "ndtms_la_statistics", "ons_code", "m07_ndtms"),
    # Its own column rather than folded into the one above. The two are
    # different reports on different schedules -- m07 reads the annual
    # publications, m27 the monthly provisional report -- and an authority can
    # legitimately have one and not the other. A single merged column would
    # answer "is there any NDTMS row for this authority", which is not a
    # question anyone has, and would hide exactly the gap worth seeing.
    ("NDTMS monthly", "ndtms_monthly_statistics", "ons_code", "m27_ndtms_monthly"),
    ("Fingertips", "fingertips_la_values", "ons_code", "m12_fingertips"),
    ("CQC", "cqc_locations", "local_authority_ons_code", "m05_cqc"),
    ("CDP docs", "cdp_documents", "authority_ons_code", "m09_cdp_documents"),
    ("CDP cands", "cdp_document_candidates", "authority_ons_code", "m09_cdp_documents"),
    ("Papers", "committee_papers", "authority_ons_code", "m10_committee_papers"),
    ("Paper cands", "committee_paper_candidates", "authority_ons_code",
      "m10_committee_papers"),
    ("FOI", "foi_requests", "ons_code", "m15_foi"),
    ("FOI cands", "foi_request_candidates", "ons_code", "m15_foi"),
    # The file-level row is the honest coverage signal for council spend. An
    # unreadable file is still a council reached and a publication found; the
    # parse status says why it produced no line-item rows. Counting only
    # `council_spend` would turn that known parser gap into an apparent absence.
    ("Spend files", "council_spend_files", "authority_ons_code",
     "m24_council_spend"),
)


def _table_exists(conn: db.Connection, name: str) -> bool:
    return catalog.object_type(conn, name) == "table"


# --- coverage -------------------------------------------------------------------


def coverage(conn: db.Connection, tier: str = "upper") -> dict:
    """Authorities down the side, evidence across the top, counts in the cells.

    `tier` is "upper" (the 159 responsible for public health) or "all". All is
    offered because contracts and CQC locations legitimately attach to
    districts; it is not the default because for everything else a district
    row is a guaranteed zero that means nothing.
    """
    if tier not in ("upper", "all"):
        raise queries.QueryError(f"tier must be 'upper' or 'all', got {tier!r}.")

    if tier == "upper":
        placeholders = ", ".join("?" for _ in UPPER_TIER)
        authorities = conn.execute(
            f"SELECT ons_code, name, type, region FROM authorities "
            f"WHERE type IN ({placeholders}) ORDER BY region, name", UPPER_TIER).fetchall()
    else:
        authorities = conn.execute(
            "SELECT ons_code, name, type, region FROM authorities "
            "ORDER BY region, name").fetchall()

    rows = {row["ons_code"]: {
        "ons_code": row["ons_code"], "name": row["name"],
        "type": row["type"], "region": row["region"], "cells": {},
    } for row in authorities}

    columns = []
    for label, table, column, module in COVERAGE_COLUMNS:
        if not _table_exists(conn, table):
            columns.append({"label": label, "table": table, "module": module,
                             "covered": 0, "total_rows": 0, "missing": True})
            continue

        covered = 0
        total = 0
        for row in conn.execute(
                f"SELECT {column} AS code, COUNT(*) AS n FROM {table} "
                f"WHERE {column} IS NOT NULL GROUP BY {column}"):
            total += row["n"]
            target = rows.get(row["code"])
            if target is None:
                # A code we hold evidence for but do not list as an authority
                # of this tier -- a district under "upper", or an abolished
                # code. Counted in the total, not in the coverage.
                continue
            target["cells"][label] = row["n"]
            covered += 1

        columns.append({"label": label, "table": table, "module": module,
                         "covered": covered, "total_rows": total, "missing": False})

    return {
        "tier": tier,
        "authorities": list(rows.values()),
        "columns": columns,
        # The denominator, stated rather than left to be counted off the rows.
        "authority_count": len(rows),
        "upper_tier_types": list(UPPER_TIER),
    }


# --- freshness and warehouse state -----------------------------------------------


def warehouse(conn: db.Connection, settings) -> dict:
    """Size, shape, and whether the schema on disk is the schema that ran.

    The migration half of this is the part that matters: what the ledger says
    was applied, what is on disk, and the two ways those can disagree. The size
    half is PostgreSQL's `pg_database_size`.
    """
    applied = [row["filename"] for row in conn.execute(
        "SELECT filename FROM schema_migrations ORDER BY filename")]
    on_disk = sorted(p.name for p in db.migrations_dir_for(settings).glob("*.sql"))

    common = {
        "applied_migrations": applied,
        "migrations_on_disk": on_disk,
        "unapplied": [name for name in on_disk if name not in applied],
        # A migration recorded as applied with no file behind it means this
        # warehouse was built by a checkout that has since changed.
        "applied_without_file": [name for name in applied if name not in on_disk],
    }

    # No file, no sidecars, no page count, and no freelist: PostgreSQL's
    # dead-tuple space is per-table and reclaimed by autovacuum rather than a
    # single database number. `pg_database_size` is the honest total; anything
    # finer belongs in a panel that measures per-relation bloat properly.
    size = conn.execute("SELECT pg_database_size(current_database()) AS n").fetchone()["n"]
    return {
        "backend": "postgres",
        "path": settings.redacted_database_url,
        "files": {},
        "bytes": size,
        "page_size": None,
        "page_count": None,
        "free_bytes": None,
        **common,
    }


# What each extension buys, for the operator reading the panel. The feature
# still works without it — this names the fallback so "slow" or "missing" has
# an explanation rather than a shrug.
_EXTENSION_BACKS = {
    "vector": "semantic-search ANN index (else an exact cosine sweep in Python)",
    "pg_trgm": "fuzzy-name ranking and the portal contract text filter (else LIKE / difflib)",
    "postgis": "geometry column and spatial index on authorities (else shapely centroids)",
}


def extensions(conn: db.Connection) -> list[dict]:
    """The extensions the warehouse uses where the server provides them.

    Empty on SQLite. On PostgreSQL, one row per name in
    `db.WAREHOUSE_EXTENSIONS`: whether the server carries it at all
    (`available`), whether it is installed in this database (`installed`), and
    the installed version. `pg_available_extensions` is readable by any role,
    so this needs none of the privilege `_postgres_integrity` goes without.
    """
    if db.backend_of(conn) != "postgres":
        return []

    names = db.WAREHOUSE_EXTENSIONS
    placeholders = ",".join("?" for _ in names)
    seen = {
        row["name"]: row for row in conn.execute(
            f"SELECT e.name, e.default_version, i.extversion AS installed_version "
            f"FROM pg_available_extensions e "
            f"LEFT JOIN pg_extension i ON i.extname = e.name "
            f"WHERE e.name IN ({placeholders})", list(names))
    }
    out = []
    for name in names:
        row = seen.get(name)
        out.append({
            "name": name,
            "available": row is not None,
            "installed": bool(row and row["installed_version"]),
            "version": (row["installed_version"] if row else None)
                        or (row["default_version"] if row else None),
            "backs": _EXTENSION_BACKS.get(name, ""),
        })
    return out


def geometry_status(conn: db.Connection) -> dict | None:
    """Whether the derived PostGIS geometry kept up with its source.

    `authorities.geom` (migration 0070) is built from `geometry_geojson` by
    `pipeline/geo.py`. `with_geom` should equal `with_geojson`, and `invalid`
    should be zero — `ST_MakeValid` runs in the derivation, so a non-zero
    count is a boundary PostGIS still cannot repair. Returns None on SQLite,
    on a PostgreSQL server without PostGIS, or before migration 0070's column
    exists.
    """
    if db.backend_of(conn) != "postgres" or not db.has_extension(conn, "postgis"):
        return None
    has_column = conn.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = current_schema() "
        "  AND table_name = 'authorities' AND column_name = 'geom'").fetchone()
    if not has_column:
        return None
    row = conn.execute(
        "SELECT COUNT(*) FILTER (WHERE geometry_geojson IS NOT NULL) AS with_geojson, "
        "       COUNT(*) FILTER (WHERE geom IS NOT NULL) AS with_geom, "
        "       COUNT(*) FILTER (WHERE geom IS NOT NULL AND NOT ST_IsValid(geom)) AS invalid "
        "FROM authorities").fetchone()
    return {"with_geojson": row["with_geojson"], "with_geom": row["with_geom"],
            "invalid": row["invalid"]}


def hosts(conn: db.Connection) -> list[dict]:
    """Every source host this warehouse has spoken to, and when it last did.

    From http_cache, which is written on every conditional request, so this is
    "when did we last ask" rather than "when did something change".
    """
    if not _table_exists(conn, "http_cache"):
        return []
    return [dict(row) for row in conn.execute(
        "SELECT host, COUNT(*) AS urls, MAX(updated_at) AS newest, "
        "       MIN(updated_at) AS oldest "
        "FROM http_cache GROUP BY host ORDER BY urls DESC")]


def graph_status(conn: db.Connection) -> dict:
    """The evidence graph's own operational state — not its content.

    `docs/evidence-graph.md` documents a whole subsystem (migration `0050`:
    entities, relationships, claims, a Neo4j projection, NetworkX metrics)
    that until now had no answer anywhere in the UI to "has this ever been
    run, and how stale is it" — a CLI-only `pipeline graph status` was the
    only way to know. Cheap, unlike `storage()` and `freshness()`: one row
    from `graph_projection_runs` (indexed, tiny) and one count from
    `graph_projection_queue`, so unlike those two this belongs in the cheap
    half of the tab.

    `_table_exists` first because the graph tables are optional-extra
    territory (`uv sync --extra graph`) applied by migration `0050` like any
    other — a warehouse that predates it, or one where nobody has ever
    touched the graph, must not fail the whole Health tab over it.
    """
    if not _table_exists(conn, "graph_projection_runs"):
        return {"last_run": None, "pending_queue": 0}

    last_run = conn.execute(
        "SELECT run_id, started_at, completed_at, status, entity_count, "
        "relationship_count, claim_count, error_detail "
        "FROM graph_projection_runs ORDER BY started_at DESC LIMIT 1").fetchone()
    pending = conn.execute(
        "SELECT COUNT(*) FROM graph_projection_queue "
        "WHERE processed_at IS NULL").fetchone()[0]
    return {
        "last_run": dict(last_run) if last_run else None,
        "pending_queue": int(pending),
    }


def document_status(conn: db.Connection) -> dict:
    """The document-analysis layer's own operational state — registered,
    parsed and searchable documents, not their content.

    `docs/document-analysis.md` documents a whole subsystem (migration
    `0053`: inspection, OCR, parsing, classification, quality) that until
    now had no answer anywhere in the UI to "how much has been processed" —
    `pipeline documents stats` on the CLI was the only way to know, the same
    shape `graph_status` closed for the evidence graph.

    Cheap: a handful of `COUNT(*)` over tables that only grow as documents
    are processed, not a per-document or per-page scan — so, like
    `graph_status`, this belongs in the cheap `health()` bundle.
    """
    if not _table_exists(conn, "document_processing_states"):
        return {"registered": 0, "parsed": 0, "failed": 0, "documents": 0}

    registered = conn.execute(
        "SELECT COUNT(*) FROM document_processing_states").fetchone()[0]
    parsed = conn.execute(
        "SELECT COUNT(*) FROM document_processing_states "
        "WHERE parse_status = 'SUCCESS'").fetchone()[0]
    failed = conn.execute(
        "SELECT COUNT(*) FROM document_processing_states "
        "WHERE parse_status = 'FAILED'").fetchone()[0]
    documents = conn.execute("SELECT COUNT(*) FROM document_records").fetchone()[0]
    return {"registered": int(registered), "parsed": int(parsed),
            "failed": int(failed), "documents": int(documents)}


def freshness(conn: db.Connection) -> list[dict]:
    """Newest `retrieved_at` per table that records one.

    The honest freshness signal. A module that ran this morning and found
    nothing new leaves a recent cursor and stale evidence; the rows know when
    they were actually fetched.

    This is the slow one, and deliberately so. `COUNT(*), MAX(retrieved_at),
    MIN(retrieved_at)` is a full scan of every table: SQLite can answer MAX or
    MIN from an index in one seek, but only when it is the single aggregate in
    the query, so asking for all three together scans regardless. On the real
    warehouse that is 1.6 seconds for contracts alone, 98,588 rows.

    The fix is not an index. It would mean `retrieved_at` indexes on twenty
    tables, paid for on every insert by every module, to speed up a panel
    somebody looks at occasionally. It is served on its own route instead, so
    the rest of the Health tab does not wait for it.
    """
    out = []
    for name in catalog.tables_with_column(conn, "retrieved_at"):
        if queries.is_restricted(name):
            continue
        quoted = queries._quote(name)
        try:
            stats = conn.execute(
                f"SELECT COUNT(*) AS rows_held, MAX(retrieved_at) AS newest, "
                f"       MIN(retrieved_at) AS oldest FROM {quoted}").fetchone()
        except db.Error:
            # Skip the table, keep the panel: one unreadable table is not a
            # reason to report nothing about the other nineteen.
            #
            # This `continue` is why the PostgreSQL read connection runs in
            # autocommit. Inside a transaction a failed statement aborts the
            # whole transaction, so the first failure here would make every
            # remaining iteration raise InFailedSqlTransaction and the panel
            # would silently truncate at the first bad table rather than skip
            # it — a wrong answer that looks like a right one. On SQLite this
            # loop has always been safe; the connection setting is what makes
            # it mean the same thing on both. See pipeline/pg.py.
            continue
        out.append({"table": name, "rows": stats["rows_held"],
                     "newest": stats["newest"], "oldest": stats["oldest"]})
    return out


# --- storage ----------------------------------------------------------------------
#
# W-21: the health cards reported the warehouse's own size and nothing else,
# while the raw archive beside it is 3.5 GiB and growing -- and P-02's answer
# to that growth is not deletion, because the archive *is* the audit trail. It
# is "measure it until it hurts", and the only instrument was a one-off audit
# written into the roadmap. The operator got no signal at all until a disk
# filled.
#
# So these are stat-ed on every visit rather than once. Four directories, each
# with a different reason to be watched: the archive grows without bound by
# design, backups are pruned by a retention rule that could be wrong, exports
# are rewritten, and logs now rotate and can be checked against the ceiling
# that rotation sets.

STORAGE_DIRS: tuple[tuple[str, str, str], ...] = (
    ("raw_archive", "raw_archive_dir",
      "The audit trail: the exact bytes behind every row. Grows without bound "
      "by design — deletion would break the provenance chain."),
    ("backups", "backup_dir",
      "VACUUM INTO snapshots. Pruned by --keep; labelled backups are never "
      "pruned."),
    ("exports", "export_output_dir",
      "What the export targets wrote. Rewritten, not accumulated."),
    ("logs", "logs_dir",
      "The per-module audit log. Rotated at a fixed ceiling per module."),
)


def storage(settings) -> list[dict]:
    """Bytes and file counts for the directories this pipeline writes into.

    A walk rather than a cached figure: the number that matters is the one now,
    and a growth curve nobody can see is a growth curve measured once.

    On its own route, and not in `health()`, for the same reason `freshness` is
    — measured in a browser against the real archive, this is **six seconds**:
    8,502 files and 4.5 GB, stat-ed one at a time. It was in the cheap half
    first, and making the whole Health tab wait six seconds to render a size in
    megabytes is precisely the shape that docstring warns about.
    """
    out = []
    for key, attribute, note in STORAGE_DIRS:
        directory = Path(getattr(settings, attribute))
        entry = {"key": key, "path": str(directory), "note": note,
                  "exists": directory.is_dir(), "files": 0, "bytes": 0,
                  "newest": None}
        if entry["exists"]:
            newest = None
            for path in directory.rglob("*"):
                # `is_file()` follows links, and a link out of the tree is
                # somebody else's bytes: counted where it points, not here.
                if not path.is_file() or path.is_symlink():
                    continue
                stat = path.stat()
                entry["files"] += 1
                entry["bytes"] += stat.st_size
                newest = max(newest or 0.0, stat.st_mtime)
            if newest:
                from datetime import datetime, timezone

                entry["newest"] = datetime.fromtimestamp(
                    newest, tz=timezone.utc).isoformat(timespec="seconds")
        out.append(entry)
    # The local row remains the recovery mirror. The extra row makes the
    # operational distinction visible without exposing an object or URL.
    remote = {"key": "raw_archive_remote", "path": settings.archive_backend,
              "note": "Primary archive backend; objects remain private.",
              "exists": False, "files": 0, "bytes": 0, "newest": None,
              "backend": settings.archive_backend, "last_verification": None,
              "mirror_lag": None}
    try:
        from pipeline.archive import get_archive
        remote_inventory = get_archive(settings).inventory()
        remote.update(exists=True, files=remote_inventory["files"],
                      bytes=remote_inventory["bytes"])
        local = out[0]
        remote["mirror_lag"] = {"objects": remote["files"] - local["files"],
                                "bytes": remote["bytes"] - local["bytes"]}
        manifest = Path(settings.backup_dir) / "archive-manifest.json"
        if manifest.is_file():
            import json
            remote["last_verification"] = json.loads(manifest.read_text(encoding="utf-8")).get("verified_at")
    except Exception as exc:  # health must still show local storage if S3 is down
        remote["error"] = f"{type(exc).__name__}: {exc}"
    out.append(remote)
    return out


def health(conn: db.Connection, settings) -> dict:
    """The cheap half: size, migrations, and which hosts were last asked.

    Neither freshness nor storage is here, and for the same reason: one is
    seconds of table scans and the other is seconds of stat calls over 8,502
    archived files. Making the whole tab wait for either to render a size in
    megabytes is the wrong shape, and each is served on its own route.
    """
    return {
        "warehouse": warehouse(conn, settings),
        "extensions": extensions(conn),
        "geometry": geometry_status(conn),
        "hosts": hosts(conn),
        "graph": graph_status(conn),
        "documents": document_status(conn),
    }


def cached_operational(conn: db.Connection, settings, key: str, compute) -> dict:
    """Serve the latest successful expensive value, refreshing when stale.

    A failed refresh never erases the last useful answer; it marks that answer
    stale and exposes the refresh error for the operator UI.
    """
    max_age = getattr(settings, "operational_snapshot_max_age_seconds", 900)
    current = operational_snapshots.load(conn, key, max_age_seconds=max_age)
    if current is not None and not current["stale"]:
        return {"value": current["payload"], "snapshot": current}
    started = __import__("time").perf_counter()
    try:
        value = compute()
        try:
            operational_snapshots.save(
                conn, key, value,
                duration_ms=(__import__("time").perf_counter() - started) * 1000)
            conn.commit()
            snapshot = operational_snapshots.load(conn, key, max_age_seconds=max_age)
        except db.Error:
            # The current web read connection may be enforced query-only. The
            # calculated value is still valid; persistence is an optimisation
            # and cannot turn an otherwise healthy route into a 500.
            conn.rollback()
            snapshot = None
        return {"value": value, "snapshot": snapshot}
    except Exception as exc:
        conn.rollback()
        if current is not None:
            operational_snapshots.record_refresh_failure(conn, key, str(exc))
            conn.commit()
            current["stale"] = True
            current["refresh_error"] = str(exc)[:2000]
            return {"value": current["payload"], "snapshot": current}
        raise


# --- parse failures ---------------------------------------------------------------


def failures(conn: db.Connection, module: str | None = None,
              search: str | None = None, limit: int = 100, offset: int = 0) -> dict:
    """Grouped by (module, field, reason), because that is one bug.

    The detail rows are what a parser author needs -- the raw fragment that
    could not be read and the URL it came from -- so both are returned: the
    groups to see how many distinct problems there are, and a page of rows to
    see what they look like.
    """
    where = []
    params: list = []
    if module:
        where.append("module = ?")
        params.append(module)
    if search:
        where.append("(reason LIKE ? ESCAPE '\\' OR raw_fragment LIKE ? ESCAPE '\\' "
                      "OR field_name LIKE ? ESCAPE '\\' OR source_url LIKE ? ESCAPE '\\')")
        params.extend([f"%{queries.escape_like(search)}%"] * 4)

    clause = f"WHERE {' AND '.join(where)}" if where else ""
    limit = max(1, min(limit, queries.MAX_PAGE_SIZE))

    total = conn.execute(
        f"SELECT COUNT(*) FROM parse_failures {clause}", params).fetchone()[0]

    groups = [dict(row) for row in conn.execute(
        f"SELECT module, field_name, reason, COUNT(*) AS n, "
        f"       MAX(created_at) AS newest, MIN(created_at) AS oldest "
        f"FROM parse_failures {clause} "
        f"GROUP BY module, field_name, reason ORDER BY n DESC, module LIMIT 200", params)]

    rows = [dict(row) for row in conn.execute(
        f"SELECT id, module, field_name, reason, raw_fragment, source_url, created_at "
        f"FROM parse_failures {clause} ORDER BY created_at DESC, id DESC "
        f"LIMIT ? OFFSET ?", [*params, limit, offset])]

    modules = [row["module"] for row in conn.execute(
        "SELECT module, COUNT(*) AS n FROM parse_failures "
        "GROUP BY module ORDER BY n DESC")]

    return {"total": total, "groups": groups, "rows": rows, "modules": modules,
             "limit": limit, "offset": offset}


# --- integrity ---------------------------------------------------------------------


def integrity_check(settings) -> list[dict]:
    """`PRAGMA integrity_check` plus a foreign-key sweep.

    Run as a job rather than inline: it walks every page of a 230 MB file and
    an HTTP request that takes forty seconds looks like a hung UI. Opened
    read-only -- a corruption check that could write is not a check.
    """
    conn = queries.readonly_connection(settings)
    try:
        if db.backend_of(conn) == "postgres":
            return _postgres_integrity(conn)
        integrity = [row[0] for row in conn.execute("PRAGMA integrity_check")]
        foreign_keys = [dict(zip(("table", "rowid", "parent", "fkid"), row))
                         for row in conn.execute("PRAGMA foreign_key_check")]
    finally:
        conn.close()

    return [{
        "integrity": integrity,
        "ok": integrity == ["ok"] and not foreign_keys,
        "foreign_key_violations": foreign_keys[:200],
        "foreign_key_violation_count": len(foreign_keys),
        "checked": "every page of the file and every foreign key",
        "not_checked": "",
    }]


def _postgres_integrity(conn) -> list[dict]:
    """The half of `PRAGMA integrity_check` that PostgreSQL can answer.

    Phase 1 refused this outright rather than return an ok nobody could
    distinguish from a check, and left the work to the phase doing backup and
    restore, on the grounds that both answer "is this warehouse intact?". This
    is that work, and it is deliberately two thirds of it:

      * **Every foreign key is swept**, one generated anti-join per constraint
        — the analogue of `PRAGMA foreign_key_check`, and the check that would
        notice a restore or a load having produced orphans.
      * **Every constraint is asked whether it is validated.** A `NOT VALID`
        constraint is enforced for new rows and never checked against the old
        ones, so it is a guarantee the schema claims and does not have. SQLite
        cannot express that state and therefore cannot have it.
      * **Pages are not checked.** There is no in-database equivalent of
        walking the file: `pg_amcheck` is a separate binary, and the `amcheck`
        extension is not installed on this server — installing it needs
        superuser, which `sectortrace_app` deliberately is not. So the panel
        says what it looked at rather than reporting a clean bill for a check
        that did not run.

    Read through the reader role like everything else here, which is also why
    the sweep is `COUNT(*)` per constraint rather than anything that writes a
    temporary table.
    """
    constraints = conn.execute(
        "SELECT c.conname AS name, c.contype AS kind, c.convalidated AS validated, "
        "       c.conrelid::regclass::text AS child, "
        "       c.confrelid::regclass::text AS parent, "
        "       c.conkey AS child_columns, c.confkey AS parent_columns "
        "FROM pg_constraint c "
        "JOIN pg_class r ON r.oid = c.conrelid "
        "WHERE r.relnamespace = current_schema()::regnamespace "
        "  AND r.relkind = 'r' "
        "ORDER BY c.conrelid::regclass::text, c.conname").fetchall()

    def columns_of(table: str, numbers) -> list[str]:
        rows = conn.execute(
            "SELECT a.attname AS name FROM pg_attribute a "
            "WHERE a.attrelid = to_regclass(?) AND a.attnum = ANY(?) "
            "ORDER BY array_position(?, a.attnum)",
            (table, list(numbers), list(numbers))).fetchall()
        return [r["name"] for r in rows]

    violations: list[dict] = []
    unvalidated: list[str] = []
    swept = 0
    for row in constraints:
        if not row["validated"]:
            unvalidated.append(f"{row['child']}.{row['name']}")
        if row["kind"] != "f":
            continue
        child_columns = columns_of(row["child"], row["child_columns"])
        parent_columns = columns_of(row["parent"], row["parent_columns"])
        if len(child_columns) != len(parent_columns):
            violations.append({"table": row["child"], "parent": row["parent"],
                                "fkid": row["name"],
                                "rowid": "constraint could not be read"})
            continue

        # MATCH SIMPLE: a row with a NULL anywhere in the key satisfies the
        # constraint however little else is true of it, so those rows are not
        # orphans and must not be counted as any.
        present = " AND ".join(f"c.{catalog.quote(col)} IS NOT NULL"
                                for col in child_columns)
        joined = " AND ".join(
            f"p.{catalog.quote(p)} = c.{catalog.quote(c)}"
            for p, c in zip(parent_columns, child_columns))
        count = conn.execute(
            f"SELECT COUNT(*) FROM {catalog.quote(row['child'])} c "
            f"WHERE {present} AND NOT EXISTS ("
            f"  SELECT 1 FROM {catalog.quote(row['parent'])} p WHERE {joined})"
        ).fetchone()[0]
        swept += 1
        if count:
            violations.append({"table": row["child"], "parent": row["parent"],
                                "fkid": row["name"],
                                "rowid": f"{count:,} orphaned row(s)"})

    integrity = []
    if unvalidated:
        integrity.append("not validated against existing rows: "
                          + ", ".join(unvalidated))
    if not integrity:
        integrity = ["ok"]

    return [{
        "integrity": integrity,
        "ok": not violations and not unvalidated,
        "foreign_key_violations": violations[:200],
        "foreign_key_violation_count": len(violations),
        "checked": f"{swept} foreign keys and {len(constraints)} constraints",
        "not_checked": "The pages. PostgreSQL has no in-database equivalent of "
                        "walking the file: pg_amcheck is a separate binary run "
                        "against the server, and the amcheck extension needs a "
                        "superuser to install. Nothing here has looked at "
                        "physical storage.",
    }]
