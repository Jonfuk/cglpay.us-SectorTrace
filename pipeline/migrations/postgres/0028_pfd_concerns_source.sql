-- Where a report's matters of concern actually came from.
--
-- Three routes now, and they are not equally good evidence:
--
--   rest  the judiciary.uk REST content. Structured, exact, what this module
--         has always used where it was available.
--   pdf   the report PDF's own text layer. Exact, but prose rather than the
--         structured stub, so the redaction has more work to do.
--   ocr   a scan, read by OCR. Legible and searchable, and demonstrably not a
--         faithful transcript -- the first real one produced
--         "TheMATTERSOFCONCERNareasfollows" and invented a full stop in
--         "statutory. duty".
--
-- Recorded because a quotation drawn from this column may end up in a
-- campaign document, and "the coroner wrote this" is a different claim from
-- "a machine read this off a photocopy". Nullable: rows written before this
-- migration predate the distinction, and backfilling them would be inventing
-- provenance rather than recording it.
--
-- PostgreSQL dialect of ../0028_pfd_concerns_source.sql. See README.md in this directory for
-- the conversion rules.
--
ALTER TABLE pfd_reports ADD COLUMN concerns_source text;

CREATE INDEX IF NOT EXISTS idx_pfd_reports_concerns_source
    ON pfd_reports (concerns_source);
