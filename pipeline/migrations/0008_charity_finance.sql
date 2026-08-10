-- Module 3: charity finance.
--
-- Deliberately THREE tables, not one. The register API and the filed PDF
-- accounts are different documents with different collection methods, so a
-- single row could not carry an honest source_url/payload_sha256 for both
-- (constraint 1) and merging them would blur two evidence layers
-- (constraint 2). They are joined on (charity_number, financial_year_end)
-- by the v_wage_per_employee view instead.

-- Layer 1: the register API's financial history series.
CREATE TABLE IF NOT EXISTS charity_financials (
    charity_number              TEXT NOT NULL,
    financial_year_end           TEXT NOT NULL, -- ISO date
    ar_cycle_reference            TEXT,
    total_income                   REAL,
    total_expenditure               REAL,
    income_from_govt_contracts       REAL,
    income_from_govt_grants           REAL,
    inc_charitable_activities          REAL,
    exp_charitable_activities           REAL,
    consolidated_account                 INTEGER,
    source_url                            TEXT NOT NULL,
    retrieved_at                           TEXT NOT NULL,
    http_status                             INTEGER NOT NULL,
    source_system                            TEXT NOT NULL,
    payload_sha256                            TEXT NOT NULL,
    PRIMARY KEY (charity_number, financial_year_end)
);

-- Layer 2: the filed accounts PDFs themselves, archived and addressable.
CREATE TABLE IF NOT EXISTS charity_accounts_documents (
    charity_number         TEXT NOT NULL,
    financial_year_end      TEXT NOT NULL,
    document_url             TEXT NOT NULL,
    document_label            TEXT,
    archived_path              TEXT,
    page_count                  INTEGER,
    source_url                   TEXT NOT NULL,
    retrieved_at                  TEXT NOT NULL,
    http_status                    INTEGER NOT NULL,
    source_system                   TEXT NOT NULL,
    payload_sha256                   TEXT NOT NULL,
    PRIMARY KEY (charity_number, financial_year_end)
);

-- Layer 3: figures extracted from those PDFs.
--
-- amounts_multiplier records how the source table was denominated (accounts
-- are usually presented in £000). It is detected explicitly from the page,
-- never assumed — a silent 1000x error here would be catastrophic in a pay
-- campaign — and a row where it cannot be determined stores NULL amounts
-- and a parse_failures entry instead.
--
-- average_employees and average_employees_fte are SEPARATE columns because
-- charities publish either or both, and conflating them is precisely the
-- error the caveat in the brief warns about. employees_basis records what
-- average_employees actually is, and is never defaulted.
CREATE TABLE IF NOT EXISTS charity_accounts_extracts (
    charity_number             TEXT NOT NULL,
    financial_year_end          TEXT NOT NULL,
    amounts_multiplier           INTEGER,      -- 1, 1000, or 1000000
    staff_costs_total             REAL,
    wages_and_salaries             REAL,
    social_security_costs           REAL,
    pension_costs                    REAL,
    agency_and_third_party            REAL,    -- agency spend: campaign-relevant
    redundancy_costs                   REAL,
    average_employees                   REAL,
    employees_basis                      TEXT, -- 'headcount' | 'fte' | 'unknown'
    average_employees_fte                 REAL,
    senior_pay_bands_json                  TEXT,
    senior_pay_band_headcount               INTEGER,
    key_management_remuneration              REAL,
    key_management_headcount                  INTEGER,
    extraction_page                            INTEGER,
    raw_text_block                              TEXT, -- verbatim source text for eyeball verification
    source_url                                   TEXT NOT NULL,
    retrieved_at                                  TEXT NOT NULL,
    http_status                                    INTEGER NOT NULL,
    source_system                                   TEXT NOT NULL,
    payload_sha256                                   TEXT NOT NULL,
    PRIMARY KEY (charity_number, financial_year_end)
);

-- Derived view. Per the brief this may divide wages by employees, but the
-- output is labelled indicative_wage_per_head and NEVER average_salary, and
-- carries mandatory annotation columns that every export must render
-- alongside the number.
--
-- Both a headcount-based and an FTE-based figure are exposed where the
-- charity publishes both, because they differ materially (CGL 2025:
-- 5,715 headcount vs 4,623 FTE) and quoting the headcount figure as if it
-- were a salary would understate pay per full-time worker by ~19%.
DROP VIEW IF EXISTS v_wage_per_employee;
CREATE VIEW v_wage_per_employee AS
SELECT
    e.charity_number,
    e.financial_year_end,
    e.wages_and_salaries,
    e.average_employees,
    e.employees_basis,
    e.average_employees_fte,
    CASE WHEN e.average_employees > 0
         THEN e.wages_and_salaries / e.average_employees END      AS indicative_wage_per_head,
    CASE WHEN e.average_employees_fte > 0
         THEN e.wages_and_salaries / e.average_employees_fte END  AS indicative_wage_per_fte,
    'Denominator is an average employee count as published by the charity; '
    || COALESCE(e.employees_basis, 'basis not stated')
    || '. A headcount average counts part-time staff as whole people, so a '
    || 'per-head figure is NOT a salary and will read lower than actual pay.'
                                                                  AS denominator_basis_note,
    'Numerator is total wages and salaries for all grades including senior '
    || 'staff and executives, before employer NI and pension costs. It is '
    || 'not a pay scale, a median, or an individual employee''s earnings.'
                                                                  AS numerator_scope_note
FROM charity_accounts_extracts e
WHERE e.wages_and_salaries IS NOT NULL;
