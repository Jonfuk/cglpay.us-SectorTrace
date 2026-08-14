-- Module 15: FOI evidence.
--
-- WHAT THIS IS NOT. This is "publicly published FOI evidence", never "all FOI
-- responses". Two limits stack:
--
--   1. WhatDoTheyKnow only holds requests routed through that platform. The
--      UK FOI system is far larger, and most requests never appear there.
--   2. This module cannot read WhatDoTheyKnow's request pages at all. They
--      sit behind a Cloudflare bot challenge that returns 403 to any
--      automated client, which is the site's access control speaking and is
--      not worked around here. Re-measured 2026-08-11: the JSON read API
--      (/body/<slug>.json, /list/all.json, /request/<slug>.json) is blocked
--      the same way and is not an alternative route. See the module
--      docstring in pipeline/modules/m15_foi.py for the full result table.
--
-- What IS collected: the authority register mySociety publishes as a data
-- file (permitted, and the route they offer), and FOI disclosure logs on
-- councils' own websites.
--
-- Any UI built on this must say "publicly published FOI evidence". Presenting
-- it as a picture of FOI activity would misstate it by an unknown and
-- probably large factor.

-- One row per English authority, from mySociety's published authority CSV.
-- Their tags carry the GSS code, so this joins to `authorities` exactly.
-- Also the first source in this pipeline of an authoritative website URL for
-- every authority — Modules 9 and 10 fall back to it.
--
-- PostgreSQL dialect of ../0019_foi.sql. See README.md in this directory for
-- the conversion rules.
--
CREATE TABLE IF NOT EXISTS authority_foi_profiles (
    ons_code                 text PRIMARY KEY,
    authority_name            text NOT NULL,
    wdtk_body_slug             text,
    wdtk_body_url               text,
    home_page_url                text,
    publication_scheme_url        text,
    disclosure_log_url             text,
    source_url                      text NOT NULL,
    retrieved_at                     text NOT NULL,
    http_status                       bigint NOT NULL,
    source_system                      text NOT NULL,
    payload_sha256                      text NOT NULL,
    FOREIGN KEY (ons_code) REFERENCES authorities (ons_code)
);

-- Candidates found on a council's own disclosure log. Discovery only: a link
-- whose text matched a search term is not an FOI response about substance
-- misuse until someone opens it. Nothing is promoted without verification,
-- the same discipline as Modules 9 and 10.
CREATE TABLE IF NOT EXISTS foi_request_candidates (
    ons_code             text NOT NULL,
    candidate_url         text NOT NULL,
    title                  text,
    matched_term            text,
    topic                    text,   -- which configured topic the term belongs to
    discovered_at             text NOT NULL,
    discovery_source           text NOT NULL, -- 'disclosure_log'
    verified                    bigint NOT NULL DEFAULT 0,
    verified_at                  text,
    rejected                      bigint NOT NULL DEFAULT 0,
    source_url                     text NOT NULL,
    retrieved_at                    text NOT NULL,
    http_status                      bigint NOT NULL,
    source_system                     text NOT NULL,
    payload_sha256                     text NOT NULL,
    PRIMARY KEY (ons_code, candidate_url),
    FOREIGN KEY (ons_code) REFERENCES authorities (ons_code)
);

CREATE INDEX IF NOT EXISTS idx_foi_candidates_verified
    ON foi_request_candidates (verified, ons_code);

-- Verified promotions only.
CREATE TABLE IF NOT EXISTS foi_requests (
    ons_code           text NOT NULL,
    request_url         text NOT NULL,
    subject              text,
    request_date          text,
    response_date          text,
    status                  text,
    topic                    text,
    response_text             text,
    archived_path              text,
    source_url                  text NOT NULL,
    retrieved_at                 text NOT NULL,
    http_status                   bigint NOT NULL,
    source_system                  text NOT NULL,
    payload_sha256                  text NOT NULL,
    PRIMARY KEY (ons_code, request_url),
    FOREIGN KEY (ons_code) REFERENCES authorities (ons_code)
);

CREATE TABLE IF NOT EXISTS foi_attachments (
    ons_code        text NOT NULL,
    request_url      text NOT NULL,
    attachment_url    text NOT NULL,
    file_name          text,
    archived_path       text,
    PRIMARY KEY (ons_code, request_url, attachment_url)
);
