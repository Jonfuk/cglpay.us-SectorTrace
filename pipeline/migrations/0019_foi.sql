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
--      not worked around here.
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
CREATE TABLE IF NOT EXISTS authority_foi_profiles (
    ons_code                 TEXT PRIMARY KEY,
    authority_name            TEXT NOT NULL,
    wdtk_body_slug             TEXT,
    wdtk_body_url               TEXT,
    home_page_url                TEXT,
    publication_scheme_url        TEXT,
    disclosure_log_url             TEXT,
    source_url                      TEXT NOT NULL,
    retrieved_at                     TEXT NOT NULL,
    http_status                       INTEGER NOT NULL,
    source_system                      TEXT NOT NULL,
    payload_sha256                      TEXT NOT NULL,
    FOREIGN KEY (ons_code) REFERENCES authorities (ons_code)
);

-- Candidates found on a council's own disclosure log. Discovery only: a link
-- whose text matched a search term is not an FOI response about substance
-- misuse until someone opens it. Nothing is promoted without verification,
-- the same discipline as Modules 9 and 10.
CREATE TABLE IF NOT EXISTS foi_request_candidates (
    ons_code             TEXT NOT NULL,
    candidate_url         TEXT NOT NULL,
    title                  TEXT,
    matched_term            TEXT,
    topic                    TEXT,   -- which configured topic the term belongs to
    discovered_at             TEXT NOT NULL,
    discovery_source           TEXT NOT NULL, -- 'disclosure_log'
    verified                    INTEGER NOT NULL DEFAULT 0,
    verified_at                  TEXT,
    rejected                      INTEGER NOT NULL DEFAULT 0,
    source_url                     TEXT NOT NULL,
    retrieved_at                    TEXT NOT NULL,
    http_status                      INTEGER NOT NULL,
    source_system                     TEXT NOT NULL,
    payload_sha256                     TEXT NOT NULL,
    PRIMARY KEY (ons_code, candidate_url),
    FOREIGN KEY (ons_code) REFERENCES authorities (ons_code)
);

CREATE INDEX IF NOT EXISTS idx_foi_candidates_verified
    ON foi_request_candidates (verified, ons_code);

-- Verified promotions only.
CREATE TABLE IF NOT EXISTS foi_requests (
    ons_code           TEXT NOT NULL,
    request_url         TEXT NOT NULL,
    subject              TEXT,
    request_date          TEXT,
    response_date          TEXT,
    status                  TEXT,
    topic                    TEXT,
    response_text             TEXT,
    archived_path              TEXT,
    source_url                  TEXT NOT NULL,
    retrieved_at                 TEXT NOT NULL,
    http_status                   INTEGER NOT NULL,
    source_system                  TEXT NOT NULL,
    payload_sha256                  TEXT NOT NULL,
    PRIMARY KEY (ons_code, request_url),
    FOREIGN KEY (ons_code) REFERENCES authorities (ons_code)
);

CREATE TABLE IF NOT EXISTS foi_attachments (
    ons_code        TEXT NOT NULL,
    request_url      TEXT NOT NULL,
    attachment_url    TEXT NOT NULL,
    file_name          TEXT,
    archived_path       TEXT,
    PRIMARY KEY (ons_code, request_url, attachment_url)
);
