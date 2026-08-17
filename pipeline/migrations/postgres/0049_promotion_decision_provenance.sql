-- PostgreSQL dialect of ../0049_promotion_decision_provenance.sql.
ALTER TABLE evidence_promotions ADD COLUMN IF NOT EXISTS actor_type text NOT NULL DEFAULT 'human';
ALTER TABLE evidence_promotions ADD COLUMN IF NOT EXISTS actor_id text;
ALTER TABLE evidence_promotions ADD COLUMN IF NOT EXISTS model_id text;
ALTER TABLE evidence_promotions ADD COLUMN IF NOT EXISTS policy_version text;
ALTER TABLE evidence_promotions ADD COLUMN IF NOT EXISTS evidence_manifest_sha256 text;
ALTER TABLE evidence_promotions ADD COLUMN IF NOT EXISTS independent_review_count bigint NOT NULL DEFAULT 0;
ALTER TABLE evidence_promotions ADD COLUMN IF NOT EXISTS confidence double precision;
ALTER TABLE evidence_promotions ADD COLUMN IF NOT EXISTS qa_status text NOT NULL DEFAULT 'not_required';

CREATE INDEX IF NOT EXISTS idx_evidence_promotions_actor
    ON evidence_promotions (actor_type, promoted_at DESC);

CREATE OR REPLACE FUNCTION ai_promotion_requires_provenance()
RETURNS trigger AS $$
BEGIN
    IF NEW.actor_type = 'ai' AND (
        NEW.actor_id IS NULL OR btrim(NEW.actor_id) = '' OR
        NEW.model_id IS NULL OR btrim(NEW.model_id) = '' OR
        NEW.policy_version IS NULL OR btrim(NEW.policy_version) = '' OR
        NEW.evidence_manifest_sha256 IS NULL OR btrim(NEW.evidence_manifest_sha256) = '' OR
        NEW.independent_review_count < 2 OR
        NEW.confidence IS NULL OR NEW.confidence < 0 OR NEW.confidence > 1
    ) THEN
        RAISE EXCEPTION 'AI promotion requires actor, model, policy, manifest, two independent reviews, and confidence'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS ai_promotion_requires_provenance ON evidence_promotions;
CREATE TRIGGER ai_promotion_requires_provenance
BEFORE INSERT ON evidence_promotions
FOR EACH ROW EXECUTE FUNCTION ai_promotion_requires_provenance();
