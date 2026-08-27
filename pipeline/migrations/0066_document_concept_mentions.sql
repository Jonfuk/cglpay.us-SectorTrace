-- Semantic-analysis layer (pipeline/nlp), tranche 034D: span-level entity
-- mentions.
--
-- 034C wrote element-level ontology topic *counts* (document_topics,
-- match_method='ontology_v1'). 034D writes span-level *mentions*: a labelled
-- character range inside a chunk, with the offsets 034E's assertion detector
-- and 034F's relation extractor need.
--
-- The extractor is GLiNER (zero-shot, CPU, behind the `nlp` extra) or an
-- offline ontology-backed stub for CI. Its label set is ENTITIES ONLY:
-- PROVIDER, COMMISSIONER, SERVICE, SUBSTANCE, TREATMENT, ROLE, LOCATION,
-- PROGRAMME. Abstract situations (workforce pressure, funding pressure, …)
-- are 034C's ontology layer and 034G's classifiers, never a span label.
--
-- Two hard rules carried in the shape of this table:
--
--   * extraction_score is the extractor's own token->label confidence, and
--     is named so it cannot be read as P(the statement is true). 1.0 means
--     "exact dictionary hit", not "certainly correct".
--   * concept_id is nullable and this table NEVER carries entity_id.
--     Resolving a PROVIDER/COMMISSIONER span to a registered entity is a
--     separate deterministic step (pipeline/nlp/resolve.py) that writes
--     document_entity_mentions. A model span is a candidate a person
--     confirms; it is not an attribution.

CREATE TABLE IF NOT EXISTS document_concept_mentions (
    document_concept_mention_id TEXT PRIMARY KEY,   -- sha256(chunk | extractor_name | extractor_version | char_start | char_end | label)
    document_chunk_id           TEXT NOT NULL REFERENCES document_chunks(document_chunk_id),
    document_element_id         TEXT REFERENCES document_elements(document_element_id),  -- the element the span starts in
    label                       TEXT NOT NULL,      -- PROVIDER | COMMISSIONER | SERVICE | SUBSTANCE | TREATMENT | ROLE | LOCATION | PROGRAMME
    concept_id                  TEXT,               -- an ontology concept id when the extractor could assign one; NULL for GLiNER's own spans
    span_text                   TEXT NOT NULL,
    char_start                  INTEGER NOT NULL,   -- offset into the chunk's text
    char_end                    INTEGER NOT NULL,
    element_char_start          INTEGER,            -- offset into that element's text, for the resolve step
    element_char_end            INTEGER,
    extractor_name              TEXT NOT NULL,      -- 'gliner' | 'ontology-stub'
    extractor_version           TEXT NOT NULL,
    extraction_score            REAL,               -- the extractor's token->label confidence; NOT P(true)
    superseded                  INTEGER NOT NULL DEFAULT 0,
    nlp_run_id                  TEXT REFERENCES nlp_runs(run_id),
    created_at                  TEXT NOT NULL,
    UNIQUE (document_chunk_id, extractor_name, extractor_version, char_start, char_end, label)
);

CREATE INDEX IF NOT EXISTS idx_document_concept_mentions_chunk
    ON document_concept_mentions (document_chunk_id) WHERE superseded = 0;
CREATE INDEX IF NOT EXISTS idx_document_concept_mentions_label
    ON document_concept_mentions (label, concept_id);
