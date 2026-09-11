-- Replay protection for Open Jobs append-only advert events.
--
-- 0114 used a per-invocation generation UUID in the event primary key. The
-- collector now reuses the active source generation for ordinary replays and
-- includes the verified release identity in the event key. This constraint is
-- the database backstop for repeated batches within one release.
CREATE UNIQUE INDEX IF NOT EXISTS uq_open_jobs_advert_event_identity
    ON open_jobs_advert_events (
        ats, slug, upstream_id, release_id, operation,
        COALESCE(removal_reason, '')
    );
