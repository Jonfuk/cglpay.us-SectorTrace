"""pipeline/nlp/claims_features.py -- labels, the deterministic held-out carve,
the predict population."""
from __future__ import annotations

import random

import pytest

from pipeline.nlp import claims, claims_features
from tests.nlp_claims_support import STUB_MODEL_KEY, seed_labelled, seed_unlabelled_chunks

CATEGORY = "vacancy_pressure"


def _examples(conn):
    return claims_features.labelled_examples(conn, CATEGORY, embedder_model_key=STUB_MODEL_KEY)


def test_labels_follow_the_gate_definition(conn):
    seed_labelled(conn, CATEGORY, n_pos=4, n_neg=3)
    examples = _examples(conn)
    assert sorted(e.label for e in examples) == [0, 0, 0, 1, 1, 1, 1]
    # every example carries its chunk text and a vector blob
    assert all(e.text for e in examples)
    assert all(isinstance(e.embedding, (bytes, bytearray)) for e in examples)


def test_latest_decision_per_candidate_wins(conn):
    [cand, *_] = seed_labelled(conn, CATEGORY, n_pos=1, n_neg=1)
    # a later decision flips the first candidate from approved -> rejected
    conn.execute(
        "INSERT INTO claim_candidate_decisions (claim_candidate_id, decision, decided_by, "
        "decided_at) VALUES (?, 'rejected', 'tester2', '2026-09-01T00:00:00+00:00')", (cand,))
    conn.commit()
    by_id = {e.candidate_id: e.label for e in _examples(conn)}
    assert by_id[cand] == 0  # the flip is authoritative


def test_example_without_embedding_has_none(conn):
    seed_labelled(conn, CATEGORY, n_pos=1, n_neg=1, embed=False)
    assert all(e.embedding is None for e in _examples(conn))


def test_heldout_carve_is_deterministic_and_order_independent(conn):
    seed_labelled(conn, CATEGORY, n_pos=25, n_neg=25)
    examples = _examples(conn)

    train_a, held_a = claims_features.split_examples(examples, CATEGORY)
    shuffled = list(examples)
    random.Random(1).shuffle(shuffled)
    train_b, held_b = claims_features.split_examples(shuffled, CATEGORY)

    ids_a = {e.candidate_id for e in held_a}
    ids_b = {e.candidate_id for e in held_b}
    assert ids_a == ids_b                                   # order-independent
    assert len(held_a) == 2 * claims.HELDOUT_PER_CLASS      # 10 + 10
    assert sum(e.label for e in held_a) == claims.HELDOUT_PER_CLASS
    assert ids_a.isdisjoint({e.candidate_id for e in train_a})   # never trained on
    assert len(train_a) == 50 - 2 * claims.HELDOUT_PER_CLASS


def test_split_refuses_when_a_class_cannot_spare_the_margin(conn):
    seed_labelled(conn, CATEGORY, n_pos=8, n_neg=25)   # 8 <= HELDOUT_PER_CLASS
    with pytest.raises(claims_features.FeatureError, match="positive"):
        claims_features.split_examples(_examples(conn), CATEGORY)


def test_predict_population_is_live_embedded_chunks(conn):
    seed_labelled(conn, CATEGORY, n_pos=3, n_neg=2)
    pop = claims_features.predict_population(conn, embedder_model_key=STUB_MODEL_KEY)
    assert len(pop) == 5
    assert all(p.embedding and p.chunk_id for p in pop)
    # a superseded chunk drops out
    conn.execute("UPDATE document_chunks SET superseded = 1 "
                 "WHERE document_chunk_id = ?", (pop[0].chunk_id,))
    conn.commit()
    assert len(claims_features.predict_population(conn, embedder_model_key=STUB_MODEL_KEY)) == 4


def test_corpus_negatives_are_unlabelled_chunks_as_label_zero(conn):
    seed_labelled(conn, CATEGORY, n_pos=3, n_neg=2)
    labelled_chunks = {e.chunk_id for e in _examples(conn)}
    seed_unlabelled_chunks(conn, "cn", n=40)

    negs = claims_features.corpus_negatives(
        conn, CATEGORY, embedder_model_key=STUB_MODEL_KEY, n=15, exclude=labelled_chunks)
    assert len(negs) == 15
    assert all(e.label == 0 and e.candidate_id.startswith("corpusneg:") for e in negs)
    assert labelled_chunks.isdisjoint({e.chunk_id for e in negs})
    # deterministic and disjoint from the base-rate draw
    again = claims_features.corpus_negatives(
        conn, CATEGORY, embedder_model_key=STUB_MODEL_KEY, n=15, exclude=labelled_chunks)
    assert [e.chunk_id for e in negs] == [e.chunk_id for e in again]
    base = claims_features.base_rate_sample(
        conn, CATEGORY, embedder_model_key=STUB_MODEL_KEY, n=15,
        exclude=labelled_chunks | {e.chunk_id for e in negs})
    assert {e.chunk_id for e in negs}.isdisjoint({r.chunk_id for r in base})
