"""The durable run ledger (BETA-058).

`runner.run_waves` is the single point every entry point — the CLI `run`
command, the web UI's job registry, a cron wrapper — already funnels through.
This records one row there per run: who started it (`origin`), the code it
ran (`revision`), where (`environment`), which run spawned it
(`parent_run_id`), when it started and finished, its status, and the
per-module result rows.

It never raises into the run. A ledger write that fails is logged and
swallowed — the collection is the job, and losing an audit row must not lose
the collection.

Not a replacement for `job_runs`: the web UI keeps that for live log
streaming. This is the entry-point-agnostic ledger beside it.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog

from pipeline import db

log = structlog.get_logger()

ORIGINS = ("cli", "admin", "scheduled")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_revision(settings) -> str | None:
    """The commit this run executed, from settings or `.git` — no subprocess.

    A deployment injects `GIT_REVISION`; a local checkout has none, so fall
    back to reading `.git/HEAD` directly (the same read `public_queries.meta`
    does, kept here so `runner` never imports from `pipeline.web`).
    """
    if getattr(settings, "git_revision", None):
        return settings.git_revision
    git_dir = Path(__file__).resolve().parent.parent / ".git"
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head.split(":", 1)[1].strip()
            ref_file = git_dir / ref
            if ref_file.is_file():
                return ref_file.read_text(encoding="utf-8").strip() or None
            packed = git_dir / "packed-refs"
            if packed.is_file():
                for line in packed.read_text(encoding="utf-8").splitlines():
                    if line.startswith(("#", "^")) or " " not in line:
                        continue
                    sha, name = line.split(" ", 1)
                    if name.strip() == ref:
                        return sha or None
            return None
        return head or None
    except OSError:
        return None


def start(settings, *, origin: str, module_selector: str, dry_run: bool,
          modules_total: int, parent_run_id: str | None = None) -> str | None:
    """Open a ledger row. Returns the run_id, or None if the row could not be
    written (in which case `finish` is a no-op)."""
    if origin not in ORIGINS:
        origin = "cli"
    run_id = uuid.uuid4().hex
    try:
        conn = db.get_connection(settings)
        try:
            conn.execute(
                "INSERT INTO run_ledger (run_id, origin, revision, environment, "
                " parent_run_id, module_selector, dry_run, started_at, status, "
                " modules_total) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?)",
                (run_id, origin, git_revision(settings),
                 getattr(settings, "environment", None), parent_run_id,
                 module_selector, 1 if dry_run else 0, _now(), modules_total))
            conn.commit()
        finally:
            conn.close()
        return run_id
    except Exception as exc:  # never break a run over a ledger row
        log.warning("run_ledger.start_failed", error=f"{type(exc).__name__}: {exc}")
        return None


def finish(settings, run_id: str | None, summary: list[dict]) -> None:
    """Close the ledger row with the run's per-module results."""
    if not run_id:
        return
    ok = sum(1 for r in summary if r.get("status") == "ok")
    failed = sum(1 for r in summary if r.get("status") == "failed")
    status = "failed" if failed and not ok else ("partial" if failed else "ok")
    results = [
        {"module": r.get("module"), "status": r.get("status"),
         "rows": r.get("rows"), "review": r.get("review"),
         "failures": r.get("failures"),
         "elapsed_ms": round((r.get("elapsed") or 0.0) * 1000)}
        for r in summary
    ]
    try:
        conn = db.get_connection(settings)
        try:
            conn.execute(
                "UPDATE run_ledger SET finished_at = ?, status = ?, "
                " modules_ok = ?, modules_failed = ?, results_json = ? "
                "WHERE run_id = ?",
                (_now(), status, ok, failed, json.dumps(results), run_id))
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        log.warning("run_ledger.finish_failed", error=f"{type(exc).__name__}: {exc}")


def recent(conn, limit: int = 20) -> list[dict]:
    """The most recent ledger rows, newest first, results parsed."""
    rows = [dict(r) for r in conn.execute(
        "SELECT run_id, origin, revision, environment, parent_run_id, "
        "module_selector, dry_run, started_at, finished_at, status, "
        "modules_total, modules_ok, modules_failed, results_json "
        "FROM run_ledger ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()]
    for row in rows:
        raw = row.pop("results_json", None)
        try:
            row["results"] = json.loads(raw) if raw else []
        except (TypeError, ValueError):
            row["results"] = []
        row["dry_run"] = bool(row.get("dry_run"))
    return rows
