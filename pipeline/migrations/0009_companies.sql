-- Module 4: corporate structure (Companies House).
--
-- Why this module exists: the entity that holds a contract is frequently not
-- the entity that employs the staff. CGL's registered charity (03861209) and
-- its trading subsidiary CHANGE, GROW, LIVE SERVICES LIMITED (06228752) are
-- different legal persons, and which one appears on a notice determines who
-- is the respondent in a tribunal claim and who is the transferor in a TUPE
-- transfer. The schema therefore keeps companies as first-class rows linked
-- to a provider, never collapsing a group into a single organisation.

CREATE TABLE IF NOT EXISTS companies (
    company_number            TEXT PRIMARY KEY, -- always zero-padded to 8 chars
    provider_key               TEXT,
    company_name                TEXT NOT NULL,
    company_status               TEXT,
    company_type                  TEXT,
    date_of_creation               TEXT,
    date_of_cessation               TEXT,
    sic_codes                        TEXT,  -- comma-joined
    registered_address                TEXT,
    jurisdiction                       TEXT,
    -- How this company got here, and whether provider_key can be trusted:
    --   'seed'                  -> company number came from an authoritative
    --                              cross-reference (charity register, CQC);
    --                              provider_key is set.
    --   'name_only_unconfirmed' -> the name matched a provider variant exactly,
    --                              but a shared name is not a shared identity
    --                              (e.g. FORWARD TRUST LIMITED 01865768 is a
    --                              dissolved Bradford & Bingley subsidiary, not
    --                              the charity). provider_key stays NULL until
    --                              a human confirms and adds the number to
    --                              provider_identifiers.
    match_basis                         TEXT,
    source_url                           TEXT NOT NULL,
    retrieved_at                          TEXT NOT NULL,
    http_status                            INTEGER NOT NULL,
    source_system                           TEXT NOT NULL,
    payload_sha256                           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_companies_provider ON companies (provider_key);

-- Former names, straight from Companies House. These are AUTHORITATIVE
-- aliases, not inference: CGL's charity was "CRIME REDUCTION INITIATIVES"
-- until 2016-04-01 and its subsidiary was "CRI UK LIMITED" until 2013, so a
-- pre-2016 contract or judgment naming CRI is a CGL record. Modules 1 and 2
-- can use this table to widen their name matching without anyone guessing.
CREATE TABLE IF NOT EXISTS company_previous_names (
    company_number      TEXT NOT NULL,
    previous_name        TEXT NOT NULL,
    effective_from        TEXT,
    ceased_on              TEXT,
    source_url              TEXT NOT NULL,
    retrieved_at             TEXT NOT NULL,
    http_status               INTEGER NOT NULL,
    source_system              TEXT NOT NULL,
    payload_sha256              TEXT NOT NULL,
    PRIMARY KEY (company_number, previous_name)
);

CREATE TABLE IF NOT EXISTS company_filings (
    company_number     TEXT NOT NULL,
    transaction_id      TEXT NOT NULL,
    filing_date          TEXT,
    category              TEXT,
    subcategory            TEXT,
    description             TEXT,
    document_url             TEXT,
    source_url                TEXT NOT NULL,
    retrieved_at               TEXT NOT NULL,
    http_status                 INTEGER NOT NULL,
    source_system                TEXT NOT NULL,
    payload_sha256                TEXT NOT NULL,
    PRIMARY KEY (company_number, transaction_id)
);

CREATE INDEX IF NOT EXISTS idx_company_filings_category ON company_filings (category);

-- RESTRICTED: named individuals. Excluded from every export by default.
-- Officer changes matter analytically (a wave of resignations around a
-- restructure is evidence), but the names themselves are personal data.
CREATE TABLE IF NOT EXISTS restricted_company_officers (
    company_number      TEXT NOT NULL,
    officer_ref          TEXT NOT NULL, -- person_number, or a hash when absent
    officer_name          TEXT,
    officer_role           TEXT,
    appointed_on            TEXT,
    resigned_on              TEXT,
    nationality               TEXT,
    occupation                 TEXT,
    address_locality            TEXT,
    PRIMARY KEY (company_number, officer_ref)
);

-- Public, name-free view of officer churn, safe to export: counts only.
DROP VIEW IF EXISTS v_company_officer_changes;
CREATE VIEW v_company_officer_changes AS
SELECT
    company_number,
    COUNT(*)                                             AS officers_total,
    SUM(CASE WHEN resigned_on IS NULL THEN 1 ELSE 0 END) AS officers_active,
    SUM(CASE WHEN resigned_on IS NOT NULL THEN 1 ELSE 0 END) AS officers_resigned,
    MIN(appointed_on)                                    AS earliest_appointment,
    MAX(COALESCE(resigned_on, appointed_on))             AS latest_change
FROM restricted_company_officers
GROUP BY company_number;
