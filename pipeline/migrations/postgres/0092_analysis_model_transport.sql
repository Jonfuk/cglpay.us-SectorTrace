-- Transport diagnostics for retry, provider and rate-limit analysis.
ALTER TABLE analysis_model_calls ADD COLUMN provider_id text;
ALTER TABLE analysis_model_calls ADD COLUMN retry_count bigint NOT NULL DEFAULT 0;
ALTER TABLE analysis_model_calls ADD COLUMN status_code bigint;
