"""Constraint 3: no restricted_ table/column may reach an export. This is
the schema test the brief requires; export modules (pipeline/exports/*)
must call guard_not_restricted before including anything in a payload.
"""
from __future__ import annotations

import pytest

from pipeline.exports import guard_not_restricted


def test_guard_rejects_restricted_table_name():
    with pytest.raises(ValueError, match="restricted_"):
        guard_not_restricted("restricted_tribunal_parties")


def test_guard_rejects_restricted_column_name():
    with pytest.raises(ValueError, match="restricted_"):
        guard_not_restricted("restricted_claimant_name")


def test_guard_allows_public_table_name():
    guard_not_restricted("tribunal_cases")  # must not raise
