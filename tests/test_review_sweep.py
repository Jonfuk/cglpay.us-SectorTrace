"""Closing review items the pipeline has answered for itself.

The risk here is not that too few items close. It is that this quietly closes
something a person should have seen, or overwrites a decision somebody made.
So most of these tests are about what the sweep refuses to touch.

The case it was built for: 1,067 `pfd_concerns_in_pdf_only` items filed when
m08 could only read a metadata stub, still pending after m08 learned to read
the PDFs, of which 459 were answered and none had left the queue.
"""
from __future__ import annotations

import pytest

from pipeline import review_sweep


def add_report(conn, ref, concerns=None):
    conn.execute(
        "INSERT INTO pfd_reports (report_ref, report_url, matters_of_concern, "
        "source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?, ?, ?, 'https://judiciary.uk/x', '2026-08-13T00:00:00Z', "
        "200, 'm08', 'h')", (ref, f"https://judiciary.uk/{ref}", concerns))


def add_item(conn, ref, status="pending", item_type="pfd_concerns_in_pdf_only"):
    conn.execute(
        "INSERT INTO review_queue (module, item_type, raw_value, context_json, "
        "status, created_at) VALUES ('m08_pfd_reports', ?, ?, '{}', ?, "
        "'2026-08-13T00:00:00Z')", (item_type, ref, status))
    return conn.execute("SELECT id FROM review_queue WHERE raw_value = ?",
                         (ref,)).fetchone()[0]


@pytest.fixture
def queued(conn):
    """Three reports: one answered by its PDF, one not, one already decided."""
    add_report(conn, "2026-0001", concerns="The trust had no out-of-hours cover.")
    add_report(conn, "2026-0002", concerns=None)
    add_report(conn, "2026-0003", concerns="Staffing levels were unsafe.")
    add_item(conn, "2026-0001")
    add_item(conn, "2026-0002")
    add_item(conn, "2026-0003", status="approved")
    conn.commit()
    return conn


def statuses(conn):
    return dict(conn.execute(
        "SELECT raw_value, status FROM review_queue").fetchall())


# --- what it closes ------------------------------------------------------------


def test_it_closes_an_item_the_warehouse_can_now_answer(queued):
    result = review_sweep.sweep(queued)

    assert result["closed"]["pfd_concerns_in_pdf_only"] == 1
    assert statuses(queued)["2026-0001"] == "answered"


def test_it_leaves_the_ones_still_genuinely_unanswered(queued):
    """608 of the real 1,067 are like this: the PDF was read and still did not
    yield concerns. Those are a source limitation, and they stay."""
    review_sweep.sweep(queued)

    assert statuses(queued)["2026-0002"] == "pending"


def test_the_closure_records_its_evidence(queued):
    review_sweep.sweep(queued)

    row = queued.execute(
        "SELECT rule, evidence, status_before FROM review_resolutions").fetchone()
    assert row["rule"] == "pfd_concerns_in_pdf_only"
    assert "matters_of_concern" in row["evidence"]
    assert row["status_before"] == "pending"


def test_it_is_idempotent(queued):
    first = review_sweep.sweep(queued)["total"]
    second = review_sweep.sweep(queued)["total"]

    assert (first, second) == (1, 0)
    assert queued.execute(
        "SELECT COUNT(*) FROM review_resolutions").fetchone()[0] == 1


# --- what it refuses to touch --------------------------------------------------


def test_it_never_touches_a_decision_a_person_made(queued):
    """2026-0003 has concerns *and* was approved by somebody. The sweep must
    not relabel it: a decided item stays decided, from both directions."""
    review_sweep.sweep(queued)

    assert statuses(queued)["2026-0003"] == "approved"
    assert queued.execute(
        "SELECT COUNT(*) FROM review_resolutions").fetchone()[0] == 1


def test_it_does_not_touch_other_item_types(conn):
    add_item(conn, "Kent County Council", item_type="unmatched_buyer_name")
    conn.commit()

    review_sweep.sweep(conn)

    assert statuses(conn)["Kent County Council"] == "pending"


def test_an_item_with_no_matching_report_is_left_alone(conn):
    add_item(conn, "2026-9999")
    conn.commit()

    assert review_sweep.sweep(conn)["total"] == 0
    assert statuses(conn)["2026-9999"] == "pending"


