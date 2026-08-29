"""Visual research journey (BETA-094).

The current local session as a branching trail of visited routes with named
checkpoints, in one bounded, guarded localStorage key. The offline suite has
no JS engine, so this pins the guarantees by reading the module source.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORTAL = ROOT / "pipeline" / "web" / "static" / "public"
JOURNEY = PORTAL / "js" / "journey.js"


def _src() -> str:
    return JOURNEY.read_text(encoding="utf-8")


def test_the_store_is_versioned_bounded_and_guarded() -> None:
    src = _src()
    assert "export const SCHEMA_VERSION = 1;" in src
    assert "MAX_EVENTS" in src
    assert "raw.v !== SCHEMA_VERSION" in src
    assert "localStorage.getItem(KEY)" in src and "localStorage.setItem(KEY" in src
    assert src.count("catch (e)") >= 2
    assert "new CustomEvent('journeychange')" in src


def test_a_visit_branches_from_the_node_the_reader_was_on() -> None:
    src = _src()
    record = src[src.index("export function recordVisit"):src.index("export function list")]
    # a new node's parent is the current node, not the linear latest
    assert "parent: state.current" in record
    # revisiting an existing hash re-points current, it does not add a node
    assert "state.events.find((e) => e.hash === hash)" in record
    assert "state.current = existing.id" in record
    # the journey page itself is not recorded
    assert "route === 'journey'" in record


def test_prune_keeps_checkpoints_and_the_current_path() -> None:
    src = _src()
    prune = src[src.index("function _prune"):src.index("/** Record a visit")]
    assert "_ancestors(state.events, state.current)" in prune
    assert "keep.has(e.id) || e.name" in prune            # named = checkpoint, kept
    assert "childCount.get(e.id)" in prune                # only leaves are dropped


def test_recording_is_wired_into_the_router() -> None:
    app = (PORTAL / "app.js").read_text(encoding="utf-8")
    assert "import('/js/journey.js')" in app
    assert "m.recordVisit({ hash: hereHash" in app
    assert ".catch(() => {})" in app                      # never blocks a render


def test_the_route_and_module_are_registered() -> None:
    app = (PORTAL / "app.js").read_text(encoding="utf-8")
    assert "'/journey': () => import('/js/journey.js')" in app
    assert "'/journey': 'Research journey'" in app
    server = (ROOT / "pipeline" / "web" / "server.py").read_text(encoding="utf-8")
    assert '"savedsearch", "journey"' in server
