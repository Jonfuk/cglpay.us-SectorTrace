-- performance.md Phase 5 archive-audit gap: the daily sample now actually
-- re-hashes what it samples (rather than only reporting metadata already in
-- `archive_objects`), and a quarterly pass verifies every object. Both
-- record what they checked and what disagreed.
--
-- audit_kind distinguishes the two schedules on the same append-only table
-- rather than a second one, so a single history query still shows drift
-- over time regardless of which pass produced a row. Existing rows predate
-- both columns and are backfilled as the only kind that existed then.
ALTER TABLE archive_audits ADD COLUMN audit_kind text NOT NULL DEFAULT 'daily_sample';
ALTER TABLE archive_audits ADD COLUMN sample_size bigint NOT NULL DEFAULT 0;
ALTER TABLE archive_audits ADD COLUMN verified_mismatches bigint NOT NULL DEFAULT 0;
