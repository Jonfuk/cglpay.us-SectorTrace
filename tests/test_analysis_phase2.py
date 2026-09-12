from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipeline.analysis.acceptance import compare_snapshots
from pipeline.analysis.lineage import add_edge, add_object, paths
from pipeline.analysis.models import request_identity
from pipeline.analysis.narrative import ThemeAccumulator, discover_themes
from pipeline.analysis.prefilter import evaluate, save_result, suppression_allowed
from pipeline.analysis.releases import create_release, finalise_manifest
from pipeline.analysis.signals import new_signal
from pipeline.analysis.state import (
    EMPTY_ORDERED_DIGEST,
    _theme_batch_summary,
    accumulate_themes,
    accumulated_themes,
    chain_digest,
    checkpoint,
    complete_and_purge,
    get_or_create_manifest,
    output_digest,
    purge_failed_detail,
)
from pipeline.analysis.store import save_signals
from pipeline.analysis.worker import AnalysisWorker
from pipeline.web import analysis as analysis_admin

FIXTURE = Path(__file__).parent / "fixtures" / "analysis" / "narrative_prefilter_regression.jsonl"


def _corpus():
    return [json.loads(line) for line in FIXTURE.read_text().splitlines() if line.strip()]


def test_prefilter_fixture_meets_shadow_recall_gate():
    result = evaluate(_corpus(), corpus_version="offline-regression-v1")
    assert result.overall_recall == 1.0
    assert result.critical_recall == 1.0
    assert result.critical_positives == 4
    assert result.accepted_critical == 4
    assert all(item["recall"] == 1.0 for item in result.critical_categories.values())
    assert result.gate_passed is True


def test_prefilter_cannot_suppress_without_persisted_gate_and_opt_in(conn):
    result = evaluate(_corpus(), corpus_version="offline-regression-v1")
    assert suppression_allowed(conn, explicitly_enabled=True) is False
    save_result(conn, result, adjudicated_by="offline regression fixture")
    assert suppression_allowed(conn, explicitly_enabled=False) is False
    assert suppression_allowed(conn, explicitly_enabled=True) is True


def test_empty_or_no_critical_corpus_never_passes():
    assert evaluate([], corpus_version="empty").gate_passed is False
    assert evaluate([{"id": "one", "text": "workforce pressure", "positive": True,
                      "critical": False, "category": "workforce"}],
                    corpus_version="no-critical").gate_passed is False


def test_prefilter_rejects_ambiguous_or_reused_corpus_versions(conn):
    with pytest.raises(ValueError, match="stable id"):
        evaluate([{"text": "workforce pressure", "positive": True,
                   "critical": True, "category": "risk"}], corpus_version="invalid-v1")
    with pytest.raises(ValueError, match="cannot be critical"):
        evaluate([{"id": "x", "text": "ordinary minutes", "positive": False,
                   "critical": True, "category": "risk"}], corpus_version="invalid-v2")
    first = evaluate(_corpus(), corpus_version="immutable-v1")
    result_id = save_result(conn, first, adjudicated_by="fixture panel")
    conn.commit()
    with pytest.raises(Exception):
        conn.execute(
            "UPDATE analysis_prefilter_results SET gate_passed = 0 WHERE result_id = %s",
            (result_id,))
    conn.rollback()
    changed = _corpus()
    changed[0]["text"] += " changed"
    with pytest.raises(ValueError, match="already belongs"):
        save_result(conn, evaluate(changed, corpus_version="immutable-v1"),
                    adjudicated_by="fixture panel")


def test_incremental_theme_accumulator_matches_original_order_and_counts():
    passages = [
        {"text": "workforce pressure", "document_id": f"d{index}", "subject_id": f"s{index}"}
        for index in range(20)
    ] + [{"text": "rare", "document_id": "tail", "subject_id": "tail"}]
    expected = discover_themes(passages, max_evidence_per_theme=2, max_evidence_total=3)
    first = ThemeAccumulator(max_evidence_per_theme=2, max_evidence_total=3)
    for passage in passages[:8]:
        first.add(passage)
    resumed = ThemeAccumulator(max_evidence_per_theme=2, max_evidence_total=3,
                               state=first.state())
    for passage in passages[8:]:
        resumed.add(passage)
    assert resumed.themes() == expected
    assert sum(len(theme["passages"]) for theme in resumed.themes()) <= 3


