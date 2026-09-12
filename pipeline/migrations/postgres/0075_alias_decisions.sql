-- BETA-056: append-only human alias-resolution decisions.
--
-- PostgreSQL dialect of ../0075_alias_decisions.sql. See README.md in this
-- directory for the conversion rules.
--
-- One append-only row per decision; a correction is a new row naming the one
-- it supersedes. `verified_aliases` is the read view: the latest accepted,
-- non-superseded decision per name. A fuzzy match is never silently promoted
-- to canonical identity (settled decision 4).

CREATE TABLE IF NOT EXISTS alias_decisions (
    decision_id       text NOT NULL,
    unmatched_name    text NOT NULL,
    target_scheme     text NOT NULL,
    canonical_id      text,
    canonical_name    text,
    status            text NOT NULL,
    decided_by        text NOT NULL,
    reason            text,
    review_item_id    bigint,
    supersedes_id     text,
    decided_at        text NOT NULL,
    PRIMARY KEY (decision_id)
);

CREATE INDEX IF NOT EXISTS idx_alias_decisions_name
    ON alias_decisions (target_scheme, unmatched_name);

CREATE OR REPLACE VIEW verified_aliases AS
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
