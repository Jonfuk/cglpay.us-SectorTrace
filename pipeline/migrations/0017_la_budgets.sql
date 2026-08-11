-- Module 13: local authority revenue budgets (MHCLG).
--
-- The structured national release, so 150+ council websites do not have to be
-- scraped for the same numbers. Every authority's budgeted revenue
-- expenditure by service line, including the Public Health line, keyed by ONS
-- code — MHCLG publishes the code itself, so this joins to `authorities`
-- without any name matching.
--
-- SEPARATE FROM THE GRANT. This is what an authority BUDGETED. The public
-- health grant (Module 11) is what it was ALLOCATED. They are different
-- measurements from different departments and are not differenced here: an
-- authority may budget above or below its grant for reasons this pipeline
-- cannot see, and the gap is a finding to investigate rather than a number to
-- publish unexamined.
--
-- Stored tidy/long because MHCLG's column set (213 columns in 2026-27) changes
-- between years, and a fixed wide table would silently drop whatever moved.

CREATE TABLE IF NOT EXISTS la_revenue_budgets (
    ons_code            TEXT NOT NULL,
    financial_year       TEXT NOT NULL,   -- e.g. '2026-27'
    line_code             TEXT NOT NULL,  -- MHCLG's own asset id, e.g. 'transpblopr'
    section                TEXT,          -- section heading, e.g. 'Public Health'
    line_number             TEXT,         -- MHCLG's published line number
    column_label             TEXT,
    -- Detected from the sheet's own "Data are reported in £ thousand" line,
    -- never assumed. A row whose denomination could not be read stores a NULL
    -- amount rather than a number that is wrong by a factor of 1,000.
    amounts_multiplier        INTEGER,
    amount                     REAL,
    value_text                  TEXT,     -- verbatim cell, kept when unparseable
    -- What kind of body this row is, from the ONS code prefix. MHCLG's release
    -- covers every precepting body, not just local authorities: police and
    -- crime commissioners, fire authorities, combined authorities, national
    -- parks, waste authorities, the GLA and the England total all appear.
    -- Those legitimately have no row in `authorities`, so recording the type
    -- keeps a correct absence from looking like a failed join.
    body_type                    TEXT,
    authority_class               TEXT,    -- MHCLG class/subclass, e.g. 'SD', 'UA'
    source_document               TEXT NOT NULL,
    source_url                     TEXT NOT NULL,
    retrieved_at                    TEXT NOT NULL,
    http_status                      INTEGER NOT NULL,
    source_system                     TEXT NOT NULL,
    payload_sha256                     TEXT NOT NULL,
    PRIMARY KEY (ons_code, financial_year, line_code)
);

CREATE INDEX IF NOT EXISTS idx_la_budgets_section ON la_revenue_budgets (section);
CREATE INDEX IF NOT EXISTS idx_la_budgets_year ON la_revenue_budgets (financial_year);

CREATE TABLE IF NOT EXISTS la_budget_publications (
    publication_slug     TEXT NOT NULL,
    document_url          TEXT NOT NULL,
    financial_year         TEXT NOT NULL,
    document_label          TEXT,
    amounts_multiplier       INTEGER,
    sheet_name                TEXT,
    data_rows                  INTEGER,
    source_url                  TEXT NOT NULL,
    retrieved_at                 TEXT NOT NULL,
    http_status                   INTEGER NOT NULL,
    source_system                  TEXT NOT NULL,
    payload_sha256                  TEXT NOT NULL,
    PRIMARY KEY (publication_slug, document_url)
);

-- Convenience view: the Public Health budget line per authority per year,
-- named and joined. Deliberately does NOT join to public_health_grants —
-- see the note at the top of this file.
DROP VIEW IF EXISTS v_la_public_health_budget;
CREATE VIEW v_la_public_health_budget AS
SELECT
    b.ons_code,
    a.name AS authority_name,
    a.region,
    b.financial_year,
    b.line_code,
    b.column_label,
    b.amount        AS budget_gbp,
    'Budgeted revenue expenditure as reported by the authority to MHCLG. '
    || 'This is what the authority budgeted, NOT what it was allocated in the '
    || 'public health grant, and NOT what it ultimately spent.' AS basis_note
FROM la_revenue_budgets b
JOIN authorities a ON a.ons_code = b.ons_code
WHERE b.section = 'Public Health'
  AND b.amount IS NOT NULL;
