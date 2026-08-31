"""Seed a tiny labelled corpus for the 034G claim-prediction tests, directly
by SQL -- the full parse/chunk/embed pipeline is far more than these tests
need, and the point here is the head, not the extraction.

`seed_labelled` writes, per requested category: one evidence/document/version,
N chunks, a stub embedding per chunk (separable by label unless `separable`
is False), one claim candidate per chunk on the category's gate predicate,
and one decision per candidate (`approved` + `AFFIRMED` for a positive,
`rejected` for a negative).
"""
from __future__ import annotations

import random
import struct

from pipeline.nlp.gate import GATE_CATEGORIES

_NOW = "2026-08-31T12:00:00+00:00"
STUB_MODEL_KEY = "embed:stub"
_DIM = 16


def _vec(rng: random.Random, label: int, separable: bool) -> bytes:
    if separable:
        centre = 1.0 if label == 1 else -1.0
        values = [centre + rng.gauss(0, 0.25) for _ in range(_DIM)]
    else:
        values = [rng.gauss(0, 1.0) for _ in range(_DIM)]
    return struct.pack("<%df" % _DIM, *values)


def _ensure_registry(conn) -> None:
    conn.execute(
        "INSERT INTO nlp_model_registry (model_key, model_provider, model_id, "
        "dimension, first_seen_at) VALUES (?, 'stub', 'stub', ?, ?) "
        "ON CONFLICT(model_key) DO NOTHING", (STUB_MODEL_KEY, _DIM, _NOW))


def seed_labelled(conn, category: str, *, n_pos: int, n_neg: int,
                  separable: bool = True, seed: int = 0, embed: bool = True,
                  decided_at: str = _NOW) -> list[str]:
    """Returns the claim_candidate_ids created, positives first."""
    predicate = GATE_CATEGORIES[category]
    rng = random.Random(f"{category}-{seed}")
    _ensure_registry(conn)

    ev = f"ev-{category}-{seed}"
    doc = f"doc-{category}-{seed}"
    ver = f"ver-{category}-{seed}"
    conn.execute(
        "INSERT INTO evidence_records (evidence_id, source_system, retrieved_at, "
        "payload_sha256, created_at) VALUES (?, 'committee_paper_promotion', ?, ?, ?)",
        (ev, _NOW, (ev * 64)[:64], _NOW))
    conn.execute(
        "INSERT INTO document_records (document_id, evidence_id, document_type, "
        "created_at, updated_at) VALUES (?, ?, 'COMMITTEE_PAPER', ?, ?)",
        (doc, ev, _NOW, _NOW))
    conn.execute(
        "INSERT INTO document_versions (document_version_id, document_id, parser_name, "
        "parser_version, parse_schema_version, config_hash, status, is_active, created_at) "
        "VALUES (?, ?, 'fixture', '1', '1', 'cfg', 'GOOD', 1, ?)", (ver, doc, _NOW))

    ids: list[str] = []
    for i in range(n_pos + n_neg):
        label = 1 if i < n_pos else 0
        chunk = f"chunk-{category}-{seed}-{i}"
        text = (f"{category} pressure is reported across the service this year."
                if label == 1 else
                f"the {category} position is stable and well managed this year.")
        conn.execute(
            "INSERT INTO document_chunks (document_chunk_id, document_version_id, "
            "chunker_name, chunker_version, chunk_index, text, text_sha256, "
            "token_estimate, char_start, char_end, created_at) "
            "VALUES (?, ?, 'fixture', '1', ?, ?, ?, 10, 0, 50, ?)",
            (chunk, ver, i, text, (chunk * 64)[:64], _NOW))
        if embed:
            conn.execute(
                "INSERT INTO document_embeddings (document_chunk_id, model_key, "
                "dimension, embedding, created_at) VALUES (?, ?, ?, ?, ?)",
                (chunk, STUB_MODEL_KEY, _DIM, _vec(rng, label, separable), _NOW))

        cand = f"cand-{category}-{seed}-{i}"
        conn.execute(
            "INSERT INTO document_claim_candidates (claim_candidate_id, document_chunk_id, "
            "predicate, assertion_status, relation_extractor, relation_extractor_version, "
            "evidence_span, char_start, char_end, created_at) "
            "VALUES (?, ?, ?, 'AFFIRMED', 'nlp-rule', '1', ?, 0, 50, ?)",
            (cand, chunk, predicate, text, _NOW))
        conn.execute(
            "INSERT INTO claim_candidate_decisions (claim_candidate_id, decision, "
            "decided_by, decided_at) VALUES (?, ?, 'tester', ?)",
            (cand, "approved" if label == 1 else "rejected", decided_at))
        ids.append(cand)
    conn.commit()
    return ids
