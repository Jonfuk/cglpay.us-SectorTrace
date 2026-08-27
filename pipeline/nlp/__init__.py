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
only.

Tranche 034C: `label` — the deterministic ontology classifier. Runs the
034B matcher over chunked elements and writes provisional `document_topics`
rows with `match_method='ontology_v1'` (concept ids and `cat:` categories),
never touching the frozen `keyword_v1` vocabulary.

Tranche 034D: `spans` — span-level entity extraction into
`document_concept_mentions` (migration 0066). An offline dictionary-backed
stub or GLiNER behind the `nlp` extra; label set is entities only. `resolve`
— the separate deterministic step that turns a PROVIDER / COMMISSIONER span
into a `document_entity_mentions` row on an exact name match, and only then.
Neither ever writes `entity_id` from a model.

Tranche 034E: `context` — assertion / context detection into
`document_assertions` (migration 0067). An always-on stdlib cue tagger, or
medSpaCy `ConText` where that optional path is installed. This is what tells
"no recruitment difficulties" from "recruitment difficulties remain".
`assertion_status` and `detector_confidence` are stored separately.

Relation-pattern claim candidates and topic clustering land in later
tranches — see `docs/semantic-analysis.md`.
"""
