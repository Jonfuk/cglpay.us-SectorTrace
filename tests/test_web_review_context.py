"""Structured review-item context in the operator UI (BETA-052).

A reviewer decides on an item; the context that justifies the item must be
legible, not a wall of pretty-printed JSON — and the complete raw object must
stay reachable for audit. These are source pins against `app.js`: the suite
runs offline with no browser.
"""
from __future__ import annotations

import re
from pathlib import Path

APP = (Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static"
       / "app.js").read_text(encoding="utf-8")


def _fn(name: str) -> str:
    start = APP.index(f"function {name}(")
    depth = 0
    for i in range(start, len(APP)):
        if APP[i] == "{":
            depth += 1
        elif APP[i] == "}":
            depth -= 1
            if depth == 0:
                return APP[start:i + 1]
    raise AssertionError(f"could not bound function {name}")


def test_the_review_item_renders_typed_context_not_raw_json():
    render_item = _fn("renderItem")
    assert "typedContext(item.context_json)" in render_item, (
        "renderItem no longer builds the typed context view")
    # The old behaviour — a bare <pre> of the whole blob — is gone from the
    # item body.
    assert "el('pre', { class: 'context', text: context })" not in render_item


def test_typed_context_classifies_into_the_named_sections():
    fn = _fn("typedContext")
    for bucket in ("source", "entity", "reason", "evidence", "other"):
        assert bucket in fn, f"the {bucket!r} section is missing from typedContext"
    # The five key classifiers exist by name so a refactor cannot silently
    # drop one.
    for classifier in ("_CTX_URL_KEYS", "_CTX_EVIDENCE_KEYS", "_CTX_ENTITY_KEYS",
                       "_CTX_REASON_KEYS"):
        assert classifier in APP, f"{classifier} classifier is missing"


def test_the_raw_context_is_kept_under_disclosure():
    fn = _fn("typedContext")
    assert "ctx-raw" in fn and "Raw context (lossless)" in fn, (
        "the complete context_json must stay available under a <details>")
    assert "formatContext(raw)" in fn, "the raw disclosure must show the full object"


def test_typed_context_builds_the_dom_without_raw_html():
    fn = _fn("typedContext")
    assert "innerHTML" not in fn
    # Values reach the DOM through el()/text nodes and maybeLink-style anchors.
    assert "el('blockquote'" in fn or "ctx-evidence" in fn


def test_navigation_links_point_at_real_portal_routes():
    fn = _fn("_ctxNav")
    assert "/#/providers/" in fn
    assert "/#/authorities/" in fn
    # An ons_code is only linked when it has the portal's own shape.
    assert re.search(r"\^\[A-Z\]\[0-9\]\{8\}\$", fn)
