-- Constraint 5 (idempotent re-runs) applied to the audit tables.
--
-- review_queue and parse_failures were plain INSERTs, so every re-run
-- appended another copy of the same unresolved item. That inflates the
-- counts reported at each build stage and makes "how many items need
-- review?" unanswerable — the exact opposite of what these tables are for.
--
-- Dedupe existing rows first (keeping the earliest, which preserves the
-- original created_at), then enforce uniqueness going forward.
--
-- PostgreSQL dialect of ../0007_dedupe_audit_tables.sql. Hand-written because
-- of the expression index below, which is the one construct in this tree
-- where the two dialects have to agree character for character.
--
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

-- The expression index behind `db.record_parse_failure`'s upsert.
--
-- Written *identically* to the `ON CONFLICT` target in that function, because
-- PostgreSQL infers which index an `ON CONFLICT (expr, ...)` clause means by
-- matching the expressions, and an inference that fails is not a silent
-- fallback — it is `there is no unique or exclusion constraint matching the
-- ON CONFLICT specification` at runtime, on the first parse failure of a
-- crawl that has already made its requests.
--
-- So: if you change one, change the other. The two live in different files
-- and `tests/test_db.py` pins that they still agree.
--
-- The COALESCE is not decoration. `''` and NULL are distinct values in a
-- unique index on both engines, so without the fold, two parse failures that
-- differ only in a NULL vs empty `field_name` would both be stored — which is
-- the duplicate this migration exists to prevent.
CREATE UNIQUE INDEX IF NOT EXISTS idx_parse_failures_natural
    ON parse_failures (module, COALESCE(source_url, ''), COALESCE(field_name, ''), COALESCE(raw_fragment, ''));
