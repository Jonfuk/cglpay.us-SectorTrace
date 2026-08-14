-- Module 10: columns the ModernGov search adapter can actually fill.
--
-- The original schema was written before anything had successfully searched a
-- committee system, so it recorded only what a document link would give you.
-- A ModernGov results page publishes more than that, and it publishes it as
-- fact rather than inference: it labels every hit with its own match quality
-- ("Excellent match" / "Good match" / "Average match"), states what kind of
-- record was matched, and prints the agenda item number. Recording those is
-- recording what the source says. Scoring them ourselves would not be.
--
-- match_quality in particular is what makes the review worklist triageable:
-- 'TUPE' and 'public health grant' appear in plenty of papers with nothing to
-- do with drug and alcohol services, and a human confirming candidates needs
-- the source's own ranking to start from.

--
-- PostgreSQL dialect of ../0020_committee_search.sql. See README.md in this directory for
-- the conversion rules.
--
ALTER TABLE committee_paper_candidates ADD COLUMN result_type text;
ALTER TABLE committee_paper_candidates ADD COLUMN match_quality text;
ALTER TABLE committee_paper_candidates ADD COLUMN item_reference text;

-- result_type   what the search system says it matched, not our guess.
--                'agenda_item', 'document' and 'file' come from where the link
--                sits in the results block; the rest are ModernGov's own
--                labels normalised to a shared vocabulary ('meeting',
--                'key_issue', 'decision'), because Kent prints "Issue:" where
--                Kirklees prints "Key issue:". A label this pipeline has not
--                seen before is stored as itself rather than flattened to
--                'other' — a new record type is worth noticing.
-- match_quality 'excellent' | 'good' | 'average' — ModernGov's own three-star
--                label, lower-cased. NULL when the page shows no star image.
-- item_reference the agenda item number as printed ('183.', 'Item5'), so a
--                reviewer can find the item in the pack without guessing.

CREATE INDEX IF NOT EXISTS idx_committee_candidates_quality
    ON committee_paper_candidates (match_quality, verified);

-- One document is routinely found by several search terms: a Darlington
-- scrutiny paper matches both 'drug and alcohol' and 'treatment and
-- recovery'. The candidate row is keyed on (authority, document_url), so a
-- singular matched_term meant the last term to find a document overwrote
-- every earlier one — the fact that three terms agreed was discarded, and
-- discarded invisibly. The column now holds all of them, comma-separated and
-- sorted so re-runs are stable.
--
-- One row per document rather than one per (document, term) is deliberate:
-- the row is a thing for a human to verify, and verifying the same PDF three
-- times because three terms found it is not better evidence, just more work.
ALTER TABLE committee_paper_candidates RENAME COLUMN matched_term TO matched_terms;

-- The matched text ModernGov prints under each hit. It is the single most
-- useful thing for a reviewer deciding whether a candidate is relevant — and
-- it routinely names officers by name and job title ("Presented by <officer>,
-- Head of Health Improvement"). Public role or not, that is personal data, so
-- it lives here rather than in committee_paper_candidates, which is
-- exportable. Same rule as restricted_pfd_report_text.
CREATE TABLE IF NOT EXISTS restricted_committee_result_snippets (
    authority_ons_code   text NOT NULL,
    document_url          text NOT NULL,
    matched_term           text NOT NULL,
    snippet_text            text,
    source_url               text NOT NULL,
    retrieved_at              text NOT NULL,
    http_status                bigint NOT NULL,
    source_system               text NOT NULL,
    payload_sha256               text NOT NULL,
    PRIMARY KEY (authority_ons_code, document_url, matched_term)
);

-- Where a committee URL came from, when it was not in the hand-verified
-- registry. 'homepage_link' means the council's own home page linked to it and
-- the target then answered a ModernGov signature path — two confirmations from
-- the source itself, rather than a guessed hostname.
ALTER TABLE authority_committee_systems ADD COLUMN url_source text;
