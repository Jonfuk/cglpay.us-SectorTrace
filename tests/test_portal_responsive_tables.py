"""Responsive public data tables (BETA-071).

The portal is table-heavy and horizontal scrolling was the only phone reading
mode. This pins the shared table contract: declarative column priority, a
per-table view menu (density, column chooser, explicit full-table), and the
`min(Xpx, 100%)` grid fix that stopped `.grid.two` overrunning a 375px
viewport. Behaviour at each width is a browser check (no JS runtime in the
offline suite); this holds the shape.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PORTAL = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static" / "public"
COMPONENTS = PORTAL / "js" / "components.js"
STYLES = PORTAL / "styles.css"
CONTRACTS = PORTAL / "js" / "pages" / "contracts.js"


@pytest.fixture(scope="module")
def components() -> str:
    return COMPONENTS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def styles() -> str:
    return STYLES.read_text(encoding="utf-8")


def test_columns_collapse_by_priority_as_the_viewport_narrows(components: str) -> None:
    assert "function withPriorities(" in components
    assert "responsiveLayout: responsive ? 'collapse' : false" in components
    # priority maps to Tabulator's `responsive` weight; unset falls back to
    # column position so the first column is the identifier.
    assert "out.responsive = out.priority !== undefined ? out.priority : index" in components


def test_the_collapsed_fields_are_still_shown_not_dropped(components: str) -> None:
    # Tabulator's collapse layout lists the hidden columns under a per-row
    # toggle, formatted — the data and the export are untouched.
    assert "responsiveLayoutCollapseUseFormatters: true" in components


def test_every_table_gets_the_view_menu(components: str) -> None:
    body = components[components.index("export function tableCard("):]
    assert "class: 'table-view'" in body
    for control in ("Density", "Columns", "Full table"):
        assert control in body, f"the table view menu lost its {control!r} control"
    # the controls act on the live instance
    assert "inst.showColumn" in body and "inst.hideColumn" in body
    assert "responsiveLayout = full ? false : 'collapse'" in body


def test_the_plain_table_fallback_carries_priority_for_css(components: str) -> None:
    body = components[components.index("export function table("):]
    assert "'data-priority'" in body


def test_grid_two_can_shrink_below_its_track_minimum(styles: str) -> None:
    # A bare `minmax(420px, 1fr)` keeps the 420px floor even at 375px wide and
    # overran the page. `min(420px, 100%)` lets it shrink.
    assert "minmax(min(420px, 100%), 1fr)" in styles
    assert "minmax(420px, 1fr)" not in styles


def test_table_overrun_is_contained_in_the_card(styles: str) -> None:
    assert re.search(r"\.tablecard[^{]*\{[^}]*min-width:\s*0", styles)
    assert re.search(r"\.tablecard > div:last-child\s*\{[^}]*overflow-x:\s*auto", styles)


def test_the_wide_contracts_table_declares_column_priorities() -> None:
    text = CONTRACTS.read_text(encoding="utf-8")
    cols = text[text.index("const columns = ["):text.index("];", text.index("const columns = ["))]
    assert "priority: 0" in cols   # Title — the identifier
    assert cols.count("priority:") >= 8   # every column ranked
