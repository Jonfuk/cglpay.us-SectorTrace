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

import sqlite3
from pathlib import Path

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
    ("Fingertips", "fingertips_la_values", "ons_code", "m12_fingertips"),
    ("CQC", "cqc_locations", "local_authority_ons_code", "m05_cqc"),
    ("CDP docs", "cdp_documents", "authority_ons_code", "m09_cdp_documents"),
    ("CDP cands", "cdp_document_candidates", "authority_ons_code", "m09_cdp_documents"),
    ("Papers", "committee_papers", "authority_ons_code", "m10_committee_papers"),
    ("Paper cands", "committee_paper_candidates", "authority_ons_code",
      "m10_committee_papers"),
    ("FOI", "foi_requests", "ons_code", "m15_foi"),
    ("FOI cands", "foi_request_candidates", "ons_code", "m15_foi"),
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,)).fetchone() is not None


# --- coverage -------------------------------------------------------------------


def coverage(conn: sqlite3.Connection, tier: str = "upper") -> dict:
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


def warehouse(conn: sqlite3.Connection, settings) -> dict:
    """Size, shape, and whether the schema on disk is the schema that ran."""
    database_path = Path(settings.database_path)
    files = {}
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(database_path) + suffix)
        if candidate.exists():
            files[candidate.name] = candidate.stat().st_size

    page_size = conn.execute("PRAGMA page_size").fetchone()[0]
    page_count = conn.execute("PRAGMA page_count").fetchone()[0]
    freelist = conn.execute("PRAGMA freelist_count").fetchone()[0]

    applied = [row["filename"] for row in conn.execute(
        "SELECT filename FROM schema_migrations ORDER BY filename")]
    on_disk = sorted(p.name for p in Path(settings.migrations_dir).glob("*.sql"))

    return {
        "path": str(database_path),
        "files": files,
        "bytes": sum(files.values()),
        "page_size": page_size,
        "page_count": page_count,
        # Free pages are space the file is holding but not using. Worth seeing
        # before wondering why a 230 MB warehouse holds 200 MB of evidence.
        "free_bytes": freelist * page_size,
        "applied_migrations": applied,
        "migrations_on_disk": on_disk,
        "unapplied": [name for name in on_disk if name not in applied],
        # A migration recorded as applied with no file behind it means this
        # warehouse was built by a checkout that has since changed.
        "applied_without_file": [name for name in applied if name not in on_disk],
    }


def hosts(conn: sqlite3.Connection) -> list[dict]:
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


def freshness(conn: sqlite3.Connection) -> list[dict]:
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
    for row in conn.execute(
            "SELECT m.name AS name FROM sqlite_master m JOIN pragma_table_info(m.name) p "
            "WHERE m.type = 'table' AND p.name = 'retrieved_at' ORDER BY m.name"):
        name = row["name"]
        if queries.is_restricted(name):
            continue
        quoted = queries._quote(name)
        try:
            stats = conn.execute(
                f"SELECT COUNT(*) AS rows_held, MAX(retrieved_at) AS newest, "
                f"       MIN(retrieved_at) AS oldest FROM {quoted}").fetchone()
        except sqlite3.Error:
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
    return out


def health(conn: sqlite3.Connection, settings) -> dict:
    """The cheap half: size, migrations, and which hosts were last asked.

    Neither freshness nor storage is here, and for the same reason: one is
    seconds of table scans and the other is seconds of stat calls over 8,502
    archived files. Making the whole tab wait for either to render a size in
    megabytes is the wrong shape, and each is served on its own route.
    """
    return {
        "warehouse": warehouse(conn, settings),
        "hosts": hosts(conn),
    }


# --- parse failures ---------------------------------------------------------------


def failures(conn: sqlite3.Connection, module: str | None = None,
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
    }]
