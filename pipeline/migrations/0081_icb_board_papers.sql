-- Module 34: Integrated Care Board governance documents.
--
-- DISCOVERY, NOT EXTRACTION -- the same discipline as Modules 9, 10 and 32.
-- An ICB is a statutory NHS body that plans and funds NHS services; it is
-- NOT the commissioner of drug and alcohol treatment (local authorities are,
-- from the public health grant). A mention of the sector in a 300-page board
-- pack is context for a person to weigh, never a figure. Nothing here is
-- evidence: a candidate is a document that was published under an ICB's
-- meetings/governance area, captured in full so a person can read it, and it
-- only reaches icb_board_papers when a person promotes it.
--
-- Per the "capture all documents" instruction (docs/m34-icb-board-papers.md
-- s2a): every document in an ICB's meetings/governance area -- the Board and
-- every standing committee, agendas / reports / minutes / enclosures -- is
-- captured regardless of subject. The subject index below only ranks the
-- review worklist; subject_hits = 0 means "not surfaced now", never
-- "discarded".

-- Reference: the 42 ICBs, seeded from the NHS England "integrated care in
-- your area" directory with provenance attached. A hand-verified board_url
-- override lives in pipeline/icb_boards.py, not here, for the same reason
-- authority websites do: it is code-reviewed.
--
-- name is the natural key, not ods_code: the directory does not reliably
-- publish an ODS code next to each ICB, and a row with no code still has to
-- be storable and joinable. ods_code is recorded when the registry supplies
-- one.
CREATE TABLE IF NOT EXISTS integrated_care_boards (
    name            TEXT PRIMARY KEY,
    ods_code        TEXT,                 -- NHS ODS 3-char code, from pipeline/icb_boards.py; NULL until confirmed
    region          TEXT,                 -- NHS England region, as the directory states it
    directory_url   TEXT,                 -- the ICB's own link on the NHS England directory
    board_url       TEXT,                 -- confirmed meetings/governance entry page (pipeline/icb_boards.py)
    board_url_source TEXT,                -- 'registry' | 'directory_link' | 'path_probe' | NULL
    source_url      TEXT NOT NULL,
    retrieved_at    TEXT NOT NULL,
    http_status     INTEGER NOT NULL,
    source_system   TEXT NOT NULL,
    payload_sha256  TEXT NOT NULL
);

-- Candidate documents. One row per document URL per ICB. verified / rejected
-- are set by a person; a re-run re-upserts a rediscovered link but preserves
-- the decision columns (db.DECISION_COLUMNS via preserve=), and a document
-- whose text was already extracted is not re-fetched or re-read.
CREATE TABLE IF NOT EXISTS icb_board_paper_candidates (
    icb_name             TEXT NOT NULL,   -- integrated_care_boards.name (stable when ods_code is NULL)
    document_url          TEXT NOT NULL,
    meeting_title         TEXT,           -- link text / nearest heading
    committee_name        TEXT,           -- the committee where URL/heading names one; NULL for the Board
    meeting_date          TEXT,           -- ISO, parsed from link text/heading; NULL if unparseable (+ parse_failures)
    document_kind         TEXT,           -- 'board_pack' | 'committee_pack' | 'agenda' | 'minutes' | 'report' | 'enclosure' | 'unknown'
    from_index_page       INTEGER NOT NULL DEFAULT 0,   -- found on a confirmed meetings/governance index
    has_body_text         INTEGER NOT NULL DEFAULT 0,
    subject_hits          INTEGER NOT NULL DEFAULT 0,    -- total substance-misuse / workforce term occurrences
    provider_mentions     INTEGER NOT NULL DEFAULT 0,    -- distinct tracked providers named in the text
    verified              INTEGER NOT NULL DEFAULT 0,
    verified_at           TEXT,
    rejected              INTEGER NOT NULL DEFAULT 0,
    discovered_at         TEXT NOT NULL,
    discovery_method      TEXT,           -- 'path_crawl:/…' | 'subpage_hop'
    source_url            TEXT NOT NULL,
    retrieved_at          TEXT NOT NULL,
    http_status           INTEGER NOT NULL,
    source_system         TEXT NOT NULL,
    payload_sha256        TEXT NOT NULL,
    PRIMARY KEY (icb_name, document_url)
);

