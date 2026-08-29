"""Split-pane review workspace (BETA-087).

Presentation only: on a wide screen the queue is a compact list on the left
and the focused item's full context, source preview, alternatives, history
and decision controls are in a right pane. `renderItem`, the single-item
APIs, the named reviewer, the explicit decision and one-candidate-at-a-time
are unchanged. Below 1000px it stacks to the familiar card list.
"""
from __future__ import annotations

from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static"
INDEX = STATIC / "index.html"
APP = STATIC / "app.js"
STYLES = STATIC / "styles.css"


@pytest.fixture(scope="module")
def app_js() -> str:
    return APP.read_text(encoding="utf-8")


def test_the_review_pane_markup_exists(app_js: str) -> None:
    html = INDEX.read_text(encoding="utf-8")
    assert 'class="review-split"' in html
    assert 'id="review-detail"' in html
    assert 'id="review-list-wrap"' in html


def test_wide_screens_use_the_compact_list_and_a_detail_pane(app_js: str) -> None:
    assert "function splitActive()" in app_js
    assert "matchMedia('(min-width: 1000px)')" in app_js
    # the left list falls back to the dense/compact table on a wide screen
    assert "$('#f-dense').checked || splitActive()" in app_js
    # the focused item is rendered into the detail pane, reusing renderItem
    assert "function renderReviewDetail()" in app_js
    assert "replace(pane, renderItem(item))" in app_js
    # renderFocus keeps the pane in sync
    body = app_js[app_js.index("function renderFocus()"):]
    assert "renderReviewDetail();" in body


def test_it_does_not_touch_the_decision_path(app_js: str) -> None:
    # the detail pane's item still decides by id through the same helper; no
    # new decision route, no change to the reviewer requirement.
    detail = app_js[app_js.index("function renderReviewDetail()"):
                    app_js.index("function renderReviewDetail()") + 600]
    assert "decideItems" not in detail            # it just renders renderItem
    assert "reviewer" not in detail


def test_the_split_stacks_below_1000px() -> None:
    css = STYLES.read_text(encoding="utf-8")
    assert ".review-split { display: block; }" in css
    assert ".review-detail { display: none; }" in css
    block = css[css.index("@media (min-width: 1000px) {", css.index(".review-split")):]
    assert "grid-template-columns: minmax(300px, 380px) 1fr" in block