def test_theme_batch_summary_has_stable_first_seen_and_distinct_order():
    passages = [
        {"text": "staffing pressure", "document_id": "doc-b", "subject_id": "subject-b"},
        {"text": "staffing vacancy", "document_id": "doc-a", "subject_id": "subject-a"},
        {"text": "staffing pressure", "document_id": "doc-b", "subject_id": "subject-b"},
    ]
    keyed, counts, first, documents, subjects = _theme_batch_summary(
        passages, first_ordinal=7)
    assert [ordinal for ordinal, _key, _passage in keyed] == [7, 8, 9]
    assert dict(counts) == {"staffing": 3}
    assert first == {"staffing": 7}
    assert documents == [("staffing", "doc-a"), ("staffing", "doc-b")]
    assert subjects == [("staffing", "subject-a"), ("staffing", "subject-b")]


def test_postgres_checkpoint_resume_preserves_counts_order_and_candidates(conn, settings):
    started = analysis_admin.start_run(conn, settings, {"domains": ["da"]})
    manifest = get_or_create_manifest(
        conn, run_id=started["run_id"], release_id=started["release_id"], domain_id="da",
        source_tables=["committee_papers"], configuration={"fixture": "resume"},
        prefilter_version="fixture-v1")
    passages = [
        {"text": "workforce pressure", "document_id": f"d{index}",
         "subject_id": f"s{index}", "evidence_ref": f"e{index}"}
        for index in range(6)
    ] + [{"text": "rare", "document_id": "tail", "subject_id": "tail",
          "evidence_ref": "etail"}]
    for start, stop in ((0, 3), (3, len(passages))):
        rows = [{"document_id": item["document_id"], "sequence": index + 1,
                 "document_element_id": item["evidence_ref"],
                 "text_sha256": f"sha-{index}"}
                for index, item in enumerate(passages[start:stop], start=start)]
        accumulate_themes(
            conn, manifest["input_manifest_id"], passages[start:stop],
            first_ordinal=start + 1, max_evidence_per_theme=2, max_evidence_total=3)
        manifest = checkpoint(
            conn, manifest, rows=rows, accumulator_state={"retained": min(stop, 3)},
            accepted=[(index + 1, item["evidence_ref"], True)
                      for index, item in enumerate(passages[start:stop], start=start)])
        conn.commit()
        manifest = get_or_create_manifest(
            conn, run_id=started["run_id"], release_id=started["release_id"], domain_id="da",
            source_tables=["committee_papers"], configuration={"ignored": "on resume"},
            prefilter_version="ignored-v2")

    expected = discover_themes(passages, max_evidence_per_theme=2, max_evidence_total=3)
    assert accumulated_themes(conn, manifest["input_manifest_id"]) == expected
    assert manifest["input_count"] == len(passages)
    assert manifest["candidate_count"] == len(passages)
    assert [row["ordinal"] for row in conn.execute(
        "SELECT ordinal FROM analysis_candidates WHERE input_manifest_id = %s ORDER BY ordinal",
        (manifest["input_manifest_id"],)).fetchall()] == list(range(1, len(passages) + 1))


def test_ordered_input_digest_changes_with_order():
    first = chain_digest(chain_digest(EMPTY_ORDERED_DIGEST, {"id": 1}), {"id": 2})
    second = chain_digest(chain_digest(EMPTY_ORDERED_DIGEST, {"id": 2}), {"id": 1})
    assert first != second


def test_request_identity_covers_every_request_dimension():
    base = dict(role="scout", system_prompt="system", prompt="prompt", model="model",
                fallback_models=["fallback"], generation={"temperature": 0},
                provider_policy={"sort": "latency"}, schema={"type": "object"},
                cache_version="1")
    identity = request_identity(**base)
    for field, value in {
        "role": "extractor", "system_prompt": "other system", "prompt": "other prompt",
        "model": "other/model", "fallback_models": ["other/fallback"],
        "generation": {"temperature": 1}, "provider_policy": {"sort": "price"},
        "schema": {"type": "array"}, "cache_version": "2",
    }.items():
        changed = {**base, field: value}
        assert request_identity(**changed) != identity


