"""Constraint 3: no restricted_ table/column may reach an export. This is
the schema test the brief requires; export modules (pipeline/exports/*)
must call guard_not_restricted before including anything in a payload.
"""
from __future__ import annotations

import pytest

from pipeline import db
from pipeline.exports import (
    assert_no_restricted_tables,
    guard_columns,
    guard_not_restricted,
)


def test_guard_rejects_restricted_table_name():
    with pytest.raises(ValueError, match="restricted_"):
        guard_not_restricted("restricted_tribunal_parties")


def test_guard_rejects_restricted_column_name():
    with pytest.raises(ValueError, match="restricted_"):
        guard_not_restricted("restricted_claimant_name")


def test_guard_allows_public_table_name():
    guard_not_restricted("tribunal_cases")  # must not raise


def test_guard_columns_rejects_personal_data_column_without_prefix():
    # claimant_name_raw has no restricted_ prefix, so the prefix check alone
    # would let it through — the personal-data column list must catch it.
    with pytest.raises(ValueError, match="personal data"):
        guard_columns("some_public_table", ["case_number", "claimant_name_raw"])


def test_guard_columns_allows_safe_columns():
    guard_columns("tribunal_cases", ["case_number", "claim_ref", "outcome"])


def test_every_restricted_table_in_the_real_schema_is_rejected(conn):
    """Runs against the actual migrated schema, so a restricted_ table added
    by a future module is automatically covered by this test.
    """
    restricted = db.restricted_tables(conn)
    assert restricted, "expected at least one restricted_ table in the schema"
    for table in restricted:
        with pytest.raises(ValueError):
            guard_not_restricted(table)


def test_assert_no_restricted_tables_blocks_a_bad_export_list(conn):
    restricted = db.restricted_tables(conn)
    with pytest.raises(ValueError, match="Refusing to export restricted tables"):
        assert_no_restricted_tables(conn, ["tribunal_cases", restricted[0]])


def test_assert_no_restricted_tables_allows_clean_export_list(conn):
    assert_no_restricted_tables(conn, ["tribunal_cases", "contracts", "authorities"])
