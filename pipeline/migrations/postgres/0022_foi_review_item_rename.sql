-- Retire a review-queue item type that Module 15 no longer emits.
--
-- `foi_wdtk_requests_not_retrievable` is superseded by
-- `foi_response_text_not_retrievable` (see 0021). The distinction is the
-- point: WhatDoTheyKnow requests *are* now discoverable via the search feed,
-- and it is specifically the response text that is not, because the JSON read
-- API still answers with a Cloudflare 403.
--
-- Without this, the old rows sit in `review_queue` forever. Nothing updates
-- them, because `record_review_item` keys on (module, item_type, raw_value)
-- and the item_type has changed — so they would be counted in "how many
-- items need review?" while stating something no longer true.
--
-- Separate from 0021 because 0021 had already been applied to the working
-- warehouse by the time this was spotted. Editing an applied migration would
-- leave that database and a freshly built one with different contents while
-- both claim the same schema version.
--
-- Only unresolved rows are removed. A row someone has already worked through
-- is a record of that work, and deleting it would destroy the audit trail
-- this table exists to keep.
--
-- PostgreSQL dialect of ../0022_foi_review_item_rename.sql. Hand-written
-- rather than generated only because it carries a data statement rather than
-- DDL; the statement itself is identical on both engines.
--
DELETE FROM review_queue
 WHERE item_type = 'foi_wdtk_requests_not_retrievable'
   AND status = 'pending';
