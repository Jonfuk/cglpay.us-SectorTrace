-- Decision provenance for human and autonomous evidence promotions.
--
-- `promoted_by` remains the accountable actor label used by existing callers.
-- These fields make an autonomous decision auditable without ever putting a
-- model name into a human reviewer field.
ALTER TABLE evidence_promotions ADD COLUMN actor_type TEXT NOT NULL DEFAULT 'human';
ALTER TABLE evidence_promotions ADD COLUMN actor_id TEXT;
ALTER TABLE evidence_promotions ADD COLUMN model_id TEXT;
ALTER TABLE evidence_promotions ADD COLUMN policy_version TEXT;
ALTER TABLE evidence_promotions ADD COLUMN evidence_manifest_sha256 TEXT;
ALTER TABLE evidence_promotions ADD COLUMN independent_review_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE evidence_promotions ADD COLUMN confidence REAL;
ALTER TABLE evidence_promotions ADD COLUMN qa_status TEXT NOT NULL DEFAULT 'not_required';

CREATE INDEX IF NOT EXISTS idx_evidence_promotions_actor
    ON evidence_promotions (actor_type, promoted_at DESC);

-- Autonomous promotions must carry enough context to be reproducible. Human
-- promotions retain the pre-existing lightweight contract.
CREATE TRIGGER IF NOT EXISTS ai_promotion_requires_provenance
BEFORE INSERT ON evidence_promotions
FOR EACH ROW
WHEN NEW.actor_type = 'ai' AND (
    NEW.actor_id IS NULL OR TRIM(NEW.actor_id) = '' OR
    NEW.model_id IS NULL OR TRIM(NEW.model_id) = '' OR
    NEW.policy_version IS NULL OR TRIM(NEW.policy_version) = '' OR
    NEW.evidence_manifest_sha256 IS NULL OR TRIM(NEW.evidence_manifest_sha256) = '' OR
    NEW.independent_review_count < 2 OR
    NEW.confidence IS NULL OR NEW.confidence < 0 OR NEW.confidence > 1
)
BEGIN
    SELECT RAISE(ABORT, 'AI promotion requires actor, model, policy, manifest, two independent reviews, and confidence');
END;
