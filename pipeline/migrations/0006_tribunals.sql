-- Module 2: employment tribunal judgments.
--
-- PERSONAL DATA BOUNDARY. GOV.UK publishes these decisions with the
-- claimant's name in the page title, the URL slug, and the indexed full
-- text. None of that may reach an export (constraint 3), so:
--   * tribunal_cases (public)      -> case_number, claim_ref pseudonym, no names
--   * restricted_tribunal_parties  -> the claimant name and source slug/title
-- claim_ref is derived deterministically from the PUBLIC case number, so it
-- is stable across re-runs and reversible only via the restricted table.
--
-- Explicitly NOT modelled: any claims-per-employee rate or normalised
-- metric. This database captures only cases reaching published judgment —
-- settled, withdrawn and struck-out claims (the majority) are invisible
-- here, so a rate computed from it would understate reality by an unknown
-- factor. See docs/CAVEATS.md.

CREATE TABLE IF NOT EXISTS tribunal_cases (
    case_number           TEXT PRIMARY KEY,
    claim_ref              TEXT NOT NULL UNIQUE, -- pseudonym derived from case_number
    provider_key            TEXT,                 -- resolved respondent
    -- How provider_key was resolved:
    --   'exact'     -> respondent string equals a known name variant
    --   'component' -> a known variant appears as a whole-token component of a
    --                  multi-respondent string (e.g. "X and Change Grow Live").
    --                  Still deterministic, but the case has co-respondents, so
    --                  it is flagged for review rather than counted silently.
    -- Cases matching NOTHING are never written here — a search on an ambiguous
    -- acronym ("CGL") returns unrelated employers, and admitting them would
    -- make a simple COUNT(*) an indefensible figure. They go to review_queue.
    provider_match_basis     TEXT,
    respondent_normalised     TEXT,
    office_prefix             TEXT,   -- leading digits of the case number (mechanical extraction)
    case_year                  TEXT,  -- trailing year of the case number
    region                      TEXT, -- from tribunal_office_regions lookup; NULL until a prefix is verified
    hearing_venue_raw            TEXT, -- "Heard at:" text from the judgment body; LOWER confidence
    decision_date                 TEXT,
    country                        TEXT,
    jurisdiction_codes              TEXT, -- comma-joined GOV.UK tribunal_decision_categories
    outcome                          TEXT,
    outcome_confidence                TEXT, -- 'high' (page metadata) | 'low' (PDF/body text derived)
    document_count                     INTEGER NOT NULL DEFAULT 0,
    source_url                          TEXT NOT NULL,
    retrieved_at                         TEXT NOT NULL,
    http_status                           INTEGER NOT NULL,
    source_system                          TEXT NOT NULL,
    payload_sha256                          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tribunal_provider ON tribunal_cases (provider_key);
CREATE INDEX IF NOT EXISTS idx_tribunal_decision_date ON tribunal_cases (decision_date);

-- A case can have several documents (e.g. a reserved judgment plus a
-- reconsideration, or judgment and written reasons issued separately), so
-- documents are modelled separately against one case rather than flattened.
CREATE TABLE IF NOT EXISTS tribunal_documents (
    case_number        TEXT NOT NULL,
    document_url        TEXT NOT NULL,
    document_title       TEXT,
    document_type         TEXT,  -- from the attachment title where stated, else NULL
    content_type           TEXT,
    archived_path           TEXT,
    source_url               TEXT NOT NULL,
    retrieved_at              TEXT NOT NULL,
    http_status                INTEGER NOT NULL,
    source_system               TEXT NOT NULL,
    payload_sha256               TEXT NOT NULL,
    PRIMARY KEY (case_number, document_url),
    FOREIGN KEY (case_number) REFERENCES tribunal_cases (case_number)
);

-- RESTRICTED: excluded from every export by default (see pipeline/exports).
CREATE TABLE IF NOT EXISTS restricted_tribunal_parties (
    case_number          TEXT PRIMARY KEY,
    claimant_name_raw     TEXT,
    page_title_raw         TEXT,
    source_slug             TEXT,
    FOREIGN KEY (case_number) REFERENCES tribunal_cases (case_number)
);

-- Case-number office prefix -> region. Deliberately seeded EMPTY: the
-- prefix scheme is not published in a form this pipeline has verified, and
-- guessing it would attribute cases to the wrong region. Unmapped prefixes
-- are routed to review_queue, and hearing_venue_raw on tribunal_cases gives
-- the raw material to populate this table from the judgments themselves.
CREATE TABLE IF NOT EXISTS tribunal_office_regions (
    office_prefix   TEXT PRIMARY KEY,
    region           TEXT NOT NULL,
    office_name       TEXT,
    verified_source    TEXT NOT NULL -- URL or citation justifying the mapping
);
