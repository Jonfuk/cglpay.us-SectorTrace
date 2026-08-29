-- BETA-056: append-only human alias-resolution decisions.
--
-- Thousands of procurement buyer names and Companies House company names
-- cannot be matched deterministically to an authority or a provider. The
-- resolution is a person picking the right target -- and that pick must be a
-- recorded, named, reversible act, never a fuzzy match silently promoted to
-- canonical identity (settled decision 4).
--
-- One append-only row per decision. A correction is a NEW row that names the
-- one it supersedes; nothing is updated or deleted. `verified_aliases` is the
-- read view: the latest accepted, non-superseded decision per name.

CREATE TABLE IF NOT EXISTS alias_decisions (
    decision_id       TEXT NOT NULL,          -- uuid4 hex
    unmatched_name    TEXT NOT NULL,          -- the name as the source spelled it
    target_scheme     TEXT NOT NULL,          -- 'buyer' (-> authorities) | 'provider'
    canonical_id      TEXT,                   -- ons_code / provider_key; NULL when rejected
    canonical_name    TEXT,                   -- snapshot of the target's name at decision time
    status            TEXT NOT NULL,          -- 'proposed' | 'accepted' | 'rejected' | 'superseded'
    decided_by        TEXT NOT NULL,          -- the reviewer, never defaulted
    reason            TEXT,
    review_item_id    INTEGER,                -- the review_queue item this resolves, if any
    supersedes_id     TEXT,                   -- the alias_decisions row this replaces
    decided_at        TEXT NOT NULL,
    PRIMARY KEY (decision_id)
);

CREATE INDEX IF NOT EXISTS idx_alias_decisions_name
    ON alias_decisions (target_scheme, unmatched_name);

-- The verified-alias registry: the newest accepted decision for a name that
-- no later row supersedes. Deterministic, and it carries who decided it.
CREATE VIEW IF NOT EXISTS verified_aliases AS
SELECT ad.target_scheme, ad.unmatched_name, ad.canonical_id, ad.canonical_name,
       ad.decided_by, ad.decided_at, ad.decision_id
FROM alias_decisions ad
WHERE ad.status = 'accepted'
  AND NOT EXISTS (
        SELECT 1 FROM alias_decisions later
        WHERE later.supersedes_id = ad.decision_id)
  AND ad.decided_at = (
        SELECT MAX(a2.decided_at) FROM alias_decisions a2
        WHERE a2.target_scheme = ad.target_scheme
          AND a2.unmatched_name = ad.unmatched_name
          AND a2.status = 'accepted');
