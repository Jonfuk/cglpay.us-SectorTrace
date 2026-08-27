-- Semantic-analysis layer (pipeline/nlp), tranche 034E: assertion / context
-- detection.
--
-- PostgreSQL dialect of ../0067_document_assertions.sql. See README.md in
-- this directory for the conversion rules. TEXT -> text, INTEGER -> bigint,
-- REAL -> double precision; everything else is identical.
--
-- assertion_status and detector_confidence are separate on purpose:
-- UNKNOWN is only for context that genuinely cannot be classified, and a low
-- confidence on a NEGATED call does not mean "probably AFFIRMED".

CREATE TABLE IF NOT EXISTS document_assertions (
    document_assertion_id  text PRIMARY KEY,
    document_chunk_id       text NOT NULL REFERENCES document_chunks(document_chunk_id),
    concept_mention_id      text REFERENCES document_concept_mentions(document_concept_mention_id),
    entity_mention_id       text REFERENCES document_entity_mentions(document_entity_mention_id),
    assertion_status        text NOT NULL,
    detector_name           text NOT NULL,
    detector_version        text NOT NULL,
    detector_confidence     double precision,
    cue_text                text,
    cue_start               bigint,
    cue_end                 bigint,
    sentence_sha256         text NOT NULL,
    superseded              bigint NOT NULL DEFAULT 0,
    nlp_run_id              text REFERENCES nlp_runs(run_id),
    created_at              text NOT NULL,
    UNIQUE (concept_mention_id, detector_name, detector_version)
);

CREATE INDEX IF NOT EXISTS idx_document_assertions_chunk
    ON document_assertions (document_chunk_id) WHERE superseded = 0;
CREATE INDEX IF NOT EXISTS idx_document_assertions_status
    ON document_assertions (assertion_status);
