-- Module 34: Integrated Care Board governance documents.
--
-- PostgreSQL dialect of ../0081_icb_board_papers.sql. See README.md in this
-- directory for the conversion rules.
--
-- DISCOVERY, NOT EXTRACTION -- the same discipline as Modules 9, 10 and 32.
-- An ICB is not the commissioner of drug and alcohol treatment (local
-- authorities are). A mention of the sector in a board pack is context for a
-- person, never a figure. A candidate reaches icb_board_papers only when a
-- person promotes it. Every governance document is captured regardless of
-- subject (docs/m34-icb-board-papers.md s2a); the subject index only ranks
-- the review worklist.

CREATE TABLE IF NOT EXISTS integrated_care_boards (
    name            text PRIMARY KEY,
    ods_code        text,
    region          text,
    directory_url   text,
    board_url       text,
    board_url_source text,
    source_url      text NOT NULL,
    retrieved_at    text NOT NULL,
    http_status     bigint NOT NULL,
    source_system   text NOT NULL,
    payload_sha256  text NOT NULL
);

CREATE TABLE IF NOT EXISTS icb_board_paper_candidates (
    icb_name             text NOT NULL,
    document_url          text NOT NULL,
    meeting_title         text,
    committee_name        text,
    meeting_date          text,
    document_kind         text,
    from_index_page       bigint NOT NULL DEFAULT 0,
    has_body_text         bigint NOT NULL DEFAULT 0,
    subject_hits          bigint NOT NULL DEFAULT 0,
    provider_mentions     bigint NOT NULL DEFAULT 0,
    verified              bigint NOT NULL DEFAULT 0,
    verified_at           text,
    rejected              bigint NOT NULL DEFAULT 0,
    discovered_at         text NOT NULL,
    discovery_method      text,
    source_url            text NOT NULL,
    retrieved_at          text NOT NULL,
    http_status           bigint NOT NULL,
    source_system         text NOT NULL,
    payload_sha256        text NOT NULL,
    PRIMARY KEY (icb_name, document_url)
);

CREATE INDEX IF NOT EXISTS idx_icb_candidates_verified
    ON icb_board_paper_candidates (verified, icb_name);
CREATE INDEX IF NOT EXISTS idx_icb_candidates_subject
    ON icb_board_paper_candidates (subject_hits);

CREATE TABLE IF NOT EXISTS icb_board_papers (
    icb_name        text NOT NULL,
    document_url     text NOT NULL,
    meeting_title    text,
    committee_name   text,
    meeting_date     text,
    document_kind    text NOT NULL,
    archived_path    text,
    full_text        text,
    source_url       text NOT NULL,
    retrieved_at     text NOT NULL,
    http_status      bigint NOT NULL,
    source_system    text NOT NULL,
    payload_sha256   text NOT NULL,
    PRIMARY KEY (icb_name, document_url)
);

CREATE TABLE IF NOT EXISTS icb_paper_subject_terms (
    document_url  text NOT NULL,
    term          text NOT NULL,
    occurrences   bigint NOT NULL,
    PRIMARY KEY (document_url, term)
);

CREATE TABLE IF NOT EXISTS icb_paper_provider_mentions (
    document_url  text NOT NULL,
    provider_key  text NOT NULL,
    matched_name  text NOT NULL,
    PRIMARY KEY (document_url, provider_key)
);

CREATE TABLE IF NOT EXISTS icb_site_crawls (
    icb_name         text PRIMARY KEY,
    board_url          text NOT NULL,
    pages_fetched      bigint NOT NULL,
    docs_found         bigint NOT NULL,
    docs_with_subject  bigint NOT NULL,
    ceiling_reached    bigint NOT NULL DEFAULT 0,
    status             text NOT NULL,
    last_crawled       text NOT NULL,
    source_url         text NOT NULL,
    retrieved_at       text NOT NULL,
    http_status        bigint NOT NULL,
    source_system      text NOT NULL,
    payload_sha256     text NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_icb_site_crawls_status ON icb_site_crawls (status);

-- RESTRICTED: kept out of every export by guard_columns() and the reveal
-- gate, not by the module remembering to redact.
CREATE TABLE IF NOT EXISTS restricted_icb_paper_snippets (
    document_url   text NOT NULL,
    term           text NOT NULL,
    snippet_text   text NOT NULL,
    source_url     text NOT NULL,
    retrieved_at   text NOT NULL,
    http_status    bigint NOT NULL,
    source_system  text NOT NULL,
    payload_sha256 text NOT NULL,
    PRIMARY KEY (document_url, term)
);
