"""Document reading room (BETA-081).

A search result opens in a split reading view: the matched passage with its
surrounding elements, document metadata and provenance, a stable passage
link, earlier/later navigation, and a back link that keeps the search behind
it. The passage window stays a bounded window — not the whole document.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PORTAL = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static" / "public"
DOCS_JS = PORTAL / "js" / "pages" / "documents.js"
STYLES = PORTAL / "styles.css"
PQ = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "public_queries.py"


@pytest.fixture(scope="module")
def docs_js() -> str:
    return DOCS_JS.read_text(encoding="utf-8")


def test_a_result_opens_the_reading_room_via_hash_keys(docs_js: str) -> None:
    assert "renderReadingRoom(" in docs_js
    # opened by a page-owned query key, not a re-navigation that loses search
    assert "setDocParams({" in docs_js and "doc: result.document_id" in docs_js
    assert "params.get('doc')" in docs_js


def test_the_reading_room_shows_metadata_provenance_and_a_passage_link(docs_js: str) -> None:
    body = docs_js[docs_js.index("async function renderReadingRoom("):
                   docs_js.index("function contextExpander(")]
    for field in ("Type", "Source", "Published", "Retrieved", "Parser"):
        assert f"text: '{field}'" in body
    assert "Open the source document" in body        # provenance
    assert "Copy passage link" in body               # stable passage link
    assert "passageLink" in body and "location.origin" in body
    assert "pinnedCaveat(data.caveat" in body        # the search caveat travels


def test_earlier_later_re_anchors_on_an_edge_element(docs_js: str) -> None:
    body = docs_js[docs_js.index("async function renderReadingRoom("):]
    assert "elements[0]?.document_element_id" in body            # earlier
    assert "elements[elements.length - 1]?.document_element_id" in body  # later
    assert "has_more_before" in body and "has_more_after" in body


def test_back_to_results_keeps_the_search(docs_js: str) -> None:
    assert "setDocParams({ doc: '', el: '' })" in docs_js
    assert "← Back to results" in docs_js


def test_the_context_ceiling_is_raised_but_still_a_ceiling() -> None:
    text = PQ.read_text(encoding="utf-8")
    assert "_DOCUMENT_CONTEXT_MAX = 8" in text
    # the cap is still applied with min()
    assert "min(int(context), _DOCUMENT_CONTEXT_MAX)" in text


def test_the_split_layout_stacks_on_narrow_screens() -> None:
    css = STYLES.read_text(encoding="utf-8")
    assert ".reading-split" in css
    assert re.search(r"max-width:\s*900px[^}]*\.reading-split\s*\{[^}]*1fr", css) \
        or re.search(r"\.reading-split\s*\{[^}]*grid-template-columns[^}]*\}", css)
