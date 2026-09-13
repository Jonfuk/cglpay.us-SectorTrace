-- Module 4 extension: Companies House Streaming API (JON-36).
--
-- Four streams (/companies, /filings, /insolvency-cases, /charges) replace
-- polling every tracked company on every run with acting only on the
-- companies a stream says changed. No event's own payload is ever trusted as
-- the source of a written row -- see the m04_companies module docstring for
-- why -- so these tables split into "the notification we saw"
-- (company_stream_events) and "the authoritative fetch it triggered"
-- (company_charges and friends, companies_house_accounts_candidates/
-- _documents).
--
-- This repository's migrations are PostgreSQL-only (there is no sibling
-- SQLite tree any more -- see CLAUDE.md settled decision 10 and
-- tests/test_integration_smoke.py), so unlike this directory's own README
-- this is the only file this change needs.

-- One row per matched, archived event across all four streams. Unmatched
-- (untracked-company) events are never archived or written here -- archiving
-- every event across the whole UK register would be enormous and answer
-- nothing this pipeline asks. `timepoint` is Companies House's own
-- monotonically increasing sequence number for the stream, which is also
-- this pipeline's resumable checkpoint (module_cursors, key
-- 'm04_companies:stream:<stream>').
CREATE TABLE IF NOT EXISTS company_stream_events (
    stream            text NOT NULL,   -- 'companies' | 'filings' | 'insolvency-cases' | 'charges'
    timepoint          bigint NOT NULL,
    resource_kind        text,
    resource_uri           text,
    event_type                text,    -- Companies House's own event.type: 'changed' | 'deleted' | ...
    company_number              text,
    source_url                     text NOT NULL,
    retrieved_at                     text NOT NULL,
    http_status                       bigint NOT NULL,
    source_system                      text NOT NULL,
    payload_sha256                      text NOT NULL,
    PRIMARY KEY (stream, timepoint)
);

CREATE INDEX IF NOT EXISTS idx_company_stream_events_company
    ON company_stream_events (company_number);

-- Charges register (mortgages, debentures and the like registered against a
-- company). Same two-table date-vocabulary split as
-- company_insolvency_cases/company_insolvency_case_dates (0025) and for the
-- identical reason: 'created_on', 'delivered_on', 'satisfied_on' and so on
-- are Companies House's own distinct fields, not stages of one lifecycle,
-- and flattening them into invented columns would assert an ordering the
-- source does not.
CREATE TABLE IF NOT EXISTS company_charges (
    company_number              text NOT NULL,
    charge_ref                    text NOT NULL,   -- the register's own id, or a stable hash when absent
    classification_type             text,
    classification_description        text,
    -- Verbatim Companies House vocabulary -- 'outstanding' | 'satisfied' |
    -- 'part-satisfied' | ... -- never collapsed into a boolean "is_satisfied".
    -- Nullable rather than NOT NULL: unlike match_basis (this pipeline's own
    -- decision), this is an external field this pipeline has not yet
    -- live-verified is always present on every charge record. See
    -- docs/CAVEATS.md.
    status                               text,
    charge_code                           text,   -- Scottish charges' own code, where published
    particulars                             text,
    -- Public register data, unlike officers/PSCs: Companies House publishes
    -- the charges register (including who is entitled) without restriction,
    -- so this is not personal data requiring a restricted_ table the way an
    -- officer's date of birth is.
    persons_entitled                          text,   -- comma-joined names, as published
    source_url                                  text NOT NULL,
    retrieved_at                                  text NOT NULL,
    http_status                                     bigint NOT NULL,
    source_system                                     text NOT NULL,
    payload_sha256                                      text NOT NULL,
    PRIMARY KEY (company_number, charge_ref),
    FOREIGN KEY (company_number) REFERENCES companies (company_number)
);

CREATE TABLE IF NOT EXISTS company_charge_dates (
    company_number    text NOT NULL,
    charge_ref          text NOT NULL,
    date_type              text NOT NULL,   -- verbatim Companies House field name: 'created_on', 'satisfied_on', ...
    date_value               text,
    PRIMARY KEY (company_number, charge_ref, date_type)
);

