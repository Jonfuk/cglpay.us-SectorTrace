-- Module 0: geography reference spine.
--
-- authorities holds one row per ONS entity code ever observed within the
-- window we track (never reused by ONS once retired, so ons_code is a
-- stable natural key across time). active_to is set once a code is
-- observed missing from a later vintage; NULL means still current.
--
-- PostgreSQL dialect of ../0002_geography.sql. See README.md in this directory for
-- the conversion rules.
--
CREATE TABLE IF NOT EXISTS authorities (
    ons_code            text NOT NULL,
    name                text NOT NULL,
    type                text NOT NULL, -- county | unitary | london_borough | metropolitan_district | non_metropolitan_district
    region_code         text,
    region              text,
    parent_code         text,          -- non_metropolitan_district -> its county's ons_code; else NULL
    active_from         text NOT NULL, -- ISO date of the earliest ONS vintage in which this code was observed
    active_to           text,          -- ISO date of the first ONS vintage in which this code was no longer present; NULL if current
    first_seen_vintage  text NOT NULL,
    last_seen_vintage   text NOT NULL,
    geometry_geojson    text,          -- generalised (BGC) boundary, WGS84; only populated for currently-active codes
    source_url          text NOT NULL,
    retrieved_at         text NOT NULL,
    http_status           bigint NOT NULL,
    source_system          text NOT NULL,
    payload_sha256           text NOT NULL,
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
    predecessor_code        text NOT NULL,
    successor_code           text NOT NULL,
    overlap_fraction          double precision NOT NULL, -- share of predecessor's area covered by successor's boundary, 0-1
    method                     text NOT NULL, -- how overlap_fraction was derived, e.g. 'geometry_overlap'
    transition_from_vintage    text NOT NULL,
    transition_to_vintage       text NOT NULL,
    source_url                   text NOT NULL,
    retrieved_at                  text NOT NULL,
    http_status                    bigint NOT NULL,
    source_system                   text NOT NULL,
    payload_sha256                    text NOT NULL,
    PRIMARY KEY (predecessor_code, successor_code)
);
