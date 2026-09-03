"""Phase 8: a census figure cannot become verified without a person.

The three things the phase said it would be verified by, plus the ones writing
it turned up:

  * a census metric cannot reach `verified = 1` without a decision row;
  * the mechanism records no payload hash of its own, because nothing was
    fetched;
  * the markdown worklist is replaced by the UI path rather than supplemented
    (that one lives in `test_m06_workforce_census.py`, next to the module that
    used to write it).
"""
from __future__ import annotations

import inspect

import pytest

from pipeline import census_verify, db
from pipeline.web import census as census_web

METRIC = {
    "census_year": 2024,
    "metric": "vacancy_rate",
    "workforce_segment": "delivery",
    "value": 8.0,
    "unit": "percent",
    "source_page": 6,
    "raw_text": "8% vacancy rate in the delivery workforce",
    "source_url": "https://example.com/census-2024.pdf",
    "retrieved_at": "2026-01-01T00:00:00+00:00",
    "http_status": 200,
    "source_system": "m06_workforce_census",
    "payload_sha256": "a" * 64,
}


def _insert_metric(conn: db.Connection, **overrides) -> dict:
    row = {**METRIC, **overrides}
    columns = ", ".join(row)
    marks = ", ".join(f":{name}" for name in row)
    conn.execute(
        f"INSERT INTO workforce_census_metrics ({columns}) VALUES ({marks})", row)
    conn.commit()
    return row


def _insert_page(conn: db.Connection, year: int = 2024, page: int = 6,
                  text: str = "…an 8% vacancy rate in the delivery workforce…") -> None:
    conn.execute(
        "INSERT INTO workforce_census_page_text "
        "(census_year, page_number, page_text, source_url, retrieved_at, "
        " http_status, source_system, payload_sha256) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (year, page, text, METRIC["source_url"], METRIC["retrieved_at"], 200,
         METRIC["source_system"], METRIC["payload_sha256"]))
    conn.commit()


@pytest.fixture
def metric(conn):
    row = _insert_metric(conn)
    return census_verify.metric_key(row)


# --- the database refuses it, not the module ----------------------------------


def test_a_metric_cannot_be_verified_without_a_decision(conn, metric):
    """The guarantee migration 0033 exists for, exercised the way somebody
    would break it: straight SQL, no module involved.

    This is the statement the generated worklist used to print at the top of
    every census_{year}_tables.md.
    """
    with pytest.raises(db.IntegrityError) as raised:
        conn.execute(
            "UPDATE workforce_census_metrics SET verified = 1 "
            "WHERE census_year = 2024")

    assert "not verified without a human" in str(raised.value)
    conn.rollback()
    assert conn.execute(
        "SELECT verified FROM workforce_census_metrics").fetchone()["verified"] == 0


def test_a_metric_cannot_be_inserted_already_verified(conn):
    """The other route in. A rule enforced on UPDATE alone is not enforced --
    a module, an import or the SQL box can write the row verified from the
    start."""
    with pytest.raises(db.IntegrityError) as raised:
        _insert_metric(conn, verified=1)
    assert "not verified without a human" in str(raised.value)


def test_verifying_writes_the_decision_and_then_the_flag(conn, metric):
    result = census_verify.verify(conn, metric, verified_by="Jon",
                                   note="checked against page 6")

    assert result["decision"] == "verified"
    row = conn.execute(
        "SELECT verified, verified_at, rejected FROM workforce_census_metrics"
    ).fetchone()
    assert row["verified"] == 1
    assert row["verified_at"]
    assert row["rejected"] == 0

    decision = conn.execute("SELECT * FROM census_verifications").fetchone()
    assert decision["decided_by"] == "Jon"
    assert decision["decision"] == "verified"
    assert decision["note"] == "checked against page 6"
    # The figure as it read at the time, so a later re-parse is detectable.
    assert decision["checked_value"] == 8.0
    assert decision["checked_unit"] == "percent"
    assert decision["checked_page"] == 6


def test_a_verification_is_attributed(conn, metric):
    with pytest.raises(census_verify.VerificationError) as raised:
        census_verify.verify(conn, metric, verified_by="   ")
    assert "attributed" in str(raised.value)
    assert conn.execute("SELECT COUNT(*) FROM census_verifications").fetchone()[0] == 0


def test_a_failed_verification_leaves_no_decision_row(conn, metric):
    """Two writes, one unit of work. If the flag cannot be raised the decision
    must not survive on its own, or the trigger's EXISTS is satisfied by a
    judgement that never took effect."""
    census_verify.verify(conn, metric, verified_by="Jon")
    with pytest.raises(census_verify.VerificationError):
        census_verify.verify(conn, metric, verified_by="Jon")
    assert conn.execute("SELECT COUNT(*) FROM census_verifications").fetchone()[0] == 1


