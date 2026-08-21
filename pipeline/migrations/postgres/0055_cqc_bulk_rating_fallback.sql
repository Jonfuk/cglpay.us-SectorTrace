-- CQC's live syndication API and its own bulk ratings export can disagree:
-- confirmed for real (location 1-12790083928, "Aspire Havering") that a
-- same-day fetch of GET /locations/{id} returns currentRatings.overall as
-- null while the bulk ratings export -- CQC's own file, not a third party --
-- carries a real published rating for the same location. Re-running m05_cqc
-- does not fix this: the API is not behind, it is structurally silent for
-- some locations under whatever CQC's "new digital system" migration
-- currently does to that field.
--
-- These columns are the fallback, kept deliberately separate from
-- overall_rating/overall_rating_date rather than overwriting them in place:
-- those two stay exactly what the API said (including staying NULL, which is
-- itself the API's honest answer), so a reader can always tell whether a
-- location's rating came from the live per-location record m05_cqc fetched
-- or from m26_cqc_directory's bulk-export fallback. m26_cqc_directory only
-- ever writes these when overall_rating IS NULL -- it never second-guesses a
-- rating the API did supply, because the bulk export's greater currency in
-- the null case is not evidence it is also more current when the API
-- disagrees with a value rather than with silence.
--
-- PostgreSQL dialect of ../0055_cqc_bulk_rating_fallback.sql. See README.md
-- in this directory for the conversion rules.
ALTER TABLE cqc_locations ADD COLUMN IF NOT EXISTS bulk_overall_rating text;
ALTER TABLE cqc_locations ADD COLUMN IF NOT EXISTS bulk_overall_rating_date text;
ALTER TABLE cqc_locations ADD COLUMN IF NOT EXISTS bulk_rating_source_url text;
ALTER TABLE cqc_locations ADD COLUMN IF NOT EXISTS bulk_rating_retrieved_at text;
