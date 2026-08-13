-- Items the pipeline answered for itself, and what answered them.
--
-- `review_queue` holds questions the pipeline could not settle. Almost all of
-- them need a person. A few do not: they were filed because the pipeline was
-- missing something it has since gone and got, and once it has it the question
-- is not a judgement any more — it is just stale.
--
-- The case that forced this: 1,067 `pfd_concerns_in_pdf_only` items, filed
-- when m08 could only read the metadata stub and the coroner's concerns were
-- in a PDF nobody had fetched. m08 now reads those PDFs, and 459 of the 1,067
-- reports have their concerns in the warehouse. The items stayed pending
-- regardless, because `record_review_item` refreshes a pending item and
-- nothing ever resolved one. A queue whose bulk is questions already answered
-- is a queue people stop reading.
--
-- This is deliberately NOT `review_decisions`:
--
--   * That table records what a *person* decided, and its `decided_by` is
--     NOT NULL because an audit row whose author is a guess is worse than no
--     audit row. Writing "pipeline" into it would make the one column that
--     means "a human looked at this" stop meaning that.
--
--   * Its `decision` is approved / rejected / pending. "Answered" is none of
--     those. Nobody approved anything; the question stopped being a question.
--
-- So `review_queue.status` gains the value 'answered', and every transition to
-- it is recorded here with the rule that made it and the evidence that
-- justified it. Reversible: resetting an item to pending is a row in
-- `review_decisions` like any other reset, and the sweep will not touch an
-- item a person has decided.
CREATE TABLE IF NOT EXISTS review_resolutions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    review_item_id  INTEGER NOT NULL REFERENCES review_queue (id) ON DELETE CASCADE,
    -- Which rule fired, by name, so a resolution can be traced to the code
    -- that made it and undone in bulk if that code was wrong.
    rule            TEXT NOT NULL,
    -- What made it answerable, in the words a person would use. Not a code:
    -- this is read by whoever is wondering why an item left their queue.
    evidence        TEXT NOT NULL,
    status_before   TEXT NOT NULL,
    resolved_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_review_resolutions_item
    ON review_resolutions (review_item_id);

-- "What did the last sweep close, and under which rule?"
CREATE INDEX IF NOT EXISTS idx_review_resolutions_rule
    ON review_resolutions (rule, resolved_at DESC);
