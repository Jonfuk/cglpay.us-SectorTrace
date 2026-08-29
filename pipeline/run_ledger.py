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


_LEDGER_COLUMNS = (
    "run_id, origin, revision, environment, parent_run_id, module_selector, "
    "dry_run, started_at, finished_at, status, modules_total, modules_ok, "
    "modules_failed, results_json"
)


def _hydrate(row: dict) -> dict:
    raw = row.pop("results_json", None)
    try:
        row["results"] = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        row["results"] = []
    row["dry_run"] = bool(row.get("dry_run"))
    return row


def recent(conn, limit: int = 20) -> list[dict]:
    """The most recent ledger rows, newest first, results parsed."""
    rows = [dict(r) for r in conn.execute(
        f"SELECT {_LEDGER_COLUMNS} FROM run_ledger "
        "ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()]
    return [_hydrate(row) for row in rows]


def one(conn, run_id: str) -> dict | None:
    """One ledger row by id, results parsed, or None."""
    row = conn.execute(
        f"SELECT {_LEDGER_COLUMNS} FROM run_ledger WHERE run_id = ?",
        (run_id,)).fetchone()
    return _hydrate(dict(row)) if row else None


def _elapsed_ms(row: dict) -> int | None:
    """Wall-clock milliseconds between started_at and finished_at, or None."""
    started, finished = row.get("started_at"), row.get("finished_at")
    if not started or not finished:
        return None
    try:
        a = datetime.fromisoformat(started)
        b = datetime.fromisoformat(finished)
    except ValueError:
        return None
    return round((b - a).total_seconds() * 1000)


def _by_module(results: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in results or []:
        name = r.get("module")
        if name:
            out[name] = r
    return out


# The precedence used to give each module one headline `change` label. A
# module can differ in several ways at once; the reader wants the most
# consequential named first, and the same input must always yield the same
# label, so this is an explicit ordered list rather than a max() over scores.
_CHANGE_PRECEDENCE = (
    "added", "removed", "regressed", "recovered",
    "rows-changed", "review-changed", "slower", "faster", "unchanged",
)


def compare(conn, run_a: str | None = None, run_b: str | None = None) -> dict:
    """A per-module diff between two runs, derived from the immutable ledger.

    Writes nothing. Duplicates no payloads: each module row carries the
    already-recorded per-module numbers (rows, review, failures, elapsed) from
    each run and their deltas, and the run headers carry `run_id` so a caller
    can link back to the ledger and the job logs for the detail.

    With no ids, compares the two most recent runs (`run_b` newest). Raises
    ValueError if a named run is missing or there are fewer than two runs.
    """
    if run_a and run_b:
        a, b = one(conn, run_a), one(conn, run_b)
        if a is None or b is None:
            missing = run_a if a is None else run_b
            raise ValueError(f"no run {missing!r} in the ledger")
    else:
        latest = recent(conn, 2)
        if len(latest) < 2:
            raise ValueError("need at least two recorded runs to compare")
        b, a = latest[0], latest[1]

    ma, mb = _by_module(a["results"]), _by_module(b["results"])
    names = sorted(set(ma) | set(mb))

    def _delta(x, y):
        return (y - x) if isinstance(x, (int, float)) and isinstance(y, (int, float)) else None

    modules: list[dict] = []
    totals = {
        "modules_only_in_a": 0, "modules_only_in_b": 0,
        "status_regressions": 0, "status_recoveries": 0,
        "rows_added": 0, "rows_removed": 0,
        "review_delta_total": 0, "failures_delta_total": 0,
    }
    for name in names:
        ra, rb = ma.get(name), mb.get(name)
        sa = (ra or {}).get("status") if ra else "absent"
        sb = (rb or {}).get("status") if rb else "absent"
        rows_a = (ra or {}).get("rows")
        rows_b = (rb or {}).get("rows")
        review_a = (ra or {}).get("review")
        review_b = (rb or {}).get("review")
        fail_a = (ra or {}).get("failures")
        fail_b = (rb or {}).get("failures")
        el_a = (ra or {}).get("elapsed_ms")
        el_b = (rb or {}).get("elapsed_ms")
        rows_delta = _delta(rows_a, rows_b)
        review_delta = _delta(review_a, review_b)
        fail_delta = _delta(fail_a, fail_b)
        el_delta = _delta(el_a, el_b)

        labels: list[str] = []
        if ra is None:
            labels.append("added")
            totals["modules_only_in_b"] += 1
        elif rb is None:
            labels.append("removed")
            totals["modules_only_in_a"] += 1
        else:
            if sa == "ok" and sb == "failed":
                labels.append("regressed")
                totals["status_regressions"] += 1
            elif sa == "failed" and sb == "ok":
                labels.append("recovered")
                totals["status_recoveries"] += 1
            if rows_delta:
                labels.append("rows-changed")
            if review_delta:
                labels.append("review-changed")
            if el_delta and el_a:
                if el_delta > 0.2 * el_a:
                    labels.append("slower")
                elif el_delta < -0.2 * el_a:
                    labels.append("faster")
        if not labels:
            labels.append("unchanged")
        change = next(k for k in _CHANGE_PRECEDENCE if k in labels)

        if rows_delta and rows_delta > 0:
            totals["rows_added"] += rows_delta
        elif rows_delta and rows_delta < 0:
            totals["rows_removed"] += -rows_delta
        if review_delta:
            totals["review_delta_total"] += review_delta
        if fail_delta:
            totals["failures_delta_total"] += fail_delta

        # The freshness effect the objective asks for, read from the run
        # outcome rather than re-derived: a module that ran clean and wrote
        # rows in B moved its datasets' freshness forward on that run.
        if sb in (None, "absent") or sb == "failed":
            freshness = "no successful run in B"
        elif rows_b:
            freshness = "advanced — wrote rows in B"
        else:
            freshness = "ran in B, no new rows"

        modules.append({
            "module": name, "change": change, "change_labels": labels,
            "status_a": sa, "status_b": sb,
            "rows_a": rows_a, "rows_b": rows_b, "rows_delta": rows_delta,
            "review_a": review_a, "review_b": review_b,
            "review_delta": review_delta,
            "failures_a": fail_a, "failures_b": fail_b,
            "failures_delta": fail_delta,
            "elapsed_ms_a": el_a, "elapsed_ms_b": el_b,
            "elapsed_delta_ms": el_delta,
            "freshness_effect": freshness,
        })

    order = {k: i for i, k in enumerate(_CHANGE_PRECEDENCE)}
    modules.sort(key=lambda m: (order.get(m["change"], 99), m["module"]))

    def _head(row: dict) -> dict:
        return {
            "run_id": row["run_id"], "origin": row["origin"],
            "revision": row["revision"], "environment": row["environment"],
            "module_selector": row["module_selector"],
            "dry_run": row["dry_run"], "started_at": row["started_at"],
            "finished_at": row["finished_at"], "status": row["status"],
            "modules_total": row["modules_total"],
            "modules_ok": row["modules_ok"],
            "modules_failed": row["modules_failed"],
            "duration_ms": _elapsed_ms(row),
        }

    dur_a, dur_b = _elapsed_ms(a), _elapsed_ms(b)
    totals["duration_a_ms"] = dur_a
    totals["duration_b_ms"] = dur_b
    totals["duration_delta_ms"] = _delta(dur_a, dur_b)

    return {
        "run_a": _head(a), "run_b": _head(b),
        "modules": modules,
        "totals": totals,
        "change_kinds": list(_CHANGE_PRECEDENCE),
        "note": "Derived from the immutable run ledger; nothing is written and "
                "no payloads are duplicated. Each module row carries the "
                "numbers the run already recorded. Full module logs stay in "
                "the job log stream — follow a run_id there for the detail.",
    }
