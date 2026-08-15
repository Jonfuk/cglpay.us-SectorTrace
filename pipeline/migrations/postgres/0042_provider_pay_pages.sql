-- Module 22: provider career and reward pages.
--
-- The provider's own half of the direct pay evidence: pay figures published
-- on the tracked providers' websites -- advertised bands, "rewards package"
-- pages, listed rates. Attribution is exact by construction: the whole page
-- is the provider's own site (the registry in `pipeline/provider_websites.py`
-- is hand-verified), so there is no free-text matching and no match_basis
-- uncertainty -- every mention carries match_basis 'site_owned'.
--
-- Two tables because two different facts are being recorded:
--
--   * `provider_pay_pages` is a page-level row per fetch: whether the page
--     answered, and how many pay mentions it carried. A page with zero
--     mentions is a real answer about that page (the provider published
--     none), which is why the count lives here and not in the mentions table.
--   * `provider_pay_mentions` is one row per figure, with the text around it
--     kept verbatim so the figure can be checked against its context.
--
-- PostgreSQL dialect of ../0042_provider_pay_pages.sql. See README.md in this directory for
-- the conversion rules; the porting decisions specific to this file are
-- commented where they occur.

CREATE TABLE IF NOT EXISTS provider_pay_pages (
    provider_key   text NOT NULL,
    page_url       text NOT NULL,
    page_role      text NOT NULL,  -- 'registered' (from the verified registry) | 'followed' (found by the crawl)
    page_title     text,           -- the page's own <title>, verbatim
    pay_mentions   bigint NOT NULL,  -- how many figures the page carried; 0 is an answer, not a gap
    source_url     text NOT NULL,
    retrieved_at   text NOT NULL,
    http_status    bigint NOT NULL,
    source_system  text NOT NULL,
    payload_sha256 text NOT NULL,
    PRIMARY KEY (provider_key, page_url)
);

CREATE TABLE IF NOT EXISTS provider_pay_mentions (
    page_url         text NOT NULL,
    mention_index    bigint NOT NULL,  -- the figure's position within the page, 0-based
    provider_key     text NOT NULL,
    section          text,           -- the nearest preceding heading, verbatim; NULL when none
    mention_text     text NOT NULL,  -- the sentence containing the figure, verbatim
    salary_raw       text,           -- the figure's own text, verbatim
    salary_min       double precision, -- parsed as m16 parses adverts; NULL when unreadable
    salary_max       double precision,
    salary_period    text,           -- 'year' | 'hour' | 'month' | 'week' | 'day' | 'session' | NULL
    salary_basis     text NOT NULL,  -- 'range' | 'single' | 'not_stated' | 'unparsed'
    match_basis      text NOT NULL,  -- always 'site_owned' -- see the table comment above
    source_url       text NOT NULL,
    retrieved_at     text NOT NULL,
    http_status      bigint NOT NULL,
    source_system    text NOT NULL,
    payload_sha256   text NOT NULL,
    PRIMARY KEY (page_url, mention_index)
);

CREATE INDEX IF NOT EXISTS idx_provider_pay_mentions_provider
    ON provider_pay_mentions (provider_key);
