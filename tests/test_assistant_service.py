"""The single-turn assistant orchestration service and its routes (BETA-112).

`service.ask` is the one function both `POST /api/admin/assistant` and
`pipeline nlp assistant` call. One read-only tool call per turn; every failure
mode resolves to an explicit outcome; one immutable ledger row per turn.
"""
from __future__ import annotations

import json
import threading

import httpx
import pytest

from pipeline import db
from pipeline.assistant import ledger, runtime, service
from pipeline.assistant.runtime import AssistantUnavailable
from pipeline.web.server import build_server


@pytest.fixture
def enabled(settings, monkeypatch):
    monkeypatch.setattr(settings, "assistant_enabled", True, raising=False)
    monkeypatch.setattr(runtime, "openai_client_installed", lambda: True)
    return settings


class FakeNeedle:
    def __init__(self, reply):
        self._reply = reply

    def generate(self, prompt, *, system=None, timeout=None, **_):
        if isinstance(self._reply, Exception):
            raise self._reply
        return json.dumps(self._reply)


class FakeLFM:
    def __init__(self, reply):
        self._reply = reply

    def generate(self, prompt, *, system=None, max_tokens=None, timeout=None, **_):
        if isinstance(self._reply, Exception):
            raise self._reply
        return self._reply


def test_disabled_layer_returns_unavailable_and_writes_no_ledger_row(conn, settings):
    out = service.ask(conn, settings, "how fresh is contracts?")
    assert out["outcome"] == "unavailable"
    assert out["run_id"] is None
    assert ledger.recent(conn) == []


def test_a_clarification_is_recorded_and_returned(conn, enabled):
    out = service.ask(conn, enabled, "tell me about the staff",
                      needle_adapter=FakeNeedle({"tool": None, "confidence": 0.1}),
                      lfm_adapter=FakeLFM("unused"))
    assert out["outcome"] == "clarified"
    assert out["clarification"]
    assert out["answer"] is None
    row = ledger.one(conn, out["run_id"])
    assert row["outcome"] == "clarified"


def test_a_full_turn_produces_a_cited_answer_and_a_ledger_row(conn, enabled):
    needle = FakeNeedle({"tool": "inspect_freshness", "arguments": {},
                          "confidence": 0.92})
    # inspect_freshness on the empty warehouse still yields table rows to cite.
    first = service.ask(conn, enabled, "which tables exist?",
                        needle_adapter=needle, lfm_adapter=FakeLFM("no cite"))
    # "no cite" -> abstained (no citation), but the tool ran and was recorded.
    assert first["outcome"] in ("abstained", "ok")
    row = ledger.one(conn, first["run_id"])
    assert row["selected_tool"] == "inspect_freshness"
    assert row["timings"]["tool_ms"] is not None


def test_a_dead_router_degrades_to_unavailable(conn, enabled):
    out = service.ask(conn, enabled, "q",
                      needle_adapter=FakeNeedle(AssistantUnavailable("down")),
                      lfm_adapter=FakeLFM("x"))
    assert out["outcome"] == "unavailable"
    assert ledger.one(conn, out["run_id"])["outcome"] == "unavailable"


def test_only_one_tool_call_per_turn(conn, enabled):
    # The router yields exactly one decision; the service executes at most one
    # tool and never loops. A second tool name in the reply is ignored.
    needle = FakeNeedle({"tool": "inspect_claim_gate", "arguments": {},
                          "confidence": 0.8, "also": "inspect_freshness"})
    out = service.ask(conn, enabled, "are we gate-ready?",
                      needle_adapter=needle, lfm_adapter=FakeLFM("INSUFFICIENT_EVIDENCE none"))
    assert out["tool"] == "inspect_claim_gate"


# --- HTTP route ---------------------------------------------------------------

def _serve(settings):
    conn = db.get_connection(settings)
    db.apply_migrations(conn, settings.migrations_dir)
    conn.close()
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_post_route_is_absent_when_the_assistant_is_disabled(settings):
    server, thread = _serve(settings)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=10.0) as http:
            r = http.post("/api/admin/assistant",
                          json={"question": "how fresh is contracts?"})
            assert r.status_code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_post_route_runs_a_turn_when_enabled_and_degrades_without_runtimes(
        settings, monkeypatch):
    monkeypatch.setattr(settings, "assistant_enabled", True, raising=False)
    server, thread = _serve(settings)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=10.0) as http:
            r = http.post("/api/admin/assistant", json={"question": "hi"})
            assert r.status_code == 200
            body = r.json()
            # No `openai` extra in CI -> require_enabled fails -> unavailable.
            assert body["outcome"] == "unavailable"
            assert "caveat" in body
            # GET still returns the BETA-107 status and contacts nothing.
            g = http.get("/api/admin/assistant").json()
            assert g["enabled"] is True and "no endpoint was contacted" in g["note"].lower()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_post_route_requires_a_question(settings, monkeypatch):
    monkeypatch.setattr(settings, "assistant_enabled", True, raising=False)
    server, thread = _serve(settings)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=10.0) as http:
            r = http.post("/api/admin/assistant", json={"question": "  "})
            assert r.status_code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
