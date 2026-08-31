-- Semantic-analysis layer (pipeline/nlp), tranche 034G: trained
-- claim-prediction heads and the predictions they write.
--
-- The 034G readiness gate (pipeline/nlp/gate.py) is green on the beta box:
-- vacancy_pressure, agency_reliance and tupe_transfer each clear the
-- per-class floor, the quorum (MIN_CATEGORIES_READY = 3) is met, and the
-- inter-reviewer check is advisory by owner decision (single-reviewer
-- corpus, caveated in docs/CAVEATS.md). This migration is the store for
-- what the gate unlocks -- one BINARY classifier head per ready category,
-- and the predictions a passing head writes over the embedded corpus. The
-- full build spec is docs/claim-predictions-spec.md.
--
-- Two tables, and the discipline is the one 034C topics and the deferred
-- 034H BERTopic run share: a prediction is a FINDING AID, never a claim.
-- Neither table is evidence, neither is attributed to a provider, neither
-- is promoted, neither is exported, neither is portal-reachable. There is
-- NO graph_claims write here -- that writer is still its own held decision
-- (pipeline/nlp/decisions.py). A prediction never reorders the review
-- queue (that is 034H active learning, also deferred).
--
--   claim_head_versions        one row per trained head. Both models in the
--                              per-category bake-off -- a pure-Python
--                              logistic regression on the 034A chunk
--                              embeddings, and SetFit -- get a row carrying
--                              their held-out precision / recall / F1 and a
--                              status of 'passed' / 'quarantined'
--                              (held-out precision below the bar) /
--                              'lost-bakeoff' (cleared the bar, lost on
--                              precision). selected = 1 marks the single
--                              head per category that is allowed to write
--                              predictions. Versioned the way nlp_runs
--                              versions an annotation: the composite
--                              model_version, the full config hash, the
--                              corpus the labels came from and that
--                              corpus's snapshot cutoff, and the exact
--                              held-out candidate ids, are all on the row,
--                              so "why does this prediction exist, under
--                              what model, trained on which corpus
--                              snapshot" is a two-join query.
--
--   document_claim_predictions one row per (chunk, category) scored by a
--                              selected head. label 0/1, score the head's
--                              confidence for label 1, split records
--                              whether the chunk was in the fit
--                              ('train' / 'heldout') or not ('unlabelled').
--                              Points back to the head via model_version
--                              and to the predict run via nlp_run_id.
--
-- model_version format: '<model_type>-<category>-<corpus_cutoff>-<hash8>',
-- e.g. 'logreg-vacancy_pressure-20260831-a1b2c3d4'. Human-readable, sorts
-- sensibly, unique per (model, category, corpus snapshot, config). hash8 is
-- the first eight chars of config_sha256 (hyperparams + embedder id +
-- held-out seed + corpus cutoff).
--
-- CAVEAT (travels with any figure a prediction ever supports): the training
-- corpus is single-reviewer, the per-class floor is 25 (thin -- few-shot's
-- own premise), the labels are model-triage-assisted, and -- until the
-- review loop is redone on the authoritative source warehouse -- the corpus
-- is the non-authoritative beta-box copy. corpus_status = 'experimental'
-- records the last of these on every head; see docs/CAVEATS.md.

CREATE TABLE IF NOT EXISTS claim_head_versions (
    model_version              TEXT PRIMARY KEY,
    category                   TEXT NOT NULL,      -- a gate.GATE_CATEGORIES key
    predicate                  TEXT NOT NULL,      -- its relations.yml predicate, denormalised for query
    model_type                 TEXT NOT NULL,      -- 'logreg' | 'setfit'

    embedder_model_key         TEXT REFERENCES nlp_model_registry(model_key),  -- logreg: the 034A embedder; setfit: NULL (carries its own body)
    setfit_base_model          TEXT,              -- setfit: HF id + resolved revision; logreg: NULL
    config_sha256              TEXT NOT NULL,      -- hyperparams + embedder id + held-out seed + corpus cutoff

    corpus                     TEXT NOT NULL,      -- 'beta-box' | 'source'
    corpus_cutoff              TEXT NOT NULL,      -- max(decided_at) over the training + held-out decisions
    corpus_status              TEXT NOT NULL,      -- 'experimental' | 'authoritative'
    heldout_candidate_ids_json TEXT NOT NULL,      -- JSON array of claim_candidate_id, the deterministic carve

    n_train_pos                INTEGER NOT NULL,
    n_train_neg                INTEGER NOT NULL,
    n_heldout_pos              INTEGER NOT NULL,
    n_heldout_neg              INTEGER NOT NULL,
    heldout_precision          REAL NOT NULL,
    heldout_recall             REAL NOT NULL,
    heldout_f1                 REAL NOT NULL,
    min_precision              REAL NOT NULL,      -- the bar this run applied (default 0.80, --min-precision override)
    status                     TEXT NOT NULL,      -- 'passed' | 'quarantined' | 'lost-bakeoff'
    selected                   INTEGER NOT NULL DEFAULT 0,

    artifact_path              TEXT,               -- nlp-cache/claims/... ; NULL only for an inline logreg blob
    artifact_sha256            TEXT,               -- verified on load by claims_predict; a mismatch refuses the run

    code_commit                TEXT,               -- git revision at train time, or NULL
    nlp_run_id                 TEXT NOT NULL REFERENCES nlp_runs(run_id),   -- the train run
    trained_at                 TEXT NOT NULL
);

-- At most one live head per category. A re-run clears the prior selection
-- for the category and sets this one; the partial unique index makes a
-- double-selection a write error, not a silent ambiguity for claims_predict.
CREATE UNIQUE INDEX IF NOT EXISTS idx_claim_head_selected_one_per_category
    ON claim_head_versions (category) WHERE selected = 1;
CREATE INDEX IF NOT EXISTS idx_claim_head_versions_category
    ON claim_head_versions (category, trained_at);

CREATE TABLE IF NOT EXISTS document_claim_predictions (
    document_chunk_id TEXT NOT NULL REFERENCES document_chunks(document_chunk_id),
    category          TEXT NOT NULL,
    model_version     TEXT NOT NULL REFERENCES claim_head_versions(model_version),
    label             INTEGER NOT NULL,   -- 0 | 1
    score             REAL NOT NULL,      -- head confidence for label = 1, [0, 1]
    split             TEXT NOT NULL DEFAULT 'unlabelled',   -- 'train' | 'heldout' | 'unlabelled'
    nlp_run_id        TEXT NOT NULL REFERENCES nlp_runs(run_id),   -- the predict run, distinct from the train run
    created_at        TEXT NOT NULL,
    PRIMARY KEY (document_chunk_id, category, model_version)
);

CREATE INDEX IF NOT EXISTS idx_claim_predictions_lookup
    ON document_claim_predictions (category, model_version, label);