CREATE INDEX IF NOT EXISTS idx_icb_candidates_verified
    ON icb_board_paper_candidates (verified, icb_name);
CREATE INDEX IF NOT EXISTS idx_icb_candidates_subject
    ON icb_board_paper_candidates (subject_hits);

-- Only verified candidates are promoted here, with archived copy + full text.
CREATE TABLE IF NOT EXISTS icb_board_papers (
    icb_name        TEXT NOT NULL,
    document_url     TEXT NOT NULL,
    meeting_title    TEXT,
    committee_name   TEXT,
    meeting_date     TEXT,
    document_kind    TEXT NOT NULL,       -- confirmed, not guessed
    archived_path    TEXT,
    full_text        TEXT,
    source_url       TEXT NOT NULL,
    retrieved_at     TEXT NOT NULL,
    http_status      INTEGER NOT NULL,
    source_system    TEXT NOT NULL,
    payload_sha256   TEXT NOT NULL,
    PRIMARY KEY (icb_name, document_url)
);

-- Term-frequency finding aid over the full text (same role as
-- sar_concern_terms / pfd_reports). Not an excerpt: an ICB pack has no shared
-- template, so no "where the relevant bit starts" pattern would be trustworthy.
CREATE TABLE IF NOT EXISTS icb_paper_subject_terms (
    document_url  TEXT NOT NULL,
    term          TEXT NOT NULL,
    occurrences   INTEGER NOT NULL,
    PRIMARY KEY (document_url, term)
);

CREATE TABLE IF NOT EXISTS icb_paper_provider_mentions (
    document_url  TEXT NOT NULL,
    provider_key  TEXT NOT NULL,
    matched_name  TEXT NOT NULL,
    PRIMARY KEY (document_url, provider_key)
);

-- One row per ICB per run, rewritten each time, so "which ICBs yield nothing"
-- is a query not an inference -- the role sab_site_crawls / council_spend_files
-- play for m32 / m24.
CREATE TABLE IF NOT EXISTS icb_site_crawls (
    icb_name         TEXT PRIMARY KEY,
    board_url          TEXT NOT NULL,
    pages_fetched      INTEGER NOT NULL,   -- meetings/governance pages read
    docs_found         INTEGER NOT NULL,   -- documents captured this run
    docs_with_subject  INTEGER NOT NULL,   -- of those, how many mention the sector (worklist size)
    ceiling_reached    INTEGER NOT NULL DEFAULT 0,   -- 1 if MAX_DOCS_PER_ICB truncated the crawl
    status             TEXT NOT NULL,      -- 'ok' | 'no_documents_found' | 'unreachable' | 'robots_disallowed'
    last_crawled       TEXT NOT NULL,
    source_url         TEXT NOT NULL,
    retrieved_at       TEXT NOT NULL,
    http_status        INTEGER NOT NULL,
    source_system      TEXT NOT NULL,
    payload_sha256     TEXT NOT NULL       -- of the board index page; '' when it could not be read
);

CREATE INDEX IF NOT EXISTS idx_icb_site_crawls_status ON icb_site_crawls (status);

-- RESTRICTED: governance documents name officers ("presented by <name>,
-- Director of Commissioning") and committee reports reference patient-safety
-- incidents more often than the Board pack does. The matched-text window
-- around a subject-term hit goes here, never to the exportable candidate
-- table -- kept out of every export by guard_columns() and the reveal gate,
-- not by this module remembering to redact.
CREATE TABLE IF NOT EXISTS restricted_icb_paper_snippets (
    document_url   TEXT NOT NULL,
    term           TEXT NOT NULL,
    snippet_text   TEXT NOT NULL,
    source_url     TEXT NOT NULL,
    retrieved_at   TEXT NOT NULL,
    http_status    INTEGER NOT NULL,
    source_system  TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    PRIMARY KEY (document_url, term)
);
