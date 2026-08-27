-- Semantic-analysis layer (pipeline/nlp), tranche 034F: machine claim
-- candidates.
--
-- This is the HIGH-VOLUME layer. 034D found spans, 034E said whether each was
-- affirmed; 034F assembles (subject, predicate, object) triples from spans in
-- one sentence using the ontology's controlled predicate vocabulary
-- (relations.yml) plus pattern and proximity rules. Co-occurrence alone never
-- yields a candidate -- a predicate pattern or a controlled concept->predicate
-- mapping has to fire.
--
-- Millions of rows are fine here. document_claim_candidates is NOT evidence
-- and NOT a claim: a separate selection policy (pipeline/nlp/promote.py)
-- promotes a small slice into review_queue as
-- item_type='semantic_claim_candidate', and only a person deciding that item
-- produces a graph_claims draft (extractor in extractor_name, never
-- promoted_by -- the pipeline/ai_promotion.py rule; decision 4). Nothing here
-- is ever auto-promoted.
--
-- relation_score is the extractor's own score for the triple. Like
-- document_concept_mentions.extraction_score it is NOT P(the claim is true);
-- it ranks candidates for a reviewer's attention, nothing more, and is never
-- multiplied into a figure.
--
-- claim_candidate_decisions captures a reviewer's CORRECTION, not just an
-- approve/reject: a candidate whose predicate or object a person fixed is far
-- better training data than a binary reject. Its writer lands with the
-- review-decision integration (034F, second cut); the table ships now so the
-- shape is fixed.

CREATE TABLE IF NOT EXISTS document_claim_candidates (
    claim_candidate_id         TEXT PRIMARY KEY,   -- sha256(chunk | subject_mention | predicate | object | char_start | char_end | extractor)
    document_chunk_id          TEXT NOT NULL REFERENCES document_chunks(document_chunk_id),
    subject_mention_id         TEXT REFERENCES document_concept_mentions(document_concept_mention_id),
    subject_hint               TEXT,               -- e.g. 'the service' when the subject is an anaphor, not a span
    predicate                  TEXT NOT NULL,      -- a relation id from ontology/relations.yml
    object_concept_id          TEXT,               -- an ontology concept id when the object is a concept
    object_literal             TEXT,               -- the verbatim literal (money / count / date) when the object is one
    assertion_status           TEXT NOT NULL,      -- carried from document_assertions for the triggering span
    relation_extractor         TEXT NOT NULL,      -- 'nlp-rule' | 'gliner-rule' | ...
    relation_extractor_version TEXT NOT NULL,
    relation_score             REAL,               -- ranks candidates for review; NOT P(true)
    evidence_span              TEXT NOT NULL,      -- the sentence the triple was read from
    char_start                 INTEGER NOT NULL,   -- offset of evidence_span into the chunk text
    char_end                   INTEGER NOT NULL,
    status                     TEXT NOT NULL DEFAULT 'new',   -- new | queued | promoted | dismissed
    superseded                 INTEGER NOT NULL DEFAULT 0,
    nlp_run_id                 TEXT REFERENCES nlp_runs(run_id),
    created_at                 TEXT NOT NULL,
    UNIQUE (document_chunk_id, relation_extractor, relation_extractor_version, char_start, char_end, predicate, subject_mention_id, object_concept_id, object_literal)
);

CREATE INDEX IF NOT EXISTS idx_claim_candidates_status
    ON document_claim_candidates (status) WHERE superseded = 0;
CREATE INDEX IF NOT EXISTS idx_claim_candidates_predicate
    ON document_claim_candidates (predicate, assertion_status);
CREATE INDEX IF NOT EXISTS idx_claim_candidates_chunk
    ON document_claim_candidates (document_chunk_id);

CREATE TABLE IF NOT EXISTS claim_candidate_decisions (
    id                           INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_candidate_id           TEXT NOT NULL REFERENCES document_claim_candidates(claim_candidate_id),
    review_queue_id              INTEGER REFERENCES review_queue(id),
    decision                     TEXT NOT NULL,    -- approved | rejected | corrected
    decided_by                   TEXT NOT NULL,
    reason_code                  TEXT,
    corrected_subject_mention_id TEXT REFERENCES document_concept_mentions(document_concept_mention_id),
    corrected_predicate          TEXT,
    corrected_object_concept_id  TEXT,
    corrected_object_literal     TEXT,
    graph_claim_id               TEXT REFERENCES graph_claims(claim_id),   -- the draft this decision produced, when approved
    note                         TEXT,
    decided_at                   TEXT NOT NULL,
    UNIQUE (claim_candidate_id, decided_by, decided_at)
);

CREATE INDEX IF NOT EXISTS idx_claim_candidate_decisions_candidate
    ON claim_candidate_decisions (claim_candidate_id);
