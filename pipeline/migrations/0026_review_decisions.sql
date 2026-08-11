-- A record of every human decision taken on a review-queue item.
--
-- `review_queue.status` has always been the *current* state of an item, and
-- until now nothing ever moved it off 'pending': the queue was written by
-- modules and read by people, with the deciding done in someone's head. The
-- reviewer UI (pipeline/web/) writes decisions back, so the queue has to be
-- able to say who decided what, when, and on what basis. A status column
-- alone cannot.
--
-- Two things live here that `review_queue` has nowhere to put:
--
--   * History. An item can go pending -> approved -> pending -> rejected; a
--     decision taken in error is revertible, and the revert is itself a
--     decision worth keeping. Only the latest state lands on
--     `review_queue.status`, and every step is a row here.
--
--   * The context as it read at the time. `record_review_item()` refreshes
--     `context_json` whenever a module re-observes a *pending* item, so an
--     item reverted to pending and then re-run can have its context rewritten
--     underneath a decision that was already taken against the old text. The
--     snapshot is what the reviewer was actually looking at.
--
-- Deciding is deliberately NOT promotion. Nothing here moves a value into a
-- canonical table: what "approved" means for an unmatched buyer name (bind it
-- to an authority) and for a PFD report whose concerns are PDF-only (nothing —
-- it is an acknowledgement) are different operations, and neither exists yet.
-- This table records the judgement so that acting on it is not also the work
-- of remembering it. See README "Reviewing what a run produced".
CREATE TABLE IF NOT EXISTS review_decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    review_item_id  INTEGER NOT NULL REFERENCES review_queue (id) ON DELETE CASCADE,
    -- 'pending' is a decision too: it is the revert, and it is recorded rather
    -- than being an untracked way back to the starting state.
    decision        TEXT NOT NULL CHECK (decision IN ('approved', 'rejected', 'pending')),
    status_before   TEXT NOT NULL,
    note            TEXT,
    -- Never defaulted or inferred. The UI asks who is reviewing and sends it;
    -- an audit row whose author is a guess is worse than no audit row.
    decided_by      TEXT NOT NULL,
    decided_at      TEXT NOT NULL,
    context_json    TEXT
);

CREATE INDEX IF NOT EXISTS idx_review_decisions_item
    ON review_decisions (review_item_id, decided_at);

-- "What has been decided lately", which is the only cheap way to answer
-- "did I already look at this batch?" after closing the browser.
CREATE INDEX IF NOT EXISTS idx_review_decisions_decided_at
    ON review_decisions (decided_at DESC);

-- The queue is filtered by status on every screen of the reviewer and grouped
-- by (module, item_type) on its overview. Without this, each of those is a
-- full scan of a table that is already in the thousands of rows and only
-- grows: the existing unique index leads with `module`, so it cannot serve a
-- status filter.
CREATE INDEX IF NOT EXISTS idx_review_queue_status
    ON review_queue (status, module, item_type);
