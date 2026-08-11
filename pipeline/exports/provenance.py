"""Companion .provenance.json for every export.

Constraint 1 says any published figure must be traceable to the document it
came from. An export that leaves the warehouse without its provenance breaks
that chain, so every writer here goes through write_export, which refuses to
produce a file without one.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def collect_provenance(conn, tables: list[str]) -> dict:
    """Source systems, retrieval window and row counts for the tables that
    contributed to an export.
    """
    contributions = []
    for table in tables:
        try:
            row = conn.execute(
                f"SELECT COUNT(*) AS rows, MIN(retrieved_at) AS first_retrieved, "
                f"MAX(retrieved_at) AS last_retrieved, "
                f"GROUP_CONCAT(DISTINCT source_system) AS source_systems FROM {table}"
            ).fetchone()
            contributions.append({
                "table": table,
                "rows": row["rows"],
                "source_systems": sorted(
                    (row["source_systems"] or "").split(",")) if row["source_systems"] else [],
                "first_retrieved_at": row["first_retrieved"],
                "last_retrieved_at": row["last_retrieved"],
            })
        except Exception:
            # Reference tables (providers, supplier_aliases) carry no
            # provenance columns by design; record the count alone.
            try:
                count = conn.execute(f"SELECT COUNT(*) AS rows FROM {table}").fetchone()["rows"]
            except Exception:
                continue
            contributions.append({
                "table": table, "rows": count, "source_systems": [],
                "first_retrieved_at": None, "last_retrieved_at": None,
                "note": "reference/config table — seeded from repository config, not fetched",
            })
    return {"contributions": contributions}


def write_export(
    path: Path,
    payload_writer,
    conn,
    tables: list[str],
    export_type: str,
    row_count: int,
    caveats: list[str] | None = None,
    extra: dict | None = None,
) -> Path:
    """Write an export and its companion provenance file together.

    payload_writer is called with the output path. The provenance file is
    written after, so a failed payload leaves no orphan provenance claiming
    data that was never produced.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload_writer(path)

    provenance = {
        "export": path.name,
        "export_type": export_type,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_count": row_count,
        "caveats": caveats or [],
        **collect_provenance(conn, tables),
        **(extra or {}),
    }
    provenance_path = path.with_suffix(path.suffix + ".provenance.json")
    provenance_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    return provenance_path
