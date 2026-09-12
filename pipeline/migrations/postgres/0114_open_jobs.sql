-- Open Jobs shadow collector persistence.
--
-- Open Jobs is a useful operator-side comparison corpus, not a canonical
-- evidence source.  Keep the bytes, their provenance, and the release that
-- selected them separate so a later rebuild can be audited without claiming
-- that a current index is the same thing as a historical one.
--
-- Artifacts, bindings, and event rows are immutable facts.  Generation and
-- release rows have a small lifecycle status so an in-flight collection can
-- be closed explicitly.  `current` and `link_state` are deliberately the two
-- mutable heads: they describe what is selected now and what a link most
-- recently did, while the append-only event stream preserves each transition.

CREATE TABLE IF NOT EXISTS open_jobs_provenance (
    provenance_id       text PRIMARY KEY,
    source_url          text NOT NULL,
    fetched_at          timestamptz NOT NULL,
    payload_sha256      text NOT NULL,
    archived_path       text,
    http_status         integer,
    content_type        text,
    byte_size           bigint,
    metadata_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (payload_sha256 ~ '^[0-9a-fA-F]{64}$'),
    CHECK (byte_size IS NULL OR byte_size >= 0),
    UNIQUE (source_url, payload_sha256)
);

CREATE TABLE IF NOT EXISTS open_jobs_generations (
    generation_id       text PRIMARY KEY,
    source_name         text NOT NULL,
    source_url          text NOT NULL,
    started_at          timestamptz NOT NULL,
    finished_at         timestamptz,
    status              text NOT NULL DEFAULT 'running',
    record_count        bigint,
    error_text          text,
    metadata_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (status IN ('running', 'complete', 'failed', 'partial')),
    CHECK (record_count IS NULL OR record_count >= 0),
    CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE TABLE IF NOT EXISTS open_jobs_releases (
    release_id          text PRIMARY KEY,
    generation_id       text NOT NULL REFERENCES open_jobs_generations(generation_id),
    release_version     text NOT NULL,
    schema_version      text NOT NULL DEFAULT 'v1',
    parent_release      text,
    content_sha256      text,
    expected_rows       bigint,
    status              text NOT NULL DEFAULT 'candidate',
    record_count        bigint,
    manifest_sha256     text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    published_at        timestamptz,
    metadata_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (status IN ('candidate', 'released', 'withdrawn')),
    CHECK (record_count IS NULL OR record_count >= 0),
    CHECK (expected_rows IS NULL OR expected_rows >= 0),
    CHECK (content_sha256 IS NULL OR content_sha256 ~ '^[0-9a-fA-F]{64}$'),
    CHECK (manifest_sha256 IS NULL OR manifest_sha256 ~ '^[0-9a-fA-F]{64}$'),
    CHECK (published_at IS NULL OR published_at >= created_at),
    UNIQUE (generation_id, release_version)
);

CREATE TABLE IF NOT EXISTS open_jobs_artifacts (
    artifact_id         text PRIMARY KEY,
    provenance_id       text NOT NULL REFERENCES open_jobs_provenance(provenance_id),
    artifact_kind       text NOT NULL,
    storage_path        text NOT NULL,
    byte_size           bigint NOT NULL,
    sha256              text NOT NULL,
    content_type        text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    metadata_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (byte_size >= 0),
    CHECK (sha256 ~ '^[0-9a-fA-F]{64}$'),
    UNIQUE (artifact_kind, sha256)
);

-- A release can contain many artifacts and an artifact may be reused by a
-- later release.  A binding is therefore its own immutable relation rather
-- than a release_id column on the artifact row.
CREATE TABLE IF NOT EXISTS open_jobs_bindings (
    binding_id          text PRIMARY KEY,
    release_id          text NOT NULL REFERENCES open_jobs_releases(release_id),
    artifact_id         text NOT NULL REFERENCES open_jobs_artifacts(artifact_id),
    binding_kind        text NOT NULL,
    ordinal             integer,
    created_at          timestamptz NOT NULL DEFAULT now(),
    metadata_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (ordinal IS NULL OR ordinal >= 0),
    UNIQUE (release_id, artifact_id, binding_kind)
);

-- One named head per source.  The row is intentionally mutable; every change
-- must also be represented by an event, which makes a current pointer cheap to
-- read while retaining a complete audit trail.
CREATE TABLE IF NOT EXISTS open_jobs_current (
    current_key         text PRIMARY KEY,
    source_name         text NOT NULL,
    generation_id       text REFERENCES open_jobs_generations(generation_id),
    release_id          text REFERENCES open_jobs_releases(release_id),
    artifact_id         text REFERENCES open_jobs_artifacts(artifact_id),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    metadata_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (generation_id IS NOT NULL OR release_id IS NOT NULL OR artifact_id IS NOT NULL)
);

-- Link availability is an observation about a posting URL, not a reason to
-- delete the posting or mutate a historical artifact.  `state` is kept small
-- and closed so callers cannot accidentally present an unbounded error string
-- as a source-status vocabulary.
CREATE TABLE IF NOT EXISTS open_jobs_link_state (
    link_key            text PRIMARY KEY,
    source_name         text NOT NULL,
    job_key             text NOT NULL,
    link_url            text NOT NULL,
    state               text NOT NULL,
    checked_at          timestamptz NOT NULL,
    http_status         integer,
    error_text          text,
    provenance_id       text REFERENCES open_jobs_provenance(provenance_id),
    metadata_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (state IN ('unknown', 'live', 'gone', 'redirected', 'blocked', 'error')),
    UNIQUE (source_name, job_key)
);

CREATE TABLE IF NOT EXISTS open_jobs_events (
    event_id            text PRIMARY KEY,
    event_type          text NOT NULL,
    entity_type         text NOT NULL,
    entity_id           text NOT NULL,
    generation_id       text REFERENCES open_jobs_generations(generation_id),
    release_id          text REFERENCES open_jobs_releases(release_id),
    occurred_at         timestamptz NOT NULL DEFAULT now(),
    payload_json        jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- The current source-shaped advert is a shadow observation.  It is keyed by
-- the lossless upstream identity rather than by a guessed provider or vacancy
-- id.  Payload fields stay JSON so adding a source column does not force a
-- schema migration or silently discard it; the small lifecycle fields below
-- are only the source contract's explicit operations and removal reasons.
CREATE TABLE IF NOT EXISTS open_jobs_adverts (
    advert_id           text PRIMARY KEY,
    ats                 text NOT NULL,
    slug                text NOT NULL,
    upstream_id         text NOT NULL,
    generation_id       text NOT NULL REFERENCES open_jobs_generations(generation_id),
    release_id          text NOT NULL REFERENCES open_jobs_releases(release_id),
    provenance_id       text NOT NULL REFERENCES open_jobs_provenance(provenance_id),
    operation           text NOT NULL,
    removal_reason      text,
    source_url          text,
    title               text,
    company             text,
    location            text,
    published_at        timestamptz,
    first_seen_at       timestamptz,
    last_seen_at        timestamptz,
    changed_at          timestamptz,
    removed_at          timestamptz,
    payload_json        jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (operation IN ('added', 'changed', 'changed_prev', 'removed', 'carried')),
    CHECK (removal_reason IS NULL OR removal_reason IN ('closed', 'left_dataset', 'unknown')),
    UNIQUE (ats, slug, upstream_id)
);

-- Every source operation remains inspectable after the current row is
-- replaced.  This is the event-shaped record that distinguishes a changed
-- posting from a carried row and a source-reported removal.
CREATE TABLE IF NOT EXISTS open_jobs_advert_events (
    advert_event_id     text PRIMARY KEY,
    ats                 text NOT NULL,
    slug                text NOT NULL,
    upstream_id         text NOT NULL,
    generation_id       text NOT NULL REFERENCES open_jobs_generations(generation_id),
    release_id          text NOT NULL REFERENCES open_jobs_releases(release_id),
    provenance_id       text NOT NULL REFERENCES open_jobs_provenance(provenance_id),
    operation           text NOT NULL,
    removal_reason      text,
    occurred_at         timestamptz NOT NULL DEFAULT now(),
    payload_json        jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (operation IN ('added', 'changed', 'changed_prev', 'removed', 'carried')),
    CHECK (removal_reason IS NULL OR removal_reason IN ('closed', 'left_dataset', 'unknown'))
);

-- Review is a human worklist, separate from both source observations and the
-- repository-wide review_queue.  A row never promotes an advert or provider;
-- it records the question and the exact release/provenance context that needs
-- a person.  Decisions are represented by a new decision event in the
-- append-only `open_jobs_events` stream rather than by erasing this request.
CREATE TABLE IF NOT EXISTS open_jobs_review_queue (
    review_id           text PRIMARY KEY,
    advert_id           text REFERENCES open_jobs_adverts(advert_id),
    review_kind         text NOT NULL,
    ats                 text,
    slug                text,
    upstream_id         text,
    generation_id       text REFERENCES open_jobs_generations(generation_id),
    release_id          text REFERENCES open_jobs_releases(release_id),
    provenance_id       text REFERENCES open_jobs_provenance(provenance_id),
    status              text NOT NULL DEFAULT 'pending',
    reason              text NOT NULL,
    payload_json        jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    resolved_at         timestamptz,
    CHECK (status IN ('pending', 'resolved', 'rejected', 'superseded')),
    CHECK (advert_id IS NOT NULL OR (ats IS NOT NULL AND slug IS NOT NULL AND upstream_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_open_jobs_generations_source_started
    ON open_jobs_generations (source_name, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_open_jobs_releases_generation_created
    ON open_jobs_releases (generation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_open_jobs_artifacts_provenance
    ON open_jobs_artifacts (provenance_id);
CREATE INDEX IF NOT EXISTS idx_open_jobs_bindings_release_ordinal
    ON open_jobs_bindings (release_id, ordinal, binding_id);
CREATE INDEX IF NOT EXISTS idx_open_jobs_current_source
    ON open_jobs_current (source_name);
CREATE INDEX IF NOT EXISTS idx_open_jobs_link_state_source_checked
    ON open_jobs_link_state (source_name, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_open_jobs_events_entity_occurred
    ON open_jobs_events (entity_type, entity_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_open_jobs_events_generation_occurred
    ON open_jobs_events (generation_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_open_jobs_adverts_release
    ON open_jobs_adverts (release_id, ats, slug, upstream_id);
CREATE INDEX IF NOT EXISTS idx_open_jobs_advert_events_key_occurred
    ON open_jobs_advert_events (ats, slug, upstream_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_open_jobs_review_pending
    ON open_jobs_review_queue (status, created_at DESC);

CREATE OR REPLACE FUNCTION reject_open_jobs_immutable_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'open_jobs % rows are append-only', TG_TABLE_NAME
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$;

DROP TRIGGER IF EXISTS open_jobs_provenance_no_update ON open_jobs_provenance;
CREATE TRIGGER open_jobs_provenance_no_update
BEFORE UPDATE OR DELETE ON open_jobs_provenance
FOR EACH ROW EXECUTE FUNCTION reject_open_jobs_immutable_mutation();

DROP TRIGGER IF EXISTS open_jobs_artifacts_no_update ON open_jobs_artifacts;
CREATE TRIGGER open_jobs_artifacts_no_update
BEFORE UPDATE OR DELETE ON open_jobs_artifacts
FOR EACH ROW EXECUTE FUNCTION reject_open_jobs_immutable_mutation();

DROP TRIGGER IF EXISTS open_jobs_bindings_no_update ON open_jobs_bindings;
CREATE TRIGGER open_jobs_bindings_no_update
BEFORE UPDATE OR DELETE ON open_jobs_bindings
FOR EACH ROW EXECUTE FUNCTION reject_open_jobs_immutable_mutation();

DROP TRIGGER IF EXISTS open_jobs_events_no_update ON open_jobs_events;
CREATE TRIGGER open_jobs_events_no_update
BEFORE UPDATE OR DELETE ON open_jobs_events
FOR EACH ROW EXECUTE FUNCTION reject_open_jobs_immutable_mutation();

DROP TRIGGER IF EXISTS open_jobs_advert_events_no_update ON open_jobs_advert_events;
CREATE TRIGGER open_jobs_advert_events_no_update
BEFORE UPDATE OR DELETE ON open_jobs_advert_events
FOR EACH ROW EXECUTE FUNCTION reject_open_jobs_immutable_mutation();
