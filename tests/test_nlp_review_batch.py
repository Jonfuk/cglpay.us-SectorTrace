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


def test_group_by_exact_collapses_to_one_row_with_members(conn, settings):
    _seed(conn, settings, [_SENTENCE, _SENTENCE])
    grouped = review_batch.sheet_rows(conn, predicate=_PREDICATE, status="new",
                                      group_by="exact")
    assert len(grouped) == 1
    assert sorted(grouped[0]["group_members"]) == sorted(
        r["candidate_id"] for r in _rows(conn))


def test_template_id_blanks_numbers_money_subject_and_object():
    t = review_batch.template_id
    # numbers / money differ, shape is the same
    assert (t("p.x", "AFFIRMED", "a budget reduction of £1.2 million", None, None)
            == t("p.x", "AFFIRMED", "a budget reduction of £900,000", None, None))
    # the blanked subject / object literal differ, shape is the same
    assert (t("p.x", "AFFIRMED", "Kent County Council had no agency staff",
              "Kent County Council", None)
            == t("p.x", "AFFIRMED", "Hull City Council had no agency staff",
                 "Hull City Council", None))
    # predicate and assertion status still split the key
    assert (t("p.x", "AFFIRMED", "a reduction of £5", None, None)
            != t("p.x", "NEGATED", "a reduction of £9", None, None))


def test_group_by_template_collapses_variants(conn, settings):
    a = "Change Grow Live is struggling to recruit recovery workers, a £12,000 gap."
    b = "Change Grow Live is struggling to recruit recovery workers, a £30,000 gap."
    _seed(conn, settings, [a, b])
    rows = review_batch.sheet_rows(conn, predicate=_PREDICATE, status="new")
    assert len(rows) == 2
    assert rows[0]["group_id"] != rows[1]["group_id"]        # exact: distinct
    assert rows[0]["template_id"] == rows[1]["template_id"]  # template: same
    (grouped,) = review_batch.sheet_rows(conn, predicate=_PREDICATE, status="new",
                                         group_by="template")
    assert sorted(grouped["group_variants"]) == sorted([a, b])
    assert len(grouped["group_members"]) == 2


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


def test_collapsed_sheet_refuses_csv(conn, settings, tmp_path):
    _seed(conn, settings, [_SENTENCE])
    grouped = review_batch.sheet_rows(conn, predicate=_PREDICATE, status="new",
                                      group_by="exact")
    with pytest.raises(review_batch.SheetError):
        review_batch.write_sheet(grouped, tmp_path / "g.csv")


# --- screen + suggestions ------------------------------------------------

def test_screen_reason_flags_broken_extractions():
    sr = review_batch.screen_reason
    assert sr("too short", None, None) == "span_too_short"
    assert sr("x" * 1300, None, None) == "span_too_long"
    assert sr("a" * 60, "15", None) == "object_is_bare_number"
    assert sr("a" * 60, "15", "concept:money") is None      # resolved -> fine
    assert sr("A clean sentence of a reasonable length about staffing.", None, None) is None


# a genuine candidate: one run-on sentence (no internal full stop, so the
# sentence splitter keeps it whole) with the "struggling to recruit" trigger
# up front and enough trailing clause to run past SCREEN_MAX_SPAN.
_LONG = ("Change Grow Live is struggling to recruit recovery workers and "
         + "also faces sustained pressure across teams and rotas and cover "
           "arrangements and vacancies carried month after month " * 15)


def test_span_too_long_is_flagged_but_not_auto_rejected(conn, settings):
    _seed(conn, settings, [_LONG])
    (row,) = review_batch.sheet_rows(conn, predicate=_PREDICATE, status="new")
    assert row["screen_reason"] == "span_too_long"          # visible to the reviewer
    assert row["suggested_decision"] == ""                  # but not a reject suggestion
    assert row["suggested_by"] == ""


def test_accept_suggested_rejected_lifts_only_blank_rows_and_notes_the_source(conn, settings):
    _seed(conn, settings, [_SENTENCE, _SENTENCE])
    a, b = review_batch.sheet_rows(conn, predicate=_PREDICATE, status="new")
    a["suggested_decision"] = "rejected"                    # as a screen / model would
    a["suggested_reason"] = "object_is_bare_number"
    a["suggested_by"] = "screen:object_is_bare_number"
    b["decision"] = "approved"                              # a real call stands
    out = review_batch.apply_sheet(conn, [a, b], decided_by="Jon Firth",
                                   accept_suggested="rejected")
    assert out["applied"] == 2 and out["from_suggestion"] == 1
    row = conn.execute(
        "SELECT decision, reason_code, note FROM claim_candidate_decisions "
        "WHERE claim_candidate_id = ?", (a["candidate_id"],)).fetchone()
    assert tuple(row) == ("rejected", "object_is_bare_number", "via screen:object_is_bare_number")


def test_accept_suggested_rejects_anything_other_than_rejected(conn, settings):
    _seed(conn, settings, [_SENTENCE])
    (row,) = review_batch.sheet_rows(conn, predicate=_PREDICATE, status="new")
    with pytest.raises(review_batch.SheetError):
        review_batch.apply_sheet(conn, [row], decided_by="Jon Firth",
                                 accept_suggested="approved")


