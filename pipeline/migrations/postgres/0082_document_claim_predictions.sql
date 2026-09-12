-- Semantic-analysis layer (pipeline/nlp), tranche 034G: trained
-- claim-prediction heads and the predictions they write.
--
-- PostgreSQL dialect of ../0082_document_claim_predictions.sql. See
-- README.md in this directory for the conversion rules.
--
-- One BINARY classifier head per gate category the 034G readiness gate
-- reports `ready`. Two tables, and the discipline is 034C topics' and the
-- deferred 034H BERTopic run's: a prediction is a FINDING AID, never a
-- claim -- not evidence, not attributed to a provider, not promoted, not
-- exported, not portal-reachable, no graph_claims write, no review-queue
-- reorder. The build spec is docs/claim-predictions-spec.md.
--
--   claim_head_versions        one row per trained head (both the logreg and
--                              the SetFit head of every category's bake-off,
--                              with held-out precision / recall / F1 and a
--                              status of 'passed' / 'quarantined' /
--                              'lost-bakeoff'); selected = 1 marks the one
--                              head per category allowed to write
--                              predictions. Carries the composite
--                              model_version, the full config hash, the
--                              labelling corpus and its snapshot cutoff, and
--                              the exact held-out candidate ids.
--   document_claim_predictions one row per (chunk, category) from a selected
--                              head: label 0/1, score, and a split of
--                              'train' / 'heldout' / 'unlabelled'.
--
-- CAVEAT (travels with any figure a prediction supports): single-reviewer
-- corpus, per-class floor 25 (thin), model-triage-assisted labels, and --
-- until the source re-run -- the non-authoritative beta-box copy
-- (corpus_status = 'experimental'). See docs/CAVEATS.md.

CREATE TABLE IF NOT EXISTS claim_head_versions (
    model_version              text PRIMARY KEY,
    category                   text NOT NULL,
    predicate                  text NOT NULL,
    model_type                 text NOT NULL,

    embedder_model_key         text REFERENCES nlp_model_registry(model_key),
    setfit_base_model          text,
    config_sha256              text NOT NULL,

    corpus                     text NOT NULL,
    corpus_cutoff              text NOT NULL,
    corpus_status              text NOT NULL,
    heldout_candidate_ids_json text NOT NULL,

    n_train_pos                bigint NOT NULL,
    n_train_neg                bigint NOT NULL,
    n_corpus_neg               bigint NOT NULL DEFAULT 0,
    n_heldout_pos              bigint NOT NULL,
    n_heldout_neg              bigint NOT NULL,
    heldout_precision          double precision NOT NULL,
    heldout_recall             double precision NOT NULL,
    heldout_f1                 double precision NOT NULL,
    min_precision              double precision NOT NULL,
    positive_rate              double precision,
    max_positive_rate          double precision NOT NULL DEFAULT 1.0,
    status                     text NOT NULL,
    selected                   bigint NOT NULL DEFAULT 0,

    artifact_path              text,
    artifact_sha256            text,

    code_commit                text,
    nlp_run_id                 text NOT NULL REFERENCES nlp_runs(run_id),
    trained_at                 text NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_claim_head_selected_one_per_category
    ON claim_head_versions (category) WHERE selected = 1;
CREATE INDEX IF NOT EXISTS idx_claim_head_versions_category
    ON claim_head_versions (category, trained_at);

CREATE TABLE IF NOT EXISTS document_claim_predictions (
    document_chunk_id text NOT NULL REFERENCES document_chunks(document_chunk_id),
    category          text NOT NULL,
    model_version     text NOT NULL REFERENCES claim_head_versions(model_version),
    label             bigint NOT NULL,
    score             double precision NOT NULL,
    split             text NOT NULL DEFAULT 'unlabelled',
    nlp_run_id        text NOT NULL REFERENCES nlp_runs(run_id),
    created_at        text NOT NULL,
    PRIMARY KEY (document_chunk_id, category, model_version)
);

CREATE INDEX IF NOT EXISTS idx_claim_predictions_lookup
    ON document_claim_predictions (category, model_version, label);
