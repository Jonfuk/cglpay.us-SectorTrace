-- Document-level prevalence diagnostics for narrative analysis.
CREATE TABLE IF NOT EXISTS analysis_prevalence_diagnostics (
    prevalence_id text PRIMARY KEY,
    release_id text NOT NULL REFERENCES analysis_releases(release_id),
    domain_id text NOT NULL,
    positives integer NOT NULL,
    negatives integer NOT NULL,
    subjects integer NOT NULL,
    pacc double precision,
    emq double precision,
    continue_exploration integer NOT NULL,
    suppressed integer NOT NULL,
    reason text,
    created_at text NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_analysis_prevalence_release ON analysis_prevalence_diagnostics(release_id, domain_id, created_at);