def test_accept_suggested_ignores_an_approved_suggestion(conn, settings):
    _seed(conn, settings, [_SENTENCE])
    (row,) = review_batch.sheet_rows(conn, predicate=_PREDICATE, status="new")
    row["suggested_decision"] = "approved"                  # a model's guess
    row["suggested_by"] = "model:test"
    out = review_batch.apply_sheet(conn, [row], decided_by="Jon Firth",
                                   accept_suggested="rejected")
    assert out["applied"] == 0 and out["skipped_blank"] == 1


def test_apply_reports_reviewer_vs_suggestion_agreement(conn, settings):
    _seed(conn, settings, [_SENTENCE, _LONG, _SENTENCE])
    rows = review_batch.sheet_rows(conn, predicate=_PREDICATE, status="new")
    # three rows, all suggested 'rejected'; the reviewer agrees on two.
    for row in rows:
        row["suggested_decision"] = "rejected"
        row["suggested_by"] = "model:test"
    rows[0]["decision"] = "rejected"
    rows[1]["decision"] = "rejected"
    rows[2]["decision"] = "approved"
    out = review_batch.apply_sheet(conn, rows, decided_by="Jon Firth")
    assert out["suggestion_agreement"]["n"] == 3
    assert out["suggestion_agreement"]["agree"] == round(2 / 3, 3)
    assert out["suggestion_agreement"]["flag"] is False


# --- sampling ----------------------------------------------------------

def test_sample_keeps_the_bands_and_a_deterministic_tail(conn, settings):
    _seed(conn, settings, [_SENTENCE, _SENTENCE, _SENTENCE])
    full = review_batch.sheet_rows(conn, predicate=_PREDICATE, status="new")
    for row in full:
        assert row["stratum"] in ("positive_band", "negative_band", "tail")
    once = review_batch.sheet_rows(conn, predicate=_PREDICATE, status="new", sample=True)
    twice = review_batch.sheet_rows(conn, predicate=_PREDICATE, status="new", sample=True)
    assert [r["candidate_id"] for r in once] == [r["candidate_id"] for r in twice]
    assert len(once) <= len(full)


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


def test_collapsed_decision_fans_out_to_every_member(conn, settings):
    _seed(conn, settings, [_SENTENCE, _SENTENCE])
    (grouped,) = review_batch.sheet_rows(conn, predicate=_PREDICATE, status="new",
                                         group_by="exact")
    grouped["decision"] = "approved"
    out = review_batch.apply_sheet(conn, [grouped], decided_by="Jon Firth")
    assert out["applied"] == 2
    for cid in grouped["group_members"]:
        assert _decided(conn, cid) == [("approved", "Jon Firth")]


# --- take-suggested-corrections + until-gate --------------------------

def test_gate_categories_for_maps_predicates_to_names():
    got = review_batch._gate_categories_for(
        {"workforce.relies_on_agency", "finance.has_cost_pressure", "not.a.gate.pred"})
    assert got == {"agency_reliance", "cost_pressure"}


def test_take_suggested_corrections_fills_a_blank_corrected_predicate(conn, settings):
    _seed(conn, settings, [_SENTENCE])
    (row,) = _rows(conn)
    row["decision"] = "corrected"                     # the reviewer's own choice
    row["suggested_corrected_predicate"] = "workforce.has_retention_pressure"
    row["suggested_by"] = "model:m/x"
    out = review_batch.apply_sheet(conn, [row], decided_by="Jon Firth",
                                   take_suggested_corrections=True)
    assert out["applied"] == 1
    got = conn.execute(
        "SELECT decision, corrected_predicate, note FROM claim_candidate_decisions "
        "WHERE claim_candidate_id = ?", (row["candidate_id"],)).fetchone()
    assert got[0] == "corrected"
    assert got[1] == "workforce.has_retention_pressure"
    assert "via model:m/x" in got[2]


def test_take_suggested_corrections_leaves_a_typed_predicate_alone(conn, settings):
    _seed(conn, settings, [_SENTENCE])
    (row,) = _rows(conn)
    row["decision"] = "corrected"
    row["corrected_predicate"] = "workforce.has_turnover"      # the reviewer typed this
    row["suggested_corrected_predicate"] = "workforce.has_retention_pressure"
    review_batch.apply_sheet(conn, [row], decided_by="Jon Firth",
                             take_suggested_corrections=True)
    got = conn.execute(
        "SELECT corrected_predicate FROM claim_candidate_decisions "
        "WHERE claim_candidate_id = ?", (row["candidate_id"],)).fetchone()
    assert got[0] == "workforce.has_turnover"


def test_until_gate_stops_once_the_category_is_ready(conn, settings, monkeypatch):
    _seed(conn, settings, [_SENTENCE] * 25)
    rows = review_batch.sheet_rows(conn, predicate=_PREDICATE, status="new")
    for row in rows:
        row["decision"] = "approved"
    # recruitment_pressure is not in GATE_CATEGORIES, so map it in for the test
    monkeypatch.setitem(review_batch.gate_mod.GATE_CATEGORIES, "rp", _PREDICATE)
    calls = {"n": 0}

    def _fake_check(_conn, **kw):
        calls["n"] += 1
        return {"categories": {"rp": {"ready": calls["n"] >= 2}}}

    monkeypatch.setattr(review_batch.gate_mod, "check", _fake_check)
    out = review_batch.apply_sheet(conn, rows, decided_by="Jon Firth", until_gate=True)
    assert out["stopped_at_gate"] is True
    assert out["applied"] < len(rows)                 # stopped before the end
    assert out["gate_categories"] == {"rp": True}
