-- Keep the logical research question stable while allowing changed source
-- bytes to arrive as a new, auditable candidate version.
ALTER TABLE provider_research_items ADD COLUMN stable_candidate_key TEXT;

CREATE INDEX IF NOT EXISTS idx_provider_research_items_stable_key
    ON provider_research_items (stable_candidate_key, created_at);
