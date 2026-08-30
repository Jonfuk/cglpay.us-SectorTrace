"""pipeline/nlp/review_suggest.py -- model triage for a review sheet.

No test here makes a network call: `suggest` takes `ask` as a parameter, and
the one `_ask` test patches `urlopen`.
"""
from __future__ import annotations

import json
import urllib.error
from unittest import mock

import pytest

from pipeline.nlp import review_suggest


def _row(**kw):
    base = {"candidate_id": "cc-1", "predicate": "workforce.relies_on_agency",
            "predicate_label": "relies on agency", "assertion_status": "AFFIRMED",
            "subject_hint": "the service", "object": "", "evidence_span": "A sentence.",
            "screen_reason": "", "suggested_decision": "", "suggested_reason": "",
            "suggested_by": "", "decision": ""}
    base.update(kw)
    return base


# --- parsing -------------------------------------------------------------

def test_parse_reads_clean_and_embedded_json():
    assert review_suggest._parse('{"verdict":"reject","reason":"garbled"}') == ("reject", "garbled")
    assert review_suggest._parse('{"verdict":"approve","reason":"clear"}') == ("approve", "clear")
    assert review_suggest._parse('Sure:\n{"verdict": "keep", "reason": "ok"}\n')[0] == "keep"


def test_parse_falls_back_to_the_word_then_to_keep():
    assert review_suggest._parse("I would REJECT this, it is truncated.")[0] == "reject"
    assert review_suggest._parse("This clearly asserts it -- approve.")[0] == "approve"
    assert review_suggest._parse("hard to say")[0] == "keep"
    assert review_suggest._parse("")[0] == "keep"


# --- suggest ------------------------------------------------------------

def _ask_reject(row, **kw):
    return "reject", "not a claim"


def _ask_approve(row, **kw):
    return "approve", "clear assertion"


def _ask_keep(row, **kw):
    return "keep", ""


def test_suggest_fills_only_undecided_unsuggested_rows(conn):
    rows = [
        _row(candidate_id="cc-clean"),
        _row(candidate_id="cc-screened", screen_reason="span_too_long",
             suggested_decision="rejected", suggested_by="screen:span_too_long"),
        _row(candidate_id="cc-decided", decision="approved"),
    ]
    out = review_suggest.suggest(conn, rows, model="m/x", api_key="k", ask=_ask_reject)
    assert out["asked"] == 1 and out["rejected"] == 1
    assert out["skipped_suggested"] == 1 and out["skipped_decided"] == 1
    assert rows[0]["suggested_decision"] == "rejected"
    assert rows[0]["suggested_by"] == "model:m/x"
    assert rows[1]["suggested_by"] == "screen:span_too_long"   # untouched
    assert rows[2]["suggested_decision"] == ""                 # untouched


def test_suggest_approve_writes_an_approved_suggestion(conn):
    rows = [_row()]
    out = review_suggest.suggest(conn, rows, model="m/x", api_key="k", ask=_ask_approve)
    assert out["approved"] == 1 and out["rejected"] == 0
    assert rows[0]["suggested_decision"] == "approved"
    assert rows[0]["suggested_by"] == "model:m/x"


def test_suggest_keep_writes_nothing(conn):
    rows = [_row()]
    out = review_suggest.suggest(conn, rows, model="m/x", api_key="k", ask=_ask_keep)
    assert out["kept"] == 1 and out["rejected"] == 0 and out["approved"] == 0
    assert rows[0]["suggested_decision"] == ""


def test_suggest_requires_a_key(conn, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        review_suggest.suggest(conn, [_row()], model="m/x")


def test_suggest_fails_safe_to_keep_on_api_error(conn):
    def _ask_err(row, **kw):
        return "keep", "api error: URLError"
    rows = [_row()]
    out = review_suggest.suggest(conn, rows, model="m/x", api_key="k", ask=_ask_err)
    assert out["errors"] == 1 and out["rejected"] == 0
    assert rows[0]["suggested_decision"] == ""


def test_suggest_honours_limit(conn):
    rows = [_row(candidate_id=f"cc-{i}") for i in range(5)]
    out = review_suggest.suggest(conn, rows, model="m/x", api_key="k",
                                 rate=0, limit=2, ask=_ask_reject)
    assert out["asked"] == 2 and out["rejected"] == 2


def test_suggest_records_an_nlp_run(conn):
    out = review_suggest.suggest(conn, [_row()], model="m/x", api_key="k",
                                 rate=0, ask=_ask_reject)
    row = conn.execute("SELECT stage, model_key, status FROM nlp_runs WHERE run_id = ?",
                       (out["run_id"],)).fetchone()
    assert tuple(row) == ("review_suggest", "m/x", "ok")


# --- the one call path ------------------------------------------------

def test_ask_parses_a_chat_completion_and_errors_fail_safe():
    payload = json.dumps({"choices": [{"message": {"content": '{"verdict":"reject","reason":"x"}'}}]})

    class _Resp:
        def read(self): return payload.encode("utf-8")
        def __enter__(self): return self
        def __exit__(self, *a): return False

    with mock.patch("urllib.request.urlopen", return_value=_Resp()):
        assert review_suggest._ask(_row(), model="m", api_key="k") == ("reject", "x")

    with mock.patch("urllib.request.urlopen",
                    side_effect=urllib.error.URLError("no route")):
        verdict, reason = review_suggest._ask(_row(), model="m", api_key="k")
        assert verdict == "keep" and reason.startswith("api error")
