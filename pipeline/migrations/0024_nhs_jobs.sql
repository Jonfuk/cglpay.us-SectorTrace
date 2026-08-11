-- Module 16: NHS Jobs advertised pay.
--
-- The only source in this pipeline that carries DIRECT pay evidence. Every
-- other pay figure here is a composite or a proxy: the charity accounts give
-- a wage bill over a headcount (v_wage_per_employee, and read its caveats),
-- the workforce census gives sector aggregates attributable to nobody. An
-- advert states what an employer offers for a named role, in its own words,
-- on a date.
--
-- WHAT THIS IS NOT.
--
--   1. It is not a pay scale. An advertised band is what the employer is
--      offering a new starter, which is not what incumbent staff are paid and
--      is not a spine point.
--
--   2. It is not a complete picture of a provider's vacancies. NHS Jobs
--      carries NHS and some commissioned-provider adverts. A charity
--      advertising only on its own site is invisible here, so every count off
--      this table is a FLOOR, never a total, and must be presented as one.
--
--   3. It is not the result set NHS Jobs returned. The search has no empty
--      answer: a nonsense employer name comes back "659 jobs found" of
--      unrelated adverts, and searching "Turning Point" returns West Point
--      Medical Centre alongside it. Rows here are the adverts whose OWN
--      employer field matched a known provider name; everything else the
--      search returned was discarded and counted. See the module docstring.
--
-- HOURLY AND ANNUAL FIGURES ARE NOT CONVERTED into one another anywhere in
-- this pipeline. salary_period says which the employer published, and an
-- hourly rate multiplied into a year is a number the source never stated and
-- that depends on contracted hours nobody here knows.

CREATE TABLE IF NOT EXISTS nhs_job_adverts (
    job_reference           TEXT PRIMARY KEY,   -- the employer's own advert reference
    provider_key             TEXT NOT NULL,
    provider_match_basis      TEXT NOT NULL,    -- 'exact' | 'component', as m02
    employer_name_raw          TEXT NOT NULL,   -- exactly as the advert states it
    job_title                   TEXT,
    advert_url                   TEXT NOT NULL,
    -- Pay as published. salary_raw is the whole string the advert showed, kept
    -- verbatim so a reader can always check what the parsed columns came from.
    salary_raw                    TEXT,
    salary_min                     REAL,
    salary_max                      REAL,
    salary_period                    TEXT,      -- year | hour | session | month | week | day
    -- 'range'      -> the advert gave two figures; min and max are both from it
    -- 'single'     -> one figure, stored in BOTH min and max, so a range query
    --                 over this table does not silently drop single-value adverts
    -- 'not_stated' -> the employer published no figure ("Depends on experience").
    --                 An honest absence, not a failure — do not treat as zero.
    -- 'unparsed'   -> a figure was present and could not be read. Recorded in
    --                 parse_failures too, because that one IS a failure.
    salary_basis                      TEXT NOT NULL,
    contract_type                      TEXT,
    working_pattern                     TEXT,
    posted_date                          TEXT,
    closing_date                          TEXT,
    -- Which provider name variant was searched to surface this advert. Not the
    -- basis for attribution — the employer field is — but it records how the
    -- advert was reached, which is what makes the coverage floor auditable.
    searched_variant                       TEXT NOT NULL,
    source_url                              TEXT NOT NULL,
    retrieved_at                             TEXT NOT NULL,
    http_status                               INTEGER NOT NULL,
    source_system                              TEXT NOT NULL,
    payload_sha256                              TEXT NOT NULL,
    FOREIGN KEY (provider_key) REFERENCES providers (provider_key)
);

CREATE INDEX IF NOT EXISTS idx_nhs_job_adverts_provider
    ON nhs_job_adverts (provider_key, posted_date);

-- One advert can name several sites ("Chichester PO19 1XP, CRAWLEY RH10 8GN,
-- Worthing BN11 1UG"). Kept as its own rows rather than a joined string so a
-- location can be counted or matched to an authority later without splitting
-- text back apart. Not matched to an ONS code here: these are free-text place
-- names and postcodes, and guessing an authority from them is the kind of
-- inferred link this pipeline records rather than invents.
CREATE TABLE IF NOT EXISTS nhs_job_advert_locations (
    job_reference     TEXT NOT NULL,
    location_raw       TEXT NOT NULL,
    PRIMARY KEY (job_reference, location_raw),
    FOREIGN KEY (job_reference) REFERENCES nhs_job_adverts (job_reference)
);

-- --- roles advertised more than once ----------------------------------------
--
-- CANDIDATES, NOT A FINDING. Re-advertisement is the empirical form of "we
-- cannot recruit at this rate" — the thing an annual workforce census cannot
-- show — but the same title appearing under two references is equally
-- consistent with two genuine vacancies at two sites, or with one post being
-- re-advertised after a failed round. This view cannot tell those apart and
-- does not try. It surfaces the pairs; a human reads the adverts.
--
-- Titles are compared case-insensitively and whitespace-collapsed. Nothing
-- fuzzier: "Recovery Worker" and "Senior Recovery Worker" are different jobs.
CREATE VIEW IF NOT EXISTS v_nhs_repeat_advertised_roles AS
    SELECT provider_key,
           employer_name_raw,
           LOWER(TRIM(job_title))            AS job_title_normalised,
           COUNT(*)                          AS advert_count,
           MIN(posted_date)                  AS first_posted_date,
           MAX(posted_date)                  AS last_posted_date,
           MIN(salary_min)                   AS lowest_advertised,
           MAX(salary_max)                   AS highest_advertised,
           -- A mix of periods in one group means the figures above are not
           -- comparable with each other. Say so rather than averaging them.
           COUNT(DISTINCT salary_period)     AS distinct_salary_periods,
           GROUP_CONCAT(job_reference, ', ') AS job_references
      FROM nhs_job_adverts
     WHERE job_title IS NOT NULL
       AND TRIM(job_title) <> ''
     GROUP BY provider_key, employer_name_raw, LOWER(TRIM(job_title))
    HAVING COUNT(*) > 1;
