"""The public shell header, and its phone-width contract (BETA-069).

Live review at 390px found the council field clipped past the right edge of
the viewport and the campaign lens printed twice above the hero. The header is
the first screen; these pin the structural facts that keep it usable at phone
widths without re-checking them by eye every change.

Static string checks on the served files, in the style of
`test_portal_offline_reading.py` — the offline suite has no browser. The live
layout at 390x844 / 768x1024 / desktop is verified in a browser per the
programme's acceptance contract.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PUBLIC = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static" / "public"
INDEX = PUBLIC / "index.html"
STYLES = PUBLIC / "styles.css"
APP_JS = PUBLIC / "app.js"


@pytest.fixture(scope="module")
def index() -> str:
    return INDEX.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def styles() -> str:
    return STYLES.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def app_js() -> str:
    return APP_JS.read_text(encoding="utf-8")


def test_council_finder_lives_inside_the_section_drawer(index: str) -> None:
    # The whole `#portal-nav` offcanvas, and the council field must be within
    # it — not a bare child of <header> where it rode the topbar flex row and
    # was clipped at 390px.
    drawer = index.split('id="portal-nav"', 1)[1].split("</header>", 1)[0]
    assert 'id="find-council"' in drawer
    assert 'id="find-council-list"' in drawer


def test_the_council_field_no_longer_sizes_itself_in_viewport_units(styles: str) -> None:
    # The clipping bug: `.findcouncil input { width: min(35vw, 150px) }` in the
    # topbar. In the drawer it is a full-width row, so no vw-based width rule
    # for it should survive.
    for match in re.findall(r"\.findcouncil[^{]*input[^{]*\{[^}]*\}", styles):
        assert "vw" not in match, match


def test_the_council_field_is_a_full_width_drawer_row(styles: str) -> None:
    assert re.search(r"\.portal-nav .findcouncil\s*\{[^}]*width:\s*100%", styles)


def test_the_mobile_theme_control_is_in_the_drawer(index: str) -> None:
    drawer = index.split('id="portal-nav"', 1)[1].split("</header>", 1)[0]
    assert 'id="theme-select-mobile"' in drawer


def test_the_desktop_lift_keeps_the_wide_layout(styles: str) -> None:
    # `.findcouncil { ... margin-left: auto }` is what pulls it back to the
    # right of the nav row on desktop; without it the drawer move would shift
    # the wide header.
    assert re.search(r"\.findcouncil\s*\{[^}]*margin-left:\s*auto", styles)


def test_the_overview_route_does_not_double_print_its_lens(app_js: str) -> None:
    block = app_js.split("lensByRoute", 1)[1].split("};", 1)[0]
    assert "'/pay'" in block  # sanity: this is the map
    assert "'/':" not in block and "'/' :" not in block


def test_the_topbar_still_carries_brand_menu_and_search(index: str) -> None:
    header = index.split("<header", 1)[1].split("</header>", 1)[0]
    assert 'class="brand"' in header
    assert "menu-toggle" in header
    assert 'id="palette-open"' in header
