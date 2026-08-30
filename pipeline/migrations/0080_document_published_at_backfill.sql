-- BETA-047: backfill document_records.published_at from the promoted source
-- rows that already carry a real publication date.
--
-- published_at has existed since 0053 (it is even half of
-- idx_document_records_type) but nothing has ever written it:
-- repository.upsert_document() omits the column. Every parsed committee paper
-- and CDP document therefore has published_at IS NULL, which collapses any
-- year-spread check over the document corpus -- the 034G readiness gate
-- (pipeline/nlp/gate.py) reads exactly this column via COALESCE(published_at,
-- retrieved_at) and, with published_at empty, every decided example dates to
-- the week it was fetched.
--
-- The date is not inferred here. committee_papers.meeting_date is the date the
-- paper went to a public committee meeting; cdp_documents.published_date is the
-- publication date the Committee Data Project recorded. Both were captured with
-- full provenance at collection. Rows whose source has no such date stay NULL
-- (settled decision 1: provenance or NULL), so this is safe to re-run.
--
-- source_key was built by pipeline/documents/bridge.py as
-- authority_ons_code || '|' || document_url; the join below reverses that. It
-- is unambiguous -- no source_key maps to two distinct meeting_date values.
--
-- This is a data-only migration: it creates no schema object. Fixing
-- upsert_document so new registrations set published_at at parse time is a
-- separate follow-up (it needs the source date carried on evidence_records or
-- re-joined from the source table, neither of which is in scope here).

UPDATE document_records
SET published_at = (
    SELECT cp.meeting_date
    FROM committee_papers cp
    WHERE cp.authority_ons_code || '|' || cp.document_url = document_records.source_key
)
WHERE source_table = 'committee_papers'
  AND published_at IS NULL
  AND EXISTS (
    SELECT 1
    FROM committee_papers cp
    WHERE cp.authority_ons_code || '|' || cp.document_url = document_records.source_key
      AND cp.meeting_date IS NOT NULL
  );

UPDATE document_records
SET published_at = (
    SELECT cd.published_date
    FROM cdp_documents cd
    WHERE cd.authority_ons_code || '|' || cd.document_url = document_records.source_key
)
WHERE source_table = 'cdp_documents'
  AND published_at IS NULL
  AND EXISTS (
    SELECT 1
    FROM cdp_documents cd
    WHERE cd.authority_ons_code || '|' || cd.document_url = document_records.source_key
      AND cd.published_date IS NOT NULL
  );
