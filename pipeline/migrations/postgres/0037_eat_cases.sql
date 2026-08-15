-- Module 2 (expansion): Employment Appeal Tribunal decisions.
--
-- The EAT is a different layer from the first-instance tribunal: a decision
-- affirmed or overturned is a materially different datum from the judgment
-- it reviews. Stored separately on purpose -- no arithmetic across the two
-- (the no-cross-layer rule), and an appeal that references several
-- first-instance cases carries all of them as its own published text.
--
-- PostgreSQL dialect of ../0037_eat_cases.sql. See README.md in this directory for
-- the conversion rules; the porting decisions specific to this file are
-- commented where they occur.

CREATE TABLE IF NOT EXISTS eat_cases (
    neutral_citation     text PRIMARY KEY,  -- "[2026] EAT 34", the case's own citation
    decision_date        text,
    provider_key         text,              -- the side that matched a provider
    provider_side        text,              -- 'appellant' | 'respondent'
    provider_match_basis text,              -- 'exact' | 'component'
    categories           text,              -- tribunal_decision_categories, comma-joined
    landmark             text,              -- 'landmark' | 'not-landmark' as published
    outcome              text,              -- body-derived: allowed / allowed_in_part /
                                            -- dismissed / withdrawn / remitted; NULL when
                                            -- the judgment says none of them
    outcome_confidence   text,              -- always 'low' when outcome is set: GOV.UK
                                            -- publishes no structured outcome field
    underlying_et_cases  text,              -- "Case No.:" references in the judgment text,
                                            -- comma-joined, deduplicated; links the appeal
                                            -- to the first-instance cases it reviews
    document_count       bigint NOT NULL DEFAULT 0,
    source_url           text NOT NULL,
    retrieved_at         text NOT NULL,
    http_status          bigint NOT NULL,
    source_system        text NOT NULL,
    payload_sha256       text NOT NULL
);

CREATE TABLE IF NOT EXISTS eat_documents (
    neutral_citation text NOT NULL,
    document_url     text NOT NULL,
    document_title   text,
    content_type     text,
    source_url       text NOT NULL,
    retrieved_at     text NOT NULL,
    http_status      bigint NOT NULL,
    source_system    text NOT NULL,
    payload_sha256   text NOT NULL,
    PRIMARY KEY (neutral_citation, document_url)
);

-- RESTRICTED: EAT decisions are titled "Appellant v Respondent" and both
-- names are personal data. The public table keys on the neutral citation and
-- never carries a name.
CREATE TABLE IF NOT EXISTS restricted_eat_parties (
    neutral_citation   text PRIMARY KEY,
    appellant_name_raw text,
    respondent_name_raw text,
    page_title_raw     text,
    source_slug        text
);
