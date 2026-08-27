-- Semantic-analysis layer (pipeline/nlp), tranche 034E: assertion / context
-- detection.
--
-- 034D found labelled spans. This says, for each one, whether its sentence
-- AFFIRMS the concept, NEGATES it, places it in the past (HISTORICAL), makes
-- it conditional or hypothetical, or attributes it to a THIRD_PARTY -- so
-- "no recruitment difficulties this year" is not stored as the same fact as
-- "recruitment difficulties remain a significant risk".
--
-- Two columns kept deliberately separate:
--
--   assertion_status     the class. UNKNOWN only when context genuinely
--                        cannot be classified -- never a default.
--   detector_confidence  how sure the detector is of THAT class. The rule
--                        tagger can emit NEGATED at 0.7; a low number does
--                        not mean "probably AFFIRMED", it means "this
--                        NEGATED call is soft".
--
-- The detector is a stdlib cue tagger (always on) or medSpaCy ConText where
-- that optional path is installed. cue_start / cue_end / sentence_sha256
-- pin exactly which words drove the call, against the sentence text hashed
-- at detection time. document_chunks.preceding_heading_element_id (migration
-- 0065) is already in place for section-aware context ("Risks" vs "Actions
-- completed") to be added later without a migration.

CREATE TABLE IF NOT EXISTS document_assertions (
    document_assertion_id  TEXT PRIMARY KEY,   -- sha256(concept_mention_id | detector_name | detector_version)
    document_chunk_id       TEXT NOT NULL REFERENCES document_chunks(document_chunk_id),
    concept_mention_id      TEXT REFERENCES document_concept_mentions(document_concept_mention_id),
    entity_mention_id       TEXT REFERENCES document_entity_mentions(document_entity_mention_id),
    assertion_status        TEXT NOT NULL,     -- AFFIRMED | NEGATED | HISTORICAL | HYPOTHETICAL | CONDITIONAL | THIRD_PARTY | UNKNOWN
    detector_name           TEXT NOT NULL,     -- 'cue-tagger' | 'medspacy-context'
    detector_version        TEXT NOT NULL,
    detector_confidence     REAL,
    cue_text                TEXT,              -- the words that drove the call; NULL for a bare AFFIRMED
    cue_start               INTEGER,           -- offset into the sentence
    cue_end                 INTEGER,
    sentence_sha256         TEXT NOT NULL,     -- the sentence as seen by the detector
    superseded              INTEGER NOT NULL DEFAULT 0,
    nlp_run_id              TEXT REFERENCES nlp_runs(run_id),
    created_at              TEXT NOT NULL,
    UNIQUE (concept_mention_id, detector_name, detector_version)
);

CREATE INDEX IF NOT EXISTS idx_document_assertions_chunk
    ON document_assertions (document_chunk_id) WHERE superseded = 0;
CREATE INDEX IF NOT EXISTS idx_document_assertions_status
    ON document_assertions (assertion_status);
