"""Turning `claim_candidate_decisions` into per-category training data.

One binary head per gate category. This module is the half that is shared
between the two models in the bake-off (`claims_train`): it reads the decided
candidates, applies the *same* positive/negative definition the gate uses
(imported from `gate`, never re-implemented), attaches each candidate's chunk
text and -- for the logreg head -- its 034A embedding, and carves the
deterministic held-out set before any fitting happens.

The held-out carve is by a stable hash of the candidate id, NOT by decision
order: re-labelling, a second reviewer, or a re-run cannot move which
examples are held out, so a head's held-out precision is comparable across
runs. The chosen ids are written onto every head row for the category
(`heldout_candidate_ids_json`), so "why is this chunk marked heldout" is a
query.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from pipeline.nlp import claims
from pipeline.nlp.gate import GATE_CATEGORIES, _label_for

# Latest decision per candidate wins. A candidate can carry more than one
# decision row -- a reviewer correcting themselves, or a second reviewer on a
# double-reviewed item. The gate counts every decision row; for a training
# label we take the most recent one per candidate as authoritative, then run
# it through `gate._label_for`. A candidate the latest decision leaves
# unlabelled for this category (e.g. approved for a different predicate) is
# simply not an example for this category.
_DECIDED_SQL = """
SELECT c.claim_candidate_id      AS claim_candidate_id,
       c.document_chunk_id       AS document_chunk_id,
       c.predicate               AS predicate,
       c.assertion_status        AS assertion_status,
       d.decision                AS decision,
       d.corrected_predicate     AS corrected_predicate,
       d.decided_at              AS decided_at,
       dc.text                   AS text,
       em.embedding              AS embedding
FROM claim_candidate_decisions d
JOIN document_claim_candidates c ON c.claim_candidate_id = d.claim_candidate_id
JOIN document_chunks dc ON dc.document_chunk_id = c.document_chunk_id
LEFT JOIN document_embeddings em
       ON em.document_chunk_id = dc.document_chunk_id AND em.model_key = ?
ORDER BY d.decided_at, d.id
"""


@dataclass(frozen=True)
class Example:
    candidate_id: str
    chunk_id: str
    text: str
    label: int                 # 1 positive, 0 negative
    decided_at: str
    embedding: bytes | None    # little-endian float32 blob, or None if the chunk is not embedded


class FeatureError(ValueError):
    """A category that cannot produce a trainable + held-out split."""


def _heldout_rank(candidate_id: str, category: str) -> str:
    return hashlib.sha256(
        f"{claims.HELDOUT_SEED}|{category}|{candidate_id}".encode("utf-8")).hexdigest()


def labelled_examples(conn, category: str, *, embedder_model_key: str) -> list[Example]:
    """Every decided candidate that is a positive or a negative for `category`,
    one row per candidate (latest decision wins), with chunk text and -- when
    the chunk is embedded under `embedder_model_key` -- its vector blob."""
    if category not in GATE_CATEGORIES:
        raise FeatureError(f"{category!r} is not a gate category "
                           f"({', '.join(GATE_CATEGORIES)}).")
    predicate = GATE_CATEGORIES[category]

    latest: dict[str, dict] = {}
    for row in conn.execute(_DECIDED_SQL, (embedder_model_key,)).fetchall():
        latest[row["claim_candidate_id"]] = dict(row)  # ORDER BY decided_at, id -> last wins

    examples: list[Example] = []
    for cand_id, row in latest.items():
        label = _label_for(row, predicate)
        if label is None:
            continue
        examples.append(Example(
            candidate_id=cand_id, chunk_id=row["document_chunk_id"], text=row["text"] or "",
            label=1 if label == "positive" else 0, decided_at=row["decided_at"] or "",
            embedding=row["embedding"]))
    return examples


def split_examples(examples: list[Example], category: str, *,
                   heldout_per_class: int = claims.HELDOUT_PER_CLASS,
                   ) -> tuple[list[Example], list[Example]]:
    """(train, heldout). The held-out set is the `heldout_per_class` positives
    and `heldout_per_class` negatives whose candidate-id hash sorts last --
    deterministic and order-independent. Raises if a class cannot spare the
    held-out margin and still leave something to train on."""
    pos = sorted((e for e in examples if e.label == 1),
                 key=lambda e: _heldout_rank(e.candidate_id, category))
    neg = sorted((e for e in examples if e.label == 0),
                 key=lambda e: _heldout_rank(e.candidate_id, category))
    for name, pool in (("positive", pos), ("negative", neg)):
        if len(pool) <= heldout_per_class:
            raise FeatureError(
                f"{category}: {len(pool)} {name} examples, need more than "
                f"{heldout_per_class} to carve a held-out set and still train.")
    heldout = pos[-heldout_per_class:] + neg[-heldout_per_class:]
    heldout_ids = {e.candidate_id for e in heldout}
    train = [e for e in examples if e.candidate_id not in heldout_ids]
    return train, heldout


def corpus_cutoff(examples: list[Example]) -> str:
    """The corpus snapshot: the latest `decided_at` across the examples. Empty
    string only if nothing is dated (a fixture)."""
    return max((e.decided_at for e in examples if e.decided_at), default="")


_PREDICT_POP_SQL = """
SELECT dc.document_chunk_id AS document_chunk_id,
       dc.text              AS text,
       em.embedding         AS embedding
