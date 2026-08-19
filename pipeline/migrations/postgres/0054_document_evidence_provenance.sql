-- Preserve the legacy row identity alongside registered evidence so a later
-- batch worker can recreate the complete EvidenceReference without guessing.
ALTER TABLE evidence_records ADD COLUMN IF NOT EXISTS source_table text;
ALTER TABLE evidence_records ADD COLUMN IF NOT EXISTS source_key text;
