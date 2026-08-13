-- Who turned a candidate into evidence, and on what.
--
-- Three modules discover candidates -- m09 (CDP documents), m10 (committee
-- papers), m15 (FOI requests) -- and none of them promotes one. That is the
-- correct default and it stays: `match_quality` is ModernGov's own ranking,
-- `confidence` counts matching signals, and neither is this pipeline's
-- judgement that a document is what its link text claims. So promotion is a
-- human act, and this is where the act is recorded.
--
-- 1,941 candidates and zero promoted rows is what prompted it. The evidence
-- was being collected and then not crossing into the evidence base, because
-- the only documented way across was hand-written SQL.
--
-- Two things this table is NOT:
--
--   * It is not `review_decisions`. That records judgements on review_queue
--     items -- "this buyer name is unmatched", "these concerns are PDF-only"
--     -- which are questions about the pipeline's own gaps. A promotion is a
--     statement about the world: this URL is a Combating Drugs Partnership
--     strategy for this authority. Different question, different evidence
--     threshold, different table.
--
--   * It is not a copy of the candidate. The candidate's provenance describes
--     the *listing page the link was found on*. An evidence row carrying that
--     hash would be claiming the document was fetched when it was not, which
--     is the one thing this project does not do. Promotion fetches the
--     document itself, and the provenance recorded here and on the evidence
--     row is that fetch.
--
-- The guarantee is structural, not conventional: the triggers below refuse an
-- insert into any of the three evidence tables that has no promotion row.
-- Nothing reaches them by another route -- not a module, not the SQL box, not
-- a future author who has not read this file.
CREATE TABLE IF NOT EXISTS evidence_promotions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_table   TEXT NOT NULL,
    -- How the candidate is identified in its own table. URL rather than
    -- rowid: rowids are not stable across a rebuild, and the URL is what a
    -- person was actually looking at.
    candidate_url     TEXT NOT NULL,
    target_table      TEXT NOT NULL,
    -- The evidence row's natural key, as "<authority>|<url>", which is what
    -- the triggers match on.
    target_key        TEXT NOT NULL,
    -- Never defaulted. The UI asks who is promoting and sends it, the same
    -- rule review_decisions has: an audit row whose author is a guess is
    -- worse than no audit row.
    promoted_by       TEXT NOT NULL,
    promoted_at       TEXT NOT NULL,
    note              TEXT,
    -- The candidate as it read when the judgement was taken. A later module
    -- run can refresh a candidate row underneath a decision already made
    -- against the old text.
    candidate_context_json TEXT NOT NULL,
    -- Provenance of the fetch that produced the evidence row.
    fetched_url       TEXT,
    http_status       INTEGER,
    payload_sha256    TEXT,
    archived_path     TEXT
);

-- The triggers below do an EXISTS on (target_table, target_key) for every
-- insert into an evidence table, so it is on the write path rather than a
-- reporting convenience.
CREATE INDEX IF NOT EXISTS idx_evidence_promotions_target
    ON evidence_promotions (target_table, target_key);

CREATE INDEX IF NOT EXISTS idx_evidence_promotions_candidate
    ON evidence_promotions (candidate_table, candidate_url);

-- "What has been promoted lately", and by whom.
CREATE INDEX IF NOT EXISTS idx_evidence_promotions_promoted_at
    ON evidence_promotions (promoted_at DESC);

-- The three refusals.
--
-- Written per table rather than generated, because a trigger naming its own
-- table and key is readable at the point someone hits it, and there are only
-- three of them. Each fires BEFORE INSERT, so the row never lands.
CREATE TRIGGER IF NOT EXISTS cdp_documents_need_a_promotion
BEFORE INSERT ON cdp_documents
FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1 FROM evidence_promotions
    WHERE target_table = 'cdp_documents'
      AND target_key = NEW.authority_ons_code || '|' || NEW.document_url)
BEGIN
    -- One literal: SQLite has no implicit string concatenation, and a
    -- migration that will not parse is a migration nobody can apply.
    SELECT RAISE(ABORT, 'cdp_documents: nothing is promoted without a human — record an evidence_promotions row first, via pipeline/promote.py');
END;

CREATE TRIGGER IF NOT EXISTS committee_papers_need_a_promotion
BEFORE INSERT ON committee_papers
FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1 FROM evidence_promotions
    WHERE target_table = 'committee_papers'
      AND target_key = NEW.authority_ons_code || '|' || NEW.document_url)
BEGIN
    -- One literal: SQLite has no implicit string concatenation, and a
    -- migration that will not parse is a migration nobody can apply.
    SELECT RAISE(ABORT, 'committee_papers: nothing is promoted without a human — record an evidence_promotions row first, via pipeline/promote.py');
END;

CREATE TRIGGER IF NOT EXISTS foi_requests_need_a_promotion
BEFORE INSERT ON foi_requests
FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1 FROM evidence_promotions
    WHERE target_table = 'foi_requests'
      AND target_key = NEW.ons_code || '|' || NEW.request_url)
BEGIN
    -- One literal: SQLite has no implicit string concatenation, and a
    -- migration that will not parse is a migration nobody can apply.
    SELECT RAISE(ABORT, 'foi_requests: nothing is promoted without a human — record an evidence_promotions row first, via pipeline/promote.py');
END;