-- Discovery-until-a-human-promotes-it, the same shape as
-- cdp_document_candidates / committee_paper_candidates / foi_request_candidates
-- (see 0030_evidence_promotions.sql). A filing tagged 'accounts' by Companies
-- House's own filing taxonomy is not itself evidence of anything in the
-- document -- it is a pointer nobody has opened yet, and it is promoted by a
-- person through pipeline/promote.py, never written to
-- companies_house_accounts_documents directly.
CREATE TABLE IF NOT EXISTS companies_house_accounts_candidates (
    company_number       text NOT NULL,
    candidate_url           text NOT NULL,   -- the Document API metadata URL (a stable identifier)
    transaction_id            text,
    filing_date                 text,
    description                    text,    -- Companies House's own filing description, verbatim
    accounts_type                    text,  -- Companies House's own filing subcategory, verbatim -- not a guess
    discovered_at                      text NOT NULL,
    discovery_method                     text,
    verified                               bigint NOT NULL DEFAULT 0,
    verified_at                              text,
    rejected                                   bigint NOT NULL DEFAULT 0,
    source_url                                   text NOT NULL,
    retrieved_at                                   text NOT NULL,
    http_status                                      bigint NOT NULL,
    source_system                                      text NOT NULL,
    payload_sha256                                       text NOT NULL,
    PRIMARY KEY (company_number, candidate_url),
    FOREIGN KEY (company_number) REFERENCES companies (company_number)
);

CREATE INDEX IF NOT EXISTS idx_ch_accounts_candidates_verified
    ON companies_house_accounts_candidates (verified, company_number);

-- Promoted evidence. Structurally separate from charity_accounts_documents
-- (Module 3, migration 0008) and never reconciled against it: a charity's
-- own accounts filed with the Charity Commission and its trading
-- subsidiary's statutory accounts filed with Companies House are different
-- legal entities' filings under different regimes. See docs/CAVEATS.md.
CREATE TABLE IF NOT EXISTS companies_house_accounts_documents (
    company_number    text NOT NULL,
    document_url        text NOT NULL,   -- = the promoted candidate's candidate_url (the metadata URL)
    transaction_id         text,
    filing_date               text,
    description                 text,
    accounts_type                 text,
    content_type                    text,   -- 'application/pdf' | 'application/xhtml+xml' -- what was actually fetched
    archived_path                     text,
    -- The actual content URL fetched, after redirect and content
    -- negotiation -- distinct from document_url above, which is the stable
    -- metadata URL a human reviewed before promoting.
    source_url                          text NOT NULL,
    retrieved_at                          text NOT NULL,
    http_status                             bigint NOT NULL,
    source_system                             text NOT NULL,
    payload_sha256                              text NOT NULL,
    PRIMARY KEY (company_number, document_url),
    FOREIGN KEY (company_number) REFERENCES companies (company_number)
);

-- The fourth promotion-required trigger, alongside the three in
-- 0030_evidence_promotions.sql. Same pattern, same porting notes (see that
-- file and this directory's README): BEFORE INSERT, RAISE EXCEPTION with
-- ERRCODE = 'integrity_constraint_violation' so it surfaces in Python as
-- psycopg.errors.IntegrityError, identical message shape to the other three.
CREATE OR REPLACE FUNCTION companies_house_accounts_documents_need_a_promotion()
RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM evidence_promotions
        WHERE target_table = 'companies_house_accounts_documents'
          AND target_key = NEW.company_number || '|' || NEW.document_url
    ) THEN
        RAISE EXCEPTION 'companies_house_accounts_documents: nothing is promoted without a human — record an evidence_promotions row first, via pipeline/promote.py'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER companies_house_accounts_documents_need_a_promotion
BEFORE INSERT ON companies_house_accounts_documents
FOR EACH ROW
EXECUTE FUNCTION companies_house_accounts_documents_need_a_promotion();
