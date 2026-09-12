-- performance.md Phase 5 ("Archive and HTTP cache"): store the exact archive
-- reference, content type and content length alongside a conditional-request
-- cache entry, so a 304 revalidation (pipeline/http.py) retrieves the
-- archived body by that stored key (Archive.get_by_ref) instead of
-- Archive.lookup's hash-prefix scan — a bucket listing call per cache hit on
-- S3-compatible storage, a directory glob on filesystem storage.
--
-- Nullable: a row written before this migration, or a fetch made with
-- use_conditional/archive off, simply falls back to the old lookup path.
ALTER TABLE http_cache ADD COLUMN archive_ref text;
ALTER TABLE http_cache ADD COLUMN content_type text;
ALTER TABLE http_cache ADD COLUMN content_length bigint;
