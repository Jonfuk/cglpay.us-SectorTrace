"""Fuzzy-name suggestions for a review-queue item.

The PostgreSQL-backed suite exercises the `pg_trgm` ranking path directly.
What is pinned here is the shape and the ordering: the right target near the
top, the score reported, nothing written, and an item type with no reference
set answered rather than errored.
"""
from __future__ import annotations

import sqlite3

import pytest

from pipeline.web import name_matches


def _authority(conn, ons_code, name, kind="unitary", active_to=None):
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, "
        " active_to, first_seen_vintage, last_seen_vintage, source_url, "
        " retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (%s, %s, %s, '2021-04-01', %s, '2024', '2026', 'https://ons.example', "
        " '2026-08-01T00:00:00Z', 200, 'ons', 'x')",
        (ons_code, name, kind, active_to))


def _queue_item(conn, item_type, raw_value):
    cur = conn.execute(
        "INSERT INTO review_queue (module, item_type, raw_value, created_at) "
        "VALUES ('m01_procurement', %s, %s, '2026-08-01T00:00:00Z') RETURNING id",
        (item_type, raw_value))
    return cur.fetchone().values().__iter__().__next__()


@pytest.fixture
def warehouse(conn: sqlite3.Connection) -> sqlite3.Connection:
    _authority(conn, "E06000019", "Herefordshire, County of")
    _authority(conn, "E08000025", "Birmingham City Council", "metropolitan_district")
    _authority(conn, "E10000028", "Staffordshire County Council", "county")
    # Retired code: excluded by the `active_to IS NULL` filter even if its
    # name is a closer string match.
    _authority(conn, "E06000048", "Herefordshire", active_to="2019-04-01")
    conn.commit()
    return conn


def test_unmatched_buyer_name_ranks_the_right_authority_first(warehouse):
    item_id = _queue_item(warehouse, "unmatched_buyer_name", "Herefordshire Council")
    result = name_matches.suggestions(warehouse, item_id)

    assert result["method"] == "pg_trgm"
    assert result["query"] == "Herefordshire Council"
    assert result["matches"], "expected at least one candidate"
    top = result["matches"][0]
    assert top["target"] == "authorities"
    assert top["id"] == "E06000019"
    assert 0.0 < top["score"] <= 1.0
    # The retired code is never offered.
    assert "E06000048" not in {m["id"] for m in result["matches"]}


def test_possible_group_company_strips_the_number_and_matches_names(warehouse):
    warehouse.execute(
        "INSERT INTO providers (provider_key, canonical_name) "
        "VALUES ('cgl', 'Change Grow Live')")
    warehouse.execute(
        "INSERT INTO companies (company_number, company_name, source_url, "
        " retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('06228752', 'CHANGE, GROW, LIVE SERVICES LIMITED', 'https://ch.example', "
        " '2026-08-01T00:00:00Z', 200, 'companies_house', 'x')")
    warehouse.commit()

    item_id = _queue_item(warehouse, "possible_group_company",
                           "06228752 Change Grow Live Services Limited")
    result = name_matches.suggestions(warehouse, item_id)

    # The leading company number is not part of the match.
    assert not result["query"].startswith("06228752")
    targets = {m["target"] for m in result["matches"]}
    assert targets <= {"providers", "companies"}
    assert result["matches"], "expected a company or provider candidate"


def test_unknown_item_type_is_answered_not_errored(warehouse):
    item_id = _queue_item(warehouse, "unmatched_buyer_name", "x")
    # Rewrite to a type with no reference set.
    warehouse.execute("UPDATE review_queue SET item_type = 'pfd_concerns_in_pdf_only' "
                       "WHERE id = %s", (item_id,))
    warehouse.commit()
    result = name_matches.suggestions(warehouse, item_id)
    assert result["matches"] == []
    assert result["method"] is None
    assert "note" in result


def test_missing_item_raises(warehouse):
    with pytest.raises(name_matches.NameMatchError):
        name_matches.suggestions(warehouse, 999999)


def test_nothing_is_written(warehouse):
    item_id = _queue_item(warehouse, "unmatched_buyer_name", "Birmingham")
    before = warehouse.execute("SELECT COUNT(*) FROM review_queue").fetchone().values().__iter__().__next__()
    name_matches.suggestions(warehouse, item_id)
    after = warehouse.execute("SELECT COUNT(*) FROM review_queue").fetchone().values().__iter__().__next__()
    assert before == after
