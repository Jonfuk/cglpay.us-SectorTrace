-- Preserve the reason a model call was unavailable, rejected or returned
-- unusable output. Existing successful call rows remain valid.
ALTER TABLE analysis_model_calls ADD COLUMN error_detail TEXT;
