"""Responsive admin navigation (BETA-085).

Twelve horizontal tabs became a grouped left rail with a narrow-screen
drawer. The `.tab[data-tab]` buttons and `showTab()` are unchanged, so every
deep link (`#review`, `#sql`, …), the Ctrl-K palette and the count pills all
keep working; only the presentation changed.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static"
INDEX = STATIC / "index.html"
STYLES = STATIC / "styles.css"
APP = STATIC / "app.js"


@pytest.fixture(scope="module")
def index() -> str:
    return INDEX.read_text(encoding="utf-8")


def test_every_tab_survives_the_regroup(index: str) -> None:
    tabs = set(re.findall(r'data-tab="([a-z]+)"', index))
    assert tabs == {
        "overview", "review", "pipeline", "health", "candidates", "census",
        "claims", "search", "claimreview", "exports", "database", "sql",
    }
    # still buttons with the class showTab() and the palette look for
    assert index.count('class="tab" data-tab=') == 12


def test_the_tabs_are_grouped(index: str) -> None:
    groups = re.findall(r'class="tabgroup" data-group="([A-Za-z]+)"', index)
    assert groups == ["Review", "Evidence", "Operations", "Data"]
    # each group carries a visible label
    assert index.count('class="tabgroup-label"') == 4


def test_the_pills_stay_on_their_tabs(index: str) -> None:
    for pill in ("pending-pill", "job-pill", "candidate-pill", "census-pill",
                 "claim-pill"):
        assert f'id="{pill}"' in index


def test_the_rail_becomes_a_drawer_on_narrow_screens() -> None:
    css = STYLES.read_text(encoding="utf-8")
    assert ".tabs {" in css and "position: fixed" in css
    # the narrow override comes after the base `main` rule so it wins the tie
    base = css.index("main { padding: 16px 16px 16px 224px")
    narrow = css.index("main { padding: 16px; }")
    assert narrow > base
    assert "@media (max-width: 1000px)" in css[base:]
    assert ".navtoggle { display: inline-flex; }" in css


def test_selecting_a_tab_closes_the_drawer() -> None:
    app = APP.read_text(encoding="utf-8")
    assert "'#admin-nav'" in app and "classList.remove('open')" in app
    assert "$('#nav-toggle')" in app and "classList.toggle('open')" in app
