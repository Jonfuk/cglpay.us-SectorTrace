-- Link model-call provenance to the durable admin run that caused it.
-- Existing rows remain valid and belong to no interactive run.
ALTER TABLE analysis_model_calls ADD COLUMN run_id text;
CREATE INDEX IF NOT EXISTS ix_analysis_model_calls_run ON analysis_model_calls(run_id, created_at);
