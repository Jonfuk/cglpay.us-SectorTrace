"""Saved searches and change alerts (BETA-089).

A repeat researcher saves a complete search — route plus its whole filter
query — into localStorage (guarded), and "Check for new" re-runs it and
compares the match count with the last-seen count. The offline suite has no
JS engine, so this pins the guarantees by reading the module source.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORTAL = ROOT / "pipeline" / "web" / "static" / "public"
SAVED = PORTAL / "js" / "savedsearch.js"


def _src() -> str:
    return SAVED.read_text(encoding="utf-8")


def test_the_store_is_versioned_bounded_and_guarded() -> None:
    src = _src()
    assert "export const SCHEMA_VERSION = 1;" in src
    assert "MAX_SEARCHES" in src
    assert "raw.v !== SCHEMA_VERSION" in src
    # both accessors are inside a catch
    assert "localStorage.getItem(KEY)" in src and "localStorage.setItem(KEY" in src
    assert src.count("catch (e)") >= 2
    assert "new CustomEvent('savedsearchchange')" in src


def test_check_compares_against_last_count_without_persisting() -> None:
    src = _src()
    # checkNew reads last_count and returns a delta; it must not write
    check = src[src.index("export async function checkNew"):src.index("export function feedURL")]
    assert "search.last_count" in check
    assert "delta: count - base" in check
    assert "localStorage.setItem" not in check
    # accepting the new count is a separate, explicit call
    assert "export function markSeen(" in src
    assert "s.last_count = Number.isFinite(count)" in src


def test_only_the_change_stream_gets_a_feed_url() -> None:
    src = _src()
    feed = src[src.index("export function feedURL"):src.index("// --- the")]
    assert "search.route !== 'changes'" in feed
    assert "/api/v1/feed/changes.atom" in feed
    # only the feed's own params are carried through
    for key in ("kind", "source", "since"):
        assert f"'{key}'" in feed


def test_the_save_button_is_wired_into_the_filter_bar() -> None:
    app = (PORTAL / "app.js").read_text(encoding="utf-8")
    assert "class: 'filter-save'" in app
    assert "import('/js/savedsearch.js').then((m) => m.promptSave(location.hash))" in app


def test_the_route_and_module_are_registered() -> None:
    app = (PORTAL / "app.js").read_text(encoding="utf-8")
    assert "'/saved': () => import('/js/savedsearch.js')" in app
    assert "'/saved': 'Saved searches'" in app
    server = (ROOT / "pipeline" / "web" / "server.py").read_text(encoding="utf-8")
    assert '"notebook", "savedsearch"' in server
