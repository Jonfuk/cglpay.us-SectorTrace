-- OpenAlex post-V1 discovery shadow tables.
--
-- These tables deliberately do not feed public evidence exports. Work metadata
-- is public-shaped; author names, ORCIDs and raw affiliations live only in the
-- restricted authorship table; every relationship remains pending review.
CREATE TABLE IF NOT EXISTS openalex_records (
    entity_type TEXT NOT NULL CHECK (entity_type IN ('work', 'institution', 'funder', 'topic')),
    entity_id TEXT NOT NULL,
    display_name TEXT,
    external_ids_json TEXT NOT NULL DEFAULT '{}',
    payload_json TEXT NOT NULL,
    upstream_updated_at TEXT,
    source_url TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    http_status BIGINT NOT NULL,
    source_system TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    PRIMARY KEY (entity_type, entity_id)
);

CREATE INDEX IF NOT EXISTS ix_openalex_records_type_updated
    ON openalex_records (entity_type, upstream_updated_at);

CREATE TABLE IF NOT EXISTS restricted_openalex_authorships (
    work_id TEXT NOT NULL,
    author_id TEXT NOT NULL,
    author_position BIGINT NOT NULL,
    author_name TEXT,
    orcid TEXT,
    raw_affiliation_strings_json TEXT NOT NULL DEFAULT '[]',
    affiliations_json TEXT NOT NULL DEFAULT '[]',
    payload_json TEXT NOT NULL,
    source_url TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    http_status BIGINT NOT NULL,
    source_system TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    PRIMARY KEY (work_id, author_id, author_position)
);

CREATE INDEX IF NOT EXISTS ix_restricted_openalex_authorships_author
    ON restricted_openalex_authorships (author_id);

CREATE TABLE IF NOT EXISTS openalex_relationship_candidates (
    candidate_id TEXT PRIMARY KEY,
    work_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL CHECK (
        relationship_type IN ('affiliated_with', 'funded_by', 'about_topic')
    ),
    object_type TEXT NOT NULL CHECK (object_type IN ('institution', 'funder', 'topic')),
    object_id TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    confidence DOUBLE PRECISION,
    status TEXT NOT NULL DEFAULT 'pending_review' CHECK (
        status IN ('pending_review', 'accepted', 'rejected')
    ),
    source_url TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    http_status BIGINT NOT NULL,
    source_system TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    UNIQUE (work_id, relationship_type, object_type, object_id)
);

CREATE INDEX IF NOT EXISTS ix_openalex_relationship_candidates_status
    ON openalex_relationship_candidates (status, relationship_type);

CREATE TABLE IF NOT EXISTS openalex_tombstones (
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    reason TEXT NOT NULL,
    source_url TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    PRIMARY KEY (entity_type, entity_id)
);
