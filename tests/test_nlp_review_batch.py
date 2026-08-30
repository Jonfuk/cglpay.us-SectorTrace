"""pipeline/nlp/review_batch.py — decision-sheet export and batch apply."""
from __future__ import annotations

import pytest

from pipeline.documents import repository
from pipeline.documents.models import EvidenceReference, ParsedDocument, ParsedElement
from pipeline.nlp import chunk as nlp_chunk
from pipeline.nlp import context as nlp_context
from pipeline.nlp import relations, resolve, review_batch, spans

_SENTENCE = ("Change Grow Live is struggling to recruit recovery workers "
             "across the drug and alcohol service.")
_PREDICATE = "workforce.has_recruitment_pressure"


def _seed_doc(conn, settings, evidence_id, sentence, *,
              source_system="committee_paper_promotion"):
    source = EvidenceReference(
        evidence_id=evidence_id, source_system=source_system,
        source_url=f"https://example.test/{evidence_id}",
        retrieved_at="2026-08-27T00:00:00+00:00", http_status=200,
        payload_sha256=(evidence_id * 64)[:64],
        raw_object_path=f"data/raw/{source_system}/{(evidence_id * 64)[:64]}.pdf",
        mime_type="application/pdf", source_table="committee_papers",
        source_key=f"E{evidence_id[-8:].rjust(8, '0')}|https://example.test/{evidence_id}")
    repository.upsert_evidence(conn, source)
    document_id = repository.upsert_document(
        conn, source, "COMMITTEE_PAPER", "fixture", 1.0, "paper.pdf",
        "application/pdf", 3, "Paper")
    parsed = ParsedDocument("fixture", "1", [
        ParsedElement("HEADING", 1, text="Workforce", page_number=1, heading_level=1),
        ParsedElement("PARAGRAPH", 2, text=sentence, parent_sequence=1, page_number=1),
    ])
    repository.persist_parse(conn, document_id, parsed, "cfg", None, "GOOD", {}, [], settings)


def _seed(conn, settings, sentences):
    from pipeline.graph.backfill import _normalise
    conn.execute(
        "INSERT INTO entities (entity_id, entity_type, canonical_name, "
        "canonical_name_normalized, status, created_at, updated_at) "
        "VALUES ('provider:change_grow_live', 'PROVIDER', 'Change Grow Live', ?, "
        "'active', '2026-01-01', '2026-01-01')", (_normalise("Change Grow Live"),))
    for i, sentence in enumerate(sentences):
        _seed_doc(conn, settings, f"evrb{i:04d}", sentence)
    nlp_chunk.run(conn)
    spans.run(conn, extractor="stub")
    nlp_context.run(conn)
    resolve.run(conn)
    relations.run(conn)


def _rows(conn, predicate=_PREDICATE):
    return review_batch.sheet_rows(conn, predicate=predicate, status="new")


# --- grouping ---------------------------------------------------------------

def test_group_id_ignores_whitespace_and_case_not_predicate_or_status():
    a = review_batch.group_id("p.x", "AFFIRMED", "The  Service had NO cover.")
    b = review_batch.group_id("p.x", "AFFIRMED", "the service had no cover.")
    assert a == b
    assert review_batch.group_id("p.x", "NEGATED", "the service had no cover.") != a
    assert review_batch.group_id("p.y", "AFFIRMED", "the service had no cover.") != a


def test_identical_sentences_from_two_documents_share_a_group(conn, settings):
    _seed(conn, settings, [_SENTENCE, _SENTENCE])
    rows = _rows(conn)
    assert len(rows) == 2
    assert rows[0]["group_id"] == rows[1]["group_id"]
    assert rows[0]["group_size"] == 2


def test_groups_only_collapses_to_one_row_with_members(conn, settings):
    _seed(conn, settings, [_SENTENCE, _SENTENCE])
    grouped = review_batch.sheet_rows(conn, predicate=_PREDICATE, status="new",
                                      groups_only=True)
    assert len(grouped) == 1
    assert sorted(grouped[0]["group_members"]) == sorted(
        r["candidate_id"] for r in _rows(conn))


# --- export shape ----------------------------------------------------------

def test_sheet_row_carries_context_and_blank_decision_columns(conn, settings):
    _seed(conn, settings, [_SENTENCE])
    (row,) = _rows(conn)
    assert row["predicate"] == _PREDICATE
    assert row["evidence_span"] == _SENTENCE
    assert row["authority"].startswith("E")          # from source_key
    assert row["source_url"].startswith("https://")
    for field in review_batch.DECISION_FIELDS:
        assert row[field] == ""


