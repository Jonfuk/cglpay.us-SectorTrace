"""The command palette — the portal's front door (BETA-027).

Pinned the way this suite pins front-end behaviour: against the source,
because the tests run offline with no browser. What is pinned here is the
contract the rest of the portal depends on, not the implementation:

  * every destination the palette offers is a real route with the router's
    own title for it, so the palette cannot send a reader somewhere stale
    after a rename;
  * the palette navigates and never filters — it holds no filter-bar state,
    so the data-filter chain in test_portal_controls.py is not involved;
  * warehouse-derived strings (document titles above all) reach the DOM as
    text nodes, the same rule every other portal surface follows;
  * document search is debounced, bounded, and stale-guarded, because a
    response for an abandoned query painting over the current one is the
    one bug an offline test can still describe precisely.

The interaction itself (does the overlay open, do arrows move) needs a
browser; that is recorded in beta.md as remaining live validation, the same
caveat BETA-024 carried.
"""
from __future__ import annotations

import re
from pathlib import Path

PORTAL = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static" / "public"
APP = PORTAL / "app.js"
INDEX = PORTAL / "index.html"
PALETTE = PORTAL / "js" / "palette.js"


def _app() -> str:
    return APP.read_text(encoding="utf-8")


def _index() -> str:
    return INDEX.read_text(encoding="utf-8")


def _palette() -> str:
    return PALETTE.read_text(encoding="utf-8")


def _route_titles(app: str) -> dict[str, str]:
    body = re.search(r"const ROUTE_TITLES = \{(.*?)\};", app, re.S)
    assert body, "app.js no longer declares ROUTE_TITLES"
    return dict(re.findall(r"'(/[^']*)': '([^']*)'", body.group(1)))


def _palette_pages(palette: str) -> list[tuple[str, str]]:
    entries = re.findall(r"\['(/[^']*)', '([^']*)', '[^']*'\]", palette)
    assert entries, "palette.js no longer declares its PAGES destinations"
    return entries


def test_every_palette_destination_is_a_real_route():
    """A palette entry for a route that was renamed or removed is a link to
    nowhere, presented as the portal's front door. The titles are held to
    ROUTE_TITLES in both directions."""
    titles = _route_titles(_app())
    for route, title in _palette_pages(_palette()):
        assert route in titles, (
            f"palette.js offers {route!r}, which the router no longer serves")
        assert titles[route] == title, (
            f"palette.js calls {route} {title!r}; the router calls it "
            f"{titles[route]!r}. They must agree or the palette lies.")


def test_index_declares_the_visible_trigger():
    """A shortcut nobody can discover is not a front door. The button is the
    discovery mechanism; Ctrl-K is the accelerator."""
    html = _index()
    assert re.search(r'<button[^>]*id="palette-open"', html), (
        "index.html no longer renders the palette trigger button")
    assert 'aria-haspopup="dialog"' in html, (
        "the palette trigger should announce what it opens")


def test_app_boots_the_palette():
    app = _app()
    assert "import { initPalette } from '/js/palette.js';" in app, (
        "app.js no longer imports the palette module")
    assert "initPalette();" in app, (
        "app.js no longer initialises the palette at boot")


def test_the_palette_navigates_it_does_not_filter():
    """The palette is a navigator like the top-bar council search: every
    choice ends in a hash change. If it ever gains a data-filter control or
    writes global filter state, it has become a filter and the
    test_portal_controls.py chain must grow to cover it."""
    palette = _palette()
    # The attribute as the el() helper would receive it, or a dataset write;
    # prose in comments may name the contract it is refusing.
    assert "'data-filter'" not in palette and "dataset.filter" not in palette, (
        "the palette renders no controls of its own; a filter belongs in the "
        "filter bar, with a state key a page reads")
    assert "setState(" not in palette, (
        "the palette must not write the portal's global filter state")


def test_values_reach_the_dom_as_text_nodes():
    """Document titles in the palette are strings scraped from council PDFs.
    Settled decision 9 applies to this surface like every other."""
    assert "innerHTML" not in _palette(), (
        "the palette must build its rows from element and text nodes, not "
        "concatenated HTML")


def test_documents_search_is_debounced_bounded_and_stale_guarded():
    palette = _palette()
    assert "DOC_MIN_QUERY" in palette and "DOC_DEBOUNCE_MS" in palette, (
        "document search needs its debounce and minimum-query guards; "
        "without names to point at, the guards are the first thing a "
        "refactor loses")
    assert "setTimeout" in palette, "the debounce itself is missing"
    assert re.search(r"limit:\s*DOCUMENT_FETCH_LIMIT", palette), (
        "document results must be bounded — the palette shows five unique "
        "documents from a slightly wider deduped window, not whatever the "
        "endpoint's ceiling is today")
    assert "token !== docToken" in palette, (
        "a slow response for an abandoned query must never paint over the "
        "results for the current one")


def test_document_selection_lands_on_the_search_page():
    """A document result navigates to the documents page for its query — the
    surface with the caveat, the snippet and the honest result count — not
    to a bare document anchor the portal does not have."""
    assert re.search(r"#/documents\?q=\$\{encodeURIComponent\(term\)\}",
                     _palette()), (
        "document results should navigate to #/documents?q=… so the reader "
        "sees the full result list with its caveat")


def test_the_palette_makes_no_external_requests():
    """Same-origin throughout, like every other portal asset: the portal
    works wherever the pipeline works."""
    palette = _palette()
    assert "http://" not in palette and "https://" not in palette, (
        "the palette must not reference any absolute URL")


def test_the_keyboard_contract():
    """The combobox contract BETA-021 established for every portal typeahead:
    arrows move a roving highlight the input announces through
    aria-activedescendant, Enter picks, Escape closes."""
    palette = _palette()
    for expected in ("ArrowDown", "ArrowUp", "Enter", "Escape",
                     "aria-activedescendant", "aria-selected"):
        assert expected in palette, (
            f"the palette's keyboard contract lost {expected}")
    assert "role: 'combobox'" in palette, (
        "the palette input must declare the combobox role")


def test_focus_is_restored_on_close():
    """Opening the palette moves focus; closing it must put focus back where
    it was, or a keyboard user is dropped into the page body."""
    assert "restoreFocusTo" in _palette(), (
        "the palette no longer remembers where focus came from")
    assert "restoreFocusTo.isConnected" in _palette(), (
        "restoring focus to a node the router has since replaced must "
        "degrade to leaving focus alone, not throw")


def test_the_kbd_hint_adapts_to_the_platform():
    """A hint naming a key the machine does not have is a papercut on first
    contact with the product."""
    assert "⌘K" in _palette(), (
        "the palette trigger's kbd hint should say ⌘K on a Mac")
