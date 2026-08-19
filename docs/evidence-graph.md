# Evidence Graph

## Architecture

The warehouse is authoritative. Raw responses remain immutable archive objects.
Parsers and review workflows write structured evidence into SQLite locally or
PostgreSQL in production. `pipeline graph` projects selected graph records into
Neo4j. NetworkX reads bounded warehouse selections and writes only derived,
reproducible metrics into `graph_metrics`.

```text
raw archive -> warehouse evidence/entities/claims/relationships -> Neo4j projection
                                                    -> bounded NetworkX -> graph_metrics
```

Neo4j contains no unique authoritative evidence. Delete SectorTrace-managed
Neo4j nodes and rebuild them from the warehouse whenever recovery is needed.

## Relational model and provenance

Migration `0050_evidence_graph.sql` adds `entities`, `entity_aliases`,
`entity_identifiers`, `evidence_records`, `graph_claims`,
`entity_relationships`, `graph_projection_queue`, `graph_projection_runs`, and
`graph_metrics`. Entity identifiers win over aliases during future entity
resolution. A relationship's `derivation_type` is `SOURCE_FACT`,
`EXTRACTED_CLAIM`, `DERIVED_RELATIONSHIP`, or `ANALYTICAL_SIGNAL`; an inference
can therefore never masquerade as a direct source field.

Use `pipeline.evidence_graph.relationship_provenance(conn, relationship_id)` or
`claim_provenance(conn, claim_id)` to follow a record to source URL, retrieval
time, payload SHA-256, and immutable `raw_object_path`.

## Neo4j model

All canonical nodes carry `:Entity` and a stable `entity_id`; recognised types
also receive labels such as `:Provider`, `:LocalAuthority`, `:Service`,
`:Contract`, and `:Document`. `:Claim` and `:Evidence` use warehouse IDs.
Claims use `:ABOUT` and `:SUPPORTED_BY`; domain edges carry relationship, claim,
evidence, temporal, confidence, and derivation metadata.

Bootstrap creates uniqueness constraints for entity, claim, and evidence IDs,
plus an entity-name index. `--clear` deletes only nodes marked
`sectortrace_managed`, never unrelated Neo4j data.

## Local setup and recovery

```powershell
uv sync --extra graph
$env:NEO4J_PASSWORD = "choose-a-local-secret"
docker compose -f deploy/docker-compose.graph.yml up -d
```

Set `NEO4J_ENABLED=true`, `NEO4J_URI=bolt://localhost:7687`, `NEO4J_USER=neo4j`,
and `NEO4J_PASSWORD` in `.env`, then run:

```powershell
uv run pipeline graph status
uv run pipeline graph rebuild --clear
uv run pipeline graph sync
uv run pipeline graph analyze
```

`rebuild` records a `graph_projection_runs` audit row and exits non-zero on
failure. `sync` consumes only unprocessed queue rows; failures keep their error
and attempt count for retry. If Neo4j is lost, recreate it and run
`rebuild --clear`; no raw archive or warehouse data needs alteration.

## NetworkX analytics

`graph analyze` builds only the authority/provider graph from `COMMISSIONS` and
`AWARDED_TO` records. `GRAPH_MAX_NODES` and `GRAPH_MAX_EDGES` prevent accidental
full-warehouse loads. `observed_counterpart_count` is a distinct observed
counterpart count, `connected_component` is structural membership, and the two
provider centrality metrics describe shared-authority network position. None
measure market share, funding volume, performance, causation, harm, or control.

Every metric includes analysis name/version, graph snapshot, calculation time,
and canonical JSON parameters. Run `python docs/benchmarks/graph_benchmark.py`
for the development-only 10,000-node/50,000-edge benchmark; it is not in CI.

## Railway and hybrid operation

The app Docker image installs the optional graph extra. Deploy the app and
PostgreSQL service as usual; use a separate Neo4j service or managed endpoint
with persistent `/data` storage. Set `NEO4J_ENABLED`, `NEO4J_URI`, `NEO4J_USER`,
`NEO4J_PASSWORD`, and `NEO4J_DATABASE` as Railway variables—never commit them.
Railway should serve the app, PostgreSQL, Neo4j, and small incremental `graph
sync` runs, not full archive reprocessing or large NetworkX jobs.

For heavy work, use a local checkout against a deliberate PostgreSQL target,
perform an explicit warehouse publication using the existing mirror workflow,
then run `graph rebuild` or `graph sync` against the serving endpoint. There is
no automatic bidirectional replication.
