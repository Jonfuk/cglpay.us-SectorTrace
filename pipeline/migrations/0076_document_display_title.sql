-- BETA-062: a human-readable display title for a document, with the basis
-- recorded.
--
-- `document_records.title` is whatever the collecting module handed the
-- document service: a CDP document's link text (good), an archived object's
-- hash-like filename (useless), or nothing. The portal was rendering
-- `title OR filename`, so a search over the ~27k-document archive returned
-- "a3f91c…pdf" as the name of a result.
--
-- `display_title` is derived once by a fixed precedence in
-- `pipeline/documents/titles.py`, and `title_basis` records which rung it
-- came from so the value stays auditable and is never shown as verbatim
-- source text:
--   source_label  the collecting module's own title
--   pdf_metadata  the PDF's /Title, read during inspection at parse time
--   heading       the first usable heading in the active parsed version
--   filename      a de-slugified archived-object filename (last resort)
--   unknown       nothing usable — the portal keeps its own raw fallback
--
-- Both columns are nullable and stay unset for existing rows until
-- `pipeline documents backfill-titles` runs. The backfill has no
-- `pdf_metadata` for versions parsed before this migration — that rung is
-- only reachable on a reparse — so an old scanned PDF with no source label
-- and no headings resolves to `filename` or `unknown`, which is the honest
-- answer.
ALTER TABLE document_records ADD COLUMN display_title TEXT;
ALTER TABLE document_records ADD COLUMN title_basis TEXT;

CREATE INDEX IF NOT EXISTS idx_document_records_title_basis
    ON document_records (title_basis);
