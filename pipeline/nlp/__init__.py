"""Semantic-analysis layer: `document_elements` -> retrieval- and
analysis-ready records.

A DOWNSTREAM, non-collecting stage, the same shape as `pipeline/documents/`
and `pipeline/graph/`: it reads the parser-neutral document model, fetches
nothing, and calls no paid AI service. Everything it writes is a finding aid
or a machine candidate — nothing is attributed to a provider or promoted to
a claim without a person, which is the existing review queue -> `graph_claims`
path (migration 0050).

Tranche 034A: `runs` (per-invocation provenance), `models` (the resolved
model registry), `chunk` (content-derived paragraph units over
`document_elements`), `embeddings` (a deterministic offline stub or a
sentence-transformers model behind the `nlp` extra), `semantic_search`
(keyword / semantic / hybrid retrieval over chunks, RRF-fused) and `eval`
(the retrieval-metrics harness that gates changing the embedding model).

Tranche 034B: `ontology` — the SectorTrace controlled vocabulary
(`ontology/concepts.yml`, `relations.yml`, `patterns/*.yml`), loaded,
validated and content-versioned into `ontology_version`. Stdlib + PyYAML
only; 034C's classifier consumes it and is always-on.

GLiNER entity spans, assertion / context detection, relation-pattern claim
candidates and topic clustering land in later tranches — see
`docs/semantic-analysis.md`.
"""
