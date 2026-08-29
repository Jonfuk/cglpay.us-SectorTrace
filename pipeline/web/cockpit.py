"""Operator action cockpit — the read model behind the overview cards (BETA-086).

The overview reports volume; this answers "what needs attention now?" as a
short list of prioritised cards, each with a deterministic reason and a link
to a pre-filtered existing workflow. It ranks *operational states* only —
review pressure, run health, schema drift, coverage gaps. It never ranks
evidence quality or a review outcome, and it decides nothing: every action is
a link a person follows.

Read-only. The one aggregate the BETA-068–087 interface contract plans.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pipeline.web import completeness_board, health

# priority: 3 act now · 2 soon · 1 watch · 0 clear
_PRIORITY_LABELS = {3: "act now", 2: "soon", 1: "watch", 0: "clear"}


def _age_days(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - then).days)


def overview(conn, settings) -> dict:
    from pipeline import run_ledger

    cards: list[dict] = []

    # --- review pressure ---------------------------------------------------
    pending = conn.execute(
        "SELECT COUNT(*) AS n, MIN(created_at) AS oldest "
        "FROM review_queue WHERE status = 'pending'").fetchone()
    n_pending = pending["n"] or 0
    oldest_days = _age_days(pending["oldest"])
    cards.append({
        "key": "review_pressure",
        "title": "Review queue",
        "priority": 3 if n_pending >= 200 or (oldest_days or 0) >= 30
        else 2 if n_pending else 0,
        "metric": n_pending,
        "reason": (
            f"{n_pending} item{'s' if n_pending != 1 else ''} pending"
            + (f", oldest {oldest_days} days" if oldest_days else "")
            if n_pending else "Nothing pending"),
        "link": "#review",
    })

    # --- failed / stale runs --------------------------------------------------
    ledger = run_ledger.recent(conn, 5)
    last = ledger[0] if ledger else None
    if last is None:
        run_priority, run_reason = 1, "No run has ever been recorded here"
    else:
        last_days = _age_days(last.get("finished_at") or last.get("started_at"))
        if last.get("status") in ("failed", "partial"):
            run_priority = 3
            run_reason = (f"Last run ({last.get('origin')}) {last.get('status')}"
                          f" — {last.get('modules_failed') or 0} module(s) failed")
        elif (last_days or 0) >= 30:
            run_priority = 2
            run_reason = f"Last run was {last_days} days ago"
        else:
            run_priority = 0
            run_reason = f"Last run {last.get('status')} {last_days or 0} days ago"
    cards.append({
        "key": "run_health", "title": "Pipeline runs",
        "priority": run_priority, "metric": (last or {}).get("modules_failed") or 0,
        "reason": run_reason, "link": "#pipeline",
    })

    # --- coverage actions + blocked sources --------------------------------
    board = completeness_board.board(conn)
    by_reason = board.get("by_reason", {})
    run_needed = by_reason.get("run_needed", 0)
    review_needed = by_reason.get("review_needed", 0)
    blocked = by_reason.get("source_blocked", 0)
    cards.append({
        "key": "coverage_actions", "title": "Coverage actions",
        "priority": 2 if (run_needed + review_needed) >= 3
        else 1 if (run_needed + review_needed) else 0,
        "metric": run_needed + review_needed,
        "reason": (f"{run_needed} dataset(s) need a first run, "
                   f"{review_needed} need review") if (run_needed + review_needed)
        else "Every catalogued dataset is run and reviewed",
        "link": "#pipeline",
    })
    cards.append({
        "key": "blocked_sources", "title": "Blocked sources",
        "priority": 1 if blocked else 0, "metric": blocked,
        "reason": (f"{blocked} source(s) have a documented gap to read"
                   if blocked else "No blocked sources"),
        "link": "#pipeline",
    })

    # --- schema drift ----------------------------------------------------------
    wh = health.warehouse(conn, settings)
    unapplied = wh.get("unapplied", [])
    orphan = wh.get("applied_without_file", [])
    cards.append({
        "key": "schema_drift", "title": "Schema state",
        "priority": 3 if unapplied else 2 if orphan else 0,
        "metric": len(unapplied) + len(orphan),
        "reason": (
            f"{len(unapplied)} migration(s) on disk not applied"
            if unapplied else
            f"{len(orphan)} applied migration(s) have no file — this checkout "
            "changed" if orphan else "Schema matches the migration files"),
        "link": "#health",
    })

    # --- archive health ------------------------------------------------------
    archive_reason, archive_priority, archive_metric = "No archive audit recorded", 1, 0
    try:
        audit = conn.execute(
            "SELECT run_at, missing_refs, duplicate_hashes "
            "FROM archive_audits ORDER BY run_at DESC LIMIT 1").fetchone()
        if audit:
            missing = audit["missing_refs"] or 0
            dupes = audit["duplicate_hashes"] or 0
            audit_days = _age_days(audit["run_at"])
            archive_metric = missing + dupes
            if missing or dupes:
                archive_priority = 3
                archive_reason = (f"{missing} missing archive ref(s), "
                                  f"{dupes} duplicate hash(es)")
            elif (audit_days or 0) >= 30:
                archive_priority = 1
                archive_reason = f"Last audit {audit_days} days ago, clean"
            else:
                archive_priority = 0
                archive_reason = f"Last audit {audit_days or 0} days ago, clean"
    except Exception:  # pragma: no cover - table may be absent on an old build
        archive_priority = 1
        archive_reason = "Archive-audit table is not present on this build"
    cards.append({
        "key": "archive_health", "title": "Raw archive",
        "priority": archive_priority, "metric": archive_metric,
        "reason": archive_reason, "link": "#health",
    })

    # --- resumable work ----------------------------------------------------
    failures = conn.execute("SELECT COUNT(*) AS n FROM parse_failures").fetchone()["n"] or 0
    cards.append({
        "key": "parse_failures", "title": "Parse failures",
        "priority": 2 if failures >= 50 else 1 if failures else 0,
        "metric": failures,
        "reason": (f"{failures} row(s) a module could not parse — each has a "
                   "logged reason" if failures else "No parse failures"),
        "link": "#health",
    })

    cards.sort(key=lambda c: (-c["priority"], c["key"]))
    top = max((c["priority"] for c in cards), default=0)
    return {
        "cards": cards,
        "priority_labels": _PRIORITY_LABELS,
        "top_priority": top,
        "attention": sum(1 for c in cards if c["priority"] >= 2),
        "note": "Operational states only, ranked by a deterministic reason. "
                "This never ranks evidence quality or a review outcome, and "
                "every action is a link a person follows.",
    }
