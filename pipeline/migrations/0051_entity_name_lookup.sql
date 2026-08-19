-- Canonical names are useful lookup fields, not stable identities.
--
-- ONS boundary history legitimately contains multiple authority codes with
-- the same display name (for example successive North Yorkshire authorities).
-- Stable entity_id/ONS code remains the identity; retaining a name lookup must
-- not make historical rows impossible to project.

DROP INDEX IF EXISTS idx_entities_type_name;

CREATE INDEX IF NOT EXISTS idx_entities_type_name
    ON entities (entity_type, canonical_name_normalized);