def test_cache_hits_count_in_run_diagnostics_but_not_cost(conn, settings):
    started = analysis_admin.start_run(conn, settings, {"domains": ["da"]})
    now = "2025-01-01T00:00:00+00:00"
    cache_rows = [
        ("request-billed", "response-billed", '{"signal": null}'),
        ("request-cached", "response-cached", '{"signal": null}'),
    ]
    conn.executemany(
        "INSERT INTO analysis_model_response_cache (request_sha256, response_sha256, response_json, "
        "requested_model, actual_model, created_at) VALUES (%s, %s, %s, 'model', 'model', %s)",
        [(request, response, payload, now) for request, response, payload in cache_rows])
    conn.executemany(
        "INSERT INTO analysis_model_calls (model_call_id, release_id, run_id, domain_id, model_id, "
        "prompt_sha256, request_sha256, response_cache_key, cached, cost_micros, latency_ms, status, "
        "created_at) VALUES (%s, %s, %s, 'da', 'model', %s, %s, %s, %s, %s, 1, 'ok', %s)",
        [("call-billed", started["release_id"], started["run_id"], "prompt-billed",
          "request-billed", "request-billed", 0, 11, now),
         ("call-cached", started["release_id"], started["run_id"], "prompt-cached",
          "request-cached", "request-cached", 1, 0, now)])
    conn.execute("UPDATE analysis_runs SET cost_micros = 11 WHERE run_id = %s", (started["run_id"],))
    conn.commit()
    summary = analysis_admin.run(conn, started["run_id"])
    assert {key: summary[key] for key in (
        "model_calls", "cache_hits", "billed_calls", "cost_micros")} == {
            "model_calls": 2, "cache_hits": 1, "billed_calls": 1, "cost_micros": 11}
    with pytest.raises(Exception):
        conn.execute("UPDATE analysis_model_calls SET cached = 0 WHERE model_call_id = 'call-cached'")
    conn.rollback()


def test_lineage_and_final_release_manifests_are_immutable(conn, settings):
    release = create_release(conn, settings, domains=["da"])
    source = add_object(conn, kind="source", canonical_id="fixture", source_url="https://example.test")
    retrieval = add_object(conn, kind="retrieval", canonical_id="retrieval-1",
                           source_url="https://example.test/item", retrieved_at="2025-01-01T00:00:00+00:00",
                           payload_sha256="a" * 64)
    add_edge(conn, generated_id=retrieval, used_id=source, activity="retrieval")
    conn.commit()
    assert paths(conn, "retrieval-1")[0]["used_canonical_id"] == "fixture"
    with pytest.raises(Exception):
        conn.execute("UPDATE lineage_objects SET canonical_id = 'changed' WHERE lineage_id = %s",
                     (retrieval,))
    conn.rollback()

    manifest = finalise_manifest(conn, release["release_id"], output_sha256="b" * 64)
    conn.commit()
    assert manifest["schema_version"]
    assert manifest["source_snapshot_sha256"]
    with pytest.raises(ValueError, match="output digest conflicts"):
        finalise_manifest(conn, release["release_id"], output_sha256="c" * 64)
    with pytest.raises(Exception):
        conn.execute("DELETE FROM release_manifests WHERE release_id = %s", (release["release_id"],))
    conn.rollback()


def test_every_lineage_layer_traces_to_an_immutable_published_output(conn, settings):
    release = create_release(conn, settings, domains=["da"])
    kinds = ["source", "retrieval", "archive_object", "document_version", "element",
             "nlp_output", "claim", "entity", "relationship", "analysis",
             "published_output"]
    nodes = []
    for kind in kinds:
        nodes.append(add_object(
            conn, kind=kind, canonical_id=f"fixture-{kind}",
            payload_sha256="a" * 64 if kind in {"archive_object", "document_version"} else None,
            restricted=kind == "claim"))
    for generated, used in zip(nodes[1:], nodes, strict=False):
        add_edge(conn, generated_id=generated, used_id=used,
                 activity="fixture_derivation", activity_version="fixture-v1")
    analytical = finalise_manifest(conn, release["release_id"], output_sha256="b" * 64)
    published = finalise_manifest(
        conn, release["release_id"], output_sha256="c" * 64,
        release_kind="published", output_name="public-api")
    conn.commit()
    assert analytical["release_kind"] == "analytical"
    assert published["release_kind"] == "published"
    assert paths(conn, "fixture-published_output")
    assert paths(conn, "fixture-claim") == []
    assert paths(conn, "fixture-claim", include_restricted=True)