FROM document_chunks dc
JOIN document_embeddings em
  ON em.document_chunk_id = dc.document_chunk_id AND em.model_key = ?
WHERE dc.superseded = 0
ORDER BY dc.document_chunk_id
"""


@dataclass(frozen=True)
class PopulationRow:
    chunk_id: str
    text: str
    embedding: bytes


def predict_population(conn, *, embedder_model_key: str) -> list[PopulationRow]:
    """Every live chunk that has an embedding under `embedder_model_key`. The
    prediction target is the same for both model types, so the logreg and
    SetFit heads of a category score an identical population."""
    return [PopulationRow(r["document_chunk_id"], r["text"] or "", r["embedding"])
            for r in conn.execute(_PREDICT_POP_SQL, (embedder_model_key,)).fetchall()]


def _deterministic_sample(rows: list[PopulationRow], *, tag: str, n: int,
                          exclude: set[str]) -> list[PopulationRow]:
    """The `n` rows whose `HELDOUT_SEED|tag|chunk_id` hash sorts first, after
    dropping `exclude`. Stable across machines and re-runs; a different `tag`
    gives a disjoint draw from the same pool."""
    pool = [r for r in rows if r.chunk_id not in exclude]
    pool.sort(key=lambda r: hashlib.sha256(
        f"{claims.HELDOUT_SEED}|{tag}|{r.chunk_id}".encode("utf-8")).hexdigest())
    return pool[:n]


def corpus_negatives(conn, category: str, *, embedder_model_key: str, n: int,
                     exclude: set[str]) -> list[Example]:
    """`n` random unlabelled chunks as synthetic negatives for `category`, so
    the head learns "affirmed claim vs the whole corpus" rather than the
    review-queue artefact. `exclude` is every chunk that is already a
    reviewer-labelled example (any split). A sampled chunk is assumed
    non-affirming -- true well over 99% of the time at these base rates."""
    rows = predict_population(conn, embedder_model_key=embedder_model_key)
    sample = _deterministic_sample(rows, tag=f"corpusneg|{category}", n=n, exclude=exclude)
    return [Example(candidate_id=f"corpusneg:{p.chunk_id}", chunk_id=p.chunk_id,
                    text=p.text, label=0, decided_at="", embedding=p.embedding)
            for p in sample]


def base_rate_sample(conn, category: str, *, embedder_model_key: str, n: int,
                     exclude: set[str]) -> list[PopulationRow]:
    """`n` random unlabelled chunks to measure a trained head's corpus-wide
    predicted-positive rate on. Drawn with a different tag from
    `corpus_negatives`, so the base-rate check is never run on chunks the
    head trained on."""
    rows = predict_population(conn, embedder_model_key=embedder_model_key)
    return _deterministic_sample(rows, tag=f"baserate|{category}", n=n, exclude=exclude)
