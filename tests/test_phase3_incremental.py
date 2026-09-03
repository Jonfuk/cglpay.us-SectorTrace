from __future__ import annotations

import logging
import sys
from types import SimpleNamespace

import pytest

from pipeline import evidence_state
from pipeline.documents import repository
from pipeline.documents.models import EvidenceReference, ParsedDocument, ParsedElement
from pipeline.nlp import accelerator, ontology, semantic_search, stage_state


def _naive_matches(onto, text):
    raw = ontology._normalise(text).split()
    tokens = ontology._fold_tokens(raw)
    found = set()
    aliases = []
    for concept in onto.concepts.values():
        aliases.extend((concept.id, alias, alias_tokens)
                       for alias, alias_tokens in concept.alias_tokens)
    for concept_id, alias, alias_tokens in aliases:
        for start in range(len(tokens) - len(alias_tokens) + 1):
            if tokens[start:start + len(alias_tokens)] == alias_tokens:
                found.add((concept_id, alias, start, start + len(alias_tokens)))
    return sorted(found, key=lambda item: (item[2], item[3], item[0]))


@pytest.mark.parametrize("text", [
    "No recruitment difficulties; vacancies remain.",
    "Needle-exchange and opioid substitution treatment.",
    "WORKERS, worker's and services: punctuation and Unicode £ café.",
    "commissioning recommissioning commissioned",
])
def test_token_trie_has_exact_naive_parity(text):
    onto = ontology.default()
    actual = [(m.concept_id, m.alias, m.start_token, m.end_token) for m in onto.match(text)]
    assert actual == _naive_matches(onto, text)


def test_packed_utf8_offsets_are_byte_offsets():
    packed = accelerator.pack_texts(["£ café", "worker"])
    assert packed.offsets == (0, len("£ café".encode()), len("£ caféworker".encode()))
    assert packed.utf8[packed.offsets[1]:].decode() == "worker"


def test_forced_mojo_fails_and_auto_reports_only_once(monkeypatch, caplog):
    monkeypatch.delitem(__import__("sys").modules, "pipeline.nlp._mojo_nlp", raising=False)
    accelerator._FALLBACK_REPORTED = False
    with pytest.raises(accelerator.MojoIncompatible, match="NLP_ACCELERATOR=mojo"):
        accelerator.select("mojo")
    with caplog.at_level(logging.WARNING):
        accelerator.select("auto")
        accelerator.select("auto")
    assert sum("using deterministic Python" in record.message for record in caplog.records) == 1


