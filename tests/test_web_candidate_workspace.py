"""The candidate-promotion campaign workspace (BETA-061).

BETA-061 adds a focused view over the *existing* candidate screens: a
session-progress line, and a per-candidate triage preview rendered through the
shared typed-context presenter. It deliberately adds no route and no bulk
path. The promotion rules live in test_promote.py; the no-bulk-promote
contract lives in test_web_candidates.py. What is pinned here is that the
workspace additions did not weaken either.
"""
from __future__ import annotations

import re
import threading

import httpx
import pytest

from pipeline.web.server import STATIC_DIR, build_server


def _read(*parts: str) -> str:
    path = STATIC_DIR
    for part in parts:
        path = path / part
    return path.read_text(encoding="utf-8")


def _fn_body(source: str, signature: str) -> str:
    """The text of one function, from its signature to the next top-level
    `function ` / `export ` at column zero. Good enough for a source pin."""
    start = source.index(signature)
    rest = source[start + len(signature):]
    end = re.search(r"\n(?:export |function |async function |const \w+ =)", rest)
    return rest[: end.start()] if end else rest


# --- the shared presenter ----------------------------------------------------


def test_the_shared_context_module_and_the_classic_script_agree_on_the_keys():
    """`typedContext` now has two copies -- app.js (classic script, no exports)
    and js/context.js (imported by the ES modules). They must classify keys the
    same way or the review queue and the candidate preview drift apart. The
    four bucket regexes are the contract."""
    classic = _read("app.js")
    module = _read("js", "context.js")

    for name in ("_CTX_URL_KEYS", "_CTX_EVIDENCE_KEYS", "_CTX_ENTITY_KEYS",
                  "_CTX_REASON_KEYS"):
        line = re.compile(rf"^const {name} = .+$", re.MULTILINE)
        in_classic = line.search(classic)
        in_module = line.search(module)
        assert in_classic and in_module, f"{name} is missing from a copy"
        assert in_classic.group(0) == in_module.group(0), (
            f"{name} differs between app.js and js/context.js")


def test_the_context_module_imports_only_a_sibling():
    module = _read("js", "context.js")
    imports = re.findall(r"""^import\s[^'"]*['"]([^'"]+)['"]""", module, re.MULTILINE)
    assert imports == ["./dom.js"], imports


# --- the preview -----------------------------------------------------------


def test_the_preview_is_triage_and_does_not_mark_a_candidate_opened():
    """Opening the preview must not make a candidate batch-promotable. The
    batch gate is that a person looked at the *document*, on its own server;
    the preview only shows the warehouse row we already hold."""
    source = _read("js", "candidates.js")
    body = _fn_body(source, "function previewBlock(item)")
    assert "markOpened" not in body, (
        "the preview calls markOpened -- viewing a summary is not opening the "
        "document, and must not satisfy the batch gate")
    assert "candidates/detail" in body, "the preview should read the detail route"
    assert "typedContext(" in body


def test_the_preview_adds_no_route():
    """BETA-061 is a view over the existing endpoints. A campaign/bulk route
    would be the regression."""
    import inspect

    from pipeline.web import server as server_mod

    src = inspect.getsource(server_mod)
    for forbidden in ("promote-all", "promote-matching", "promote-many",
                       "candidates/campaign", "candidates/promote-"):
        assert forbidden not in src, f"server.py grew a {forbidden!r} route"


# --- the session line ----------------------------------------------------


def test_the_session_line_counts_promote_reject_and_reset():
    source = _read("js", "candidates.js")
    for kind in ("'promoted'", "'rejected'", "'reset'"):
        assert f"bumpSession({kind}" in source, f"nothing increments {kind}"
    assert "candidate-session" in _read("index.html")


def test_the_session_line_is_not_persisted():
    """'decided this session' is a claim about the person here now. A
    localStorage key would let it survive a reload and read as somebody
    else's work -- the same reasoning as state.opened."""
    source = _read("js", "candidates.js")
    body = _fn_body(source, "function bumpSession(kind, n = 1)")
    assert "localStorage" not in body and "store." not in body


# --- no bulk-promote control -------------------------------------------------


def test_there_is_still_no_promote_all_control():
    html = _read("index.html")
    lowered = html.lower()
    assert "promote all" not in lowered
    assert "promote-all" not in lowered
    # The only promote buttons are the per-row one and the opened-batch one.
    assert 'id="candidate-promote-opened"' in html
    assert lowered.count("promote") >= 1


# --- the detail route still backs the preview ------------------------------


@pytest.fixture
def client(conn, settings):
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=10.0) as http:
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def seeded(conn):
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, "
        "first_seen_vintage, last_seen_vintage, source_url, retrieved_at, "
        "http_status, source_system, payload_sha256) VALUES "
        "('E10000016', 'Kent', 'CTY', '2013-04-01', '2024', '2024', "
        "'https://example.org/a', '2026-08-01T00:00:00Z', 200, 'ons', 'abc')")
    conn.execute(
        "INSERT INTO cdp_document_candidates (authority_ons_code, candidate_url, "
        "title, document_type_guess, confidence, discovered_at, discovery_method, "
        "verified, rejected, source_url, retrieved_at, http_status, source_system, "
        "payload_sha256) VALUES ('E10000016', 'https://kent.gov.uk/doc0.pdf', "
        "'Kent drug and alcohol strategy', 'strategy', 0.5, "
        "'2026-08-01T00:00:00Z', 'link', 0, 0, 'https://kent.gov.uk/list', "
        "'2026-08-01T00:00:00Z', 200, 'm09', 'listing-hash')")
    conn.commit()
    return conn


def test_the_preview_data_source_returns_the_whole_row(client, seeded):
    """The preview renders `candidate` from the detail payload. It has to be
    the full row, not the three summary columns, for the typed sections to
    have anything to sort."""
    payload = client.get(
        "/api/admin/candidates/detail"
        "?kind=cdp_document&url=https://kent.gov.uk/doc0.pdf").json()

    row = payload["candidate"]
    assert row["title"] == "Kent drug and alcohol strategy"
    assert row["source_url"] == "https://kent.gov.uk/list"
    assert row["candidate_url"] == "https://kent.gov.uk/doc0.pdf"


def test_the_preview_route_is_not_on_the_portal(client, seeded):
    assert client.get(
        "/api/v1/candidates/detail?kind=cdp_document&url=x").status_code == 404
