-- Module 0: geography reference spine.
--
-- authorities holds one row per ONS entity code ever observed within the
-- window we track (never reused by ONS once retired, so ons_code is a
-- stable natural key across time). active_to is set once a code is
-- observed missing from a later vintage; NULL means still current.
CREATE TABLE IF NOT EXISTS authorities (
    ons_code            TEXT NOT NULL,
    name                TEXT NOT NULL,
    type                TEXT NOT NULL, -- county | unitary | london_borough | metropolitan_district | non_metropolitan_district
    region_code         TEXT,
    region              TEXT,
    parent_code         TEXT,          -- non_metropolitan_district -> its county's ons_code; else NULL
    active_from         TEXT NOT NULL, -- ISO date of the earliest ONS vintage in which this code was observed
    active_to           TEXT,          -- ISO date of the first ONS vintage in which this code was no longer present; NULL if current
    first_seen_vintage  TEXT NOT NULL,
    last_seen_vintage   TEXT NOT NULL,
    geometry_geojson    TEXT,          -- generalised (BGC) boundary, WGS84; only populated for currently-active codes
    source_url          TEXT NOT NULL,
    retrieved_at         TEXT NOT NULL,
    http_status           INTEGER NOT NULL,
    source_system          TEXT NOT NULL,
    payload_sha256           TEXT NOT NULL,
    PRIMARY KEY (ons_code)
);

CREATE INDEX IF NOT EXISTS idx_authorities_parent ON authorities (parent_code);
CREATE INDEX IF NOT EXISTS idx_authorities_active ON authorities (active_to);

-- Predecessor -> successor edges for local government reorganisation.
-- Populated only when a real geometric overlap was measured between the
-- retiring boundary and the incoming one (constraint 6: never guessed).
-- A predecessor with no row here is a known gap, not a silent collapse —
-- check review_queue (item_type='unresolved_successor') for those.
CREATE TABLE IF NOT EXISTS authority_successors (
    predecessor_code        TEXT NOT NULL,
    successor_code           TEXT NOT NULL,
    overlap_fraction          REAL NOT NULL, -- share of predecessor's area covered by successor's boundary, 0-1
    method                     TEXT NOT NULL, -- how overlap_fraction was derived, e.g. 'geometry_overlap'
    transition_from_vintage    TEXT NOT NULL,
    transition_to_vintage       TEXT NOT NULL,
    source_url                   TEXT NOT NULL,
    retrieved_at                  TEXT NOT NULL,
    http_status                    INTEGER NOT NULL,
    source_system                   TEXT NOT NULL,
    payload_sha256                    TEXT NOT NULL,
    PRIMARY KEY (predecessor_code, successor_code)
);
