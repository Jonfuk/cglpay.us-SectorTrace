-- Core infrastructure tables shared by every module.
-- Applied automatically by pipeline.db.apply_migrations before any module runs.

CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    TEXT PRIMARY KEY,
    applied_at  TEXT NOT NULL
);

-- Constraint 6: fail loudly, never silently guess. A field that could not be
-- parsed is written as NULL and logged here with the raw fragment.
CREATE TABLE IF NOT EXISTS parse_failures (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    module        TEXT NOT NULL,
    source_url    TEXT,
    field_name    TEXT,
    raw_fragment  TEXT,
    reason        TEXT,
    created_at    TEXT NOT NULL
);

-- Anything that requires human judgement before it can be promoted into a
-- canonical table (unmatched buyer names, unverified CDP/committee document
-- candidates, charities whose accounts don't parse cleanly, etc).
CREATE TABLE IF NOT EXISTS review_queue (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    module         TEXT NOT NULL,
    item_type      TEXT NOT NULL,
    raw_value      TEXT NOT NULL,
    context_json   TEXT,
    status         TEXT NOT NULL DEFAULT 'pending',
    created_at     TEXT NOT NULL,
    resolved_at    TEXT
);

-- Constraint 5: idempotent and resumable. Each module persists a cursor
-- (e.g. last publication date processed) so an interrupted run resumes.
CREATE TABLE IF NOT EXISTS module_cursors (
    module        TEXT PRIMARY KEY,
    cursor_value  TEXT,
    updated_at    TEXT NOT NULL
);

-- Constraint 4: conditional requests on re-runs. Keyed by URL so http.py can
-- send If-None-Match / If-Modified-Since without re-fetching unchanged docs.
CREATE TABLE IF NOT EXISTS http_cache (
    url            TEXT PRIMARY KEY,
    host           TEXT NOT NULL,
    etag           TEXT,
    last_modified  TEXT,
    payload_sha256 TEXT,
    updated_at     TEXT NOT NULL
);