def test_mojo_is_linux_only_and_cannot_activate_before_parity(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(accelerator.MojoIncompatible, match="Linux-only"):
        accelerator.select("mojo")
    monkeypatch.setattr(sys, "platform", "linux")
    boundary = SimpleNamespace(abi_version=lambda: 1, parity_approved=lambda: False)
    monkeypatch.setitem(sys.modules, "pipeline.nlp._mojo_nlp", boundary)
    with pytest.raises(accelerator.MojoIncompatible, match="exact ontology parity"):
        accelerator.select("mojo")


def test_three_path_rrf_is_stable_and_never_names_truth_or_quality():
    first = semantic_search._rrf(["b", "a"], ["c", "a"], [("d", 0.9), ("a", 0.8)])
    second = semantic_search._rrf(["b", "a"], ["c", "a"], [("d", 0.9), ("a", 0.8)])
    assert first == second
    assert [item[0] for item in first] == ["a", "b", "c", "d"]
    assert not ({"truth", "quality", "authority", "corroboration"} & set(first[0][1]))


def test_stage_state_noop_and_dependency_invalidation(conn):
    config = {"rules": "v1"}
    stage_state.mark_complete(
        conn, "spans", "chunk-1", "hash-1", processor_version="extractor-1",
        model_or_ontology_version="model-1", configuration=config,
        dependency_hash="deps-1", output=["mention-1"])
    assert not stage_state.needs_processing(
        conn, "spans", "chunk-1", "hash-1", processor_version="extractor-1",
        model_or_ontology_version="model-1", configuration=config,
        dependency_hash="deps-1")
    assert stage_state.needs_processing(
        conn, "spans", "chunk-1", "hash-1", processor_version="extractor-1",
        model_or_ontology_version="model-1", configuration=config,
        dependency_hash="deps-2")
    stage_state.mark_complete(
        conn, "context", "chunk-1", "hash-1", processor_version="cue-1",
        configuration={}, output=[])
    assert stage_state.invalidate_downstream(conn, "spans", "chunk-1") == 1
    assert conn.execute(
        "SELECT status FROM nlp_stage_state WHERE stage='context' AND input_identity='chunk-1'"
    ).fetchone()["status"] == "invalidated"


def test_per_input_rollback_retains_failure_attribution(conn):
    with pytest.raises(RuntimeError):
        try:
            with conn.raw.transaction():
                conn.execute(
                    "INSERT INTO review_queue(module,item_type,raw_value,created_at) "
                    "VALUES ('nlp','fixture','must roll back','2026-01-01T00:00:00Z')")
                raise RuntimeError("broken fixture input")
        except RuntimeError as exc:
            stage_state.mark_failed(
                conn, "spans", "chunk-bad", "hash-bad", processor_version="extractor-1",
                error=exc, run_id=None)
            raise
    assert conn.execute(
        "SELECT 1 FROM review_queue WHERE raw_value='must roll back'").fetchone() is None
    failure = conn.execute(
        "SELECT failure_class,input_identity FROM nlp_stage_failures").fetchone()
    assert dict(failure) == {"failure_class": "RuntimeError", "input_identity": "chunk-bad"}


def test_temporal_changes_and_quality_axes_remain_separate(conn):
    a = evidence_state.observe(
        conn, layer="document_element", identity="doc|1", evidence_hash="aaa",
        retrieved_at="2026-01-01T00:00:00Z", source_url="https://example.test/a")
    same = evidence_state.observe(
        conn, layer="document_element", identity="doc|1", evidence_hash="aaa",
        retrieved_at="2026-01-02T00:00:00Z", source_url="https://example.test/a")
    changed = evidence_state.observe(
        conn, layer="document_element", identity="doc|1", evidence_hash="bbb",
        retrieved_at="2026-01-03T00:00:00Z", source_url="https://example.test/a")
    assert [a["change_state"], same["change_state"], changed["change_state"]] == [
        "new", "unchanged", "modified"]
    redirected = evidence_state.observe(
        conn, layer="document_element", identity="doc|1", evidence_hash="bbb",
        retrieved_at="2026-01-04T00:00:00Z", source_url="https://example.test/moved")
    removed = evidence_state.observe(
        conn, layer="document_element", identity="doc|1", evidence_hash="bbb",
        retrieved_at="2026-01-05T00:00:00Z", source_url="https://example.test/moved",
        explicit_state="removed",
        provenance={"meaning": "passage absent, not proof the fact ended"})
    assert redirected["change_state"] == "redirected"
    assert removed["change_state"] == "removed"
    states = conn.execute(
        "SELECT temporal_state_id,state,is_current,supersedes_id FROM evidence_temporal_state "
        "WHERE layer='document_element' AND evidence_identity='doc|1' ORDER BY created_at"
    ).fetchall()
    assert len(states) == 4
    assert sum(bool(row["is_current"]) for row in states) == 1
    assert all(states[index]["supersedes_id"] == states[index - 1]["temporal_state_id"]
               for index in range(1, len(states)))
    assert states[-1]["state"] == "removed"
    for axis in ("authority", "extraction_quality", "corroboration",
                 "temporal_completeness", "review_state"):
        evidence_state.assert_quality(
            conn, layer="document_element", identity="doc|1", assertion_type=axis,
            value=None, status="unknown", method="fixture")
    rows = conn.execute(
        "SELECT assertion_type FROM evidence_quality_assertions WHERE is_current "
        "ORDER BY assertion_type").fetchall()
    assert [row["assertion_type"] for row in rows] == sorted([
        "authority", "extraction_quality", "corroboration",
        "temporal_completeness", "review_state"])


def test_changed_source_bytes_preserve_history_but_only_new_version_is_active(conn, settings):
    versions = []
    for ordinal, text in enumerate(("A retained paragraph.\nA removed passage.",
                                    "A retained paragraph, modified."), start=1):
        reference = EvidenceReference(
            evidence_id=f"source-revision-{ordinal}", source_system="committee_fixture",
            source_url="https://example.test/paper", retrieved_at=f"2026-01-0{ordinal}T00:00:00Z",
            http_status=200, payload_sha256=str(ordinal) * 64,
            raw_object_path=f"data/raw/committee_fixture/{ordinal}.pdf",
            mime_type="application/pdf", source_table="committee_papers",
            source_key="E00000001|paper-7")
        repository.upsert_evidence(conn, reference)
        document_id = repository.upsert_document(
            conn, reference, "COMMITTEE_PAPER", "fixture", 1.0,
            "paper.pdf", "application/pdf", 1, "Paper")
        elements = [ParsedElement("PARAGRAPH", index, paragraph, page_number=1)
                    for index, paragraph in enumerate(text.splitlines(), start=1)]
        versions.append(repository.persist_parse(
            conn, document_id, ParsedDocument("fixture", "1", elements),
            "cfg", None, "GOOD", {}, [], settings))
        conn.commit()

    active = conn.execute(
        "SELECT document_version_id FROM document_versions WHERE is_active=1"
    ).fetchall()
    assert [row["document_version_id"] for row in active] == [versions[1]]
    history = conn.execute(
        "SELECT state,is_current FROM evidence_temporal_state "
        "WHERE layer='document_version' ORDER BY created_at"
    ).fetchall()
    assert len(history) == 2 and history[0]["state"] == "superseded"
    assert history[1]["state"] == "modified" and history[1]["is_current"]
    removed = conn.execute(
        "SELECT provenance_json FROM evidence_temporal_state "
        "WHERE layer='document_element' AND state='removed'"
    ).fetchone()
    assert "not proof the fact ended" in removed["provenance_json"]["meaning"]


def test_bulk_stage_state_lookup_matches_scalar_semantics(conn):
    stage_state.mark_complete(
        conn, "labels", "chunk-a", "hash-a", processor_version="trie-v1",
        model_or_ontology_version="ontology-a", configuration={"rules": 1},
        dependency_hash="dep-a", output=[])
    pending = stage_state.pending_identities(
        conn, "labels", [("chunk-a", "hash-a", "dep-a"),
                         ("chunk-b", "hash-b", "dep-b")],
        processor_version="trie-v1", model_or_ontology_version="ontology-a",
        configuration={"rules": 1})
    assert pending == {"chunk-b"}
    assert stage_state.pending_identities(
        conn, "labels", [("chunk-a", "hash-a", "dep-a")],
        processor_version="trie-v1", model_or_ontology_version="ontology-a",
        configuration={"rules": 1}, force=True) == {"chunk-a"}
