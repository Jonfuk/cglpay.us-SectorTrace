"""The unified quarantine/replay contract (migration 0103) for the three
categories that had no durable table before it: a rejected candidate, a
failed stage input, and an archive object whose hash no longer matches.
`review_queue`/`parse_failures` are untouched — see pipeline/quarantine.py.
"""
from __future__ import annotations

import pytest

from pipeline import quarantine


def test_quarantine_rejects_an_unknown_kind(conn):
    with pytest.raises(ValueError, match="unknown quarantine kind"):
        quarantine.quarantine(
            conn, kind="not_a_real_kind", module="m01_procurement",
            item_identity="x", failure_class="oops", reason="oops")


def test_quarantining_an_item_is_idempotent(conn):
    """Re-observing the same item updates last_seen_at/reason rather than
    appending another copy — the same idiom as parse_failures (migration
    0007), so "how many are still unresolved?" stays answerable."""
    quarantine.quarantine(
        conn, kind="failed_stage_input", module="m03_charity_finance",
        item_identity="charity-123", failure_class="parse_error",
        reason="first observation")
    quarantine.quarantine(
        conn, kind="failed_stage_input", module="m03_charity_finance",
        item_identity="charity-123", failure_class="parse_error",
        reason="second observation, same item")
    conn.commit()

    rows = conn.execute(
        "SELECT reason FROM quarantine_items WHERE item_identity = %s",
        ("charity-123",)).fetchall()
    assert len(rows) == 1
    assert rows[0]["reason"] == "second observation, same item"


def test_a_resolved_item_is_left_alone_by_re_observation(conn):
    item_id = quarantine.quarantine(
        conn, kind="archive_mismatch", module="archive_process",
        item_identity="data/raw/m09/abc.pdf", failure_class="sha256_mismatch",
        reason="original mismatch", input_sha256="abc", output_sha256="def")
    conn.commit()
    quarantine.mark_retried(conn, item_id, outcome="fixed on reprocess", resolved=True)
    conn.commit()

    same_id = quarantine.quarantine(
        conn, kind="archive_mismatch", module="archive_process",
        item_identity="data/raw/m09/abc.pdf", failure_class="sha256_mismatch",
        reason="re-observed after resolution", input_sha256="abc", output_sha256="def")
    conn.commit()

    row = conn.execute(
        "SELECT reason, retry_state FROM quarantine_items WHERE item_id = %s",
        (item_id,)).fetchone()
    assert same_id == item_id
    assert row["retry_state"] == "resolved"
    # mark_retried appends the outcome to the existing reason rather than
    # replacing it, so the resolution note survives alongside the original.
    assert row["reason"] == "original mismatch (retry: fixed on reprocess)"


def test_list_items_filters_and_pages(conn):
    for i in range(3):
        quarantine.quarantine(
            conn, kind="rejected_candidate", module="cdp_document_promotion",
            item_identity=f"https://example.org/{i}", failure_class="human_rejection",
            reason="not what it looked like")
    quarantine.quarantine(
        conn, kind="failed_stage_input", module="m03_charity_finance",
        item_identity="other-item", failure_class="parse_error", reason="x")
    conn.commit()

    rejected = quarantine.list_items(conn, kind="rejected_candidate")
    assert len(rejected) == 3
    assert {row["kind"] for row in rejected} == {"rejected_candidate"}

    first_page = quarantine.list_items(conn, kind="rejected_candidate", limit=2)
    assert len(first_page) == 2
    second_page = quarantine.list_items(
        conn, kind="rejected_candidate", limit=2, cursor=first_page[-1]["item_id"])
    assert len(second_page) == 1
    assert second_page[0]["item_id"] > first_page[-1]["item_id"]


def test_mark_retried_without_resolving_leaves_it_open_for_another_attempt(conn):
    item_id = quarantine.quarantine(
        conn, kind="failed_stage_input", module="m03_charity_finance",
        item_identity="charity-456", failure_class="parse_error", reason="bad xml")
    conn.commit()
    quarantine.mark_retried(conn, item_id, outcome="still failing")
    conn.commit()

    row = quarantine.get_item(conn, item_id)
    assert row["retry_state"] == "retrying"
    assert row["retry_count"] == 1
    assert row["resolved_at"] is None
    assert "still failing" in row["reason"]
