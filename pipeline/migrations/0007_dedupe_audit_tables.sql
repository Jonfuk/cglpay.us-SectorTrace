-- Constraint 5 (idempotent re-runs) applied to the audit tables.
--
-- review_queue and parse_failures were plain INSERTs, so every re-run
-- appended another copy of the same unresolved item. That inflates the
-- counts reported at each build stage and makes "how many items need
-- review?" unanswerable — the exact opposite of what these tables are for.
--
-- Dedupe existing rows first (keeping the earliest, which preserves the
-- original created_at), then enforce uniqueness going forward.

DELETE FROM review_queue
WHERE id NOT IN (
    SELECT MIN(id) FROM review_queue
    GROUP BY module, item_type, raw_value
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_review_queue_natural
    ON review_queue (module, item_type, raw_value);

DELETE FROM parse_failures
WHERE id NOT IN (
    SELECT MIN(id) FROM parse_failures
    GROUP BY module, COALESCE(source_url, ''), COALESCE(field_name, ''), COALESCE(raw_fragment, '')
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_parse_failures_natural
    ON parse_failures (module, COALESCE(source_url, ''), COALESCE(field_name, ''), COALESCE(raw_fragment, ''));
