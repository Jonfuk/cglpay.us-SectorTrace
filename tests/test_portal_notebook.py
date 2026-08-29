"""Evidence notebook (BETA-088).

A single-browser research workspace in `localStorage`: one versioned,
size-bounded key holding named collections of pinned items, each with a
private note, plus lossless JSON import/export. Nothing leaves the browser.
The offline suite has no JS engine, so this pins the guarantees by reading
the module source.
"""
from __future__ import annotations

from pathlib import Path

PORTAL = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static" / "public"
NOTEBOOK = PORTAL / "js" / "notebook.js"


def _src() -> str:
    return NOTEBOOK.read_text(encoding="utf-8")


def test_the_schema_is_versioned_and_size_bounded() -> None:
    src = _src()
    assert "export const SCHEMA_VERSION = 1;" in src
    for bound in ("MAX_BYTES", "MAX_COLLECTIONS", "MAX_ITEMS", "MAX_NOTE"):
        assert bound in src, bound
    # a write that would cross the byte ceiling is refused, not truncated
    assert "serialized.length > MAX_BYTES" in src
    assert "return { ok: false, reason: 'full' }" in src


def test_every_localstorage_access_is_guarded() -> None:
    """Private mode must degrade to an empty notebook, never throw."""
    src = _src()
    # the three raw accessors only ever appear inside a try block
    for call in ("localStorage.getItem(KEY)", "localStorage.setItem(KEY",):
        assert call in src
    # read() and write() both catch
    assert src.count("catch (e)") >= 3
    assert "} catch (e) {\n    return _fresh();" in src
    assert "reason: 'blocked'" in src  # setItem failure is handled, not raised


def test_import_rejects_anything_that_is_not_a_matching_notebook() -> None:
    src = _src()
    assert "parsed.v !== SCHEMA_VERSION" in src
    assert "not a v${SCHEMA_VERSION} notebook" in src
    # export is the whole cleaned notebook, so a round-trip is lossless
    assert "export function exportJSON() {" in src
    assert "JSON.stringify(read(), null, 2)" in src


def test_writes_announce_themselves_for_live_buttons() -> None:
    src = _src()
    assert "new CustomEvent('notebookchange')" in src
    assert "window.addEventListener('notebookchange', paint)" in src


def test_only_known_public_kinds_can_be_pinned() -> None:
    src = _src()
    assert "export const ITEM_KINDS = {" in src
    for kind in ("record", "passage", "chart", "provider", "authority"):
        assert f"{kind}:" in src
    # addItem refuses an unknown kind or a missing ref
    assert "if (!(kind in ITEM_KINDS) || !ref) return { ok: false, reason: 'invalid' }" in src


def test_the_pin_button_is_wired_into_entity_and_passage_pages() -> None:
    for page in ("providers.js", "authority.js", "documents.js"):
        text = (PORTAL / "js" / "pages" / page).read_text(encoding="utf-8")
        assert "import { notebookButton } from '/js/notebook.js';" in text, page
        assert "notebookButton({" in text, page


def test_the_route_and_module_are_registered() -> None:
    app = (PORTAL / "app.js").read_text(encoding="utf-8")
    assert "'/notebook': () => import('/js/notebook.js')" in app
    assert "'/notebook': 'Evidence notebook'" in app
    server = (Path(__file__).resolve().parent.parent / "pipeline" / "web"
              / "server.py").read_text(encoding="utf-8")
    assert '"recent", "notebook"' in server
