"""Assistant evaluation and the release gate (BETA-113).

The frozen suites are large enough and cover the required kinds; the gate's
static checks run with no runtime; `may_enable` is closed until every check
passes, which it cannot in CI (no local runtimes).
"""
from __future__ import annotations

from pipeline.assistant import evaluation, tools


def test_routing_fixture_meets_the_size_and_coverage_bar():
    cases = evaluation.load_routing_cases()
    cov = evaluation.routing_coverage(cases)
    assert cov["n"] >= evaluation.MIN_ROUTING_PROMPTS
    assert cov["tools_missing"] == []
    assert set(cov["tools_covered"]) == set(tools.TOOL_NAMES)
    assert cov["kinds_missing"] == []
    for kind in ("injection", "forbidden", "malformed", "clarify"):
        assert cov["by_kind"].get(kind, 0) >= 5


def test_grounding_fixture_meets_the_size_bar_and_has_both_expectations():
    cases = evaluation.load_grounding_cases()
    cov = evaluation.grounding_coverage(cases)
    assert cov["n"] >= evaluation.MIN_ANALYST_QUESTIONS
    assert cov["by_expectation"].get("answer", 0) >= 20
    assert cov["by_expectation"].get("abstain", 0) >= 10


def test_every_fixture_line_is_well_formed():
    for case in evaluation.load_routing_cases():
        assert {"id", "kind", "question"} <= set(case)
        assert case["kind"] in evaluation.ROUTING_KINDS
        if case["kind"] == "route":
            assert case["expect_tool"] in tools.TOOL_NAMES
    for case in evaluation.load_grounding_cases():
        assert {"id", "question", "expect"} <= set(case)
        assert case["expect"] in ("answer", "abstain")


def test_gate_is_closed_without_local_runtimes(conn, settings):
    report = evaluation.gate_report(conn, settings)
    assert report["gate"]["may_enable"] is False
    assert report["gate"]["runtime_ready"] is False
    names = {c["name"]: c["ok"] for c in report["gate"]["checks"]}
    # static checks still pass...
    assert names["routing_prompts_present"] is True
    assert names["routing_covers_all_tools"] is True
    assert names["analyst_questions_present"] is True
    # ...dynamic ones are blocked on the missing runtime
    assert names["routing_precision"] is False


def test_the_gate_note_names_may_enable_as_the_only_authoriser(conn, settings):
    report = evaluation.gate_report(conn, settings)
    assert "may_enable" in report["gate"]["note"]
