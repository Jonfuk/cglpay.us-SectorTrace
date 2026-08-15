-- Module 4 (expansion): People with Significant Control.
--
-- The ownership edges for the entity graph: who owns or controls the
-- companies that hold the sector's contracts. Same API family and key as the
-- rest of Module 4, and the same match-basis discipline -- nothing here is
-- linked to a provider on a name.
--
-- A corporate PSC arrives with its own company number asserted by Companies
-- House (identification.company_number): that is an authoritative identifier,
-- and it is stored on the public row so the entity graph can follow it.
-- Individual PSCs are named, and the name (and the month-and-year of birth
-- Companies House publishes with it) live only in the restricted table.
--
-- PostgreSQL dialect of ../0038_company_psc.sql. See README.md in this directory for
-- the conversion rules; the porting decisions specific to this file are
-- commented where they occur.

CREATE TABLE IF NOT EXISTS company_psc (
    company_number               text NOT NULL,
    psc_ref                      text NOT NULL,  -- the register's own id for the entry
    kind                         text,           -- individual / corporate-entity / legal-person
    natures_of_control           text,           -- comma-joined, the register's vocabulary
    notifiable                   bigint NOT NULL DEFAULT 0,
    is_sanctioned                bigint NOT NULL DEFAULT 0,
    ceased_on                    text,
    notified_on                  text,
    identification_company_number text,          -- corporate PSCs only
    identification_legal_form    text,
    identification_country_registered text,
    register_view                text,           -- 'active' | 'exemptions' | 'protected'
    source_url                   text NOT NULL,
    retrieved_at                 text NOT NULL,
    http_status                  bigint NOT NULL,
    source_system                text NOT NULL,
    payload_sha256               text NOT NULL,
    PRIMARY KEY (company_number, psc_ref)
);

CREATE INDEX IF NOT EXISTS idx_company_psc_identification
    ON company_psc (identification_company_number);

-- RESTRICTED: a PSC is a named person, with the month and year of birth the
-- register publishes. Excluded from every export.
CREATE TABLE IF NOT EXISTS restricted_company_psc (
    company_number         text NOT NULL,
    psc_ref                text NOT NULL,
    name                   text,
    date_of_birth_month    bigint,
    date_of_birth_year     bigint,
    nationality            text,
    country_of_residence   text,
    ceased_on              text,
    PRIMARY KEY (company_number, psc_ref)
);
