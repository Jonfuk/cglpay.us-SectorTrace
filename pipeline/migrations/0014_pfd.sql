-- Module 8: Prevention of Future Deaths reports (judiciary.uk).
--
-- PERSONAL DATA BOUNDARY. Every PFD report names the deceased, in the page
-- title and in a "Deceased name :" field. None of that reaches a public
-- table: pfd_reports is keyed on the coroner's own report reference, and the
-- name and raw title live only in restricted_pfd_persons.
--
-- The coroner's name IS public here. They are a public official acting in
-- that capacity, named on the face of a published report, and the brief lists
-- coroner name among the fields to capture.
--
-- NO AUTOMATED CHARACTERISATION. matters_of_concern is stored verbatim. The
-- pipeline indexes it for workforce-related terms so a human can find the
-- relevant reports quickly, but it never summarises, scores or paraphrases
-- what a coroner found — that is for a person to read.

CREATE TABLE IF NOT EXISTS pfd_reports (
    report_ref            TEXT PRIMARY KEY,   -- the coroner's own reference, e.g. '2026-0285'
    report_date            TEXT,
    coroner_name            TEXT,
    coroner_area             TEXT,
    categories                TEXT,            -- comma-joined judiciary.uk report types
    report_url                 TEXT NOT NULL,
    -- Verbatim except that the deceased's name is redacted where it appears
    -- (it does in roughly 1 report in 20). Never summarised or paraphrased.
    matters_of_concern          TEXT,
    -- NOTE: the full report body is NOT here. PFD reports name the deceased
    -- throughout — in every one of a 200-report sample — so the body text
    -- lives in restricted_pfd_report_text instead. Putting it in this table
    -- would have leaked a name into every export that touched it.
    source_url                    TEXT NOT NULL,
    retrieved_at                   TEXT NOT NULL,
    http_status                     INTEGER NOT NULL,
    source_system                    TEXT NOT NULL,
    payload_sha256                    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pfd_date ON pfd_reports (report_date);

-- RESTRICTED: excluded from every export by default.
CREATE TABLE IF NOT EXISTS restricted_pfd_persons (
    report_ref        TEXT PRIMARY KEY,
    deceased_name      TEXT,
    page_title_raw      TEXT,                  -- titles embed the deceased's name
    FOREIGN KEY (report_ref) REFERENCES pfd_reports (report_ref)
);

-- RESTRICTED: the full report text. Kept because it is the searchable corpus
-- and the evidence behind every extracted field, but restricted because a PFD
-- report names the deceased throughout — not only in the header field.
CREATE TABLE IF NOT EXISTS restricted_pfd_report_text (
    report_ref     TEXT PRIMARY KEY,
    body_text       TEXT NOT NULL,
    FOREIGN KEY (report_ref) REFERENCES pfd_reports (report_ref)
);

-- One row per organisation the report was sent to, rather than a blob, so a
-- recipient can be matched and counted.
CREATE TABLE IF NOT EXISTS pfd_recipients (
    report_ref          TEXT NOT NULL,
    organisation_name    TEXT NOT NULL,
    PRIMARY KEY (report_ref, organisation_name),
    FOREIGN KEY (report_ref) REFERENCES pfd_reports (report_ref)
);

-- Two distinct kinds of provider involvement, deliberately not collapsed:
--   'recipient'  -> the coroner addressed the report to this provider
--   'body_text'  -> the provider is named in the report but was NOT a recipient
-- These mean very different things and must never be counted together.
CREATE TABLE IF NOT EXISTS pfd_provider_mentions (
    report_ref        TEXT NOT NULL,
    provider_key       TEXT NOT NULL,
    mention_type        TEXT NOT NULL,         -- 'recipient' | 'body_text'
    matched_name         TEXT,                 -- the variant that matched
    PRIMARY KEY (report_ref, provider_key, mention_type),
    FOREIGN KEY (report_ref) REFERENCES pfd_reports (report_ref)
);

-- Index of workforce-related terms found in MATTERS OF CONCERN. A hit means
-- the word appears — it is a finding aid, not a judgement about the report.
CREATE TABLE IF NOT EXISTS pfd_concern_terms (
    report_ref     TEXT NOT NULL,
    term            TEXT NOT NULL,
    occurrences      INTEGER NOT NULL,
    PRIMARY KEY (report_ref, term),
    FOREIGN KEY (report_ref) REFERENCES pfd_reports (report_ref)
);

CREATE TABLE IF NOT EXISTS pfd_documents (
    report_ref      TEXT NOT NULL,
    document_url     TEXT NOT NULL,
    document_type     TEXT,                    -- 'report' | 'response' | NULL when not stated
    PRIMARY KEY (report_ref, document_url),
    FOREIGN KEY (report_ref) REFERENCES pfd_reports (report_ref)
);
