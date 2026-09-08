# Open Jobs shadow collector

The Open Jobs integration is an operator-only, disabled-by-default source for
secondary vacancy observations and provider discovery. It consumes verified
public diff artifacts through the shared `PipelineHTTPClient`, archives exact
bytes, and writes source-specific observations and review candidates. It does
not replace NHS Jobs, create a canonical vacancy table, or publish advert
descriptions.

Enable the optional reader dependency with `uv sync --extra open-jobs` only on
an operator worker (the beta mirror image installs it at build time). Before
enabling collection, verify the deployed Open Jobs
manifest contract (release anchor, predecessor, part digests, schema and
finality metadata). A contract failure quarantines the release and leaves the
last committed cursor unchanged.

The initial mode is incremental-only. It records the selected feed head and
known coverage gap rather than presenting an incomplete baseline as a census.
Each logical release is staged and validated before current observations and
the feed cursor advance together. Replay is idempotent; `changed_prev`,
`carried`, and removal reasons remain distinct source facts.

Open Jobs rows are excluded from `pipeline/web/public_queries.py`, exports and
the public catalogue. Provider-board bindings, role relevance, geography,
salary parsing and cross-source links remain nullable until a person records a
review decision. See [CAVEATS.md](CAVEATS.md#open-jobs-operator-only-shadow-observations)
for the limits that must travel with any operator report.
