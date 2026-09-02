-- Transport diagnostics for retry, provider and rate-limit analysis.
ALTER TABLE analysis_model_calls ADD COLUMN provider_id TEXT;
ALTER TABLE analysis_model_calls ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE analysis_model_calls ADD COLUMN status_code INTEGER;
