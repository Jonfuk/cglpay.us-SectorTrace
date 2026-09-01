from __future__ import annotations

import pytest

from pipeline.analysis.budget import AnalysisCancelled, CallBudget, CostCeilingExceeded, run_batches
from pipeline.analysis.domains import AnalysisDomainSpec, domain_registry
from pipeline.analysis.graph import EDGE_TYPES, NODE_LABELS, exact_entity_attachment
from pipeline.analysis.linking import link_signals
from pipeline.analysis.narrative import NarrativeCandidate, candidate_to_signal, discover_themes
from pipeline.analysis.operations import detect_drift
from pipeline.analysis.prevalence import diagnostics
from pipeline.analysis.quality import ProgramMetrics, promotion_eligible
from pipeline.analysis.releases import create_release, load_release
from pipeline.analysis.structured import Observation, anomaly, compare_periods
from pipeline.web import analysis as analysis_admin


def _spec(*rules: str) -> AnalysisDomainSpec:
    return AnalysisDomainSpec("test", ("fixture",), "document_window", ("subject_id",),
                              "SELECT 1", "test", cross_source_rules=rules,
                              consolidation_key=("subject_id",))


def test_domain_registry_has_complete_contracts():
    registry = domain_registry()
    assert {"da", "provider", "commissioning", "quality_safety", "legal_employment", "housing"} <= set(registry)
    for spec in registry.values():
        spec.validate()


def test_release_freezes_model_resolution(conn, settings):
    settings.claim_signal_scout_model = "scout-v1"
    first = create_release(conn, settings, domains=["da"])
    settings.claim_signal_scout_model = "scout-v2"
    assert load_release(conn, first["release_id"])["models"]["scout"] == "scout-v1"


def test_narrative_requires_exact_dual_grounded_evidence():
    text = "The service reported high caseloads."
    candidate = NarrativeCandidate("da", "workforce_strain", "caseload", "affirmed", "adverse",
                                   "authority", "authority-1", "high caseloads", "high caseloads", "doc:1")
    assert candidate_to_signal(candidate, release_id="r1", source_text=text, second_model=candidate)
    assert candidate_to_signal(candidate, release_id="r1", source_text=text, second_model=None) is None


def test_discovery_preserves_outliers_and_recurrence_bar():
    passages = [{"text": "rare phrase", "document_id": "d1", "subject_id": "s1"}]
    themes = discover_themes(passages)
    assert themes[0]["outlier"] is True
    assert themes[0]["passages"]


def test_structured_comparison_and_anomaly_guards():
    previous = Observation("metric", "r1", "authority", "a1", "vacancies", 10, "count", "2024", "2024")
    current = Observation("metric", "r2", "authority", "a1", "vacancies", 15, "count", "2025", "2025")
    assert compare_periods(previous, current)["percentage_change"] == 50
    assert anomaly(10, [1, 1, 1, 1, 1])["robust_z"] is None
    assert compare_periods(previous, Observation("metric", "r3", "authority", "a1", "vacancies", 1, "percent", "2025", "2025"))["comparable"] is False


def test_links_require_canonical_identity_and_block_causal_explanation():
    spec = _spec("entity_overlap")
    left = {"signal_id": "a", "release_id": "r", "domain_id": "test", "subject_type": "authority", "subject_id": "a1", "period_end": "2025-01-01"}
    right = {**left, "signal_id": "b", "period_end": "2025-01-02"}
    assert link_signals(left, right, left_spec=spec, right_spec=spec, relationship_type="entity_overlap")
    assert link_signals(left, {**right, "subject_id": "a2"}, left_spec=spec, right_spec=spec, relationship_type="entity_overlap") is None
    try:
        link_signals(left, right, left_spec=spec, right_spec=spec, relationship_type="entity_overlap", explanation="caused the increase")
    except ValueError:
        pass
    else:
        raise AssertionError("causal explanation was accepted")


def test_drift_is_proposal_only():
    proposals = detect_drift({"expected_schema": {"value": "number"}, "observed_schema": {"value": "text"}, "extractor_agreement": .90}, {"extractor_agreement": .99})
    assert {item["proposal_type"] for item in proposals} >= {"schema_drift", "extractor_agreement_drift"}


def test_graph_projection_isolated_from_canonical_claims():
    assert "Claim" not in NODE_LABELS
    assert "SUPPORTED_BY" not in EDGE_TYPES
    assert exact_entity_attachment("entity-1", [{"exact": True}]) == "entity-1"
    assert exact_entity_attachment("entity-1", [{"exact": False}]) is None


def test_admin_analysis_read_models_are_admin_only(conn):
    assert analysis_admin.overview(conn)["counts"]["automated_signals"] == 0
    assert analysis_admin.graph(conn)["canonical_claim_isolation"] is True


def test_batch_budget_stops_at_ceiling_and_boundary():
    budget = CallBudget(ceiling_micros=10)
    budget.before_call(10)
    budget.record(10)
    with pytest.raises(CostCeilingExceeded):
        budget.before_call(1)
    budget = CallBudget()
    budget.cancel()
    with pytest.raises(AnalysisCancelled):
        run_batches([1, 2], lambda batch: batch, budget=budget)


def test_program_and_prevalence_gates_are_conservative():
    baseline = ProgramMetrics(.70, 1.0, 0, .90)
    assert promotion_eligible(ProgramMetrics(.75, 1.0, 0, .89), baseline)
    assert not promotion_eligible(ProgramMetrics(.75, .99, 0, .89), baseline)
    assert diagnostics(positives=49, negatives=50, subjects=10, pacc=.5, emq=.5).suppressed
    assert diagnostics(positives=50, negatives=50, subjects=10, pacc=.02, emq=.01).continue_exploration
