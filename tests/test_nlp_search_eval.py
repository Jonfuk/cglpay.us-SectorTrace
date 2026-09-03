"""pipeline/nlp/semantic_search.py and pipeline/nlp/eval.py.

The stub embedder is a signed bag-of-words: it cannot match a paraphrase with
no shared vocabulary, so the semantic assertions here use queries that share
words with the target passage. That is the stub's known limit; the point of
these tests is that ranking, fusion, filtering and the metric maths are
correct, not that the stub retrieves well.
"""
from __future__ import annotations

import json

import pytest

from pipeline.documents import repository
from pipeline.documents.models import EvidenceReference, ParsedDocument, ParsedElement
from pipeline.nlp import chunk as nlp_chunk
from pipeline.nlp import embeddings, semantic_search
from pipeline.nlp import eval as nlp_eval


def _seed(conn, settings, evidence_id, source_system, heading, *paragraphs):
    source = EvidenceReference(
        evidence_id=evidence_id, source_system=source_system,
        source_url=f"https://example.test/{evidence_id}",
        retrieved_at="2026-08-27T00:00:00+00:00", http_status=200,
        payload_sha256=(evidence_id * 64)[:64],
        raw_object_path=f"data/raw/{source_system}/{(evidence_id * 64)[:64]}.pdf",
        mime_type="application/pdf")
    repository.upsert_evidence(conn, source)
    document_id = repository.upsert_document(
        conn, source, "COMMITTEE_PAPER", "fixture", 1.0, "paper.pdf",
        "application/pdf", 3, heading)
    elements = [ParsedElement("HEADING", 1, text=heading, page_number=1, heading_level=1)]
    for i, para in enumerate(paragraphs, start=2):
        elements.append(ParsedElement("PARAGRAPH", i, text=para, parent_sequence=1,
                                      page_number=1))
    parsed = ParsedDocument("fixture", "1", elements)
    return repository.persist_parse(conn, document_id, parsed, "cfg", None, "GOOD", {}, [], settings)


_RECRUIT = ("Recruitment and retention of drug and alcohol key workers is the single "
            "biggest risk to the treatment service, with vacancies unfilled for months.")
_BUDGET = ("The public health grant reduction forces budget savings across the "
           "commissioned treatment contract from the next financial year.")
_UNRELATED = ("The committee noted the car park resurfacing programme and the "
              "highway maintenance schedule for the coming quarter.")


@pytest.fixture
def corpus(conn, settings, monkeypatch):
    # The production stub is intentionally 256-wide, while migration 0071's
    # canonical pgvector column is 384-wide.  Use a compatible temporary width
    # here so this fixture exercises the required PostgreSQL ranking path.
    monkeypatch.setattr(embeddings, "STUB_DIMENSION", embeddings.VECTOR_COLUMN_DIM)
    monkeypatch.setattr(embeddings.StubEmbedder, "dimension", embeddings.VECTOR_COLUMN_DIM)
    _seed(conn, settings, "evrec", "committee_paper_promotion", "Workforce", _RECRUIT)
    _seed(conn, settings, "evbud", "committee_paper_promotion", "Finance", _BUDGET)
    _seed(conn, settings, "evcar", "cdp_document_promotion", "Estates", _UNRELATED)
    nlp_chunk.run(conn)
    embeddings.run(conn, model="stub")
    return conn


# --- semantic_search -------------------------------------------------------

def test_keyword_mode_finds_the_literal_term(corpus):
    out = semantic_search.search(corpus, "recruitment retention", mode="keyword", limit=5)
    assert out["mode"] == "keyword"
    assert out["results"], "expected a keyword hit"
    top = out["results"][0]
    assert "Recruitment and retention" in top["text"]
    assert top["source_url"] == "https://example.test/evrec"
    assert top["page_start"] == 1
    assert top["score"]["keyword_rank"] == 1


