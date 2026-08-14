-- Module 3: charity finance.
--
-- Deliberately THREE tables, not one. The register API and the filed PDF
-- accounts are different documents with different collection methods, so a
-- single row could not carry an honest source_url/payload_sha256 for both
-- (constraint 1) and merging them would blur two evidence layers
-- (constraint 2). They are joined on (charity_number, financial_year_end)
-- by the v_wage_per_employee view instead.

-- Layer 1: the register API's financial history series.
--
-- PostgreSQL dialect of ../0008_charity_finance.sql. See README.md in this directory for
-- the conversion rules.
--
CREATE TABLE IF NOT EXISTS charity_financials (
    charity_number              text NOT NULL,
    financial_year_end           text NOT NULL, -- ISO date
    ar_cycle_reference            text,
    total_income                   double precision,
    total_expenditure               double precision,
    income_from_govt_contracts       double precision,
    income_from_govt_grants           double precision,
    inc_charitable_activities          double precision,
    exp_charitable_activities           double precision,
    consolidated_account                 bigint,
    source_url                            text NOT NULL,
    retrieved_at                           text NOT NULL,
    http_status                             bigint NOT NULL,
    source_system                            text NOT NULL,
    payload_sha256                            text NOT NULL,
    PRIMARY KEY (charity_number, financial_year_end)
);

-- Layer 2: the filed accounts PDFs themselves, archived and addressable.
CREATE TABLE IF NOT EXISTS charity_accounts_documents (
    charity_number         text NOT NULL,
    financial_year_end      text NOT NULL,
    document_url             text NOT NULL,
    document_label            text,
    archived_path              text,
    page_count                  bigint,
    source_url                   text NOT NULL,
    retrieved_at                  text NOT NULL,
    http_status                    bigint NOT NULL,
    source_system                   text NOT NULL,
    payload_sha256                   text NOT NULL,
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
    charity_number             text NOT NULL,
    financial_year_end          text NOT NULL,
    amounts_multiplier           bigint,      -- 1, 1000, or 1000000
    staff_costs_total             double precision,
    wages_and_salaries             double precision,
    social_security_costs           double precision,
    pension_costs                    double precision,
    agency_and_third_party            double precision,    -- agency spend: campaign-relevant
    redundancy_costs                   double precision,
    average_employees                   double precision,
    employees_basis                      text, -- 'headcount' | 'fte' | 'unknown'
    average_employees_fte                 double precision,
    senior_pay_bands_json                  text,
    senior_pay_band_headcount               bigint,
    key_management_remuneration              double precision,
    key_management_headcount                  bigint,
    extraction_page                            bigint,
    raw_text_block                              text, -- verbatim source text for eyeball verification
    source_url                                   text NOT NULL,
    retrieved_at                                  text NOT NULL,
    http_status                                    bigint NOT NULL,
    source_system                                   text NOT NULL,
    payload_sha256                                   text NOT NULL,
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
