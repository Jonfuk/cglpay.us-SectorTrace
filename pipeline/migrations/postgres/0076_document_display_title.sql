-- BETA-062: a human-readable display title for a document, with the basis
-- recorded.
--
-- PostgreSQL dialect of ../0076_document_display_title.sql. See README.md in
-- this directory for the conversion rules.
--
-- `display_title` is derived once by a fixed precedence in
-- `pipeline/documents/titles.py`, and `title_basis` records which rung it
-- came from (source_label / pdf_metadata / heading / filename / unknown) so
-- the value stays auditable and is never shown as verbatim source text.
-- Both columns stay unset for existing rows until
-- `pipeline documents backfill-titles` runs.
ALTER TABLE document_records ADD COLUMN display_title text;
ALTER TABLE document_records ADD COLUMN title_basis text;

CREATE INDEX IF NOT EXISTS idx_document_records_title_basis
    ON document_records (title_basis);
