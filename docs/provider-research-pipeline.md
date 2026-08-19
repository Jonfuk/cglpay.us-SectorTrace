# Provider research pipeline

Provider research is an additive candidate workflow for the thirteen tracked
providers. A research model or researcher produces a JSON manifest and a
bundle of source files; it never writes directly to a canonical evidence
table.

```text
repository audit
  -> clarification questions and priority scores
  -> provider research manifest + source bundle
  -> schema/archive validation
  -> identity review
  -> evidence review
  -> promotion of cross-cutting findings
  -> provider portal and Sheets export
```

## Manifest and ingestion

The manifest has a `research_run` object and an `items` array. Every item names
one configured `provider_key`, a category and fact type, the question it
answers, the source URL, citation, access date, identity-match basis, evidence
status, destination, and priority. Source-backed findings also name a file in
the source bundle; the ingestion command hashes and archives that file under
`data/raw/provider_research/`.

Validate without writing:

```bash
./start.sh research-ingest research/manifest.json \
  --bundle-dir research/sources --dry-run
```

Ingest candidates and create the two review-queue gates:

```bash
./start.sh research-ingest research/manifest.json \
  --bundle-dir research/sources
```

The same manifest hash is idempotent. A changed source hash produces a new
candidate key and can be compared with the earlier item without overwriting a
decision.

## Review and promotion

Ingestion creates separate `provider_research` review items for identity and
evidence. A reviewer must approve both. The generic review API records the
decision history and mirrors it onto `provider_research_items`; it does not
silently update provider identifiers or existing source-specific tables.

After both decisions are approved, a reviewer may promote the item:

```bash
./start.sh research-promote 123 --promoted-by "Reviewer name"
```

Promoted cross-cutting findings are stored in
`provider_research_evidence`. Findings that belong to Modules 2, 3, 4, 5, 14,
16, 18, 20, 22, 1, or 24 should instead be routed to that module's canonical
candidate/evidence workflow; `destination` records this intended hand-off.

AI output is treated as discovery and extraction. Human review remains the
default for identity and publication. Autonomous promotion is subject to the
existing evidence-promotion provenance requirements.

## Coverage and publication

The coverage matrix is available from the CLI:

```bash
./start.sh research-coverage
```

The admin UI's Provider research tab shows the thirteen-provider matrix,
candidate states, review gates, and promotion actions. Public provider pages
show only promoted findings, with the source citation, identity basis, licence,
and the caveat that the research describes evidence held by the project rather
than everything true about a provider.
Once reviewed, controlled outcomes such as “no evidence currently held”,
“source inaccessible”, “not applicable”, and “already covered by project” are
shown separately; an unreviewed candidate is never public.

The Sheets export adds `11_Provider_Research`. It contains only promoted,
non-superseded cross-cutting findings. Existing module exports remain separate.
