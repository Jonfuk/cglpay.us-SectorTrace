-- Module 16: the sustained crawl adds a role-keyword pass alongside the
-- employer searches. An advert can now be surfaced by either kind of search,
-- and which one matters: `searched_variant` carries the keyword term for a
-- role search, and `surfaced_by` records the pass that first found the
-- advert, so the CAVEATS reading ("the search that surfaced it means nothing
-- on its own") stays checkable.
--
-- PostgreSQL dialect of ../0043_nhs_jobs_surfaced_by.sql. See README.md in this directory for
-- the conversion rules; the porting decisions specific to this file are
-- commented where they occur.

ALTER TABLE nhs_job_adverts ADD COLUMN IF NOT EXISTS surfaced_by text;
-- 'employer_search' | 'role_search'; NULL on rows collected before this
-- migration, which is the truth about them.