# --- no payload hash, because nothing was fetched -----------------------------


def test_the_mechanism_records_no_payload_hash_of_its_own(conn):
    """`evidence_promotions` carries fetched_url, http_status, payload_sha256
    and archived_path because promotion retrieves the document. Nothing is
    retrieved here, and a column named as though something had been is an
    invitation to fill it in.
    """
    columns = {row["column_name"] for row in conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = ?",
        ("census_verifications",),
    )}

    for absent in ("payload_sha256", "fetched_url", "http_status", "archived_path"):
        assert absent not in columns, (
            f"census_verifications has a {absent} column. Verification fetches "
            "nothing; the hash it records is m06's, and is named "
            "checked_against_sha256 so it cannot be mistaken for its own.")

    assert {"checked_against_url", "checked_against_sha256"} <= columns


def test_verification_never_touches_the_network(conn, metric):
    """Asserted against the source: promote.py's fetch is the thing this
    mechanism was carved away from, and an import of the client here would be
    the first step back towards it."""
    source = inspect.getsource(census_verify)
    for forbidden in ("PipelineHTTPClient", "httpx", "urllib.request"):
        assert forbidden not in source


def test_the_recorded_hash_is_the_report_m06_archived(conn, metric):
    census_verify.verify(conn, metric, verified_by="Jon")
    decision = conn.execute("SELECT * FROM census_verifications").fetchone()
    assert decision["checked_against_sha256"] == METRIC["payload_sha256"]
    assert decision["checked_against_url"] == METRIC["source_url"]


# --- rejection ----------------------------------------------------------------


def test_rejecting_records_a_decision_and_a_parse_failure(conn, metric):
    count = census_verify.reject(conn, [metric], rejected_by="Jon",
                                  note="that 8% is the 2023 figure")
    assert count == 1

    row = conn.execute(
        "SELECT verified, rejected FROM workforce_census_metrics").fetchone()
    assert (row["verified"], row["rejected"]) == (0, 1)

    decision = conn.execute("SELECT decision FROM census_verifications").fetchone()
    assert decision["decision"] == "rejected"

    # And findable from the parser's side, where m06's other failures are.
    failure = conn.execute("SELECT * FROM parse_failures").fetchone()
    assert failure["module"] == "m06_workforce_census"
    assert "that 8% is the 2023 figure" in failure["reason"]
    assert failure["raw_fragment"] == METRIC["raw_text"]


def test_a_rejected_figure_cannot_be_verified_without_a_reset(conn, metric):
    census_verify.reject(conn, [metric], rejected_by="Jon")
    with pytest.raises(census_verify.VerificationError) as raised:
        census_verify.verify(conn, metric, verified_by="Jon")
    assert "Reset it" in str(raised.value)

    census_verify.reset(conn, metric)
    census_verify.verify(conn, metric, verified_by="Jon")
    assert conn.execute(
        "SELECT verified FROM workforce_census_metrics").fetchone()["verified"] == 1


def test_resetting_keeps_the_decisions(conn, metric):
    """A judgement that was taken was still taken. Deleting the record to tidy
    the flag is how 'who said this?' stops having an answer."""
    census_verify.verify(conn, metric, verified_by="Jon")
    census_verify.reset(conn, metric)

    assert conn.execute(
        "SELECT verified FROM workforce_census_metrics").fetchone()["verified"] == 0
    assert conn.execute("SELECT COUNT(*) FROM census_verifications").fetchone()[0] == 1


# --- a verification can go stale ----------------------------------------------


def test_a_reparsed_value_makes_its_verification_stale(conn, metric):
    census_verify.verify(conn, metric, verified_by="Jon")
    assert census_verify.stale(conn) == []

    # Same line, different number read off it -- which updates the row in
    # place, because raw_text is part of the key and the value is not.
    conn.execute("UPDATE workforce_census_metrics SET value = 9.0")
    conn.commit()

    stale = census_verify.stale(conn)
    assert len(stale) == 1
    assert "value now 9.0, checked as 8.0" in stale[0]["why"]


def test_a_reissued_report_makes_its_verification_stale(conn, metric):
    census_verify.verify(conn, metric, verified_by="Jon")
    conn.execute("UPDATE workforce_census_metrics SET payload_sha256 = ?", ("b" * 64,))
    conn.commit()

    stale = census_verify.stale(conn)
    assert len(stale) == 1
    assert "reissued" in stale[0]["why"][0]


def test_an_unverified_figure_is_never_stale(conn, metric):
    conn.execute("UPDATE workforce_census_metrics SET value = 9.0")
    conn.commit()
    assert census_verify.stale(conn) == []


