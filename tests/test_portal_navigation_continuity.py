"""Navigation continuity (BETA-077).

A deep evidence page should behave like a research workspace: a route-aware
breadcrumb back to the exact filtered list it was opened from, a local trail
of recently viewed entities, and scroll restored when returning to a list.
Runtime behaviour is a browser check; this holds the wiring.
"""
from __future__ import annotations

from pathlib import Path

import pytest

PORTAL = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static" / "public"
APP = PORTAL / "app.js"
RECENT = PORTAL / "js" / "recent.js"
SERVER = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "server.py"


@pytest.fixture(scope="module")
def app_js() -> str:
    return APP.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def recent() -> str:
    return RECENT.read_text(encoding="utf-8")


def test_the_router_restores_scroll_for_a_known_url(app_js: str) -> None:
    assert "scrollByHash" in app_js
    assert "scrollByHash.set(lastRenderedHash, window.scrollY)" in app_js
    assert "scrollByHash.has(hereHash)" in app_js
    # a fresh navigation still starts at the top
    assert "window.scrollTo(0, 0)" in app_js


def test_the_breadcrumb_links_back_to_the_originating_filtered_list(app_js: str) -> None:
    assert "lastListHash" in app_js
    # the last *bare* list route (no /key suffix) is what a detail returns to
    assert "if (path === base) lastListHash.set(base, hereHash)" in app_js
    assert "const parentHref = lastListHash.get(base) || parentFallback" in app_js
    assert "class: 'breadcrumbs'" in app_js


def test_recent_module_is_served_and_guarded(recent: str) -> None:
    assert '"recent"' in SERVER.read_text(encoding="utf-8")
    for name in ("getRecent", "pushRecent", "clearRecent", "renderRecentList"):
        assert f"export function {name}" in recent
    assert "sectortrace.recent" in recent
    assert recent.count("catch (e)") >= 3          # private mode never throws
    assert "slice(0, CAP)" in recent               # the list is capped


def test_recent_stores_only_public_identifiers(recent: str) -> None:
    # a type, a public id, a display name the portal already shows — nothing else
    assert "{ type, id, name, at:" in recent
    assert "postcode" not in recent.lower()


def test_the_detail_pages_push_and_the_overview_shows(app_js: str) -> None:
    providers = (PORTAL / "js" / "pages" / "providers.js").read_text(encoding="utf-8")
    authority = (PORTAL / "js" / "pages" / "authority.js").read_text(encoding="utf-8")
    overview = (PORTAL / "js" / "pages" / "overview.js").read_text(encoding="utf-8")
    assert "pushRecent({ type: 'provider'" in providers
    assert "pushRecent({ type: 'authority'" in authority
    assert "renderRecentList(" in overview
    assert "removeEventListener('recentchange'" in overview
