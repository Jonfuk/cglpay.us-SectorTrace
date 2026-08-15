-- Module 2 (expansion): Employment Appeal Tribunal decisions.
--
-- The EAT is a different layer from the first-instance tribunal: a decision
-- affirmed or overturned is a materially different datum from the judgment
-- it reviews. Stored separately on purpose -- no arithmetic across the two
-- (the no-cross-layer rule), and an appeal that references several
-- first-instance cases carries all of them as its own published text.

CREATE TABLE IF NOT EXISTS eat_cases (
    neutral_citation     TEXT PRIMARY KEY,  -- "[2026] EAT 34", the case's own citation
    decision_date        TEXT,
    provider_key         TEXT,              -- the side that matched a provider
    provider_side        TEXT,              -- 'appellant' | 'respondent'
    provider_match_basis TEXT,              -- 'exact' | 'component'
    categories           TEXT,              -- tribunal_decision_categories, comma-joined
    landmark             TEXT,              -- 'landmark' | 'not-landmark' as published
    outcome              TEXT,              -- body-derived: allowed / allowed_in_part /
                                            -- dismissed / withdrawn / remitted; NULL when
                                            -- the judgment says none of them
    outcome_confidence   TEXT,              -- always 'low' when outcome is set: GOV.UK
                                            -- publishes no structured outcome field
    underlying_et_cases  TEXT,              -- "Case No.:" references in the judgment text,
                                            -- comma-joined, deduplicated; links the appeal
                                            -- to the first-instance cases it reviews
    document_count       INTEGER NOT NULL DEFAULT 0,
    source_url           TEXT NOT NULL,
    retrieved_at         TEXT NOT NULL,
    http_status          INTEGER NOT NULL,
    source_system        TEXT NOT NULL,
    payload_sha256       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eat_documents (
    neutral_citation TEXT NOT NULL,
    document_url     TEXT NOT NULL,
    document_title   TEXT,
    content_type     TEXT,
    source_url       TEXT NOT NULL,
    retrieved_at     TEXT NOT NULL,
    http_status      INTEGER NOT NULL,
    source_system    TEXT NOT NULL,
    payload_sha256   TEXT NOT NULL,
    PRIMARY KEY (neutral_citation, document_url)
);

-- RESTRICTED: EAT decisions are titled "Appellant v Respondent" and both
-- names are personal data. The public table keys on the neutral citation and
-- never carries a name.
CREATE TABLE IF NOT EXISTS restricted_eat_parties (
    neutral_citation   TEXT PRIMARY KEY,
    appellant_name_raw TEXT,
    respondent_name_raw TEXT,
    page_title_raw     TEXT,
    source_slug        TEXT
);
