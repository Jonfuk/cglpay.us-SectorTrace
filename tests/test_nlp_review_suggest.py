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

_REAL_PREDICATE = "workforce.has_retention_pressure"   # a genuine relations.yml id


def _row(**kw):
    base = {"candidate_id": "cc-1", "predicate": "workforce.relies_on_agency",
            "predicate_label": "relies on agency", "assertion_status": "AFFIRMED",
            "subject_hint": "the service", "object": "", "evidence_span": "A sentence.",
            "screen_reason": "", "suggested_decision": "", "suggested_reason": "",
            "suggested_by": "", "suggested_corrected_predicate": "", "decision": ""}
    base.update(kw)
    return base


def _ask(verdict, reason="r", predicate=""):
    def _fn(row, **kw):
        return verdict, reason, predicate
    return _fn


def _by_model(mapping):
    """A fake `ask` that returns per model id."""
    def _fn(row, *, model, **kw):
        return mapping[model]
    return _fn


# --- parsing -----------------------------------------------------------

def test_parse_reads_verdict_and_predicate():
    assert review_suggest._parse('{"verdict":"reject","reason":"garbled"}') == ("reject", "garbled", "")
    assert review_suggest._parse(
        '{"verdict":"correct","predicate":"x.y","reason":"wrong"}') == ("correct", "wrong", "x.y")
    assert review_suggest._parse('noise then {"verdict":"approve"} tail')[0] == "approve"


def test_parse_falls_back_to_the_word_then_keep():
    assert review_suggest._parse("I would REJECT this.")[0] == "reject"
    assert review_suggest._parse("hmm")[0] == "keep"


# --- single model ----------------------------------------------------

def test_suggest_fills_only_undecided_unsuggested_rows(conn):
    rows = [
        _row(candidate_id="cc-clean"),
        _row(candidate_id="cc-screened", screen_reason="span_too_long",
             suggested_decision="rejected", suggested_by="screen:span_too_long"),
        _row(candidate_id="cc-decided", decision="approved"),
    ]
    out = review_suggest.suggest(conn, rows, models=["m/x"], api_key="k",
                                 ask=_ask("reject", "not a claim"))
    assert out["asked"] == 1 and out["rejected"] == 1
    assert out["skipped_suggested"] == 1 and out["skipped_decided"] == 1
    assert rows[0]["suggested_decision"] == "rejected"
    assert rows[0]["suggested_by"] == "model:m/x"


def test_suggest_approve_and_keep(conn):
    a, b = _row(candidate_id="a"), _row(candidate_id="b")
    review_suggest.suggest(conn, [a], models=["m/x"], api_key="k", ask=_ask("approve"))
    review_suggest.suggest(conn, [b], models=["m/x"], api_key="k", ask=_ask("keep"))
    assert a["suggested_decision"] == "approved"
    assert b["suggested_decision"] == "" and b["suggested_by"] == ""


def test_suggest_correct_writes_a_validated_predicate(conn):
    good, bad = _row(candidate_id="g"), _row(candidate_id="b")
    review_suggest.suggest(conn, [good], models=["m/x"], api_key="k",
                           ask=_ask("correct", "wrong predicate", _REAL_PREDICATE))
    review_suggest.suggest(conn, [bad], models=["m/x"], api_key="k",
                           ask=_ask("correct", "wrong", "not.a.real.id"))
    assert good["suggested_decision"] == "corrected"
    assert good["suggested_corrected_predicate"] == _REAL_PREDICATE
    assert bad["suggested_decision"] == ""          # invalid id -> dropped to keep


def test_suggest_requires_a_model_and_a_key(conn, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        review_suggest.suggest(conn, [_row()], models=[], api_key="k")
    with pytest.raises(RuntimeError):
        review_suggest.suggest(conn, [_row()], models=["m/x"])


def test_suggest_fails_safe_to_keep_on_api_error(conn):
    rows = [_row()]
    out = review_suggest.suggest(conn, rows, models=["m/x"], api_key="k",
                                 ask=_ask("keep", "api error: URLError"))
    assert out["errors"] == 1 and out["rejected"] == 0
    assert rows[0]["suggested_decision"] == ""


def test_suggest_honours_limit_and_records_a_run(conn):
    rows = [_row(candidate_id=f"cc-{i}") for i in range(5)]
    out = review_suggest.suggest(conn, rows, models=["m/x"], api_key="k",
                                 rate=0, limit=2, ask=_ask("reject"))
    assert out["asked"] == 2 and out["rejected"] == 2
    row = conn.execute("SELECT stage, model_key, status FROM nlp_runs WHERE run_id = ?",
                       (out["run_id"],)).fetchone()
    assert tuple(row) == ("review_suggest", "m/x", "ok")


# --- ensemble --------------------------------------------------------

def test_ensemble_writes_only_on_agreement(conn):
    agree, split = _row(candidate_id="a"), _row(candidate_id="s")
    review_suggest.suggest(conn, [agree], models=["m/a", "m/b"], api_key="k", rate=0,
                           ask=_by_model({"m/a": ("reject", "x", ""),
                                          "m/b": ("reject", "y", "")}))
    review_suggest.suggest(conn, [split], models=["m/a", "m/b"], api_key="k", rate=0,
                           ask=_by_model({"m/a": ("reject", "x", ""),
                                          "m/b": ("keep", "y", "")}))
    assert agree["suggested_decision"] == "rejected"
    assert agree["suggested_by"] == "model:m/a+model:m/b"
    assert split["suggested_decision"] == ""
    assert split["suggested_by"] == "ensemble:split"
    assert "m/a=reject" in split["suggested_reason"] and "m/b=keep" in split["suggested_reason"]


def test_ensemble_correct_needs_the_same_predicate(conn):
    same, diff = _row(candidate_id="same"), _row(candidate_id="diff")
    review_suggest.suggest(conn, [same], models=["m/a", "m/b"], api_key="k", rate=0,
                           ask=_by_model({"m/a": ("correct", "x", _REAL_PREDICATE),
                                          "m/b": ("correct", "y", _REAL_PREDICATE)}))
    review_suggest.suggest(conn, [diff], models=["m/a", "m/b"], api_key="k", rate=0,
                           ask=_by_model({"m/a": ("correct", "x", _REAL_PREDICATE),
                                          "m/b": ("correct", "y", "workforce.relies_on_agency")}))
    assert same["suggested_decision"] == "corrected"
    assert same["suggested_corrected_predicate"] == _REAL_PREDICATE
    assert diff["suggested_decision"] == "" and diff["suggested_by"] == "ensemble:split"


# --- the one call path --------------------------------------------

def test_ask_parses_a_chat_completion_and_errors_fail_safe():
    payload = json.dumps({"choices": [{"message": {"content": '{"verdict":"reject","reason":"x"}'}}]})

    class _Resp:
        def read(self): return payload.encode("utf-8")
        def __enter__(self): return self
        def __exit__(self, *a): return False

    with mock.patch("urllib.request.urlopen", return_value=_Resp()):
        assert review_suggest._ask(_row(), model="m", api_key="k") == ("reject", "x", "")

    with mock.patch("urllib.request.urlopen",
                    side_effect=urllib.error.URLError("no route")):
        verdict, reason, _ = review_suggest._ask(_row(), model="m", api_key="k")
        assert verdict == "keep" and reason.startswith("api error")
