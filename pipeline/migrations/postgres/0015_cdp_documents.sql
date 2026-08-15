-- Module 9: Combating Drugs Partnership documents.
--
-- DISCOVERY, NOT EXTRACTION. There is no common schema across 150+
-- authorities, so this module finds candidate documents and a human confirms
-- them. Nothing reaches cdp_documents without that confirmation: a candidate
-- is a URL that looked right, which is not the same as a document that is
-- what it claims to be.

--
-- PostgreSQL dialect of ../0015_cdp_documents.sql. See README.md in this directory for
-- the conversion rules.
--
CREATE TABLE IF NOT EXISTS cdp_document_candidates (
    authority_ons_code     text NOT NULL,
    candidate_url           text NOT NULL,
    title                    text,
    document_type_guess       text,   -- 'cdp_strategy' | 'needs_assessment' | 'outcomes_framework' | NULL
    -- 0-1. Reflects how many independent signals matched (URL path, link
    -- text, file type) — it is a triage aid for the review worklist, never a
    -- substitute for someone opening the document.
    confidence                 double precision NOT NULL DEFAULT 0,
    discovered_at               text NOT NULL,
    discovery_method             text,  -- how it was found, so a bad method can be retired
    verified                      bigint NOT NULL DEFAULT 0,
    verified_at                    text,
    rejected                        bigint NOT NULL DEFAULT 0,
    source_url                       text NOT NULL,
    retrieved_at                      text NOT NULL,
    http_status                        bigint NOT NULL,
    source_system                       text NOT NULL,
    payload_sha256                       text NOT NULL,
    PRIMARY KEY (authority_ons_code, candidate_url),
    FOREIGN KEY (authority_ons_code) REFERENCES authorities (ons_code)
);

CREATE INDEX IF NOT EXISTS idx_cdp_candidates_verified
    ON cdp_document_candidates (verified, authority_ons_code);

-- Only verified candidates are promoted here, with their archived copy and
-- extracted text, so the corpus is searchable for workforce references.
CREATE TABLE IF NOT EXISTS cdp_documents (
    authority_ons_code   text NOT NULL,
    document_url          text NOT NULL,
    title                  text,
    document_type           text NOT NULL,   -- confirmed, not guessed
    published_date           text,
    archived_path             text,
    full_text                  text,
    source_url                  text NOT NULL,
    retrieved_at                 text NOT NULL,
    http_status                   bigint NOT NULL,
    source_system                  text NOT NULL,
    payload_sha256                  text NOT NULL,
    PRIMARY KEY (authority_ons_code, document_url),
    FOREIGN KEY (authority_ons_code) REFERENCES authorities (ons_code)
);
