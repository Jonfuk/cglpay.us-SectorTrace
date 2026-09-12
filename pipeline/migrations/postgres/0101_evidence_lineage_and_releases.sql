-- Centrally owned Phase 2 lineage/release contract. PostgreSQL is canonical;
-- graph projections may be rebuilt from these append-only rows.
CREATE TABLE IF NOT EXISTS lineage_objects (
    lineage_id text PRIMARY KEY,
    object_kind text NOT NULL CHECK (object_kind IN (
        'source', 'retrieval', 'archive_object', 'document_version', 'element',
        'nlp_output', 'claim', 'entity', 'relationship', 'analysis',
        'published_output')),
    canonical_id text NOT NULL,
    source_url text,
    retrieved_at text,
    payload_sha256 text,
    processor_version text,
    metadata_json text NOT NULL DEFAULT '{}',
    restricted bigint NOT NULL DEFAULT 0,
    created_at text NOT NULL,
    UNIQUE (object_kind, canonical_id)
);

CREATE TABLE IF NOT EXISTS lineage_edges (
    lineage_edge_id text PRIMARY KEY,
    generated_lineage_id text NOT NULL REFERENCES lineage_objects(lineage_id),
    used_lineage_id text NOT NULL REFERENCES lineage_objects(lineage_id),
    activity text NOT NULL,
    activity_version text,
    metadata_json text NOT NULL DEFAULT '{}',
    created_at text NOT NULL,
    UNIQUE (generated_lineage_id, used_lineage_id, activity, activity_version)
);

CREATE INDEX IF NOT EXISTS ix_lineage_objects_canonical
    ON lineage_objects (object_kind, canonical_id);
CREATE INDEX IF NOT EXISTS ix_lineage_edges_generated
    ON lineage_edges (generated_lineage_id, created_at);
CREATE INDEX IF NOT EXISTS ix_lineage_edges_used
    ON lineage_edges (used_lineage_id, created_at);

CREATE TABLE IF NOT EXISTS release_manifests (
    release_manifest_id text PRIMARY KEY,
    release_id text NOT NULL REFERENCES analysis_releases(release_id),
    release_kind text NOT NULL CHECK (release_kind IN ('analytical', 'published')),
    output_name text NOT NULL DEFAULT 'analysis',
    git_commit text NOT NULL,
    schema_version text NOT NULL,
    schema_sha256 text NOT NULL,
    warehouse_data_version text NOT NULL,
    source_snapshot_sha256 text NOT NULL,
    archive_manifest_sha256 text NOT NULL,
    nlp_version text NOT NULL,
    ontology_version text NOT NULL,
    rule_version text NOT NULL,
    embedding_model text,
    embedding_dimensions bigint,
    entity_resolution_version text NOT NULL,
    graph_projection_version text NOT NULL,
    model_configuration_sha256 text NOT NULL,
    created_at text NOT NULL,
    output_sha256 text NOT NULL,
    manifest_json text NOT NULL,
    manifest_sha256 text NOT NULL UNIQUE,
    UNIQUE (release_id, release_kind, output_name)
);

CREATE OR REPLACE FUNCTION reject_lineage_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'evidence lineage and release manifests are append-only'
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$;

DROP TRIGGER IF EXISTS lineage_objects_no_update ON lineage_objects;
CREATE TRIGGER lineage_objects_no_update BEFORE UPDATE OR DELETE ON lineage_objects
FOR EACH ROW EXECUTE FUNCTION reject_lineage_mutation();
DROP TRIGGER IF EXISTS lineage_edges_no_update ON lineage_edges;
CREATE TRIGGER lineage_edges_no_update BEFORE UPDATE OR DELETE ON lineage_edges
FOR EACH ROW EXECUTE FUNCTION reject_lineage_mutation();
DROP TRIGGER IF EXISTS release_manifests_no_update ON release_manifests;
CREATE TRIGGER release_manifests_no_update BEFORE UPDATE OR DELETE ON release_manifests
FOR EACH ROW EXECUTE FUNCTION reject_lineage_mutation();

CREATE OR REPLACE VIEW v_evidence_lineage AS
SELECT generated.lineage_id,
       generated.object_kind,
       generated.canonical_id,
       edge.activity,
       edge.activity_version,
       used.lineage_id AS used_lineage_id,
       used.object_kind AS used_object_kind,
       used.canonical_id AS used_canonical_id,
       used.source_url,
       used.retrieved_at,
       used.payload_sha256,
       generated.restricted
FROM lineage_objects generated
LEFT JOIN lineage_edges edge ON edge.generated_lineage_id = generated.lineage_id
LEFT JOIN lineage_objects used ON used.lineage_id = edge.used_lineage_id;
