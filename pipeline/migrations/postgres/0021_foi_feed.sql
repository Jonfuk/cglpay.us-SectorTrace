-- Module 15: FOI request discovery via WhatDoTheyKnow's search feed.
--
-- Numbered 0021 rather than 0020: 0020_committee_search.sql already holds that
-- slot. Migrations apply in filename order, so a duplicated prefix makes the
-- order between the two depend on how the filesystem sorts them.
--
-- Supersedes part of 0019's header. That migration recorded that WDTK request
-- data was unreachable, which was true of every endpoint measured at the time
-- (the HTML request pages and the JSON read API, all 403). It was not true of
-- /feed/search/<query>.json, which was not tested then because robots.txt
-- disallows */feed/* and this pipeline honours robots.txt. Measured
-- 2026-08-11: that endpoint returns 200 application/json to this pipeline's
-- own User-Agent.
--
-- It is now fetched under a single explicit, logged exception — see
-- Settings.robots_exceptions, which carries the reasoning. Every run that uses
-- it raises a `robots_override_in_use` review item, so the override is visible
-- in the audit trail and not only in the config.
--
-- WHAT THIS STILL IS NOT. Three limits stack now, and all three belong on
-- anything built from this:
--
--   1. WhatDoTheyKnow only holds requests routed through that platform. Most
--      UK FOI requests never appear there.
--   2. The feed is a DISCOVERY source. Each entry carries a short, truncated,
--      search-highlighted `snippet` and never a full message body. Full text
--      still requires the read API, which is still 403. That is why the
--      snippet lands in its own column here and never in
--      `foi_requests.response_text` — a truncated fragment must not become
--      quotable evidence by sitting in a column the campaign quotes from.
--   3. A term match is a candidate, not evidence about substance misuse.
--      Nothing is promoted without a human confirming it, the same discipline
--      as Modules 9, 10 and the disclosure-log path.

-- Feed discovery reuses foi_request_candidates: same discovery-then-verify
-- contract, distinguished by discovery_source ('wdtk_feed_search' vs
-- 'disclosure_log'). These columns are the fields the feed carries that a
-- disclosure-log link does not; they stay NULL for disclosure-log rows.
--
-- PostgreSQL dialect of ../0021_foi_feed.sql. See README.md in this directory for
-- the conversion rules.
--
ALTER TABLE foi_request_candidates ADD COLUMN request_slug text;
ALTER TABLE foi_request_candidates ADD COLUMN authority_slug text;
ALTER TABLE foi_request_candidates ADD COLUMN wdtk_status text;
ALTER TABLE foi_request_candidates ADD COLUMN disclosed bigint;
ALTER TABLE foi_request_candidates ADD COLUMN request_date text;
ALTER TABLE foi_request_candidates ADD COLUMN last_updated text;
ALTER TABLE foi_request_candidates ADD COLUMN event_type text;
ALTER TABLE foi_request_candidates ADD COLUMN event_date text;

-- Explicitly NOT response_text. See limit 2 above.
ALTER TABLE foi_request_candidates ADD COLUMN snippet text;

CREATE INDEX IF NOT EXISTS idx_foi_candidates_source
    ON foi_request_candidates (discovery_source, ons_code);

CREATE INDEX IF NOT EXISTS idx_foi_candidates_status
    ON foi_request_candidates (wdtk_status);
