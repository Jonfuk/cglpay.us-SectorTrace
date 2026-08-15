-- Module 14: provider annual report narrative.
--
-- Module 3 already downloads and archives each charity's filed accounts,
-- which for these providers ARE the annual report, but it only extracts the
-- staff-costs note. This module reads the narrative around it: what the
-- provider says about recruitment, retention, restructuring, wellbeing,
-- equality and principal risks.
--
-- It re-reads the PDFs already on disk rather than fetching them again.
--
-- NOTHING IS SUMMARISED. Passages are stored verbatim with their page number,
-- exactly as PFD matters of concern are. A term index says where to look; a
-- person decides what it means.
--
-- The disclosure-gap table is the point of the module as much as the
-- passages. A provider writing at length about retention while publishing no
-- retention figure is itself evidence — but see the wording of
-- `search_terms`: this records that no passage matched those terms, which is
-- weaker than "the provider does not disclose it" and must be read that way.

--
-- PostgreSQL dialect of ../0018_annual_reports.sql. See README.md in this directory for
-- the conversion rules.
--
CREATE TABLE IF NOT EXISTS provider_annual_reports (
    provider_key         text NOT NULL,
    financial_year_end    text NOT NULL,
    charity_number         text,
    document_url            text NOT NULL,
    archived_path            text,
    page_count                bigint,
    source_url                 text NOT NULL,
    retrieved_at                text NOT NULL,
    http_status                  bigint NOT NULL,
    source_system                 text NOT NULL,
    payload_sha256                 text NOT NULL,
    PRIMARY KEY (provider_key, financial_year_end)
);

-- One row per (report, topic, page) where the topic's terms appear. The
-- passage is the verbatim page text around the match.
CREATE TABLE IF NOT EXISTS provider_report_passages (
    provider_key      text NOT NULL,
    financial_year_end text NOT NULL,
    topic               text NOT NULL,   -- 'recruitment' | 'retention' | 'restructuring' | ...
    page_number          bigint NOT NULL,
    matched_term          text NOT NULL,
    passage_text           text NOT NULL, -- verbatim; never summarised
    source_url              text NOT NULL,
    retrieved_at             text NOT NULL,
    http_status               bigint NOT NULL,
    source_system              text NOT NULL,
    payload_sha256              text NOT NULL,
    PRIMARY KEY (provider_key, financial_year_end, topic, page_number, matched_term)
);

CREATE INDEX IF NOT EXISTS idx_report_passages_topic ON provider_report_passages (topic);

-- What a report did and did not appear to cover.
--
-- `matched = 0` means no passage matched `search_terms` — NOT that the
-- provider discloses nothing on the subject. A figure given only in a table,
-- or described in wording the terms do not cover, would read the same way.
-- Treat a gap as a prompt to look, not as a finding in itself.
CREATE TABLE IF NOT EXISTS provider_report_disclosure (
    provider_key       text NOT NULL,
    financial_year_end  text NOT NULL,
    topic                text NOT NULL,
    matched               bigint NOT NULL,
    pages_matched          bigint NOT NULL DEFAULT 0,
    search_terms            text NOT NULL,  -- exactly what was looked for
    source_url               text NOT NULL,
    retrieved_at              text NOT NULL,
    http_status                bigint NOT NULL,
    source_system               text NOT NULL,
    payload_sha256               text NOT NULL,
    PRIMARY KEY (provider_key, financial_year_end, topic)
);

-- Topics a report did not appear to cover, joined to the provider. Useful for
-- the campaign question "what does the provider not publish?" — read with the
-- caveat above.
DROP VIEW IF EXISTS v_provider_disclosure_gaps;
CREATE VIEW v_provider_disclosure_gaps AS
SELECT
    d.provider_key,
    p.canonical_name AS provider_name,
    d.financial_year_end,
    d.topic,
    d.search_terms,
    'No passage in this annual report matched these terms. That is weaker '
    || 'than "not disclosed": a figure given only in a table, or described in '
    || 'other wording, would look the same. Check the report before relying '
    || 'on this.' AS caveat
FROM provider_report_disclosure d
JOIN providers p ON p.provider_key = d.provider_key
WHERE d.matched = 0;
