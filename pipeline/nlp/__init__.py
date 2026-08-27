"""Semantic-analysis layer: `document_elements` -> retrieval- and
analysis-ready records.

A DOWNSTREAM, non-collecting stage, the same shape as `pipeline/documents/`
and `pipeline/graph/`: it reads the parser-neutral document model, fetches
nothing, and calls no paid AI service. Everything it writes is a finding aid
or a machine candidate — nothing is attributed to a provider or promoted to
a claim without a person, which is the existing review queue -> `graph_claims`
path (migration 0050).

Tranche 034A (this cut): `runs` (per-invocation provenance), `models` (the
resolved model registry), and `chunk` (content-derived paragraph units over
`document_elements`). Embeddings, hybrid search, span/assertion/relation
extraction and topic clustering land in later tranches — see
`docs/semantic-analysis.md`.
"""
