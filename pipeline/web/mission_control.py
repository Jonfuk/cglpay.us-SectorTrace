"""Pipeline mission control — one read model over the run state (BETA-082).

The operator already has the pieces: `/api/admin/modules` (registry, waves,
dependencies, review and parse-failure counts), `/api/admin/jobs` (the
browser-started jobs and which one is running), `/api/admin/run-ledger`
(every module-run, whatever started it). This joins them into one payload so
the operator does not have to mentally reconcile three tabs.

Strictly read-only. No cancellation, no SSE/WebSockets, no new write
semantics — the existing run route and its safeguards are untouched. The UI
keeps polling this the way it polls the others.
"""
from __future__ import annotations

from . import admin

_HISTORY = 10


def overview(conn, settings, jobs) -> dict:
    from pipeline import run_ledger

    mods = admin.modules(conn)
    module_rows = mods.get("modules", [])
    ledger = run_ledger.recent(conn, _HISTORY)

    running = jobs.running() if jobs is not None else None
    active = running.head() if running is not None else None
    queued = []
    if jobs is not None:
        for job in jobs.all():
            head = job.head()
            if head.get("state") in ("queued", "pending") and (
                    active is None or head.get("id") != active.get("id")):
                queued.append(head)

    # Most recent per-module result across the last few ledger rows: the run
    # that last touched each module, its status and what it wrote.
    last_by_module: dict[str, dict] = {}
    for run in ledger:
        for result in run.get("results", []):
            name = result.get("module")
            if not name or name in last_by_module:
                continue
            last_by_module[name] = {
                "status": result.get("status"),
                "rows": result.get("rows"),
                "failures": result.get("failures"),
                "elapsed_ms": result.get("elapsed_ms"),
                "run_id": run.get("run_id"),
                "origin": run.get("origin"),
                "finished_at": run.get("finished_at"),
            }

    waves: dict[int, list[dict]] = {}
    for module in module_rows:
        wave = module.get("wave") or 0
        waves.setdefault(wave, []).append({
            "name": module["name"],
            "depends_on": module.get("depends_on", []),
            "missing_dependencies": module.get("missing_dependencies", []),
            "pending_review": module.get("pending_review", 0),
            "parse_failures": module.get("parse_failures", 0),
            "cursor_updated_at": module.get("cursor_updated_at"),
            "last_run": last_by_module.get(module["name"]),
        })
    wave_list = [
        {"wave": wave, "modules": sorted(items, key=lambda m: m["name"])}
        for wave, items in sorted(waves.items())
    ]

    # Failure summary: modules carrying parse failures or a failed last run.
    failing = [
        {
            "module": m["name"],
            "parse_failures": m.get("parse_failures", 0),
            "pending_review": m.get("pending_review", 0),
            "last_status": (last_by_module.get(m["name"]) or {}).get("status"),
        }
        for m in module_rows
        if m.get("parse_failures")
        or (last_by_module.get(m["name"]) or {}).get("status") == "failed"
    ]
    failing.sort(key=lambda f: (-f["parse_failures"], f["module"]))

    # Freshness consequence: modules never run, or whose cursor has not moved.
    never_run = [m["name"] for m in module_rows
                 if m["name"] not in last_by_module
                 and not m.get("cursor_updated_at")]

    return {
        "generated_from": ["module registry", "active job", "run ledger"],
        "wave_count": mods.get("waves", 0),
        "waves": wave_list,
        "active": active,
        "queued": queued,
        "history": ledger,
        "last_run": ledger[0] if ledger else None,
        "failure_summary": failing,
        "never_run": never_run,
        "note": "Read model only. No cancellation, no streaming, no new "
                "writes — the run route and its safeguards are unchanged.",
    }
