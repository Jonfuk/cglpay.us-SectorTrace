"""Recording a human decision on a review-queue item.

This is the only writable path in the UI, and it writes exactly two things:
the item's new status, and a row saying who decided it and why.

What it deliberately does not do is act on the decision. Approving an
`unmatched_buyer_name` does not bind that name to an authority; approving a
`possible_group_company` does not add the company to `companies`. Those are
sixteen different operations belonging to sixteen different modules, each with
its own idea of what evidence is sufficient, and inventing a generic one here
would mean the UI writing rows into canonical tables that no module can
account for or reproduce. The judgement is the thing worth capturing now; the
promotion, where it makes sense at all, belongs in the module that owns the
table.

That boundary is stated in the UI too — a reviewer who thinks approving
publishes something is worse off than one who knows it does not.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from pipeline.web.queries import REVIEW_STATUSES

DECISIONS = REVIEW_STATUSES  # 'approved', 'rejected', and 'pending' as the revert

MAX_NOTE_LENGTH = 2000
MAX_BATCH = 500


class DecisionError(Exception):
    """A decision that was refused, with a message for the reviewer."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def decide(
    conn: sqlite3.Connection,
    item_ids: list[int],
    decision: str,
    decided_by: str,
    note: str | None = None,
) -> dict:
    """Apply `decision` to each of `item_ids`, in one transaction.

    Returns what happened, per outcome, because a bulk action that reports
    only "done" is unreviewable: on a page of fifty, some may already have
    been decided in another tab and some may have been deleted since it
    loaded, and the reviewer should be told which.

    Re-applying the status an item already has is a no-op unless a note comes
    with it. Otherwise a double-click, or approving a page where half the
    items were already approved, would write duplicate audit rows that say
    nothing happened — history worth keeping is history of change, plus any
    remark a person deliberately attached.
    """
    if decision not in DECISIONS:
        raise DecisionError(
            f"Unknown decision {decision!r}. Use one of: {', '.join(DECISIONS)}."
        )

    decided_by = (decided_by or "").strip()
    if not decided_by:
        raise DecisionError(
            "A reviewer name is required — a decision nobody is attached to "
            "cannot be followed up."
        )
    if len(decided_by) > 200:
        raise DecisionError("Reviewer name is too long (200 characters maximum).")

    note = (note or "").strip() or None
    if note and len(note) > MAX_NOTE_LENGTH:
        raise DecisionError(f"Note is too long ({MAX_NOTE_LENGTH} characters maximum).")

    # Deduplicate but keep the order the reviewer sent, so the report reads
    # in the order the screen was in.
    seen: set[int] = set()
    ids: list[int] = []
    for raw in item_ids:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise DecisionError(f"{raw!r} is not a review item id.") from None
        if value not in seen:
            seen.add(value)
            ids.append(value)

    if not ids:
        raise DecisionError("No items selected.")
    if len(ids) > MAX_BATCH:
        raise DecisionError(
            f"{len(ids)} items in one action, which is more than the {MAX_BATCH} "
            "allowed. Deciding in batches keeps a bulk action to something a "
            "person has actually looked at."
        )

    now = _utcnow()
    placeholders = ", ".join("?" for _ in ids)
    existing = {
        row["id"]: row
        for row in conn.execute(
            f"SELECT id, status, context_json FROM review_queue WHERE id IN ({placeholders})",
            ids,
        )
    }

    updated: list[int] = []
    unchanged: list[int] = []
    missing = [item_id for item_id in ids if item_id not in existing]

    # One transaction for the batch: a bulk decision half-applied is worse
    # than one refused, because the reviewer's record of what they did is the
    # screen they were looking at.
    with conn:
        for item_id in ids:
            row = existing.get(item_id)
            if row is None:
                continue
            if row["status"] == decision and not note:
                unchanged.append(item_id)
                continue

            conn.execute(
                "UPDATE review_queue SET status = ?, resolved_at = ? WHERE id = ?",
                # Back to pending clears resolved_at, so the column keeps
                # meaning "when this stopped needing a decision" rather than
                # "when it was last touched".
                (decision, None if decision == "pending" else now, item_id),
            )
            conn.execute(
                "INSERT INTO review_decisions "
                "(review_item_id, decision, status_before, note, decided_by, decided_at, context_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (item_id, decision, row["status"], note, decided_by, now, row["context_json"]),
            )
            updated.append(item_id)

    return {
        "decision": decision,
        "decided_by": decided_by,
        "decided_at": now,
        "note": note,
        "updated": updated,
        "unchanged": unchanged,
        "missing": missing,
    }
