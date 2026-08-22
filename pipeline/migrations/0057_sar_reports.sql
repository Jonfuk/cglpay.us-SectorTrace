-- Module 28: Safeguarding Adult Reviews (SARs), read from the National SAR
-- Library (nationalnetwork.org.uk), maintained by the National Network for
-- Chairs of Adult Safeguarding Boards.
--
-- Chosen over crawling ~150 independent Safeguarding Adults Board websites
-- for the same reason m08 reads judiciary.uk rather than 150 coroners'
-- courts individually: one source with real coverage beats 150 with none.
--
-- WHAT THE SOURCE DOES NOT GIVE US. Unlike judiciary.uk, the library carries
-- no structured per-document metadata -- no board-name field, no
-- publication date, no distribution list. Each entry is only a title (as
-- submitted, often a bare filename) and a download link, grouped by the
-- year it was added to the library. Two things follow:
--
--   * sab_name is read from the DOCUMENT'S OWN TEXT, the same way
--     pfd_reports.coroner_area is read from a PFD report's own header --
--     never guessed from the title, never inferred from which folder the
--     library filed it under. NULL plus a parse_failures row when the
--     pattern is not found.
--   * There is no equivalent of PFD's "matters of concern" field. That
--     field works because judiciary.uk reports share one template; SAR
--     reports are written by ~150 different boards over a decade and share
--     none. No section is extracted into a public column by guessing where
--     it starts -- see docs/CAVEATS.md. What this gives instead is a
--     term-frequency finding aid over the full text (sar_concern_terms) and
--     provider mentions, exactly as PFD's.
--
-- PERSONAL DATA BOUNDARY. A SAR's title is very often the subject's own name
-- or a chosen pseudonym ("Hannah", "Mr Z", "Ruth Mitchell"), with nothing in
-- the source to say which is which. Rather than guess, every title is
-- treated as personal data and lives only in restricted_sar_persons, exactly
-- like PFD's restricted_pfd_persons: guard_columns() and the reveal gate
-- keep it out of every export, not intention.

CREATE TABLE IF NOT EXISTS sar_documents (
    document_url      TEXT PRIMARY KEY,   -- the PDF/DOCX itself; the natural key
    document_ext        TEXT,             -- '.pdf', '.docx', ... as published
    library_year          INTEGER NOT NULL, -- the year section the library filed it under; NOT a publication date
    -- Read from the document's own text where it names its board plainly
    -- ("... Safeguarding Adults Board"). Free text, unvalidated against any
    -- fixed list of boards -- see coroner_area in pfd_reports for the same
    -- choice and why.
    sab_name                TEXT,
    has_body_text              INTEGER NOT NULL, -- whether text extraction succeeded
    source_url                    TEXT NOT NULL,
    retrieved_at                    TEXT NOT NULL,
    http_status                      INTEGER NOT NULL,
    source_system                      TEXT NOT NULL,
    payload_sha256                      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sar_documents_year ON sar_documents (library_year);
CREATE INDEX IF NOT EXISTS idx_sar_documents_sab ON sar_documents (sab_name);

-- RESTRICTED: excluded from every export by default. The library gives no
-- structured name field the way judiciary.uk's header does -- the title is
-- the closest thing to one, and it is often exactly that.
CREATE TABLE IF NOT EXISTS restricted_sar_persons (
    document_url     TEXT PRIMARY KEY,
    title_raw          TEXT NOT NULL,
    FOREIGN KEY (document_url) REFERENCES sar_documents (document_url)
);

-- RESTRICTED: the extracted text. Kept as the searchable corpus and the
-- evidence behind sab_name and the term index, restricted because a SAR
-- names its subject throughout, not only in the title.
CREATE TABLE IF NOT EXISTS restricted_sar_report_text (
    document_url     TEXT PRIMARY KEY,
    body_text          TEXT NOT NULL,
    FOREIGN KEY (document_url) REFERENCES sar_documents (document_url)
);

-- A provider named in a SAR's text. Unlike pfd_provider_mentions there is no
-- 'recipient' concept here -- the library gives no distribution list -- so
-- every mention is the equivalent of PFD's 'body_text' kind and is not
-- claimed to be anything more specific than that.
CREATE TABLE IF NOT EXISTS sar_provider_mentions (
    document_url     TEXT NOT NULL,
    provider_key       TEXT NOT NULL,
    matched_name         TEXT,
    PRIMARY KEY (document_url, provider_key),
    FOREIGN KEY (document_url) REFERENCES sar_documents (document_url)
);

-- Index of workforce-related terms found anywhere in the document text. A
-- hit means the word appears -- a finding aid, not a characterisation of the
-- review, exactly as pfd_concern_terms.
CREATE TABLE IF NOT EXISTS sar_concern_terms (
    document_url     TEXT NOT NULL,
    term               TEXT NOT NULL,
    occurrences          INTEGER NOT NULL,
    PRIMARY KEY (document_url, term),
    FOREIGN KEY (document_url) REFERENCES sar_documents (document_url)
);
