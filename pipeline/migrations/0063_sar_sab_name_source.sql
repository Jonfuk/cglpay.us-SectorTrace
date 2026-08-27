-- Module 28: a canonical list of Safeguarding Adults Boards, and a record of
-- HOW each SAR's sab_name was obtained.
--
-- 0057 read sab_name only from a document's own text ("... Safeguarding
-- Adults Board") and left it NULL otherwise. That left roughly a third of
-- the library with no board: the phrase is often only on a cover page the
-- extractor did not reach, is stated as an acronym, or is not in the
-- document at all (7-minute briefings, executive summaries).
--
-- Two things change here.

-- 1. A reference list of the boards themselves, from the Ann Craft Trust's
--    "find your nearest Safeguarding Adults Board" directory -- the one
--    maintained national index of them, ~190 boards across the four
--    nations. Reference/config, no per-row provenance beyond the fetch: it
--    is one page, refreshed on every m28 run, and a board that drops off it
--    is removed. The value it adds is a fixed set of *official* names to
--    resolve a free-text or title-derived board against, so "Camden",
--    "Camden Safeguarding Adults Board" and "Camden Safeguarding Adults
--    Partnership Board" all land on one canonical string.
CREATE TABLE IF NOT EXISTS safeguarding_adults_boards (
    name           TEXT PRIMARY KEY,   -- official name, exactly as the directory lists it
    nation         TEXT,               -- 'England' | 'Wales' | 'Scotland' | 'Northern Ireland'
    website_url    TEXT,
    source_url     TEXT NOT NULL,
    retrieved_at   TEXT NOT NULL,
    http_status    INTEGER NOT NULL,
    source_system  TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sabs_nation ON safeguarding_adults_boards (nation);

-- 2. sab_name is now resolved in layers, and this column says which layer
--    produced the value so the weaker ones stay distinguishable:
--
--      document_text            the board names itself in the document's own
--                               text and the name matches the directory --
--                               the 0057 rule, still first and strongest.
--      document_text_unverified the text names a board but it is not in the
--                               directory; kept verbatim, lower confidence.
--      sab_directory            the board was not in the text, but the
--                               library entry's title carries a place name
--                               that resolves to exactly one directory board.
--
--    NULL source with a non-NULL name only happens on rows written before
--    this migration; the backfill sets it.
ALTER TABLE sar_documents ADD COLUMN sab_name_source TEXT;

CREATE INDEX IF NOT EXISTS idx_sar_documents_sab_source
    ON sar_documents (sab_name_source);
