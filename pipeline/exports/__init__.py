"""Shared guards used by every export module (sheets.py, geojson.py,
echarts.py). Constraint 3: restricted_ tables must never reach an export.
"""
from __future__ import annotations

RESTRICTED_PREFIX = "restricted_"


def guard_not_restricted(table_or_column_name: str) -> None:
    """Raise if the given table or column name is a restricted_ one.
    Call this before including anything in an export payload.
    """
    if table_or_column_name.startswith(RESTRICTED_PREFIX):
        raise ValueError(
            f"Refusing to export {table_or_column_name!r}: restricted_ tables/columns "
            "hold personal data and are excluded from all exports by default."
        )


# Columns that are known to hold personal data even though they don't carry
# the restricted_ prefix (because they live on an otherwise-public table).
# Nothing currently in the schema needs this, but exports must fail closed if
# one is ever added, rather than leaking it because the prefix check passed.
PERSONAL_DATA_COLUMNS: set[str] = {
    "claimant_name_raw",
    # Tribunal and PFD page titles embed the claimant's / deceased's name.
    "page_title_raw",
    "deceased_name",
    "officer_name",
    "person_name",
}
# Deliberately NOT listed: coroner_name. A coroner is a public official named
# on the face of a published report, acting in that capacity, and the brief
# lists coroner name among the fields to capture — blocking it would make the
# field pointless rather than safer.


def guard_columns(table: str, column_names: list[str]) -> None:
    """Validate a table and every column about to be written to an export."""
    guard_not_restricted(table)
    for column in column_names:
        guard_not_restricted(column)
        if column in PERSONAL_DATA_COLUMNS:
            raise ValueError(
                f"Refusing to export column {column!r} from {table!r}: it holds "
                "personal data and must not leave the warehouse."
            )


def assert_no_restricted_tables(conn, tables: list[str]) -> None:
    """Belt-and-braces check that an export's table list contains nothing
    the database itself classifies as restricted.
    """
    from pipeline import db

    restricted = set(db.restricted_tables(conn))
    overlap = restricted.intersection(tables)
    if overlap:
        raise ValueError(
            f"Refusing to export restricted tables: {sorted(overlap)}. These hold "
            "personal data and are excluded from all exports by default."
        )
