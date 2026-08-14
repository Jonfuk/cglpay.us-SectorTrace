-- Module 4 extension: insolvency and disqualification.
--
-- Provider viability, from the register this pipeline already has a key and a
-- working client for. Not a new module: Companies House already answers the
-- question, `companies.company_status` already distinguishes liquidation and
-- administration, and the Individual Insolvency Register — the obvious-looking
-- alternative — is a register of *individuals*, which is personal data and the
-- wrong entity entirely. See docs/SOURCES.md.
--
-- This is not a hypothetical concern for this sector. LIFELINE PROJECT
-- (01842240), a substance misuse provider large enough to appear as a
-- co-respondent alongside CGL in employment tribunal judgments, went into
-- administration on 2017-06-02, was wound up on 2018-06-07 and dissolved on
-- 2024-01-25. Services and staff moved to other providers. That is the shape
-- of event this table exists to record.
--
-- DISSOLVED IS NOT INSOLVENT, and the two must not be read as one. Of the
-- dissolved companies this pipeline holds, none has an insolvency case: a
-- company can be struck off voluntarily having paid everyone. `company_status`
-- says how a company ended; only these tables say whether it failed.

-- One row per insolvency case. A company can have several — Lifeline has two,
-- an administration followed by a creditors' voluntary liquidation, and they
-- are different events with different dates.
--
-- PostgreSQL dialect of ../0025_company_insolvency.sql. See README.md in this directory for
-- the conversion rules; the porting decisions specific to this file are
-- commented where they occur.
--
CREATE TABLE IF NOT EXISTS company_insolvency_cases (
    company_number      text NOT NULL,
    case_number          text NOT NULL,   -- Companies House's own numbering within the company
    case_type             text,           -- 'in-administration', 'creditors-voluntary-liquidation', …
    source_url             text NOT NULL,
    retrieved_at            text NOT NULL,
    http_status              bigint NOT NULL,
    source_system             text NOT NULL,
    payload_sha256             text NOT NULL,
    PRIMARY KEY (company_number, case_number),
    FOREIGN KEY (company_number) REFERENCES companies (company_number)
);

-- Case dates, keeping Companies House's own date vocabulary rather than
-- flattening it into columns this pipeline invented. The set of date types
-- varies with the case type ('administration-started-on' and
-- 'administration-ended-on' for one, 'wound-up-on' and 'dissolved-on' for
-- another), and mapping them onto a fixed started/ended pair would mean
-- deciding that an administration ending and a winding-up are the same kind of
-- fact. They are not.
CREATE TABLE IF NOT EXISTS company_insolvency_case_dates (
    company_number    text NOT NULL,
    case_number        text NOT NULL,
    date_type           text NOT NULL,   -- verbatim from the source
    date_value           text,
    PRIMARY KEY (company_number, case_number, date_type)
);

-- RESTRICTED: named individuals. Insolvency practitioners are licensed
-- professionals acting as statutory office-holders and their names are on the
-- public register — but a pay campaign has no use for them, and the cheapest
-- way to be sure a name is never exported is not to put it in an exportable
-- table. Their firm addresses are not stored at all: they add nothing here,
-- and an address that serves no evidential purpose is a personal-data
-- footprint with no argument behind it.
CREATE TABLE IF NOT EXISTS restricted_company_insolvency_practitioners (
    company_number       text NOT NULL,
    case_number           text NOT NULL,
    practitioner_name      text NOT NULL,
    role                    text,
    appointed_on             text,
    ceased_to_act_on          text,
    PRIMARY KEY (company_number, case_number, practitioner_name)
);