def test_semantic_mode_ranks_by_cosine(corpus):
    out = semantic_search.search(
        corpus, "recruitment retention key workers vacancies", mode="semantic", limit=5)
    assert out["model_key"] == "embed:stub"
    assert out["results"]
    assert "Recruitment and retention" in out["results"][0]["text"]
    assert out["results"][0]["score"]["cosine"] >= out["results"][-1]["score"]["cosine"]


def test_hybrid_fuses_both_lists(corpus):
    out = semantic_search.search(
        corpus, "recruitment retention of key workers", mode="hybrid", limit=5)
    assert out["mode"] == "hybrid"
    top = out["results"][0]
    assert "Recruitment and retention" in top["text"]
    assert "rrf" in top["score"]
    assert top["score"].get("keyword_rank") == 1
    assert top["score"].get("semantic_rank") is not None


def test_source_system_filter_excludes_out_of_scope_chunks(corpus):
    out = semantic_search.search(
        corpus, "highway maintenance resurfacing", mode="keyword", limit=5,
        source_system="committee_paper_promotion")
    assert out["results"] == []
    unscoped = semantic_search.search(
        corpus, "highway maintenance resurfacing", mode="keyword", limit=5)
    assert unscoped["results"]


def test_hybrid_degrades_to_keyword_when_no_embeddings(conn, settings):
    _seed(conn, settings, "evrec", "committee_paper_promotion", "Workforce", _RECRUIT)
    nlp_chunk.run(conn)  # chunks but no embeddings
    out = semantic_search.search(conn, "recruitment retention", mode="hybrid", limit=5)
    assert out["results"]
    assert any("no embeddings" in note for note in out["notes"])
    assert any("degraded to keyword-only" in note for note in out["notes"])


def test_bad_input_is_a_search_error(corpus):
    with pytest.raises(semantic_search.SearchError):
        semantic_search.search(corpus, "   ", mode="hybrid")
    with pytest.raises(semantic_search.SearchError):
        semantic_search.search(corpus, "recruitment", mode="magic")


def test_nothing_is_written_by_a_search(corpus):
    before = corpus.execute("SELECT COUNT(*) FROM nlp_runs").fetchone()[0]
    semantic_search.search(corpus, "recruitment retention", mode="hybrid", limit=5)
    assert corpus.execute("SELECT COUNT(*) FROM nlp_runs").fetchone()[0] == before


# --- eval harness ---------------------------------------------------------

def _query_file(tmp_path, queries):
    path = tmp_path / "queries.json"
    path.write_text(json.dumps({"queries": queries}), encoding="utf-8")
    return path


def test_eval_scores_a_marked_query_and_skips_an_unmarked_one(corpus, tmp_path):
    path = _query_file(tmp_path, [
        {"id": "recruit", "query": "recruitment and retention of key workers",
         "relevant_markers": ["single biggest risk to the treatment service"]},
        {"id": "later", "query": "something not yet judged", "relevant_markers": []},
    ])
    report = nlp_eval.run(corpus, queries_path=path, mode="hybrid", model="stub")

    assert report["n_queries"] == 2
    assert report["metrics"]["scored_queries"] == 1
    assert report["metrics"]["recall@5"] == 1.0
    assert report["metrics"]["mrr"] == 1.0

    by_id = {q["id"]: q for q in report["per_query"]}
    assert by_id["recruit"]["first_rank"] == 1
    assert by_id["recruit"]["unmarked"] is False
    assert by_id["later"]["unmarked"] is True


def test_eval_reports_a_miss_as_zero(corpus, tmp_path):
    path = _query_file(tmp_path, [
        {"id": "absent", "query": "recruitment retention",
         "relevant_markers": ["a passage that appears in no chunk anywhere"]},
    ])
    report = nlp_eval.run(corpus, queries_path=path, mode="keyword", model="stub")
    assert report["metrics"]["recall@5"] == 0.0
    assert report["metrics"]["mrr"] == 0.0
    assert report["per_query"][0]["first_rank"] is None


def test_the_committed_query_set_is_well_formed():
    queries = nlp_eval._load(nlp_eval.DEFAULT_QUERY_SET)
    assert len(queries) >= 5
    assert all(q.get("query") for q in queries)
