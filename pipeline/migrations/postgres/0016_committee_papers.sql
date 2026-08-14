-- Module 10: council committee papers.
--
-- Same discipline as Module 9: discovery, with human confirmation before
-- anything is promoted. A search hit on a committee system is a document
-- whose title matched a term — not evidence that it concerns drug and
-- alcohol services.

-- Which committee system each authority runs, detected from path signatures
-- rather than assumed. 'unknown' is a real, recorded answer: it routes the
-- authority to the null adapter and into review_queue.
--
-- PostgreSQL dialect of ../0016_committee_papers.sql. See README.md in this directory for
-- the conversion rules.
--
CREATE TABLE IF NOT EXISTS authority_committee_systems (
    ons_code            text PRIMARY KEY,
    committee_system     text NOT NULL,   -- 'moderngov' | 'cmis' | 'democracy' | 'unknown'
    committee_url         text,
    detected_by            text,          -- the signature path that matched
    detected_at             text NOT NULL,
    FOREIGN KEY (ons_code) REFERENCES authorities (ons_code)
);

CREATE TABLE IF NOT EXISTS committee_paper_candidates (
    authority_ons_code    text NOT NULL,
    document_url           text NOT NULL,
    committee_name          text,
    meeting_date             text,
    agenda_item_title         text,
    report_title               text,
    matched_term                text,     -- which configured search term found it
    committee_system             text,
    verified                      bigint NOT NULL DEFAULT 0,
    verified_at                    text,
    rejected                        bigint NOT NULL DEFAULT 0,
    discovered_at                    text NOT NULL,
    source_url                        text NOT NULL,
    retrieved_at                       text NOT NULL,
    http_status                         bigint NOT NULL,
    source_system                        text NOT NULL,
    payload_sha256                        text NOT NULL,
    PRIMARY KEY (authority_ons_code, document_url),
    FOREIGN KEY (authority_ons_code) REFERENCES authorities (ons_code)
);

CREATE INDEX IF NOT EXISTS idx_committee_candidates_verified
    ON committee_paper_candidates (verified, authority_ons_code);

-- Only verified candidates are promoted.
CREATE TABLE IF NOT EXISTS committee_papers (
    authority_ons_code   text NOT NULL,
    document_url          text NOT NULL,
    committee_name         text,
    meeting_date            text,
    agenda_item_title        text,
    report_title              text,
    archived_path              text,
    full_text                   text,
    source_url                   text NOT NULL,
    retrieved_at                  text NOT NULL,
    http_status                    bigint NOT NULL,
    source_system                   text NOT NULL,
    payload_sha256                   text NOT NULL,
    PRIMARY KEY (authority_ons_code, document_url),
    FOREIGN KEY (authority_ons_code) REFERENCES authorities (ons_code)
);
