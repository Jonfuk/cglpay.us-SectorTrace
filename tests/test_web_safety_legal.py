"""Safety and legal evidence hub (BETA-079).

Six accountability sources on one chronology (HSE notices and HSE
convictions, added JON-43, are two of the six — kept as separate sources
because a notice and a conviction are different instruments). They encode
materially different relationships, so each event carries exactly one label —
addressed_to / named_in / matched_to / regulated_by — and the counts are
given by source and by relationship and are never added together. A mention
is never a finding of fault.
"""
from __future__ import annotations

import sqlite3

import pytest

from pipeline.web import public_queries as pq


@pytest.fixture
def sl(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.execute("INSERT INTO providers (provider_key, canonical_name, is_target) "
                  "VALUES ('cgl', 'Change Grow Live', 1)")
    conn.execute(
        "INSERT INTO pfd_reports (report_ref, report_date, coroner_area, "
        " report_url, source_url, retrieved_at, http_status, source_system, "
        " payload_sha256) VALUES ('2024-0001', '2024-05-01', 'Inner London', "
        " 'https://judiciary.example/1', 'https://judiciary.example/1', "
        " '2026-08-01T00:00:00Z', 200, 'judiciary_uk', 'p1')")
    conn.execute(
        "INSERT INTO pfd_provider_mentions (report_ref, provider_key, "
        " mention_type, matched_name) VALUES "
        "('2024-0001', 'cgl', 'recipient', 'Change Grow Live')")
    conn.execute(
        "INSERT INTO pfd_provider_mentions (report_ref, provider_key, "
        " mention_type, matched_name) VALUES "
        "('2024-0001', 'cgl', 'body_text', 'Change Grow Live')")
    conn.execute(
        "INSERT INTO hse_enforcement_notices (notice_number, recipient_name, "
        " provider_key, notice_type, issuing_body, issue_date, result, "
        " source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('HSE/1', 'Change Grow Live', 'cgl', 'Improvement', 'HSE', "
        " '2023-03-10', 'Complied', 'https://hse.example/1', "
        " '2026-08-01T00:00:00Z', 200, 'hse', 'h1')")
    conn.execute(
        "INSERT INTO hse_enforcement_convictions (breach_id, case_number, "
        " defendant_name, provider_key, hearing_date, result, fine_text, "
        " legislation, source_url, retrieved_at, http_status, source_system, "
        " payload_sha256) VALUES ('4740932001', '47409320', 'Change Grow Live', "
        " 'cgl', '2024-03-15', 'Guilty-Fine', '300,000.00', "
        " 'HSWA 1974 / 2 / 1', 'https://hse.example/breach/1', "
        " '2026-08-01T00:00:00Z', 200, 'hse_enforcement_convictions', 'c1')")
    conn.commit()
    return conn


def test_events_carry_one_relationship_label_and_counts_are_not_summed(sl) -> None:
    out = pq.safety_legal(sl)
    labels = {e["relationship"] for e in out["events"]}
    assert labels <= {"addressed_to", "named_in", "matched_to", "regulated_by"}

    # PFD recipient -> addressed_to; PFD body_text -> named_in;
    # HSE notice + HSE conviction -> matched_to (two distinct sources, one
    # relationship label between them).
    by_rel = out["counts"]["by_relationship"]
    assert by_rel["addressed_to"] == 1
    assert by_rel["named_in"] == 1
    assert by_rel["matched_to"] == 2
    # there is no single total key anywhere in counts
    assert set(out["counts"]) == {"by_source", "by_relationship"}
    assert "total" not in out and "count" not in out


def test_the_four_labels_are_explained_and_a_mention_is_not_a_finding(sl) -> None:
    out = pq.safety_legal(sl)
    assert set(out["labels"]) == {"addressed_to", "named_in", "matched_to", "regulated_by"}
    assert "not a finding" in out["labels"]["named_in"].lower()
    assert "never" in out["note"].lower() and "fault" in out["note"].lower()


def test_each_source_keeps_its_own_caveat(sl) -> None:
    out = pq.safety_legal(sl)
    assert set(out["caveats"]) == {
        "pfd", "sar", "hse", "hse_conviction", "tribunal", "cqc"}
    assert all(out["caveats"].values())


def test_hse_conviction_is_a_source_distinct_from_hse_notices(sl) -> None:
    convictions = pq.safety_legal(sl, source="hse_conviction")
    assert {e["source"] for e in convictions["events"]} == {"hse_conviction"}
    assert convictions["counts"]["by_source"] == {"hse_conviction": 1}
    event = convictions["events"][0]
    assert event["result"] == "Guilty-Fine (fine 300,000.00)"
    assert "breach" in event["title"].lower()

    notices = pq.safety_legal(sl, source="hse")
    assert {e["source"] for e in notices["events"]} == {"hse"}
    assert notices["counts"]["by_source"] == {"hse": 1}


def test_source_and_relationship_filters_narrow_the_same_rows(sl) -> None:
    hse = pq.safety_legal(sl, source="hse")
    assert {e["source"] for e in hse["events"]} == {"hse"}
    assert hse["counts"]["by_source"] == {"hse": 1}

    named = pq.safety_legal(sl, relationship="named_in")
    assert {e["relationship"] for e in named["events"]} == {"named_in"}


def test_the_hse_result_is_the_registers_own_text_not_an_inference(sl) -> None:
    hse = pq.safety_legal(sl, source="hse")
    assert hse["events"][0]["result"] == "Complied"


def test_year_bounds_only_touch_dated_events(sl) -> None:
    out = pq.safety_legal(sl, year_from="2024")
    # the 2023 HSE notice drops; the 2024 PFD events and 2024 HSE conviction
    # (a distinct source from the notice) stay
    assert {e["source"] for e in out["events"]} == {"pfd", "hse_conviction"}


def test_the_route_is_in_the_openapi_document() -> None:
    from pipeline.web import openapi
    doc = openapi.document()
    assert "/api/v1/safety_legal" in doc["paths"]
