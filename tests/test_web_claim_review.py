"""The semantic claim-candidate review workbench (BETA-047).

The nlp layer already records and audits a reviewer's decision
(`pipeline/nlp/decisions.py`, pinned in `tests/test_nlp_decisions.py`) and
reports training readiness (`pipeline/nlp/gate.py`,
`tests/test_nlp_gate.py`). This file pins the `/api/admin/*` bridge that lets
a person actually do the review:

  * list / detail / ontology-options are read-only and admin-only;
  * one decision per request, named reviewer required, corrections
    ontology-validated;
  * nothing here writes `graph_claims`, trains a model, or bulk-approves.
"""
from __future__ import annotations

import inspect
import sqlite3
import threading

import httpx
import pytest

from pipeline.config import Settings
from pipeline.documents import repository
from pipeline.documents.models import EvidenceReference, ParsedDocument, ParsedElement
from pipeline.nlp import chunk as nlp_chunk
from pipeline.nlp import context as nlp_context
from pipeline.nlp import relations, spans
from pipeline.web import server as server_module
from pipeline.web.server import build_server


def _seed(conn, settings):
    source = EvidenceReference(
        evidence_id="ev-cr", source_system="committee_paper_promotion",
        source_url="https://example.test/ev-cr", retrieved_at="2026-08-27T00:00:00+00:00",
        http_status=200, payload_sha256="c" * 64,
        raw_object_path="data/raw/committee_paper_promotion/" + "c" * 64 + ".pdf",
        mime_type="application/pdf")
    repository.upsert_evidence(conn, source)
    document_id = repository.upsert_document(
        conn, source, "COMMITTEE_PAPER", "fixture", 1.0, "paper.pdf",
        "application/pdf", 3, "Workforce report")
    parsed = ParsedDocument("fixture", "1", [
        ParsedElement("HEADING", 1, text="Workforce", page_number=1, heading_level=1),
        ParsedElement("PARAGRAPH", 2, text="Change Grow Live is struggling to recruit "
                      "recovery workers across the drug and alcohol service.",
                      parent_sequence=1, page_number=1),
    ])
    repository.persist_parse(conn, document_id, parsed, "cfg", None, "GOOD", {}, [], settings)
    nlp_chunk.run(conn)
    spans.run(conn, extractor="stub")
    nlp_context.run(conn)
    relations.run(conn)
    return conn.execute(
        "SELECT claim_candidate_id FROM document_claim_candidates LIMIT 1").fetchone().values().__iter__().__next__()


@pytest.fixture
def client(conn: sqlite3.Connection, settings: Settings):
    candidate_id = _seed(conn, settings)
    conn.commit()
    conn.close()
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=15.0) as http:
            http.candidate_id = candidate_id
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _decide(client, **body):
    return client.post("/api/admin/claim-candidates/decide", json=body,
                       headers={"Content-Type": "application/json",
                                "Origin": str(client.base_url)})


def test_listing_returns_the_candidate_with_labels_and_a_caveat(client):
    body = client.get("/api/admin/claim-candidates?status=new").json()
    assert body["total"] >= 1
    row = body["candidates"][0]
    assert row["claim_candidate_id"] == client.candidate_id
    assert row["evidence_span"]
    assert row["predicate_label"]           # resolved from the ontology
    assert row["source_system"] == "committee_paper_promotion"
    assert row["last_decision"] is None
    assert "not a claim" in body["caveat"]


def test_detail_carries_the_sentence_chunk_and_an_empty_history(client):
    row = client.get(f"/api/admin/claim-candidates/{client.candidate_id}").json()
    assert row["chunk_text"]
    assert row["ontology_version"]
    assert row["decisions"] == []


def test_unknown_candidate_is_a_400(client):
    assert client.get("/api/admin/claim-candidates/not-a-candidate").status_code == 400


def test_ontology_options_expose_the_controlled_vocabularies(client):
    opts = client.get("/api/admin/claim-ontology").json()
    assert opts["predicates"] and opts["concepts"]
    assert all("id" in p and "label" in p for p in opts["predicates"])
    assert opts["reason_codes"]


def test_gate_report_is_the_readonly_034g_check(client):
    gate = client.get("/api/admin/claim-gate").json()
    assert gate["ready"] is False           # a single fixture cannot pass it
    assert set(gate["categories"]) == {
        "vacancy_pressure", "agency_reliance", "tupe_transfer",
        "funding_reduction", "cost_pressure", "waiting_time"}
    assert gate["blocking"]


def test_a_decision_needs_a_named_reviewer(client):
    response = _decide(client, claim_candidate_id=client.candidate_id,
                       decision="approved", decided_by="   ")
    assert response.status_code == 400


def test_approve_records_the_decision_and_moves_the_candidate(client):
    response = _decide(client, claim_candidate_id=client.candidate_id,
                       decision="approved", decided_by="Reviewer A")
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"

    detail = client.get(f"/api/admin/claim-candidates/{client.candidate_id}").json()
    assert [d["decision"] for d in detail["decisions"]] == ["approved"]
    assert detail["decisions"][0]["decided_by"] == "Reviewer A"
    assert detail["decisions"][0]["graph_claim_id"] is None   # no draft written


def test_corrected_requires_an_ontology_valid_correction(client):
    bare = _decide(client, claim_candidate_id=client.candidate_id,
                   decision="corrected", decided_by="Reviewer A")
    assert bare.status_code == 400

    bad = _decide(client, claim_candidate_id=client.candidate_id, decision="corrected",
                  decided_by="Reviewer A", corrected_predicate="workforce.not_real")
    assert bad.status_code == 400

    good = _decide(client, claim_candidate_id=client.candidate_id, decision="corrected",
                   decided_by="Reviewer A",
                   corrected_predicate="workforce.has_retention_pressure",
                   reason_code="wrong_predicate")
    assert good.status_code == 200


def test_there_is_no_bulk_decision_path():
    """One candidate per request. The workbench must not grow a decide-all."""
    source = inspect.getsource(server_module.Handler._post_routes)
    assert "claim-candidates/decide" in source
    for forbidden in ("claim-candidates/decide-all", "claim-candidates/bulk",
                      "claim-candidates/approve-all"):
        assert forbidden not in source
