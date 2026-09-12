"""Read-only pipeline and data-lineage graph (BETA-102).

The expanded system is hard to reason about from separate registries even
though the dependency metadata already exists. This composes one typed graph
from the machine-owned registries and the live schema. Nothing here is a
hand-maintained edge where a registry can supply it:

  node kinds  source · module · table · export
  edge kinds  collected_by  source -> module   [datasets.py]
              depends_on    module -> module   [registry MODULE_META]
              writes        module -> table    [datasets.py public_tables]
              references    table  -> table    [live schema foreign keys]
              exported_by   table  -> export   [exports/schema.py TabSpec.sql]

Routes and portal pages consume tables too, but the Python side has no
registry mapping a route or a page to the tables it reads without parsing
`public_queries`, so they are left out rather than guessed. The payload's
`omitted` field says so.

Writes nothing. Row counts and last-run health are measured on the request.
"""
from __future__ import annotations

import re

from pipeline import catalog
from pipeline.licences import for_module
from pipeline.web import admin, datasets

# `FROM tbl` / `JOIN tbl` — the table an export's SQL actually reads. The
# registry SQL names real tables here (no CTEs, no `FROM (subquery)`), so a
# word-boundary match is exact enough and stays deterministic.
_SQL_TABLE = re.compile(r"\b(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*)", re.IGNORECASE)

_MODULE_HISTORY = 10


def _tables_in_sql(sql: str) -> list[str]:
    seen: list[str] = []
    for name in _SQL_TABLE.findall(sql or ""):
        low = name.lower()
        if low not in seen and low not in ("select",):
            seen.append(low)
    return seen


def _module_health(conn) -> dict[str, dict]:
    """Last recorded result per module, newest run first. Empty if the run
    ledger table is not there yet (migration 0073)."""
    if not any(o["name"] == "run_ledger" for o in catalog.list_objects(conn)):
        return {}
    from pipeline import run_ledger

    out: dict[str, dict] = {}
    for run in run_ledger.recent(conn, _MODULE_HISTORY):
        for result in run.get("results", []):
            name = result.get("module")
            if not name or name in out:
                continue
            out[name] = {
                "status": result.get("status"),
                "rows": result.get("rows"),
                "failures": result.get("failures"),
                "run_id": run.get("run_id"),
                "finished_at": run.get("finished_at"),
            }
    return out


def graph(conn, settings=None) -> dict:
    from pipeline.exports.schema import TABS

    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def node(node_id: str, kind: str, label: str, **extra) -> None:
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "kind": kind, "label": label, **extra}

    def edge(source: str, rel: str, target: str) -> None:
        edges.append({"source": source, "rel": rel, "target": target})

    present = {o["name"] for o in catalog.list_objects(conn)}
    referenced_tables: set[str] = set()

    # --- modules, their wave, review/parse debt and last-run health ----------
    health = _module_health(conn)
    for m in admin.modules(conn).get("modules", []):
        mid = f"module:{m['name']}"
        node(mid, "module", m["name"],
             wave=m.get("wave"),
             pending_review=m.get("pending_review", 0),
             parse_failures=m.get("parse_failures", 0),
             missing_dependencies=m.get("missing_dependencies", []),
             last_run=health.get(m["name"]))
        for dep in m.get("depends_on", []):
            node(f"module:{dep}", "module", dep)
            edge(mid, "depends_on", f"module:{dep}")

    # --- sources, the module that collects each, the tables it writes --------
    for ds in datasets.DATASETS:
        sid = f"source:{ds.dataset_id}"
        licence = for_module(ds.module)
        node(sid, "source", ds.title,
             publisher=ds.publisher, official_url=ds.official_url,
             evidence_layer=ds.evidence_layer, cadence=ds.cadence,
             stated_cadence_days=ds.stated_cadence_days,
             licence=(licence.name if licence else None))
        node(f"module:{ds.module}", "module", ds.module)
        edge(sid, "collected_by", f"module:{ds.module}")
        for table in ds.public_tables:
            referenced_tables.add(table)
            edge(f"module:{ds.module}", "writes", f"table:{table}")

    # --- foreign keys: table -> table --------------------------------------
    fks = catalog.foreign_key_columns(conn)
    for fk in fks:
        referenced_tables.add(fk["child"])
        referenced_tables.add(fk["parent"])

    # --- exports and the tables each reads --------------------------------
    export_reads: list[tuple[str, str]] = []
    for tab in TABS:
        eid = f"export:{tab.name}"
        node(eid, "export", tab.name,
             description=tab.description, columns=len(tab.columns))
        for table in _tables_in_sql(tab.sql):
            referenced_tables.add(table)
            export_reads.append((table, eid))

    # --- table nodes: only those actually named, with live counts ---------
    countable = sorted(t for t in referenced_tables if t in present)
    counts = catalog.row_counts(conn, countable) if countable else {}
    for table in sorted(referenced_tables):
        node(f"table:{table}", "table", table,
             present=table in present,
             rows=counts.get(table),
             restricted=table.startswith("restricted_"))
    for fk in fks:
        edge(f"table:{fk['child']}", "references", f"table:{fk['parent']}")
    for table, eid in export_reads:
        edge(f"table:{table}", "exported_by", eid)

    # --- consumer count: how many edges point *at* each node --------------
    incoming: dict[str, int] = {}
    for e in edges:
        incoming[e["target"]] = incoming.get(e["target"], 0) + 1
    for node_id, data in nodes.items():
        data["consumer_count"] = incoming.get(node_id, 0)

    by_kind: dict[str, int] = {}
    for data in nodes.values():
        by_kind[data["kind"]] = by_kind.get(data["kind"], 0) + 1
    by_rel: dict[str, int] = {}
    for e in edges:
        by_rel[e["rel"]] = by_rel.get(e["rel"], 0) + 1

    return {
        "nodes": sorted(nodes.values(), key=lambda n: (n["kind"], n["label"])),
        "edges": edges,
        "counts": {"by_kind": by_kind, "by_rel": by_rel},
        "node_kinds": ["source", "module", "table", "export"],
        "edge_kinds": ["collected_by", "depends_on", "writes",
                        "references", "exported_by"],
        "omitted": [
            "API routes and portal pages: no Python-side registry maps one to "
            "the tables it reads without parsing public_queries, so they are "
            "not drawn rather than guessed.",
            "The raw-bytes archive under data/raw/ is one store per fetch, not "
            "a per-module node.",
        ],
        "note": "Composed on the request from the module registry, the dataset "
                "catalogue, the live foreign keys and the export tab registry. "
                "Every edge is derived; none is hand-maintained. Nothing is "
                "written.",
    }
