"""The portal's routes are distinguishable outside the page itself.

app.js is a hash router over one HTML document, so every route shares the DOM
that index.html shipped. Two consequences were live for the portal's whole
existence before BETA-024:

  * all thirteen routes shared index.html's static <title>, so browser
    history could not tell routes apart and nothing named the page a reader
    had just navigated to;
  * a route change replaced #main wholesale while focus stayed wherever it
    was — usually the nav link that was clicked — so a screen reader user
    activating a link heard nothing about the page that replaced the old
    one.

This file pins both behaviours the way this suite pins front-end behaviour:
against the source, because the tests run offline with no browser.
"""
from __future__ import annotations

import re
from pathlib import Path

PORTAL = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static" / "public"
APP = PORTAL / "app.js"
INDEX = PORTAL / "index.html"


def _source() -> str:
    return APP.read_text(encoding="utf-8")


def _object_route_keys(source: str, name: str) -> set[str]:
    body = re.search(rf"const {name} = \{{(.*?)\}};", source, re.S)
    assert body, f"app.js no longer declares {name}"
    return set(re.findall(r"'(/[^']*)':", body.group(1)))


def test_every_route_declares_a_title():
    source = _source()
    routes = _object_route_keys(source, "ROUTES")
    titles = _object_route_keys(source, "ROUTE_TITLES")
    assert routes == titles, (
        "ROUTES and ROUTE_TITLES have drifted apart: "
        f"untitled routes {sorted(routes - titles)}, "
        f"titles without routes {sorted(titles - routes)}")


def test_render_sets_document_title():
    assert "document.title = routeLabel ? `${routeLabel} · SectorTrace` : 'SectorTrace';" \
        in _source(), (
        "render() no longer names the route in document.title")


def test_focus_moves_to_main_on_navigation_only():
    source = _source()
    assert "main.focus({ preventScroll: true })" in source, (
        "route changes no longer hand focus to #main")
    # The gate matters as much as the move: filter changes re-render the whole
    # page through the state subscription, and those must not yank focus out
    # of whatever control the reader is using. Pin both halves of the guard.
    assert "const navigating = renderedBase !== null && renderedBase !== base;" in source
    assert "if (navigating) main.focus({ preventScroll: true });" in source


def test_main_is_focusable_for_the_handoff():
    """#main must carry tabindex="-1": programmatic .focus() lands nowhere on
    an element without it, and the failure is silent."""
    html = INDEX.read_text(encoding="utf-8")
    assert re.search(r'<main[^>]*tabindex="-1"', html), (
        "index.html's <main> lost tabindex=\"-1\"; the navigation focus "
        "handoff depends on it")
