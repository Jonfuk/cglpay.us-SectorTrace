-- Module 9: Combating Drugs Partnership documents.
--
-- DISCOVERY, NOT EXTRACTION. There is no common schema across 150+
-- authorities, so this module finds candidate documents and a human confirms
-- them. Nothing reaches cdp_documents without that confirmation: a candidate
-- is a URL that looked right, which is not the same as a document that is
-- what it claims to be.

CREATE TABLE IF NOT EXISTS cdp_document_candidates (
    authority_ons_code     TEXT NOT NULL,
    candidate_url           TEXT NOT NULL,
    title                    TEXT,
    document_type_guess       TEXT,   -- 'cdp_strategy' | 'needs_assessment' | 'outcomes_framework' | NULL
    -- 0-1. Reflects how many independent signals matched (URL path, link
    -- text, file type) — it is a triage aid for the review worklist, never a
    -- substitute for someone opening the document.
    confidence                 REAL NOT NULL DEFAULT 0,
    discovered_at               TEXT NOT NULL,
    discovery_method             TEXT,  -- how it was found, so a bad method can be retired
    verified                      INTEGER NOT NULL DEFAULT 0,
    verified_at                    TEXT,
    rejected                        INTEGER NOT NULL DEFAULT 0,
    source_url                       TEXT NOT NULL,
    retrieved_at                      TEXT NOT NULL,
    http_status                        INTEGER NOT NULL,
    source_system                       TEXT NOT NULL,
    payload_sha256                       TEXT NOT NULL,
    PRIMARY KEY (authority_ons_code, candidate_url),
    FOREIGN KEY (authority_ons_code) REFERENCES authorities (ons_code)
);

CREATE INDEX IF NOT EXISTS idx_cdp_candidates_verified
    ON cdp_document_candidates (verified, authority_ons_code);

-- Only verified candidates are promoted here, with their archived copy and
-- extracted text, so the corpus is searchable for workforce references.
CREATE TABLE IF NOT EXISTS cdp_documents (
    authority_ons_code   TEXT NOT NULL,
    document_url          TEXT NOT NULL,
    title                  TEXT,
    document_type           TEXT NOT NULL,   -- confirmed, not guessed
    published_date           TEXT,
    archived_path             TEXT,
    full_text                  TEXT,
    source_url                  TEXT NOT NULL,
    retrieved_at                 TEXT NOT NULL,
    http_status                   INTEGER NOT NULL,
    source_system                  TEXT NOT NULL,
    payload_sha256                  TEXT NOT NULL,
    PRIMARY KEY (authority_ons_code, document_url),
    FOREIGN KEY (authority_ons_code) REFERENCES authorities (ons_code)
);