def test_whitespace_is_not_an_answer(conn):
    """A `matters_of_concern` of spaces is the parser having found nothing,
    not the question being answered."""
    add_report(conn, "2026-0004", concerns="   ")
    add_item(conn, "2026-0004")
    conn.commit()

    assert review_sweep.sweep(conn)["total"] == 0


# --- reporting and reversal ----------------------------------------------------


def test_a_dry_run_reports_without_closing(queued):
    result = review_sweep.sweep(queued, dry_run=True)

    assert result["closed"]["pfd_concerns_in_pdf_only"] == 1
    assert result["dry_run"] is True
    assert statuses(queued)["2026-0001"] == "pending"
    assert queued.execute(
        "SELECT COUNT(*) FROM review_resolutions").fetchone()[0] == 0


def test_preview_changes_nothing(queued):
    assert review_sweep.preview(queued)["pfd_concerns_in_pdf_only"] == 1
    assert statuses(queued)["2026-0001"] == "pending"


def test_a_rule_can_be_undone_in_one_operation(queued):
    """The reason the rule name is recorded: a rule that turns out to be wrong
    is undone without going through hundreds of rows by hand."""
    review_sweep.sweep(queued)
    assert statuses(queued)["2026-0001"] == "answered"

    reopened = review_sweep.reopen(queued, "pfd_concerns_in_pdf_only")

    assert reopened == 1
    assert statuses(queued)["2026-0001"] == "pending"
    assert queued.execute(
        "SELECT COUNT(*) FROM review_resolutions").fetchone()[0] == 0


def test_reopening_does_not_disturb_a_human_decision(queued):
    """Someone may have decided an answered item in between."""
    review_sweep.sweep(queued)
    queued.execute("UPDATE review_queue SET status = 'rejected' "
                    "WHERE raw_value = '2026-0001'")
    queued.commit()

    review_sweep.reopen(queued, "pfd_concerns_in_pdf_only")

    assert statuses(queued)["2026-0001"] == "rejected"


def test_an_unknown_rule_is_refused(conn):
    with pytest.raises(KeyError):
        review_sweep.sweep(conn, rule="wishful_thinking")
    with pytest.raises(KeyError):
        review_sweep.reopen(conn, "wishful_thinking")


def test_the_sweep_makes_no_requests(queued, httpx_mock):
    """It is a query over what is already there. Any fetch would make this a
    slow operation that needs scheduling rather than one that can be run on a
    whim."""
    review_sweep.sweep(queued)

    assert not httpx_mock.get_requests()


# --- the registry rule ---------------------------------------------------------


def test_a_committee_url_in_the_registry_answers_its_item(conn):
    """The URLs moved into pipeline/authority_websites.py after 191 of them
    were lost with the override table. An item asking where a council
    publishes is answered once the answer is committed to git."""
    from pipeline.authority_websites import AUTHORITY_WEBSITES

    known = next(code for code, entry in AUTHORITY_WEBSITES.items()
                  if entry.committee_url)
    add_item(conn, known, item_type="committee_url_unknown")
    add_item(conn, "E99999999", item_type="committee_url_unknown")
    conn.commit()

    result = review_sweep.sweep(conn, rule="committee_url_in_registry")

    assert result["closed"]["committee_url_in_registry"] == 1
    assert statuses(conn)[known] == "answered"
    assert statuses(conn)["E99999999"] == "pending", (
        "an authority nobody has verified is still an open question")


def test_the_registry_rule_records_the_url_it_answered_with(conn):
    from pipeline.authority_websites import AUTHORITY_WEBSITES

    known = next(code for code, entry in AUTHORITY_WEBSITES.items()
                  if entry.committee_url)
    add_item(conn, known, item_type="committee_url_unknown")
    conn.commit()

    review_sweep.sweep(conn, rule="committee_url_in_registry")

    evidence = conn.execute(
        "SELECT evidence FROM review_resolutions").fetchone()[0]
    assert AUTHORITY_WEBSITES[known].committee_url in evidence


def test_the_registry_rule_leaves_a_decided_item_alone(conn):
    from pipeline.authority_websites import AUTHORITY_WEBSITES

    known = next(code for code, entry in AUTHORITY_WEBSITES.items()
                  if entry.committee_url)
    add_item(conn, known, item_type="committee_url_unknown", status="rejected")
    conn.commit()

    assert review_sweep.sweep(conn, rule="committee_url_in_registry")["total"] == 0
    assert statuses(conn)[known] == "rejected"
