-- Authority URLs supplied by a reviewer, for Modules 9 and 10.
--
-- Those two modules cannot derive where a council publishes: hostnames are
-- genuinely unpredictable (democracy.kent.gov.uk works; the same pattern
-- applied to five other authorities resolved to nothing). Until now the only
-- way to teach them one was to edit pipeline/authority_websites.py, and the
-- 304 items sitting in review_queue as `authority_website_unknown` and
-- `committee_url_unknown` had nowhere to go but a code change.
--
-- This is that missing destination. `website_for()` reads it ahead of the
-- code registry, so resolving an item in the reviewer takes effect on the
-- next run of m09/m10 without a deploy.
--
-- It is deliberately NOT `authority_committee_systems`. That table is Module
-- 10's own output — it records what the module found, including URLs it
-- guessed from a homepage link and labelled `homepage_link` precisely so they
-- would not be mistaken for confirmed. Writing human answers into it would
-- mean the module reading its own guesses back as authority on the next run,
-- and would erase the distinction that table exists to preserve. Asserted
-- input and derived output stay in separate tables.
--
-- Every row is verified by an actual request before it is written, which is
-- the standard the code registry sets ("find the site, confirm it loads").
-- checked_status is what the server saw when it checked, not a claim by
-- whoever typed the URL.
--
-- PostgreSQL dialect of ../0027_authority_url_overrides.sql. See README.md in this directory for
-- the conversion rules.
--
CREATE TABLE IF NOT EXISTS authority_url_overrides (
    ons_code          text PRIMARY KEY,
    -- The council's main domain, for Module 9's site-scoped document search.
    base_url          text,
    -- The committee system root, for Module 10. Different host in most cases.
    committee_url     text,
    -- 'moderngov' | 'cmis' | 'unknown', detected by probing the signature
    -- paths against the URL given, never taken on trust from the form.
    committee_system  text,
    checked_url       text,
    checked_status    bigint,
    checked_at        text,
    -- Never defaulted. An assertion about where a council publishes is worth
    -- exactly as much as the name attached to it.
    verified_by       text NOT NULL,
    verified_at       text NOT NULL,
    note              text,
    -- The queue item this answered, so the decision and its effect are one
    -- another's audit trail.
    review_item_id    bigint REFERENCES review_queue (id),

    -- A row that names neither URL teaches the modules nothing and would sit
    -- there looking like an answer.
    CHECK (base_url IS NOT NULL OR committee_url IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_authority_url_overrides_item
    ON authority_url_overrides (review_item_id);
