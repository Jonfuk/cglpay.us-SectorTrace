-- Preserve the legacy row identity alongside registered evidence so a later
-- batch worker can recreate the complete EvidenceReference without guessing.
ALTER TABLE evidence_records ADD COLUMN source_table TEXT;
ALTER TABLE evidence_records ADD COLUMN source_key TEXT;