def test_completed_and_expired_failed_detail_is_purged_but_manifests_remain(conn, settings):
    started = analysis_admin.start_run(conn, settings, {"domains": ["da"]})
    manifest = get_or_create_manifest(
        conn, run_id=started["run_id"], release_id=started["release_id"], domain_id="da",
        source_tables=["committee_papers"], configuration={"test": True},
        prefilter_version="test-v1")
    conn.execute(
        "INSERT INTO analysis_candidates (candidate_id, input_manifest_id, ordinal, "
        "document_element_id, prefilter_matched, created_at) "
        "VALUES ('candidate-complete', %s, 1, 'element-missing', 1, %s)",
        (manifest["input_manifest_id"], "2025-01-01T00:00:00+00:00"))
    digest = output_digest(conn, release_id=started["release_id"], domain_id="da")
    complete_and_purge(conn, manifest["input_manifest_id"], expected_output_sha256=digest)
    assert conn.execute(
        "SELECT COUNT(*) AS count FROM analysis_candidates WHERE input_manifest_id = %s",
        (manifest["input_manifest_id"],)).fetchone()["count"] == 0
    retained = conn.execute(
        "SELECT ordered_input_sha256, output_sha256, status FROM analysis_input_manifests "
        "WHERE input_manifest_id = %s", (manifest["input_manifest_id"],)).fetchone()
    assert retained["status"] == "complete"
    assert retained["output_sha256"] == digest
    conn.commit()
    with pytest.raises(Exception):
        conn.execute(
            "UPDATE analysis_input_manifests SET input_count = 999 WHERE input_manifest_id = %s",
            (manifest["input_manifest_id"],))
    conn.rollback()

    analysis_admin.cancel_run(conn, started["run_id"])
    second = analysis_admin.start_run(conn, settings, {"domains": ["provider"]})
    failed = get_or_create_manifest(
        conn, run_id=second["run_id"], release_id=second["release_id"], domain_id="provider",
        source_tables=["provider_annual_reports"], configuration={"test": True},
        prefilter_version="test-v1")
    conn.execute(
        "UPDATE analysis_input_manifests SET status = 'failed', "
        "updated_at = '2000-01-01T00:00:00+00:00' WHERE input_manifest_id = %s",
        (failed["input_manifest_id"],))
    assert purge_failed_detail(
        conn, retention_days=7, now=datetime(2026, 1, 1, tzinfo=timezone.utc)) == 1
    assert conn.execute(
        "SELECT detail_purged_at FROM analysis_input_manifests WHERE input_manifest_id = %s",
        (failed["input_manifest_id"],)).fetchone()["detail_purged_at"]


def test_failed_detail_is_retained_through_exact_seven_day_boundary(conn, settings):
    started = analysis_admin.start_run(conn, settings, {"domains": ["da"]})
    manifest = get_or_create_manifest(
        conn, run_id=started["run_id"], release_id=started["release_id"], domain_id="da",
        source_tables=["committee_papers"], configuration={"fixture": True},
        prefilter_version="fixture-v1")
    conn.execute(
        "UPDATE analysis_input_manifests SET status = 'failed', "
        "updated_at = '2025-12-25T00:00:00+00:00' WHERE input_manifest_id = %s",
        (manifest["input_manifest_id"],))
    assert purge_failed_detail(
        conn, retention_days=7, now=datetime(2026, 1, 1, tzinfo=timezone.utc)) == 0
    assert purge_failed_detail(
        conn, retention_days=7,
        now=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc)) == 1


