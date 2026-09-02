-- Restore the derived wage view after a benchmark scratch-schema regression
-- briefly resolved an unqualified DROP VIEW against the live PostgreSQL
-- `public` schema. This is a no-data repair: charity_accounts_extracts remains
-- authoritative and both dialects retain the same view contract.

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
         THEN e.wages_and_salaries / e.average_employees END AS indicative_wage_per_head,
    CASE WHEN e.average_employees_fte > 0
         THEN e.wages_and_salaries / e.average_employees_fte END AS indicative_wage_per_fte,
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
