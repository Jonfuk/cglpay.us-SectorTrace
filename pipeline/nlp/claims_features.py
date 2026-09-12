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
from pipeline.nlp.embedding_repository import PostgresEmbeddingRepository
from pipeline.nlp.gate import GATE_CATEGORIES, _label_for

# Latest decision per candidate wins. A candidate can carry more than one
# decision row -- a reviewer correcting themselves, or a second reviewer on a
# double-reviewed item. The gate counts every decision row; for a training
# label we take the most recent one per candidate as authoritative, then run
# it through `gate._label_for`. A candidate the latest decision leaves
# unlabelled for this category (e.g. approved for a different predicate) is
# simply not an example for this category.
_DECIDED_PAGE_SQL = """
SELECT * FROM (
SELECT DISTINCT ON (c.claim_candidate_id)
       c.claim_candidate_id      AS claim_candidate_id,
       c.document_chunk_id       AS document_chunk_id,
       c.predicate               AS predicate,
       c.assertion_status        AS assertion_status,
       d.decision                AS decision,
       d.corrected_predicate     AS corrected_predicate,
       d.decided_at              AS decided_at,
       dc.text                   AS text
FROM claim_candidate_decisions d
JOIN document_claim_candidates c ON c.claim_candidate_id = d.claim_candidate_id
JOIN document_chunks dc ON dc.document_chunk_id = c.document_chunk_id
WHERE c.claim_candidate_id > %s
ORDER BY c.claim_candidate_id, d.decided_at DESC, d.id DESC
) latest
ORDER BY claim_candidate_id
LIMIT %s
"""

_READ_PAGE_SIZE = 2000


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

    examples: list[Example] = []
    after = ""
    repository = PostgresEmbeddingRepository(conn)
    while True:
        page = conn.execute(_DECIDED_PAGE_SQL, (after, _READ_PAGE_SIZE)).fetchall()
        if not page:
            break
        vectors = repository.vectors_for_chunks(
            embedder_model_key, sorted({row["document_chunk_id"] for row in page}))
        for row in page:
            label = _label_for(row, predicate)
            if label is None:
                continue
            examples.append(Example(
                candidate_id=row["claim_candidate_id"],
                chunk_id=row["document_chunk_id"], text=row["text"] or "",
                label=1 if label == "positive" else 0, decided_at=row["decided_at"] or "",
                embedding=vectors.get(row["document_chunk_id"])))
        after = page[-1]["claim_candidate_id"]
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


@dataclass(frozen=True)
class PopulationRow:
    chunk_id: str
    text: str
    embedding: bytes


def predict_population(conn, *, embedder_model_key: str) -> list[PopulationRow]:
    """Every live chunk that has an embedding under `embedder_model_key`. The
    prediction target is the same for both model types, so the logreg and
    SetFit heads of a category score an identical population."""
    return [PopulationRow(chunk_id, text, vector) for chunk_id, text, vector
            in PostgresEmbeddingRepository(conn).population(embedder_model_key)]


def _deterministic_sample(rows: list[PopulationRow], *, tag: str, n: int,
                          exclude: set[str]) -> list[PopulationRow]:
    """The `n` rows whose `HELDOUT_SEED|tag|chunk_id` hash sorts first, after
    dropping `exclude`. Stable across machines and re-runs; a different `tag`
    gives a disjoint draw from the same pool."""
    pool = [r for r in rows if r.chunk_id not in exclude]
    pool.sort(key=lambda r: hashlib.sha256(
        f"{claims.HELDOUT_SEED}|{tag}|{r.chunk_id}".encode("utf-8")).hexdigest())
    return pool[:n]


def _deterministic_population_sample(conn, *, embedder_model_key: str, tag: str,
                                     n: int, exclude: set[str]) -> list[PopulationRow]:
    """Stable hash sample while retaining only ``n + page_size`` rows.

    Classifier training needs a deterministic corpus sample, not a complete
    in-memory corpus.  Each repository page is merged into the current best
    ``n`` hashes, preserving the exact result of a full sort.
    """
    if n <= 0:
        return []
    selected: list[tuple[str, PopulationRow]] = []
    repository = PostgresEmbeddingRepository(conn)
    for page in repository.iter_population(embedder_model_key, page_size=_READ_PAGE_SIZE):
        selected.extend(
            (hashlib.sha256(
                f"{claims.HELDOUT_SEED}|{tag}|{chunk_id}".encode("utf-8")
             ).hexdigest(), PopulationRow(chunk_id, text, vector))
            for chunk_id, text, vector in page if chunk_id not in exclude)
        selected.sort(key=lambda item: item[0])
        del selected[n:]
    return [row for _, row in selected]


def corpus_negatives(conn, category: str, *, embedder_model_key: str, n: int,
                     exclude: set[str]) -> list[Example]:
    """`n` random unlabelled chunks as synthetic negatives for `category`, so
    the head learns "affirmed claim vs the whole corpus" rather than the
    review-queue artefact. `exclude` is every chunk that is already a
    reviewer-labelled example (any split). A sampled chunk is assumed
    non-affirming -- true well over 99% of the time at these base rates."""
    sample = _deterministic_population_sample(
        conn, embedder_model_key=embedder_model_key,
        tag=f"corpusneg|{category}", n=n, exclude=exclude)
    return [Example(candidate_id=f"corpusneg:{p.chunk_id}", chunk_id=p.chunk_id,
                    text=p.text, label=0, decided_at="", embedding=p.embedding)
            for p in sample]


def base_rate_sample(conn, category: str, *, embedder_model_key: str, n: int,
                     exclude: set[str]) -> list[PopulationRow]:
    """`n` random unlabelled chunks to measure a trained head's corpus-wide
    predicted-positive rate on. Drawn with a different tag from
    `corpus_negatives`, so the base-rate check is never run on chunks the
    head trained on."""
    return _deterministic_population_sample(
        conn, embedder_model_key=embedder_model_key,
        tag=f"baserate|{category}", n=n, exclude=exclude)
