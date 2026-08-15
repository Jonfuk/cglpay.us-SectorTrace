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

CREATE TABLE IF NOT EXISTS company_psc (
    company_number               TEXT NOT NULL,
    psc_ref                      TEXT NOT NULL,  -- the register's own id for the entry
    kind                         TEXT,           -- individual / corporate-entity / legal-person
    natures_of_control           TEXT,           -- comma-joined, the register's vocabulary
    notifiable                   INTEGER NOT NULL DEFAULT 0,
    is_sanctioned                INTEGER NOT NULL DEFAULT 0,
    ceased_on                    TEXT,
    notified_on                  TEXT,
    identification_company_number TEXT,          -- corporate PSCs only
    identification_legal_form    TEXT,
    identification_country_registered TEXT,
    register_view                TEXT,           -- 'active' | 'exemptions' | 'protected'
    source_url                   TEXT NOT NULL,
    retrieved_at                 TEXT NOT NULL,
    http_status                  INTEGER NOT NULL,
    source_system                TEXT NOT NULL,
    payload_sha256               TEXT NOT NULL,
    PRIMARY KEY (company_number, psc_ref)
);

CREATE INDEX IF NOT EXISTS idx_company_psc_identification
    ON company_psc (identification_company_number);

-- RESTRICTED: a PSC is a named person, with the month and year of birth the
-- register publishes. Excluded from every export.
CREATE TABLE IF NOT EXISTS restricted_company_psc (
    company_number         TEXT NOT NULL,
    psc_ref                TEXT NOT NULL,
    name                   TEXT,
    date_of_birth_month    INTEGER,
    date_of_birth_year     INTEGER,
    nationality            TEXT,
    country_of_residence   TEXT,
    ceased_on              TEXT,
    PRIMARY KEY (company_number, psc_ref)
);