# --- the module re-running does not undo a check ------------------------------


def test_a_module_rerun_does_not_unverify_a_checked_figure(conn, metric):
    """m06 upserts every metric it re-reads carrying `verified: 0`, and
    `preserve=DECISION_COLUMNS` is what stops that landing. Before 0033 the
    table had only one of the three columns that list names, so `preserve` was
    protecting one by accident -- and the trigger would now abort the write
    outright if it were not preserved.
    """
    from pipeline import db

    census_verify.verify(conn, metric, verified_by="Jon")
    db.upsert(conn, "workforce_census_metrics", {**METRIC, "verified": 0},
               natural_key=["census_year", "metric", "workforce_segment", "raw_text"],
               preserve=db.DECISION_COLUMNS)
    conn.commit()

    assert conn.execute(
        "SELECT verified FROM workforce_census_metrics").fetchone()["verified"] == 1


# --- keys ---------------------------------------------------------------------


def test_a_metric_key_is_stable_and_not_a_rowid(conn, metric):
    """Rowids are not stable across a rebuild, and the identity of a census
    figure has to survive one."""
    same = census_verify.metric_key(dict(METRIC))
    assert same == metric

    conn.execute("DELETE FROM workforce_census_metrics")
    _insert_metric(conn)
    conn.commit()
    assert census_verify.metric_key(
        dict(conn.execute("SELECT * FROM workforce_census_metrics").fetchone())) == metric


def test_metrics_differing_only_in_one_key_column_get_different_keys():
    base = dict(METRIC)
    for column, changed in (("census_year", 2023), ("metric", "turnover_rate"),
                             ("workforce_segment", "commissioning"),
                             ("raw_text", "8% vacancy rate in the delivery workforce.")):
        assert census_verify.metric_key({**base, column: changed}) \
            != census_verify.metric_key(base)


def test_an_unknown_key_is_refused_rather_than_guessed(conn, metric):
    with pytest.raises(census_verify.VerificationError) as raised:
        census_verify.verify(conn, "0" * 16, verified_by="Jon")
    assert "no census metric" in str(raised.value)


# --- the worklist a person actually reads -------------------------------------


def test_the_worklist_carries_the_line_untruncated(conn):
    """The markdown worklist cut the source line at 240 characters, which is
    exactly where a parse that had swallowed a neighbouring sentence stopped
    being visible."""
    long_line = "8% vacancy rate in the delivery workforce. " + ("x" * 400)
    _insert_metric(conn, raw_text=long_line)

    items = census_web.listing(conn)["items"]
    assert items[0]["raw_text"] == long_line


def test_the_worklist_serves_the_page_the_figure_was_read_from(conn, metric):
    """The whole reason this screen can replace the markdown rather than
    duplicate it: the line is what was parsed, the page is what it meant."""
    _insert_page(conn)
    page = census_web.page_text(conn, 2024, 6)

    assert "vacancy rate" in page["page_text"]
    assert page["payload_sha256"] == METRIC["payload_sha256"]
    assert [m["metric"] for m in page["metrics_on_page"]] == ["vacancy_rate"]


def test_a_missing_page_says_so_rather_than_returning_empty_text(conn, metric):
    with pytest.raises(census_verify.VerificationError) as raised:
        census_web.page_text(conn, 2024, 99)
    assert "no archived text" in str(raised.value)


def test_the_counts_track_what_is_still_unchecked(conn, metric):
    _insert_metric(conn, metric="turnover_rate",
                    raw_text="a 19% turnover rate for all staff")

    before = census_web.counts(conn)
    assert (before["total"], before["unchecked"], before["verified"]) == (2, 2, 0)

    census_verify.verify(conn, metric, verified_by="Jon")
    after = census_web.counts(conn)
    assert (after["total"], after["unchecked"], after["verified"]) == (2, 1, 1)
    assert after["years"][0]["census_year"] == 2024


def test_the_worklist_filters_by_status(conn, metric):
    _insert_metric(conn, metric="turnover_rate",
                    raw_text="a 19% turnover rate for all staff")
    census_verify.verify(conn, metric, verified_by="Jon")

    unchecked = census_web.listing(conn, status="unchecked")["items"]
    assert [item["metric"] for item in unchecked] == ["turnover_rate"]

    verified = census_web.listing(conn, status="verified")["items"]
    assert [item["metric"] for item in verified] == ["vacancy_rate"]
    assert verified[0]["decisions"][0]["decided_by"] == "Jon"


def test_an_unknown_status_is_refused(conn):
    with pytest.raises(census_verify.VerificationError):
        census_web.listing(conn, status="promoted")