-- RESTRICTED: disqualified directors.
--
-- READ THIS BEFORE USING THE TABLE. Companies House publishes no link from an
-- officer's appointment to a disqualification, so the only route is to search
-- the register by name. A name match is not an identity match — that is the
-- lesson m04 already learned from FORWARD TRUST LIMITED — and getting it wrong
-- here does not mis-attribute a contract, it says a named person was banned
-- from being a director when they were not.
--
-- So nothing reaches this table on a name alone. A row is written only where
-- the register's record corroborates on BOTH the name and the month and year
-- of birth that Companies House publishes for the serving director, or where
-- the person numbers match outright. Everything weaker goes to review_queue
-- as a candidate and is never stored as a fact.
--
-- Expect this table to be empty, and that is the point. Acting as a director
-- while disqualified is a criminal offence, so a serving director of a large
-- registered charity being on this register would be extraordinary. An empty
-- table is a checkable negative; it is not evidence that the check was skipped.
CREATE TABLE IF NOT EXISTS restricted_officer_disqualifications (
    company_number        text NOT NULL,
    officer_ref            text NOT NULL,   -- joins restricted_company_officers
    officer_name            text,
    case_identifier          text NOT NULL,
    disqualification_type     text,          -- 'undertaking', 'order', 'sanction'
    disqualified_from          text,
    disqualified_until          text,
    reason_act                   text,
    reason_description            text,
    disqualified_company_names     text,     -- the companies the register names
    -- 'person_number'          -> the register's person number equals the
    --                             officer's; an identifier match, not a guess
    -- 'name_and_date_of_birth' -> forename, surname and the published month and
    --                             year of birth all agree
    match_basis                     text NOT NULL,
    source_url                       text NOT NULL,
    retrieved_at                      text NOT NULL,
    http_status                        bigint NOT NULL,
    source_system                       text NOT NULL,
    payload_sha256                       text NOT NULL,
    PRIMARY KEY (company_number, officer_ref, case_identifier)
);

-- --- what is already collected, surfaced ------------------------------------
--
-- The viability question answered from rows this pipeline already held. No new
-- fetching is involved in the view itself: company_status and date_of_cessation
-- come from the profile m04 has always read, the officer counts from the
-- name-free churn view, and the insolvency columns from the tables above.
--
-- `viability_flag` is a restatement of what the source says, not a judgement
-- this pipeline forms. 'insolvency_case_recorded' means Companies House
-- published one. 'dissolved_no_insolvency_case' means the company ended
-- without one — struck off, merged or wound up solvent — and must NOT be
-- presented as a failure.
CREATE OR REPLACE VIEW v_provider_viability AS
    SELECT c.provider_key,
           c.company_number,
           c.company_name,
           c.company_status,
           c.date_of_cessation,
           c.match_basis,
           COUNT(i.case_number)                       AS insolvency_cases,
           -- SQLite's one-argument GROUP_CONCAT separates with ',' and takes
           -- no separator argument when DISTINCT is used, so the separator is
           -- stated explicitly here to produce the same string.
           string_agg(DISTINCT i.case_type, ',')      AS insolvency_case_types,
           (SELECT MIN(d.date_value)
              FROM company_insolvency_case_dates d
             WHERE d.company_number = c.company_number
               AND d.date_value IS NOT NULL)          AS first_insolvency_date,
           (SELECT MAX(d.date_value)
              FROM company_insolvency_case_dates d
             WHERE d.company_number = c.company_number
               AND d.date_value IS NOT NULL)          AS last_insolvency_date,
           v.officers_active,
           v.officers_resigned,
           CASE
               WHEN COUNT(i.case_number) > 0        THEN 'insolvency_case_recorded'
               WHEN c.company_status = 'dissolved'  THEN 'dissolved_no_insolvency_case'
               WHEN c.company_status = 'active'     THEN 'active'
               ELSE COALESCE(c.company_status, 'status_unknown')
           END                                        AS viability_flag
      FROM companies c
      LEFT JOIN company_insolvency_cases i ON i.company_number = c.company_number
      LEFT JOIN v_company_officer_changes v ON v.company_number = c.company_number
     -- SQLite accepts `GROUP BY c.company_number` alone here and picks an
     -- arbitrary row for every ungrouped column. PostgreSQL does not, with
     -- one exception that covers most of this list: `companies.company_number`
     -- is the primary key, so every `c.*` column above is functionally
     -- dependent on it and PostgreSQL allows those without restating them.
     --
     -- `v.*` is the part that is not covered. Functional dependency is not
     -- inferred through a view, so the two officer columns have to be named.
     -- Adding them to the grouping is exactly equivalent rather than merely
     -- close: `v_company_officer_changes` is itself grouped by
     -- `company_number`, so it has at most one row per join key, and a column
     -- with one value per group cannot split that group. A company with no
     -- officer rows joins to NULLs and stays one group for the same reason.
     GROUP BY c.company_number, v.officers_active, v.officers_resigned;
