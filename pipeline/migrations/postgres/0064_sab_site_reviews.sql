-- Module 32: SARs found by crawling a Safeguarding Adults Board's own
-- website, in addition to the National SAR Library that Module 28 reads.
--
-- Module 28's founding decision (migration 0057) was one aggregator over
-- ~150 board sites. Module 32 is the deliberate exception, scoped in
-- docs/m32-sab-site-crawl.md: it crawls each England board's site — from the
-- website_url in safeguarding_adults_boards, which m28 fills from the Ann
-- Craft Trust directory — for reviews the board published but never
-- submitted to the library.
--
-- PostgreSQL dialect of ../0064_sab_site_reviews.sql. See README.md in this
-- directory for the conversion rules.

-- Where a sar_documents row was found. Backfilled for existing rows from
-- their source URL; every future row (m28 and m32) sets it.
--   national_library  the National SAR Library's main index
--   scie_library      its SCIE 2015-2018 collection
--   sab_website       a board's own site (Module 32)
ALTER TABLE sar_documents ADD COLUMN discovered_via text;

UPDATE sar_documents
   SET discovered_via = CASE WHEN source_url LIKE '%SCIE%20Library%'
                             THEN 'scie_library' ELSE 'national_library' END
 WHERE discovered_via IS NULL;

CREATE INDEX IF NOT EXISTS idx_sar_documents_discovered_via
    ON sar_documents (discovered_via);

-- One row per board crawl, rewritten every run, so "which boards yield
-- nothing" is a query rather than an inference from review items — the same
-- role council_spend_files plays for m24.
CREATE TABLE IF NOT EXISTS sab_site_crawls (
    sab_name       text PRIMARY KEY,   -- the board's official directory name
    website_url    text NOT NULL,
    pages_fetched  bigint NOT NULL,    -- discovery pages read on the board's site
    docs_found     bigint NOT NULL,    -- candidate documents fetched
    docs_ingested  bigint NOT NULL,    -- auto-ingested into sar_documents this run
    docs_candidate bigint NOT NULL,    -- routed to review_queue for a person instead
    status         text NOT NULL,      -- 'ok' | 'no_sars_found' | 'unreachable' | 'robots_disallowed'
    last_crawled   text NOT NULL,
    source_url     text NOT NULL,      -- the board site's base URL, this crawl's provenance
    retrieved_at   text NOT NULL,
    http_status    bigint NOT NULL,
    source_system  text NOT NULL,
    payload_sha256 text NOT NULL       -- of the board homepage; '' when it could not be read
);

CREATE INDEX IF NOT EXISTS idx_sab_site_crawls_status ON sab_site_crawls (status);
