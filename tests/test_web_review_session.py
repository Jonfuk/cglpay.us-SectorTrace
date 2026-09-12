"""Review-session workflow polish (BETA-055).

Session progress, saved filter/note presets, a primary-source shortcut and
the keyboard map. None of it touches a decision or a confirmation path —
these are source pins that it stays that way.
"""
from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static"
APP = (STATIC / "app.js").read_text(encoding="utf-8")
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")


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
    raise AssertionError(f"could not bound {name}")


def test_the_session_progress_line_is_a_live_region():
    assert 'id="review-session"' in INDEX
    assert 'id="review-session" class="muted small" aria-live="polite"' in INDEX


def test_the_session_counter_makes_no_server_call():
    fn = _fn("bumpReviewSession")
    assert "/api/" not in fn and "post(" not in fn and "fetch(" not in fn
    # It is skipped for an undo, so an undo does not inflate the count.
    assert "if (!isUndo) bumpReviewSession(result.updated.length);" in APP


def test_the_primary_source_shortcut_opens_a_new_tab_and_is_documented():
    fn = _fn("openFocusedSource")
    assert "window.open(" in fn and "'_blank'" in fn
    assert "o: openFocusedSource," in APP
    keys = INDEX[INDEX.index('class="muted small keys"'):]
    keys = keys[:keys.index("</p>")]
    assert "<kbd>o</kbd> open primary source" in keys


def test_the_source_url_is_taken_from_context_or_a_url_raw_value():
    fn = _fn("itemSourceUrl")
    assert "context.context_json" not in fn        # parses item.context_json
    assert "source_url" in fn and "written_statement_url" in fn
    assert "item.raw_value" in fn


def test_presets_are_localstorage_only():
    assert "const PRESET_KEY = 'cglpay.review.presets';" in APP
    for fname in ("loadPresets", "savePresets", "applyPreset", "initReviewPresets"):
        fn = _fn(fname)
        assert "/api/" not in fn, f"{fname} talks to the server; presets are local"
    # The presets control exists in the tab.
    assert 'id="review-preset"' in INDEX
    assert 'id="review-preset-save"' in INDEX


def test_applying_a_preset_reloads_the_list_but_touches_no_decision_path():
    fn = _fn("applyPreset")
    assert "loadReview()" in fn
    assert "decide" not in fn and "confirm_count" not in fn
