"""The assistant run ledger (BETA-108).

`assistant_runs` records one immutable row per single-turn run — every
outcome, not only the successful ones — with no secrets, keys or model file
paths, only identities and hashes. `record()` never updates or deletes.
"""
from __future__ import annotations

import pytest

from pipeline.assistant import ledger


def test_record_writes_one_row_and_returns_its_id(conn):
    run_id = ledger.record(
        conn, question="how stale is contracts?", filters={"limit": 5},
        outcome="ok", needle_model="openrouter/router-slug",
        lfm_model="openrouter/answerer-slug",
        lfm_quant="", selected_tool="inspect_freshness",
        routing_confidence=0.81, tool_args={"table": "contracts"},
        retrieved_chunk_ids=["contracts"], answer="Contracts last fetched 2026-01-01 [[contracts]].",
        citation_ids=["contracts"], timings={"total_ms": 42})
    assert run_id
    row = ledger.one(conn, run_id)
    assert row["question"] == "how stale is contracts?"
    assert row["outcome"] == "ok"
    assert row["filters"] == {"limit": 5}
    assert row["tool_args"] == {"table": "contracts"}
    assert row["citation_ids"] == ["contracts"]
    assert row["timings"] == {"total_ms": 42}


def test_every_outcome_is_recordable(conn):
    for outcome in ledger.OUTCOMES:
        rid = ledger.record(conn, question="q", filters={}, outcome=outcome)
        assert ledger.one(conn, rid)["outcome"] == outcome
    # an unknown outcome is coerced, never written verbatim
    rid = ledger.record(conn, question="q", filters={}, outcome="banana")
    assert ledger.one(conn, rid)["outcome"] == "failed"


def test_recent_is_newest_first(conn):
    ids = [ledger.record(conn, question=f"q{i}", filters={}, outcome="ok")
           for i in range(3)]
    rows = ledger.recent(conn, limit=3)
    assert [r["run_id"] for r in rows][:3] == list(reversed(ids))


def test_it_refuses_to_store_a_credential_or_model_path(conn):
    with pytest.raises(ValueError):
        ledger.record(conn, question="q", filters={}, outcome="ok",
                      api_key="sk-secret")
    with pytest.raises(ValueError):
        ledger.record(conn, question="q", filters={}, outcome="ok",
                      model_path="/models/lfm.gguf")


def test_the_module_never_updates_or_deletes(conn):
    src = (__import__("pathlib").Path(ledger.__file__)).read_text(encoding="utf-8")
    assert "UPDATE assistant_runs" not in src.upper().replace("  ", " ") or True
    # explicit: no UPDATE/DELETE against the table anywhere in the module
    upper = src.upper()
    assert "UPDATE ASSISTANT_RUNS" not in upper
    assert "DELETE FROM ASSISTANT_RUNS" not in upper


def test_a_failed_write_returns_none_not_an_exception(conn):
    conn.execute("DROP TABLE assistant_runs")
    assert ledger.record(conn, question="q", filters={}, outcome="ok") is None
