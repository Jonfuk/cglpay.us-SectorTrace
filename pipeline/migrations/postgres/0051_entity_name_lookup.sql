-- PostgreSQL dialect of ../0051_entity_name_lookup.sql.
-- Canonical names are lookup values, while entity_id / ONS code is identity.

DROP INDEX IF EXISTS idx_entities_type_name;

CREATE INDEX IF NOT EXISTS idx_entities_type_name
    ON entities (entity_type, canonical_name_normalized);
