-- Module 16: the sustained crawl adds a role-keyword pass alongside the
-- employer searches. An advert can now be surfaced by either kind of search,
-- and which one matters: `searched_variant` carries the keyword term for a
-- role search, and `surfaced_by` records the pass that first found the
-- advert, so the CAVEATS reading ("the search that surfaced it means nothing
-- on its own") stays checkable.

ALTER TABLE nhs_job_adverts ADD COLUMN surfaced_by TEXT;
-- 'employer_search' | 'role_search'; NULL on rows collected before this
-- migration, which is the truth about them.
