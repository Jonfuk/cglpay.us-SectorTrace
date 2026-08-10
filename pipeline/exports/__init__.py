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
