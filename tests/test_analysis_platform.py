from __future__ import annotations

import pytest

from pipeline.analysis.budget import AnalysisCancelled, CallBudget, CostCeilingExceeded, run_batches
from pipeline.analysis.domains import AnalysisDomainSpec, domain_registry
from pipeline.analysis.graph import (
    EDGE_TYPES,
    NODE_LABELS,
    exact_entity_attachment,
    queue_release_projection,
)
from pipeline.analysis.linking import link_signals
from pipeline.analysis.narrative import NarrativeCandidate, candidate_to_signal, discover_themes
from pipeline.analysis.operations import detect_drift
from pipeline.analysis.prevalence import diagnostics
from pipeline.analysis.quality import ProgramMetrics, promotion_eligible
from pipeline.analysis.releases import create_release, load_release
from pipeline.analysis.structured import (
    Observation,
    anomaly,
    categorical_transitions,
    compare_periods,
    comparisons_for_domain,
    observations_from_table,
)
from pipeline.analysis.worker import AnalysisWorker
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


def test_categorical_transitions_keep_states_and_do_not_calculate():
    changes = categorical_transitions(
        [{"location_id": "l1", "provider_key": "p1", "overall_rating": "Good", "rated": "2024-01-01"},
         {"location_id": "l2", "provider_key": "p1", "overall_rating": "Requires improvement", "rated": "2025-01-01"}],
        subject_key="provider_key", metric="overall_rating", period_key="rated",
        source_table="cqc_locations", source_id_key="location_id", subject_type="provider_id")
    assert changes[0]["previous"]["value"] == "Good"
    assert changes[0]["current"]["value"] == "Requires improvement"
    assert changes[0]["absolute_change"] is None


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


def test_signal_graph_rebuild_is_durable_and_isolated(conn, settings):
    release = create_release(conn, settings, domains=["da"])
    result = queue_release_projection(conn, release["release_id"])
    assert result["status"] == "queued"
    assert conn.execute("SELECT COUNT(*) FROM signal_graph_projection_queue WHERE release_id = ?",
                        (release["release_id"],)).fetchone()[0] == 1


def test_admin_analysis_read_models_are_admin_only(conn):
    assert analysis_admin.overview(conn)["counts"]["automated_signals"] == 0
    assert analysis_admin.graph(conn)["canonical_claim_isolation"] is True


def test_analysis_run_controls_are_durable_and_resumable(conn, settings):
    started = analysis_admin.start_run(
        conn, settings, {"domains": ["da"], "run_kind": "pilot", "cost_ceiling_micros": 2500})
    assert started["status"] == "queued"
    assert started["run_kind"] == "pilot"
    assert started["cost_ceiling_micros"] == 2500
    assert started["domains"][0]["status"] == "pending"
    assert analysis_admin.runs(conn)["runs"][0]["run_id"] == started["run_id"]

    cancelled = analysis_admin.cancel_run(conn, started["run_id"])
    assert cancelled["status"] == "cancelled"
    assert cancelled["domains"][0]["status"] == "cancelled"

    resumed = analysis_admin.resume_run(conn, started["run_id"])
    assert resumed["status"] == "queued"
    assert resumed["domains"][0]["status"] == "pending"


def test_analysis_run_rejects_empty_domain_selection(conn, settings):
    with pytest.raises(ValueError, match="at least one"):
        analysis_admin.start_run(conn, settings, {"domains": []})


def test_analysis_worker_claims_and_completes_structured_run(conn, settings):
    started = analysis_admin.start_run(conn, settings, {"domains": ["procurement"]})
    result = AnalysisWorker(settings, poll_seconds=.1, batch_size=2,
                            worker_id="test-analysis-worker").run_once()
    assert result["run_id"] == started["run_id"]
    assert result["status"] == "complete"
    assert result["domains"][0]["status"] == "complete"
    assert analysis_admin.worker_status(conn)["worker_id"] == "test-analysis-worker"