def test_write_sheet_roundtrips_jsonl_and_csv(conn, settings, tmp_path):
    _seed(conn, settings, [_SENTENCE, _SENTENCE])
    rows = _rows(conn)
    for name in ("sheet.jsonl", "sheet.csv"):
        path = tmp_path / name
        review_batch.write_sheet(rows, path)
        back = review_batch.read_sheet(path)
        assert [r["candidate_id"] for r in back] == [r["candidate_id"] for r in rows]


def test_groups_only_sheet_refuses_csv(conn, settings, tmp_path):
    _seed(conn, settings, [_SENTENCE])
    grouped = review_batch.sheet_rows(conn, predicate=_PREDICATE, status="new",
                                      groups_only=True)
    with pytest.raises(review_batch.SheetError):
        review_batch.write_sheet(grouped, tmp_path / "g.csv")


# --- apply ---------------------------------------------------------------

def _decided(conn, candidate_id):
    return [tuple(r) for r in conn.execute(
        "SELECT decision, decided_by FROM claim_candidate_decisions "
        "WHERE claim_candidate_id = ?", (candidate_id,)).fetchall()]


def test_apply_records_one_decision_per_row_under_the_given_name(conn, settings):
    _seed(conn, settings, [_SENTENCE])
    (row,) = _rows(conn)
    row["decision"] = "approved"
    out = review_batch.apply_sheet(conn, [row], decided_by="Jon Firth")
    assert out["applied"] == 1 and out["by_decision"] == {"approved": 1}
    assert _decided(conn, row["candidate_id"]) == [("approved", "Jon Firth")]
    assert conn.execute(
        "SELECT status FROM document_claim_candidates WHERE claim_candidate_id = ?",
        (row["candidate_id"],)).fetchone()[0] == "accepted"


def test_apply_skips_blank_decisions(conn, settings):
    _seed(conn, settings, [_SENTENCE])
    (row,) = _rows(conn)
    out = review_batch.apply_sheet(conn, [row], decided_by="Jon Firth")
    assert out["applied"] == 0 and out["skipped_blank"] == 1
    assert _decided(conn, row["candidate_id"]) == []


def test_dry_run_validates_but_writes_no_decision(conn, settings):
    _seed(conn, settings, [_SENTENCE])
    (row,) = _rows(conn)
    row["decision"] = "approved"
    out = review_batch.apply_sheet(conn, [row], decided_by="Jon Firth", dry_run=True)
    assert out["dry_run"] is True and out["applied"] == 1 and out["errors"] == []
    assert _decided(conn, row["candidate_id"]) == []
    # a dry run still leaves an nlp_runs trace (D-02)
    assert conn.execute(
        "SELECT rows_written FROM nlp_runs WHERE run_id = ?",
        (out["run_id"],)).fetchone()[0] == 0


def test_apply_skips_a_candidate_this_reviewer_already_decided(conn, settings):
    _seed(conn, settings, [_SENTENCE])
    (row,) = _rows(conn)
    row["decision"] = "approved"
    review_batch.apply_sheet(conn, [dict(row)], decided_by="Jon Firth")
    again = review_batch.apply_sheet(conn, [dict(row)], decided_by="Jon Firth")
    assert again["applied"] == 0 and again["skipped_existing"] == 1
    forced = review_batch.apply_sheet(conn, [dict(row)], decided_by="Jon Firth",
                                      allow_redecide=True)
    assert forced["applied"] == 1
    assert len(_decided(conn, row["candidate_id"])) == 2


def test_apply_aborts_on_an_invalid_row_and_names_it(conn, settings):
    _seed(conn, settings, [_SENTENCE, _SENTENCE])
    r1, r2 = _rows(conn)
    r1["decision"] = "approved"
    r2["decision"] = "corrected"
    r2["corrected_predicate"] = "not.a.real.predicate"
    out = review_batch.apply_sheet(conn, [r1, r2], decided_by="Jon Firth")
    assert out["applied"] == 1                       # r1 stuck
    assert out["errors"] and "row 2" in out["errors"][0]
    assert conn.execute(
        "SELECT status FROM nlp_runs WHERE run_id = ?",
        (out["run_id"],)).fetchone()[0] == "failed"


def test_groups_only_decision_fans_out_to_every_member(conn, settings):
    _seed(conn, settings, [_SENTENCE, _SENTENCE])
    (grouped,) = review_batch.sheet_rows(conn, predicate=_PREDICATE, status="new",
                                         groups_only=True)
    grouped["decision"] = "approved"
    out = review_batch.apply_sheet(conn, [grouped], decided_by="Jon Firth")
    assert out["applied"] == 2
    for cid in grouped["group_members"]:
        assert _decided(conn, cid) == [("approved", "Jon Firth")]
