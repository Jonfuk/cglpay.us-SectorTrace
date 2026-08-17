-- The claims-to-evidence index (Workstream C, Phase 17).
--
-- The difference between a data portal and an evidence portfolio: claims as
-- rows, each linked to the verified evidence rows supporting it, with the
-- caveats that travel with it, the reviewer and the date. Nothing in the
-- registry is computed -- a claim is a statement linked to rows, and the
-- linkage is a human judgement recorded like every other decision in this
-- warehouse.
--
-- Three tables, and the third is why the first two work:
--
--   * `claims` -- the statement itself, who wrote it, its status. The status
--     is the lifecycle a reviewer moves it through: 'draft' (written, not yet
--     decided), 'published' (a human said this claim can be made), 'rejected'
--     (a human said it cannot), 'retracted' (it was published and withdrawn).
--
--   * `claim_citations` -- the linkage: which evidence rows support the
--     claim. A citation names a table and a row in it by the row's own
--     natural key, in the same "<authority>|<url>" shape migration 0030
--     uses. The linkage is a judgement -- who cited it and when are columns
--     here, never defaulted.
--
--   * `claim_verifications` -- the reviewer and the decision history. This
--     is the guarantee the plan demands: "a claim without a recorded
--     reviewer and decision history is not a claim", the same standard 0030
--     sets for promotion. Nothing reaches 'published' (or 'rejected', or
--     'retracted') without a row here naming who decided it.
--
-- Why this is not a review_queue item: review items are questions about the
-- pipeline's own gaps -- "this buyer name is unmatched" -- and deciding one
-- records a status, nothing more. A claim is a statement about the world
-- that the campaign will quote, and publishing it is an act with the same
-- threshold as promotion, recorded the same way: a named person, a date, a
-- note. Same reason it is not an evidence_promotions row: promotion creates
-- an evidence row by fetching a document; a claim creates nothing, it
-- packages rows that already exist.
--
-- Like 0033, the guarantee is structural rather than conventional: the
-- triggers at the bottom refuse a claim that is decided -- or born decided --
-- without a claim_verifications row behind it.
CREATE TABLE IF NOT EXISTS claims (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    -- The statement itself, as the campaign would quote it.
    claim_text  TEXT NOT NULL,
    -- A claim is born a draft. Every other status is a decision, and the
    -- trigger at the bottom says who had to have made it.
    status      TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'published', 'rejected', 'retracted')),
    -- The "you may not compute this from it" lines. Written by the claim's
    -- author, rendered by the portal as pinned caveats beside the statement.
    -- One line per caveat, newline-separated.
    caveats     TEXT NOT NULL DEFAULT '',
    -- Never defaulted, the same rule review_decisions, evidence_promotions
    -- and census_verifications have: an authorship that is a guess is worse
    -- than none.
    created_by  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    note        TEXT
);

-- The linkage. What a claim rests on: evidence rows, named by their own
-- table and natural key.
CREATE TABLE IF NOT EXISTS claim_citations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id       INTEGER NOT NULL REFERENCES claims(id),
    -- Which evidence table the cited row lives in, and the row's natural
    -- key within it -- for documents the same "<authority>|<url>" shape
    -- evidence_promotions.target_key uses. Table names are pinned in
    -- pipeline/claims.py (CITABLE), the same way promote.py pins KINDS, so a
    -- citation can never name a table the portal cannot resolve.
    evidence_table TEXT NOT NULL,
    evidence_key   TEXT NOT NULL,
    cited_by       TEXT NOT NULL,
    cited_at       TEXT NOT NULL,
    note           TEXT,
    UNIQUE (claim_id, evidence_table, evidence_key)
);

-- The decision history. One row per decision, whoever made it, when, and on
-- what note. `decide()` writes the row first and then moves the claim's
-- status, the same ordering promote() and census_verify() use: the audit
-- trail is not something the caller is trusted to remember afterwards.
--
-- Deliberately no FOREIGN KEY to claims, the same choice 0033 makes for
-- census_verifications: the load order for a PostgreSQL migration has to be
-- able to write this table before the claims it vouches for, and an FK would
-- make that ordering impossible. The claims trigger below is what holds the
-- two tables together instead.
CREATE TABLE IF NOT EXISTS claim_verifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id   INTEGER NOT NULL,
    -- 'published' / 'rejected' / 'retracted' -- the status it authorised.
    decision   TEXT NOT NULL
               CHECK (decision IN ('published', 'rejected', 'retracted')),
    decided_by TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    note       TEXT
);

CREATE INDEX IF NOT EXISTS idx_claim_citations_claim
    ON claim_citations (claim_id);

CREATE INDEX IF NOT EXISTS idx_claim_verifications_claim
    ON claim_verifications (claim_id);

CREATE INDEX IF NOT EXISTS idx_claim_verifications_decided_at
    ON claim_verifications (decided_at DESC);

-- The two refusals.
--
-- The INSERT one makes a claim's lifecycle honest: nothing arrives decided.
-- A claim row is written as a draft and every later status is a decision
-- recorded in claim_verifications first. (The "or a claim_verifications row
-- exists" clause exists for the PostgreSQL loader, which writes verifications
-- ahead of the claims they vouch for so that COPY answers yes -- the same
-- arrangement 0033 documents.)
CREATE TRIGGER IF NOT EXISTS claims_insert_needs_a_decision
BEFORE INSERT ON claims
FOR EACH ROW
WHEN NEW.status <> 'draft' AND NOT EXISTS (
    SELECT 1 FROM claim_verifications
    WHERE claim_id = NEW.id AND decision = NEW.status)
BEGIN
    -- One literal: SQLite has no implicit string concatenation, and a
    -- migration that will not parse is a migration nobody can apply.
    SELECT RAISE(ABORT, 'claims: a claim is not decided without a human — record a claim_verifications row first, via pipeline/claims.py');
END;

-- The UPDATE trigger fires on `status` being named, so the WHEN clause reads
-- OLD as well as NEW: re-writing a claim that already has a status is not a
-- new decision and must not need a second one. A claim staying 'published'
-- while its text or citations are edited keeps its verification; the status
-- column only moves when a decision row authorises the move.
CREATE TRIGGER IF NOT EXISTS claims_status_needs_a_decision
BEFORE UPDATE OF status ON claims
FOR EACH ROW
WHEN NEW.status <> OLD.status
 AND NEW.status <> 'draft'
 AND NOT EXISTS (
    SELECT 1 FROM claim_verifications
    WHERE claim_id = NEW.id AND decision = NEW.status)
BEGIN
    -- One literal: SQLite has no implicit string concatenation, and a
    -- migration that will not parse is a migration nobody can apply.
    SELECT RAISE(ABORT, 'claims: a claim is not decided without a human — record a claim_verifications row first, via pipeline/claims.py');
END;