def test_analysis_worker_writes_exact_structured_comparison(conn, settings):
    common = {
        "currency": "GBP", "source_url": "https://example.test/contract",
        "retrieved_at": "2025-01-01T00:00:00+00:00", "http_status": 200,
        "source_system": "fixture", "payload_sha256": "hash",
    }
    for notice_id, value, period in (("n1", 100, "2024-01-01"), ("n2", 125, "2025-01-01")):
        conn.execute(
            "INSERT INTO contracts (notice_id, supplier_id, ocid, value_core, currency, date_start, "
            "source_url, retrieved_at, http_status, source_system, payload_sha256) "
            "VALUES (?, 'provider-1', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (notice_id, f"ocid-{notice_id}", value, common["currency"], period,
             common["source_url"], common["retrieved_at"], common["http_status"],
             common["source_system"], common["payload_sha256"]))
    observations = observations_from_table(conn, "contracts")
    assert comparisons_for_domain(observations)[0]["absolute_change"] == 25
    started = analysis_admin.start_run(conn, settings, {"domains": ["procurement"]})
    result = AnalysisWorker(settings, batch_size=2, worker_id="structured-fixture-worker").run_once()
    assert result["run_id"] == started["run_id"]
    assert conn.execute("SELECT COUNT(*) FROM structured_signals WHERE signal_id IN "
                        "(SELECT signal_id FROM automated_signals WHERE release_id = ?)",
                        (started["release_id"],)).fetchone()[0] == 1


def test_analysis_worker_processes_narrative_domain(conn, settings):
    started = analysis_admin.start_run(conn, settings, {"domains": ["da"]})
    result = AnalysisWorker(settings, poll_seconds=.1, batch_size=2,
                            worker_id="test-narrative-worker").run_once()
    assert result["run_id"] == started["run_id"]
    assert result["status"] == "complete"
    assert result["domains"][0]["status"] == "complete"


def test_analysis_worker_extracts_dual_model_narrative_signal(conn, settings):
    now = "2025-01-01T00:00:00+00:00"
    conn.execute(
        "INSERT INTO evidence_records (evidence_id, source_system, source_url, retrieved_at, http_status, "
        "payload_sha256, raw_object_path, mime_type, content_length, source_table, source_key, created_at) "
        "VALUES ('evidence-analysis-1', 'fixture', 'https://example.test/doc', ?, 200, 'hash-analysis', "
        "'/data/doc.pdf', 'application/pdf', 10, 'committee_papers', 'authority-1', ?)", (now, now))
    conn.execute(
        "INSERT INTO document_records (document_id, evidence_id, source_table, source_key, document_type, "
        "created_at, updated_at) VALUES ('document-analysis-1', 'evidence-analysis-1', 'committee_papers', "
        "'authority-1', 'REPORT', ?, ?)", (now, now))
    conn.execute(
        "INSERT INTO document_versions (document_version_id, document_id, parser_name, parser_version, "
        "parse_schema_version, config_hash, status, is_active, created_at) VALUES "
        "('version-analysis-1', 'document-analysis-1', 'fixture', '1', '1', 'hash', 'complete', 1, ?)", (now,))
    conn.execute(
        "INSERT INTO document_elements (document_element_id, document_version_id, element_type, sequence, text, "
        "text_sha256) VALUES ('element-analysis-1', 'version-analysis-1', 'PARAGRAPH', 1, "
        "'The service reported high caseloads.', 'text-hash')")

    class FakeModelClient:
        def __init__(self, settings, **kwargs):
            self.conn = kwargs["conn"]
            self.last_cost_micros = 7
            self.last_cached = False

        def generate_json(self, prompt, *, role, domain_id, window_id):
            return {"signal": {"signal_type": "workforce_strain", "subtype": "caseload",
                                "assertion_status": "affirmed", "direction": "adverse",
                                "evidence_quote": "high caseloads", "scope_quote": "high caseloads",
                                "period_start": None, "period_end": None,
                                "planned_or_hypothetical": False}}

    started = analysis_admin.start_run(conn, settings, {"domains": ["da"]})
    result = AnalysisWorker(settings, batch_size=2, worker_id="model-fixture-worker",
                            model_client_factory=FakeModelClient).run_once()
    assert result["run_id"] == started["run_id"]
    assert result["cost_micros"] == 14
    signal = conn.execute("SELECT signal_type, direction, human_verified FROM automated_signals "
                          "WHERE release_id = ?", (started["release_id"],)).fetchone()
    assert dict(signal) == {"signal_type": "workforce_strain", "direction": "adverse", "human_verified": 0}
    prevalence = conn.execute("SELECT positives, subjects, suppressed FROM analysis_prevalence_diagnostics "
                              "WHERE release_id = ?", (started["release_id"],)).fetchone()
    assert dict(prevalence) == {"positives": 1, "subjects": 1, "suppressed": 1}


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
