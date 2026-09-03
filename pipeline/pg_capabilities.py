"""Read-only PostgreSQL capability report (BETA-063).

BETA-036 made the warehouse degrade cleanly when an optional extension is
absent, and `pipeline/web/health.py` shows an operator whether each extension
is *installed*. This is the deployment-time / CI view of the same question,
and it goes one step further: for every extension it names the indexes and
operator classes that are meant to back it, checks whether they actually
exist and were built the right way, and lists which query paths are running
on their fallback right now because something is missing.

Strictly read-only — `pg_catalog` / `information_schema` lookups only. No
`CREATE EXTENSION`, no `CREATE INDEX`. PostgreSQL is the only application
backend, so this is the active deployment gate rather than an optional probe.
"""
from __future__ import annotations

from dataclasses import dataclass

from pipeline import db


@dataclass(frozen=True)
class BackedIndex:
    """One extension-backed index the migrations declare, and what breaks
    without it. `index` is the name; it is identical on both dialect trees
    (`tests/test_migration_equivalence.py` — SQLite declares plain btrees of
    the same name), so a missing row here is a real gap, not a dialect quirk.
    """
    extension: str
    index: str
    table: str
    method: str          # the access method the PostgreSQL index must use
    opclass: str | None  # the operator class, when one is named explicitly
    feature: str         # the query path it accelerates
    fallback: str        # what runs instead when it is absent


# The matrix. Kept here rather than derived from the migration text because
# the point is to assert the intended shape against reality — a migration that
# silently stopped creating an index would still parse.
BACKED_INDEXES: tuple[BackedIndex, ...] = (
    BackedIndex("pg_trgm", "idx_authorities_name_trgm", "authorities", "gin",
                "gin_trgm_ops",
                "operator fuzzy-name search vs authorities.name",
                "not available: pg_trgm is required (pipeline/web/name_matches.py)"),
    BackedIndex("pg_trgm", "idx_companies_name_trgm", "companies", "gin",
                "gin_trgm_ops",
                "review-queue possible_group_company vs companies.company_name",
                "not available: pg_trgm is required"),
    BackedIndex("pg_trgm", "idx_providers_name_trgm", "providers", "gin",
                "gin_trgm_ops",
                "review-queue possible_group_company vs providers.canonical_name",
                "not available: pg_trgm is required"),
    BackedIndex("pg_trgm", "idx_contracts_supplier_name_trgm", "contracts", "gin",
                "gin_trgm_ops",
                "portal contract supplier text filter",
                "full ILIKE '%...%' scan of the contracts table"),
    BackedIndex("pg_trgm", "idx_contracts_buyer_name_trgm", "contracts", "gin",
                "gin_trgm_ops",
                "portal contract buyer text filter",
                "full ILIKE '%...%' scan of the contracts table"),
    BackedIndex("postgis", "idx_authorities_geom", "authorities", "gist", None,
                "authority point-in-polygon and centroid queries on authorities.geom",
                "not available: PostGIS is required (pipeline/geo.py)"),
    BackedIndex("vector", "idx_document_embeddings_vec", "document_embeddings", "hnsw",
                "vector_cosine_ops",
                "semantic-search approximate nearest neighbour",
                "not available: pgvector is required (pipeline/nlp/semantic_search.py)"),
)

# A derived column, not an index: pgvector's typed copy of the embedding
# bytes. `idx_document_embeddings_vec` cannot exist without it, so it is
# checked and reported alongside.
_VECTOR_COLUMN = ("document_embeddings", "embedding_vec")

def _server_version(conn: db.Connection) -> str | None:
    row = conn.execute("SELECT current_setting('server_version') AS v").fetchone()
    return row["v"] if row else None


def _installed_extensions(conn: db.Connection) -> dict[str, dict]:
    """`name -> {available, installed, version}` for the warehouse's
    extensions. `pg_available_extensions` is readable by any role."""
    names = db.WAREHOUSE_EXTENSIONS
    placeholders = ",".join("?" for _ in names)
    rows = conn.execute(
        f"SELECT e.name, e.default_version, i.extversion AS installed_version "
        f"FROM pg_available_extensions e "
        f"LEFT JOIN pg_extension i ON i.extname = e.name "
        f"WHERE e.name IN ({placeholders})", list(names))
    seen = {row["name"]: row for row in rows}
    out = {}
    for name in names:
        row = seen.get(name)
        out[name] = {
            "available": row is not None,
            "installed": bool(row and row["installed_version"]),
            "version": (row["installed_version"] if row else None)
                        or (row["default_version"] if row else None),
        }
    return out


def _index_defs(conn: db.Connection, names: tuple[str, ...]) -> dict[str, str]:
    placeholders = ",".join("?" for _ in names)
    rows = conn.execute(
        f"SELECT indexname, indexdef FROM pg_indexes "
        f"WHERE schemaname = current_schema() AND indexname IN ({placeholders})",
        list(names))
    return {row["indexname"]: row["indexdef"] for row in rows}


def _has_column(conn: db.Connection, table: str, column: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = ? "
        "AND column_name = ?", (table, column)).fetchone() is not None


def report(conn: db.Connection) -> dict:
    """The capability report. See module docstring. Read-only."""
    extensions = _installed_extensions(conn)
    defs = _index_defs(conn, tuple(b.index for b in BACKED_INDEXES))
    vector_column = _has_column(conn, *_VECTOR_COLUMN)

    ext_rows = [
        {"name": name, **info,
         "backs": sorted({b.feature for b in BACKED_INDEXES if b.extension == name})}
        for name, info in extensions.items()
    ]

    index_rows: list[dict] = []
    fallbacks: list[dict] = []
    for backed in BACKED_INDEXES:
        ext_installed = extensions.get(backed.extension, {}).get("installed", False)
        indexdef = defs.get(backed.index)
        present = indexdef is not None
        method_ok = bool(indexdef and f"USING {backed.method} " in indexdef)
        opclass_ok = bool(
            indexdef and (backed.opclass is None or backed.opclass in indexdef))
        healthy = present and method_ok and opclass_ok

        index_rows.append({
            "extension": backed.extension,
            "index": backed.index,
            "table": backed.table,
            "expected_method": backed.method,
            "expected_opclass": backed.opclass,
            "present": present,
            "method_ok": method_ok,
            "opclass_ok": opclass_ok,
            "healthy": healthy,
            "feature": backed.feature,
        })

        if healthy:
            continue
        if not ext_installed:
            reason = f"{backed.extension} is not installed"
        elif not present:
            reason = f"index {backed.index} is missing"
        elif not method_ok:
            reason = f"index {backed.index} is not USING {backed.method}"
        else:
            reason = f"index {backed.index} lacks operator class {backed.opclass}"
        fallbacks.append({
            "feature": backed.feature,
            "extension": backed.extension,
            "reason": reason,
            "fallback": backed.fallback,
        })

    notes = []
    if extensions.get("vector", {}).get("installed") and not vector_column:
        notes.append(
            f"{_VECTOR_COLUMN[0]}.{_VECTOR_COLUMN[1]} is absent though pgvector "
            "is installed — run `pipeline migrate` (it adds the column and index).")

    ready = not fallbacks and all(info["installed"] for info in extensions.values())

    return {
        "backend": "postgres",
        "applies": True,
        "server_version": _server_version(conn),
        "ready": ready,
        "extensions": ext_rows,
        "vector_column_present": vector_column,
        "indexes": index_rows,
        "active_fallbacks": fallbacks,
        "notes": notes,
    }
