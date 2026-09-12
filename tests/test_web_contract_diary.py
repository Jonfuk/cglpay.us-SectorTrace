"""Contract diary and milestone calendar (BETA-098).

Procurement lifecycle records as dated events. Every date is transcribed
from the notice; an "ends" event is the contract period as published, never
a prediction of renewal, re-tender or completion.
"""
from __future__ import annotations

import sqlite3

import pytest

from pipeline.web import contract_diary
from pipeline.web.queries import QueryError


def _notice(conn, notice_id, *, ntype="tender", ons="E08000025",
            supplier="CHANGE GROW LIVE", published="2025-01-10",
            start="2025-04-01", end="2028-03-31", ocid="ocds-x-1"):
    conn.execute(
        "INSERT INTO contracts (notice_id, supplier_id, ocid, notice_type, "
        " buyer_name, buyer_ons_code, supplier_name_raw, title, value_core, "
        " currency, date_published, date_start, date_end, source_url, "
        " retrieved_at, http_status, source_system, payload_sha256) VALUES "
        "(%s, '', %s, %s, 'Birmingham', %s, %s, 'Substance misuse service', "
        " 5000000, 'GBP', %s, %s, %s, 'https://ft/x', "
        " '2026-01-01T00:00:00Z', 200, 'find_tender', 'h')",
        (notice_id, ocid, ntype, ons, supplier, published, start, end))
    conn.commit()


def test_notice_dates_become_dated_events(conn: sqlite3.Connection) -> None:
    _notice(conn, "n1")
    out = contract_diary.diary(conn, buyer_ons_code="E08000025")
    kinds = [(e["date"], e["kind"]) for e in out["events"]]
    assert kinds == [
        ("2025-01-10", "published"),
        ("2025-04-01", "period_start"),
        ("2028-03-31", "period_end"),
    ]
    assert all(e["source_url"] == "https://ft/x" for e in out["events"])
    assert out["span"] == {"min": "2025-01-10", "max": "2028-03-31"}


def test_an_award_notice_is_marked_award(conn: sqlite3.Connection) -> None:
    _notice(conn, "n2", ntype="award,contract")
    out = contract_diary.diary(conn, buyer_ons_code="E08000025")
    pub = next(e for e in out["events"] if e["date"] == "2025-01-10")
    assert pub["kind"] == "award"


def test_a_period_end_is_labelled_as_published_and_predicts_nothing(
        conn: sqlite3.Connection) -> None:
    _notice(conn, "n3")
    out = contract_diary.diary(conn, buyer_ons_code="E08000025")
    end = next(e for e in out["events"] if e["kind"] == "period_end")
    assert "as published" in end["kind_label"].lower()
    assert "not a forecast" in out["note"].lower()
    assert "never predicts a renewal" in out["note"].lower()


def test_the_year_filter_keeps_only_that_year(conn: sqlite3.Connection) -> None:
    _notice(conn, "n4")
    out = contract_diary.diary(conn, buyer_ons_code="E08000025", year="2025")
    assert {e["date"][:4] for e in out["events"]} == {"2025"}
    assert not any(e["kind"] == "period_end" for e in out["events"])  # 2028


def test_a_scope_is_required(conn: sqlite3.Connection) -> None:
    with pytest.raises(QueryError):
        contract_diary.diary(conn)


def test_provider_scope_uses_verified_aliases(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO supplier_aliases (alias_raw, supplier_key, "
                 "canonical_name) VALUES ('CHANGE GROW LIVE', 'cgl', 'CGL')")
    _notice(conn, "n5", supplier="CHANGE GROW LIVE")
    _notice(conn, "n6", supplier="SOMEONE ELSE")
    out = contract_diary.diary(conn, provider_key="cgl")
    assert {e["notice_id"] for e in out["events"]} == {"n5"}


def test_the_route_is_in_the_openapi_document() -> None:
    from pipeline.web import openapi
    assert "/api/v1/contract_diary" in openapi.document()["paths"]