def test_indexed_link_run_keeps_every_eligible_pair(conn, settings):
    started = analysis_admin.start_run(conn, settings, {"domains": ["da", "procurement"]})
    signals = []
    for domain_id in ("da", "procurement"):
        for suffix, day in (("a", "2025-01-01"), ("b", "2025-01-02")):
            signals.append(new_signal(
                release_id=started["release_id"], domain_id=domain_id,
                taxonomy_namespace=domain_id, signal_type=f"fixture-{suffix}",
                subject_type="authority", subject_id="E00000001", direction="neutral",
                assertion_status="affirmed", period_start=day, period_end=day,
                evidence_refs=[f"fixture:{domain_id}:{suffix}"],
                derivation_method="fixture", confidence_contract={}))
    save_signals(conn, signals)
    conn.commit()
    AnalysisWorker(settings, batch_size=2)._link_run(started["run_id"])
    rows = conn.execute(
        "SELECT left_signal_id, right_signal_id FROM cross_source_signal_links "
        "WHERE release_id = %s ORDER BY left_signal_id, right_signal_id",
        (started["release_id"],)).fetchall()
    assert len(rows) == 4
    assert len({(row["left_signal_id"], row["right_signal_id"]) for row in rows}) == 4
    AnalysisWorker(settings, batch_size=1)._link_run(started["run_id"])
    repeated = conn.execute(
        "SELECT left_signal_id, right_signal_id FROM cross_source_signal_links "
        "WHERE release_id = %s ORDER BY left_signal_id, right_signal_id",
        (started["release_id"],)).fetchall()
    assert [tuple(row.values()) for row in repeated] == [tuple(row.values()) for row in rows]


def test_phase2_candidate_and_link_indexes_have_reproducible_plans(conn, settings):
    started = analysis_admin.start_run(conn, settings, {"domains": ["da", "procurement"]})
    indexes = {row["indexname"]: row["indexdef"] for row in conn.execute(
        "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = current_schema() "
        "AND indexname IN ('ix_analysis_candidates_pending', "
        "'ix_automated_signals_link_candidates', 'ux_analysis_health_release_source')")}
    assert set(indexes) == {"ix_analysis_candidates_pending",
                            "ix_automated_signals_link_candidates",
                            "ux_analysis_health_release_source"}
    conn.execute("SET LOCAL enable_seqscan = off")
    plan = conn.execute(
        "EXPLAIN (FORMAT JSON) SELECT l.signal_id, r.signal_id FROM automated_signals l "
        "JOIN automated_signals r ON l.release_id = r.release_id "
        "AND l.subject_type = r.subject_type AND l.subject_id = r.subject_id "
        "AND l.domain_id < r.domain_id WHERE l.release_id = %s "
        "ORDER BY l.signal_id, r.signal_id LIMIT 100", (started["release_id"],)).fetchone()
    assert "ix_automated_signals_link_candidates" in json.dumps(plan)


def test_health_sources_and_exact_counts_are_snapshotted_once_per_release(conn, settings):
    requested = ["da", "commissioning"]
    started = analysis_admin.start_run(conn, settings, {"domains": requested})
    worker = AnalysisWorker(settings, worker_id="health-fixture-worker")
    worker._record_health(started["run_id"], requested)
    worker._record_health(started["run_id"], requested)
    source_tables = {"committee_papers", "cdp_documents", "icb_board_papers", "foi_requests"}
    rows = conn.execute(
        "SELECT source_table, COUNT(*) AS count FROM analysis_health_snapshots "
        "WHERE release_id = %s GROUP BY source_table ORDER BY source_table",
        (started["release_id"],)).fetchall()
    assert {row["source_table"] for row in rows} == source_tables
    assert all(row["count"] == 1 for row in rows)
    operational = conn.execute(
        "SELECT snapshot_key FROM operational_snapshots "
        "WHERE snapshot_key LIKE 'analysis.source.%' ORDER BY snapshot_key").fetchall()
    assert {row["snapshot_key"].removeprefix("analysis.source.") for row in operational} == source_tables


def test_acceptance_compare_requires_same_dataset_counts_sets_and_order():
    sections = {"signals": {"count": 2, "digest": "set", "ordered_digest": "order"}}
    baseline = {"dataset_digest": "dataset", "snapshot_digest": "before",
                "source_digests": [{"status": "captured"}],
                "sections": sections}
    same = {"dataset_digest": "dataset", "snapshot_digest": "after",
            "source_digests": [{"status": "captured"}], "sections": sections}
    assert compare_snapshots(baseline, same)["parity_passed"] is True
    reordered = {"dataset_digest": "dataset", "snapshot_digest": "after",
                 "source_digests": [{"status": "captured"}],
                 "sections": {"signals": {"count": 2, "digest": "set",
                                           "ordered_digest": "different"}}}
    result = compare_snapshots(baseline, reordered)
    assert result["same_dataset"] is True
    assert result["sections"]["signals"]["set_equal"] is True
    assert result["sections"]["signals"]["order_equal"] is False
    assert result["parity_passed"] is False
