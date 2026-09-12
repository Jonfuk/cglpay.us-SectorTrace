-- Module 36: GOV.UK Search API / Content API publication discovery (JON-15).
--
-- DISCOVERY, NOT EXTRACTION, same as 0015 (CDP documents). GOV.UK's own
-- search relevance and its `document_type` vocabulary are both signals
-- towards a candidate's confidence, not a judgement that a document is what
-- it claims to be -- "alcohol" turns up licensing guidance as often as
-- workforce or treatment material, and a policy paper on general practice
-- funding is not evidence about the substance misuse sector merely because
-- DHSC published it. A human confirms every one before it is evidence.
--
-- `publishing_organisation` is a GOV.UK organisation slug
-- (e.g. "department-of-health-and-social-care"), not an ONS code, so unlike
-- cdp_document_candidates there is no foreign key to `authorities` -- these
-- are national publications, not council ones. The admin candidate browser
-- (pipeline/web/candidates.py) already left-joins that column against
-- `authorities` and shows an unresolved name under its own code rather than
-- requiring the join to succeed, so this degrades the same way an authority
-- with no spine entry would.
CREATE TABLE IF NOT EXISTS govuk_document_candidates (
    publishing_organisation  text NOT NULL,
    candidate_url            text NOT NULL,
    content_id               text NOT NULL,
    base_path                text NOT NULL,
    title                    text,
    -- GOV.UK's own content_store document_type (e.g. 'policy_paper',
    -- 'guidance', 'consultation'). Still a guess from this table's point of
    -- view: the reviewer confirms it on promotion, same as cdp_document.
    document_type_guess      text,
    attachment_content_type  text,
    -- 0-1. Counts independent signals (the search hit itself, a
    -- health-relevant publishing organisation, a substantive document type,
    -- a real file attachment) -- a triage aid, never a probability.
    confidence               double precision NOT NULL DEFAULT 0,
    -- Comma-joined keywords that found this attachment; accumulates across
    -- runs the same way m19's data_gov_uk_datasets.matched_terms does.
    matched_terms            text,
    public_updated_at        text,
    first_published_at       text,
    discovered_at            text NOT NULL,
    discovery_method         text,
    verified                 bigint NOT NULL DEFAULT 0,
    verified_at              text,
    rejected                 bigint NOT NULL DEFAULT 0,
    source_url               text NOT NULL,
    retrieved_at             text NOT NULL,
    http_status              bigint NOT NULL,
    source_system            text NOT NULL,
    payload_sha256           text NOT NULL,
    PRIMARY KEY (publishing_organisation, candidate_url)
);

CREATE INDEX IF NOT EXISTS idx_govuk_candidates_verified
    ON govuk_document_candidates (verified, publishing_organisation);

-- Only verified candidates are promoted here, with an archived copy of the
-- actual document -- the candidate's own provenance is a fetch of the GOV.UK
-- Content API page that listed the attachment, never the attachment itself.
CREATE TABLE IF NOT EXISTS govuk_publication_documents (
    publishing_organisation  text NOT NULL,
    document_url             text NOT NULL,
    title                    text,
    document_type            text NOT NULL,   -- confirmed, not guessed
    published_date           text,
    content_id               text,
    base_path                text,
    archived_path            text,
    source_url               text NOT NULL,
    retrieved_at             text NOT NULL,
    http_status              bigint NOT NULL,
    source_system            text NOT NULL,
    payload_sha256           text NOT NULL,
    PRIMARY KEY (publishing_organisation, document_url)
);

-- The fourth refusal alongside the three in 0030: nothing reaches
-- govuk_publication_documents without a recorded evidence_promotions row.
-- Same shape, same ERRCODE, same reasoning -- see 0030 and this directory's
-- README.md for why.
CREATE OR REPLACE FUNCTION govuk_publication_documents_need_a_promotion()
RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM evidence_promotions
        WHERE target_table = 'govuk_publication_documents'
          AND target_key = NEW.publishing_organisation || '|' || NEW.document_url
    ) THEN
        RAISE EXCEPTION 'govuk_publication_documents: nothing is promoted without a human — record an evidence_promotions row first, via pipeline/promote.py'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER govuk_publication_documents_need_a_promotion
BEFORE INSERT ON govuk_publication_documents
FOR EACH ROW
EXECUTE FUNCTION govuk_publication_documents_need_a_promotion();
