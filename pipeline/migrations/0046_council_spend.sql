-- Phase 19 (G5): council spend-transparency files.
--
-- The strongest procurement evidence the corpus could hold: "council X paid
-- provider Y £Z in [period]" is actual money, not a notice. Councils publish
-- £500+ spend as files on their own sites (the Local Government Transparency
-- Code); there is no central API, so m24 discovers the file on the
-- authority's own domain, fetches it through the pipeline client (archived,
-- with provenance), and parses line items.
--
-- Line-item quality varies council to council, and this schema is written
-- for that: `payee` and `amount_text` are verbatim (a value is kept exactly
-- as the council published it), and `amount` is the same figure parsed as a
-- number — NULL where the council's formatting could not be read, never a
-- guess and never a zero. `period` is the period label the council's own
-- file used for the row, NULL where the file carries none; it is not
-- inferred from anything.
--
-- `council_spend_files` is the file-level record: one row per spend file
-- fetched, whether it parsed and how many line items it yielded. A file that
-- could not be parsed is recorded here with parse_status 'unreadable' plus a
-- `parse_failures` row and a review item — a council whose spend file this
-- pipeline cannot read must not look like a council that published nothing.
--
-- `provider_key` is set only by an exact-normalised match of the payee
-- against the tracked providers' own name variants (m04's discipline,
-- matching m16/m20). A payee that matches no provider keeps its verbatim
-- name and a NULL key — the universe work (m23) owns name reconciliation at
-- scale, and a near-miss is never stored as a match.
--
-- There is deliberately NO arithmetic across rows or sources: no monthly
-- totals, no share-of-spend, no comparison against contracts. The rows are
-- what the council published, one line per payment.

CREATE TABLE IF NOT EXISTS council_spend_files (
    authority_ons_code TEXT NOT NULL,
    file_url           TEXT NOT NULL,  -- the spend file itself
    discovered_from    TEXT,           -- the page that linked it
    file_format        TEXT,           -- 'csv' | 'xlsx' | 'ods' | 'unknown'
    parse_status       TEXT NOT NULL,  -- 'parsed' | 'unreadable'
    row_count          INTEGER,
    source_url         TEXT NOT NULL,  -- the file's own provenance
    retrieved_at       TEXT NOT NULL,
    http_status        INTEGER NOT NULL,
    source_system      TEXT NOT NULL,
    payload_sha256     TEXT NOT NULL,
    PRIMARY KEY (authority_ons_code, file_url)
);

CREATE TABLE IF NOT EXISTS council_spend (
    authority_ons_code TEXT NOT NULL,
    file_url           TEXT NOT NULL,
    row_index          INTEGER NOT NULL,   -- the line's position in the file
    period             TEXT,               -- the council's own period label
    payee              TEXT NOT NULL,      -- verbatim
    amount             REAL,               -- NULL where unreadable; never a zero
    amount_text        TEXT,               -- verbatim, kept either way
    description        TEXT,               -- the council's own line description
    provider_key       TEXT,               -- exact-normalised match only
    source_url         TEXT NOT NULL,
    retrieved_at       TEXT NOT NULL,
    http_status        INTEGER NOT NULL,
    source_system      TEXT NOT NULL,
    payload_sha256     TEXT NOT NULL,
    PRIMARY KEY (authority_ons_code, file_url, row_index)
);

CREATE INDEX IF NOT EXISTS idx_council_spend_authority
    ON council_spend (authority_ons_code);
CREATE INDEX IF NOT EXISTS idx_council_spend_provider
    ON council_spend (provider_key);
