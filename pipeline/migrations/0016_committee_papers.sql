-- Module 10: council committee papers.
--
-- Same discipline as Module 9: discovery, with human confirmation before
-- anything is promoted. A search hit on a committee system is a document
-- whose title matched a term — not evidence that it concerns drug and
-- alcohol services.

-- Which committee system each authority runs, detected from path signatures
-- rather than assumed. 'unknown' is a real, recorded answer: it routes the
-- authority to the null adapter and into review_queue.
CREATE TABLE IF NOT EXISTS authority_committee_systems (
    ons_code            TEXT PRIMARY KEY,
    committee_system     TEXT NOT NULL,   -- 'moderngov' | 'cmis' | 'democracy' | 'unknown'
    committee_url         TEXT,
    detected_by            TEXT,          -- the signature path that matched
    detected_at             TEXT NOT NULL,
    FOREIGN KEY (ons_code) REFERENCES authorities (ons_code)
);

CREATE TABLE IF NOT EXISTS committee_paper_candidates (
    authority_ons_code    TEXT NOT NULL,
    document_url           TEXT NOT NULL,
    committee_name          TEXT,
    meeting_date             TEXT,
    agenda_item_title         TEXT,
    report_title               TEXT,
    matched_term                TEXT,     -- which configured search term found it
    committee_system             TEXT,
    verified                      INTEGER NOT NULL DEFAULT 0,
    verified_at                    TEXT,
    rejected                        INTEGER NOT NULL DEFAULT 0,
    discovered_at                    TEXT NOT NULL,
    source_url                        TEXT NOT NULL,
    retrieved_at                       TEXT NOT NULL,
    http_status                         INTEGER NOT NULL,
    source_system                        TEXT NOT NULL,
    payload_sha256                        TEXT NOT NULL,
    PRIMARY KEY (authority_ons_code, document_url),
    FOREIGN KEY (authority_ons_code) REFERENCES authorities (ons_code)
);

CREATE INDEX IF NOT EXISTS idx_committee_candidates_verified
    ON committee_paper_candidates (verified, authority_ons_code);

-- Only verified candidates are promoted.
CREATE TABLE IF NOT EXISTS committee_papers (
    authority_ons_code   TEXT NOT NULL,
    document_url          TEXT NOT NULL,
    committee_name         TEXT,
    meeting_date            TEXT,
    agenda_item_title        TEXT,
    report_title              TEXT,
    archived_path              TEXT,
    full_text                   TEXT,
    source_url                   TEXT NOT NULL,
    retrieved_at                  TEXT NOT NULL,
    http_status                    INTEGER NOT NULL,
    source_system                   TEXT NOT NULL,
    payload_sha256                   TEXT NOT NULL,
    PRIMARY KEY (authority_ons_code, document_url),
    FOREIGN KEY (authority_ons_code) REFERENCES authorities (ons_code)
);
