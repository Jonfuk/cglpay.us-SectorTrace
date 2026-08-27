-- Semantic-analysis layer (pipeline/nlp), tranche 034D: span-level entity
-- mentions.
--
-- PostgreSQL dialect of ../0066_document_concept_mentions.sql. See README.md
-- in this directory for the conversion rules. TEXT -> text, INTEGER ->
-- bigint, REAL -> double precision; everything else is identical.
--
-- extraction_score is the extractor's own token->label confidence, named so
-- it cannot be read as P(the statement is true). concept_id is nullable and
-- this table NEVER carries entity_id: resolving a PROVIDER/COMMISSIONER span
-- to a registered entity is pipeline/nlp/resolve.py's job and writes
-- document_entity_mentions.

CREATE TABLE IF NOT EXISTS document_concept_mentions (
    document_concept_mention_id text PRIMARY KEY,
    document_chunk_id           text NOT NULL REFERENCES document_chunks(document_chunk_id),
    document_element_id         text REFERENCES document_elements(document_element_id),
    label                       text NOT NULL,
    concept_id                  text,
    span_text                   text NOT NULL,
    char_start                  bigint NOT NULL,
    char_end                    bigint NOT NULL,
    element_char_start          bigint,
    element_char_end            bigint,
    extractor_name              text NOT NULL,
    extractor_version           text NOT NULL,
    extraction_score            double precision,
    superseded                  bigint NOT NULL DEFAULT 0,
    nlp_run_id                  text REFERENCES nlp_runs(run_id),
    created_at                  text NOT NULL,
    UNIQUE (document_chunk_id, extractor_name, extractor_version, char_start, char_end, label)
);

CREATE INDEX IF NOT EXISTS idx_document_concept_mentions_chunk
    ON document_concept_mentions (document_chunk_id) WHERE superseded = 0;
CREATE INDEX IF NOT EXISTS idx_document_concept_mentions_label
    ON document_concept_mentions (label, concept_id);
