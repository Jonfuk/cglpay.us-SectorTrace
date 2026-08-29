# Beta Autonomous Development

## Purpose

This file is the persistent journal, decision record, backlog and
machine-readable work queue for autonomous improvement work on the `beta`
branch, per the "Autonomous Beta Development Agent" brief the project owner
supplied on 2026-08-25. It is designed to survive context loss, session
restarts and hand-off to a different agent: read this file, the queue below,
and `git log`, and continue — do not re-derive product discovery from
scratch.

**Read `docs/upgrade-roadmap.md` too.** It is this project's own pre-existing,
much more detailed planning register (findings F/D/P/U/W/O-##, phases 1–19,
an explicit "Rejected" table and "Open questions"). As of 2026-08-25 every
entry in it has been checked against current code and is accurate (see
BETA-002) — it can now be trusted the way it could not at the start of this
file. Its "Rejected" table in particular records settled product decisions
this session must not re-litigate. What it does *not* cover: anything that
shipped outside its own phase system, which by now is most of the project
(Railway, S3 archive, PostgreSQL mirroring, the Ansible VPS deployment,
`m24`–`m28`, this file's own beta-deployment work). That gap is deliberate,
not a defect — see BETA-002's DONE entry for the reasoning.

## Current Beta Status

- `beta` created 2026-08-25 from `master` at `c1c3ecd`, which already
  includes BETA-001 (see its note on why that one commit is on `master`
  directly, not `beta`). Before this roadmap update, local `beta` and
  `origin/beta` were both at **`b5ff6a9`**, which records the second approved
  front-end refinement programme after BETA-067; see Recent Commits for the
  delivered sequence.
- **BETA-038–049 is complete. Last completed queue item: BETA-067. No
  IN_PROGRESS item: the approved successor programme (BETA-050 through
  BETA-067, delivered in four waves) is complete, as is the original
  BETA-038–049 round. The project owner has approved the next twenty-item
  front-end refinement programme, BETA-068–087, a further nineteen-item
  programme, BETA-088–106, and the seven-item local analyst-assistant
  programme BETA-107–113, but none has been promoted into the execution
  queue.** BETA-028 and
  BETA-029 are DONE
  at `6d1be0e`. BETA-030 was not
  selected for this round and is DEFERRED; BETA-031 is DEFERRED because
  BETA-033 supplied and settled the homepage treatment. BETA-034 is BLOCKED
  pending a successful human-reviewed `pipeline nlp gate-034g` corpus. The
  approved twelve-item round is BETA-038 through BETA-049.
- The project owner approved the revised BETA-068–087 programme after a live
  desktop/mobile review of both front ends and two rounds of item selection.
  It is recorded under Candidate Feature Backlog as an approved, unqueued
  programme. The final selection deliberately excludes the proposed homepage
  hierarchy, public download centre and terminology layer, replacing them
  with focused workforce-pay, treatment-metric and safety/legal explorers.
- The project owner then approved BETA-088–106 after a second audit and three
  selection rounds. This additional programme adds local research continuity,
  change and publication awareness, version and relationship exploration,
  document-table inspection, resilient source access, and deeper read-only
  operator diagnostics. The explicitly rejected reference-network proposal
  is not part of the programme. BETA-068–087 retains execution priority.
- The project owner subsequently approved BETA-107–113 as a third, local-only
  programme: a Needle 2-routed, Liquid Foundation Model analyst assistant over
  existing read-only SectorTrace tools and retrieval. It is approved but
  unqueued **after BETA-068–106**. It authorises an operator finding aid, not
  model-generated evidence, claim publication or a new public API.
- Recent feature commits record the full offline suite green up to **2615
  passed**. BETA-035's earlier documentation run recorded the known flaky
  concurrency timing test once and then passing in isolation. This journal-
  only reconciliation does not claim a new application test run.

## Architectural Summary

Stdlib Python HTTP server (`pipeline/web/server.py`), SQLite by default with
an optional PostgreSQL backend (`DATABASE_URL`), 33 collection modules
(`m00`–`m32`) each writing their own tables, a public evidence portal at `/`
and an operator UI at `/admin`, vanilla JS front ends (no framework, no build
step — see settled decision 6 in `CLAUDE.md`).

PostgreSQL can now opt into managed `pg_trgm`, PostGIS and pgvector
capabilities without changing SQLite's portable path. Trigram matching and
vector ANN acceleration are capability-gated; pgvector backfill is explicit,
not a web-startup side effect. Public GET responses can use the optional
process-local LRU with route-specific TTLs. None of these mechanisms changes
the evidence model or promotes machine-derived material.

**Deployment (updated after BETA-003):** production is **Railway** (per the
project owner directly, and per `docs/DEPLOYMENT.md`'s existing "Somewhere
else: Railway" section — this was already documented, just not cross-checked
against `deploy/ansible/` before this session asked). `deploy/ansible/` is a
separate, real, working self-host build (Debian VPS, Docker Compose:
Postgres, Neo4j, app, Caddy) whose live/fallback/unused status relative to
Railway was **not** asked about — the project owner's answer only confirmed
Railway is production, not what `deploy/ansible/` currently is. Not re-opened
speculatively; ask if it matters for future work.

**`deploy/ansible-mirror/` now builds two things**, chosen by its wizard:
the original disaster-recovery mirror (unchanged: read-only, wiped nightly,
"read it, do not work in it"), and a new **beta deployment** mode
(`mirror_role: beta`) that pins a git branch, seeds its database from
production — including Railway, via the sync path already built for exactly
that ("directly from a PostgreSQL URL") — **once**, and is then left as an
ordinary writable database for testing. See BETA-003's DONE entry. **Not yet
exercised against a real VPS** — this dev environment has no `ansible-playbook`
to run it against; validated statically only (syntax, YAML parse, manual
Jinja review). First real run should be watched by a human, per the brief's
own "reduced testing policy" for infrastructure changes.

## Product Direction

Unchanged from the project's own settled framing (`README.md`, `CLAUDE.md`):
a smaller, defensible evidence base beats a larger, plausible one. This
session found no reason to challenge that, and the original brief's broad
license to "add AI features / entity resolution / new datasets" was
deliberately **not** exercised speculatively — this project already has an
unusually well-reasoned, explicit boundary on exactly those things
(`docs/CAVEATS.md`, `CLAUDE.md` settled decisions 1–10, the roadmap's own
"Rejected" table). Proposing more of that surface without a concrete,
evidenced need would be scope-seeking, not product judgement.

The completed BETA-038–067 programmes kept that boundary while improving
release integrity, evidence discovery, public cataloguing, deterministic
relationships, review workflows, operations and carefully caveated public
evidence.

The approved BETA-068–087 programme now concentrates on making those expanded
capabilities coherent in the two front ends: resilient degradation, responsive
reading, focused pay/treatment/safety exploration, navigable entity and
document workbenches, geographic discovery, evidence-health context and
operator workflows. It adds no dataset or speculative analysis and remains
unqueued until implementation is explicitly started.

The approved BETA-088–106 programme extends that foundation into a research
workspace: local notebooks and alerts, visible source/release change, record
comparison, relationship paths, careful co-occurrence/discrepancy views,
contract and document inspection, and operator-side run, parser, validation
and review-quality tools. It is also approved but unqueued and does not
displace BETA-068–087.

The approved BETA-107–113 programme then adds a deliberately narrow local
analyst assistant: Needle 2 chooses one read-only tool, and LFM explains only
the public evidence that tool returns with validated citations. It follows
BETA-068–106 and leaves collection, evidence status, human review and public
interfaces unchanged.

## Comparable Product Research (2026-08-26, per the project owner's request)

Asked directly to "explore competing products to ensure my project is
competitive." Before researching externally, re-read `docs/upgrade-roadmap.md`
§3J ("Possible future") and §6 ("Rejected") in full — this project already
ran a comparable-product review (explicitly against WhatDoTheyKnow, LG
Inform, and Fingertips) and filed the results with reasoning, several
already declined or deferred for principled reasons (peer-group
benchmarking, significance-aware colouring, trend markers, tartan-rug
matrix views). Re-proposing any of those without new evidence would be
re-litigating a settled call, which the brief itself warns against. What
follows is additive to that, not a repeat of it.

**OCCRP Aleph** (investigative data platform, ~250 datasets, entity-based
cross-referencing across leaks/registries/financial records — [GIJN
tutorial](https://gijn.org/stories/aleph-pro-tutorial-occrp-updated-investigative-data-platform/)):
its two headline features are entity cross-referencing and document search.
This project already does the first, deterministically and conservatively
(the relationship explorer, BETA-010; `docs/CAVEATS.md`'s own
`name_only_unconfirmed` discipline is stricter than Aleph's own matching,
by design). It did not do the second — **this was the finding that led to
BETA-022** (see its DONE entry): the search backend already existed
(`pipeline/documents/`), unexposed.

**Tussell** (UK public-procurement intelligence — tenders, frameworks,
spend, supplier risk): most of its differentiators are either already
covered by this project's own caveats (the framework/call-off ceiling-value
warning `contracts.js` already pins) or are exactly the kind of inference
this project has already declined for principled reasons — peer
benchmarking (Phase 13: deferred, "the compare view is the honest
replacement for a peer group"), market alerts (SSE/WebSockets rejected,
§6). Nothing here changed a decision; it confirmed the existing ones are
not naive.

**A union-specific comparator** (Unite's own "Work, Voice, Pay Monthly" —
the closest thing to a direct competitor, published by the same union
whose deck this project's demographic pay data was verified against) was
bot-blocked from fetching, the same wall LittleSis and OpenSecrets hit
earlier in this session and OpenSanctions/LittleSis hit in an earlier one.
Not investigated further — a pattern worth noting (three of four attempted
fetches this cycle were blocked), not a finding in itself.

**Conclusion:** no new feature category emerged that this project has not
already considered and either built, deferred, or declined with reasoning.
The one concrete, evidenced gap — document search — was not a "which
comparable product should I copy" finding so much as "this project already
has the infrastructure a comparable product would need, and never exposed
it." That is the more valuable kind of finding this exercise could produce,
and it is why BETA-022 is the direct result of this research rather than a
coincidence.

### Successor-round source and pattern check (2026-08-29)

- The official [OCDS reference](https://standard.open-contracting.org/latest/en/schema/reference/)
  and [Find a Tender developer documentation](https://www.find-tender.service.gov.uk/Developer/Documentation)
  confirm OCID as the stable link across related releases and expose explicit
  lifecycle/performance notice fields. That supports BETA-050's lifecycle,
  but not an inferred completion or performance judgement.
- The official [HSE enforcement-notice register](https://resources.hse.gov.uk/notices/Notice/default.asp)
  publishes organisation-level improvement/prohibition notices with stated
  scope and status limitations. BETA-051 therefore treats it as attributed
  safety/legal evidence, limits publication to exact tracked-organisation
  matches and excludes individuals.
- The remaining selected review, operations and public-interface items were
  traced to concrete repository gaps: raw `context_json`, browser-only job
  history, a point-in-time archive size scan, hash-like document titles, the
  deliberately omitted H-CLIC TA1 B&B breakdown, unexposed CQC coordinates,
  existing provider successor data and stale committee-system documentation.
  No discarded idea was reintroduced under a new name.

## Strategic Reassessment (§52, run 2026-08-26 — the reassessment BETA-026's close-out flagged as owed)

Run after four consecutive narrow front-end items (BETA-023–026), i.e. the
top of §52's own 3–6-item window. Each §52 question was checked against the
actual code this cycle, not against memory:

1. **Is the roadmap still sensible?** The *discipline* is sound (every item
   shipped vertical, tested, documented), but item *selection* had drifted
   narrow: impacts ran 4 → 2 → 3 → 1. The project owner then removed the
   ambiguity directly: front-end web UI improvements are the priority, and
   the release needs to "really amaze end users". Correction applied: the
   queue below is repopulated with impact ≥ 3 front-end items only.
2. **Has the architecture changed what is now possible?** Yes, twice.
   Document full-text search (BETA-022–026) exists behind one public
   endpoint, and the portal already fetches the full authorities and
   providers lists at boot (`initFindCouncil`/`initFilterBar`, both cached
   by `fetchJSON`). A unified search surface — the one thing comparable
   platforms (Aleph above all) treat as the front door — is now nearly
   free in data terms. It did not exist as an option before this cycle.
3. **Over-investing in one subsystem?** Yes — four items in a row on
   document search. Search is now the portal's most-polished surface;
   every other surface got nothing this cycle.
4. **Neglected high-value part?** Two, both checked in code:
   - The **map page is the one page that half-breaks settled decision 6**
     ("both front ends must render with the network cable unplugged").
     `geography.js:25` loads the basemap style from
     `basemaps.cartocdn.com` — a *deliberate, documented* exception (CSP
     allowlists it in `server.py:183-185`; `tests/test_web_layers.py:253`
     pins the URLs), not an oversight. But with no network the style fetch
     fails, MapLibre never fires `load`, and the choropleth layers are
     never added: the reader gets the text alternative only, not a map.
     index.html's own header comment ("makes no external requests") is
     true of every asset and false of this one page's basemap. A local
     fallback style would honour the promise without taking the basemap
     away from online readers. Queued as BETA-028.
   - The **homepage downloads 500 notice rows to draw a 10-bar chart**
     (`overview.js` calls `contracts?limit=500`; `value_concentration` is
     computed server-side over the whole corpus; `provenance()` dedupes and
     shows at most 6 URLs). The payload is the page's single biggest
     transfer and 98% of it is unused. Queued as BETA-029 — also the first
     performance-section entry in three cycles.
   - The admin UI remains untouched this whole session — real, but
     deliberately deferred *again* by the owner's explicit "end users
     first" steer. Kept visible in the backlog, not forgotten.
5. **Comparable systems revealing a major gap?** No new category emerged
   beyond what the 2026-08-26 research recorded. The applicable
   un-emulated pattern is unified search as the front door — see (2).
6. **Technical debt constraining?** No new constraint found. The deferred
   nits (inline hex literals in map/graph code, claims-page filter) remain
   as recorded in Deferred Ideas.
7. **Users able to actually discover functionality?** Re-checked the way
   BETA-017 did: document search (nav + homepage tile + noscript + /api),
   comparators (authority page), relationships (nav) — all discoverable.
   The remaining gap is *between* surfaces: three separate search boxes
   (find-council, provider filter, document page) and no way to search
   across them. That is a discoverability finding, not just a feature
   request, and it is what BETA-027 addresses.
8. **Data additions outpacing understanding?** No — no new datasets this
   cycle; coverage and health surfaces keep pace.
9. **Queue dominated by low-impact work?** Yes — see (1). This
   reassessment's main correction.

**Direction set for the next cycle:** front-end, high-impact, end-user
facing, within the settled constraints (no build step, no new vendor
dependencies, text-node DOM discipline, caveats discipline). BETA-027 is
the flagship; BETA-028/029 make the portal's own documented promises true;
BETA-030 is the first researcher-delight item; BETA-031 researches the
homepage's first impression with a live browser before touching it.

## Autonomous Work Queue

<!--
AUTONOMOUS_QUEUE_VERSION: 1
This section is intentionally structured for machine parsing.
Do not remove the status prefixes.
Valid states:
NEXT
IN_PROGRESS
BLOCKED
READY
RESEARCH
DEFERRED
DONE
-->

### IN_PROGRESS

_(Empty. The first and second front-end refinement programmes
(BETA-068–106) and the local analyst-assistant programme (BETA-107) are all
complete — see DONE. Nothing is queued.)_

### BLOCKED

- [BLOCKED] BETA-034 | Semantic-analysis layer (pipeline/nlp): evidence-intelligence over the archive
  - started: 2026-08-27
  - priority: P2
  - impact: 5
  - effort: 5
  - confidence: 3
  - risk: 3
  - area: nlp/pipeline
  - depends_on: pipeline/documents (document_elements), pipeline/graph (graph_claims)
  - blocked_by: A successful human-review corpus reported by
    `pipeline nlp gate-034g`; current code makes the gate measurable but
    cannot substitute for named reviewers and representative decisions.
  - resume_when: Every gate category meets its positive/negative, source,
    subject, year-spread, held-out and inter-reviewer-agreement thresholds.
  - alternative_work_available: BETA-038 through BETA-049 can proceed without
    weakening or bypassing this gate.
  - origin: **Not drawn from this queue.** Project owner via `/plan` on
    2026-08-27, after two rounds of steering (clinical-NLP vs
    evidence-intelligence framing; then a detailed pre-implementation
    review). The approved plan and the authoritative design live in
    `docs/semantic-analysis.md`; the plan file is
    `~/.claude/plans/tranquil-riding-reddy.md`.
  - objective: A downstream, local-only, non-collecting stage that makes the
    ~27k-document archive semantically searchable and connects extracted
    claims into the Evidence Graph — every derived statement a finding aid
    or a machine candidate until a person promotes it through the existing
    review queue → `graph_claims` path. Staged A–H; ship and stop per
    letter.
  - current_state: **034A–034F and the read-only 034G gate checker are complete
    on `beta`; 034G training and 034H remain gated.** The latest resolver
    batching work is `194ea33`. PostgreSQL semantic search now also has the
    pgvector follow-up series: `c8d43fb` (ANN search/index), `1a1118e` (serial
    HNSW build) and `777828a` (explicit backfill, removed from web startup).
    These improve execution but do not satisfy the human-review gate. 034F
    still withholds the `graph_claims` write — see `context_034f_graph`.
    034A — the foundation (migration `0065` — `nlp_runs`,
    `nlp_model_registry`, `document_chunks`, `document_embeddings`;
    `pipeline/nlp/{runs,models,chunk}.py`; `pipeline nlp chunk`) plus the
    remainder: `pipeline/nlp/embeddings.py` (deterministic `stub` embedder —
    signed hashed BoW, no download, CI default — and sentence-transformers
    behind the new `nlp` extra, lazy import, revision-SHA recorded);
    `pipeline/nlp/semantic_search.py` (keyword = existing FTS lifted
    element→chunk; semantic = Python-side exact cosine; hybrid = RRF k=60,
    degrades to keyword-only without embeddings; `source_system`/date
    pre-filters); `/api/admin/search?mode=…` via `pipeline/web/semantic.py`
    (adapter turning `SearchError` into the handler's `QueryError`→400;
    `/api/v1/*` untouched, pinned by `test_portal_isolation.py`);
    `pipeline nlp {embed,search,eval-retrieval}`; `pipeline/nlp/eval.py` +
    `tests/fixtures/nlp/retrieval_queries.json` (Recall@5/10, MRR,
    nDCG@5/10 over marked queries). `nlp_embed_batch_size` setting.
    034B — `pipeline/nlp/ontology/` — `concepts.yml` (~80 concepts:
    substances, medications, treatments, services, roles,
    workforce-pressure conditions, finance, commissioning, outcomes,
    generic provider/commissioner types; stable dotted ids, plural
    `categories`, `pressure` marker category), `relations.yml` (~30 closed
    predicates with `subject`/`object`/`pressure`),
    `patterns/workforce_pressure.yml` + `patterns/README.md` (regex seeds
    for 034C/F, not run by the loader). `pipeline/nlp/ontology.py` — load +
    validate (unique ids, category/related/predicate refs resolve, unsafe
    aliases) + content-hashed `ontology_version` + m28-idiom whole-token
    matcher with a shallow `-s` plural fold. `pyyaml` added as a **base
    dependency** (not an extra): the vocabulary is hand-maintained so YAML
    (comments, no quoting) beats JSON, and 034C's always-on classifier
    consumes it — mirrors the `rich` call, was already present
    transitively.
    034C — `pipeline/nlp/label.py` + `pipeline nlp label`: runs the 034B
    matcher over each non-superseded chunk's elements and writes provisional
    `document_topics` rows with `match_method='ontology_v1'` — a row per
    concept (`topic=<concept_id>`, `match_count`=distinct alias spans) plus a
    `cat:<category>` rollup row. Records `ontology_version` on the run;
    idempotent (deletes/rewrites only its own `ontology_v1` rows). `keyword_v1`
    left untouched — `classify.TOPICS` frozen with a docstring saying so and
    pointing at the ontology as authoritative; deliberately **not**
    code-coupled (a collection run needs nothing from the nlp layer), so the
    "one vocabulary" guarantee is that new terms only ever go in the ontology.
    034D — migration `0066` (`document_concept_mentions`, both trees; `REAL`
    -> `double precision` the only dialect change). `pipeline/nlp/spans.py` +
    `pipeline nlp spans`: span-level entity extraction into
    `document_concept_mentions` — an offline `stub` (regex over the 034B
    ontology's SUBSTANCE/TREATMENT/ROLE/SERVICE/COMMISSIONER concepts +
    `SUPPLIER_NAME_VARIANTS` as PROVIDER; `extraction_score` 1.0; no
    LOCATION/PROGRAMME/novel names) and `gliner` (lazy, `nlp` extra, full
    label set, `concept_id` always NULL). `extraction_score` typed so it
    can't read as P(true); the table never carries `entity_id`.
    `pipeline/nlp/resolve.py` + `pipeline nlp resolve` — the separate
    deterministic step: exact normalised PROVIDER-variant match →
    `provider:<key>` entity (when `graph backfill` seeded it) →
    `document_entity_mentions` (`match_method='<extractor>+alias'`);
    COMMISSIONER → `LOCAL_AUTHORITY` entity by canonical name; anything
    weaker stays a lead. `pipeline/nlp/spans_eval.py` +
    `tests/fixtures/nlp/gold_spans.json` (P/R/F1 per label; 4-entry seed) +
    `pipeline nlp eval-spans`. `gliner` added to the `nlp` extra.
    034E — migration `0067` (`document_assertions`, both trees). `pipeline/nlp/context.py`
    + `pipeline nlp context`: one assertion row per span — `AFFIRMED` /
    `NEGATED` / `HISTORICAL` / `HYPOTHETICAL` / `CONDITIONAL` / `THIRD_PARTY`
    / `UNKNOWN` (UNKNOWN only when the sentence can't be located). Always-on
    stdlib `cue` tagger: regex cue families with a direction + scope window,
    termination words break scope, precedence NEGATED > HISTORICAL >
    HYPOTHETICAL > CONDITIONAL > THIRD_PARTY. `assertion_status` /
    `detector_confidence` separate columns; `cue_start`/`cue_end`/
    `sentence_sha256` pin the call. medSpaCy `ConText` is a lazy optional
    path, **not added to the `nlp` extra** — spaCy pipeline models don't
    install as clean deps; deferred with a note. `pipeline/nlp/context_eval.py`
    + `tests/fixtures/nlp/assertion_cases.json` (15-case seed, 5 hard
    negatives, all passing at 1.0) + `pipeline nlp eval-context`.
    `tests/test_nlp_context.py` + migration-count bump (66→67) green;
    `ruff` clean.
    034F (first cut) — migration `0068` (`document_claim_candidates` +
    `claim_candidate_decisions`, both trees; the decisions table's
    AUTOINCREMENT → `bigint GENERATED BY DEFAULT AS IDENTITY`).
    `pipeline/nlp/relations.py` + `pipeline nlp relations`: (subject,
    predicate, object) triples from 034D spans + 034E assertions via a
    controlled `CONCEPT_PREDICATE` map or a `patterns/*.yml` predicate
    pattern — never co-occurrence. Subject = the org the claim is about
    (workforce claims take PROVIDER/COMMISSIONER, ROLE is context), with
    documented fallbacks + `subject_hint` anaphora; assertion taken at the
    trigger, not the subject. `relation_score` ranks for review only.
    `ontology.match_spans()` added (char-offset concept matching).
    `pipeline/nlp/promote.py` + `pipeline nlp queue-claims`: the narrow
    policy — primary (campaign predicate + score floor + AFFIRMED + resolved
    subject entity), contradiction, novel, deterministic validation sample —
    writes `review_queue` `semantic_claim_candidate` items with full
    `context_json` and marks candidates `queued`. `tests/test_nlp_{relations,promote}.py`
    + migration-count bump (67→68) green; `ruff` clean. No new dependency.
    034F (second cut, scoped by owner to "decisions table only") —
    `pipeline/nlp/decisions.py` + `pipeline nlp decide-claim`:
    `decide(conn, candidate_id, approved|rejected|corrected, decided_by, …)`
    writes a `claim_candidate_decisions` row and moves the candidate to
    `accepted` / `dismissed`. A `corrected` decision requires (and validates
    against the ontology) a better `corrected_predicate` /
    `corrected_object_concept_id` / `corrected_object_literal` /
    `corrected_subject_mention_id` + `reason_code` — the 034G training signal;
    `decisions.training_export()` joins the verdict to the triple.
    `decided_by` never defaulted. `graph_claim_id` stays NULL — **no
    `graph_claims` draft is written**. `tests/test_nlp_decisions.py` green.
    034G gate-checker — `pipeline/nlp/gate.py` + `pipeline nlp gate-034g`:
    read-only report over `claim_candidate_decisions`, per classifier
    category (recruitment_pressure / pay_concern / high_caseload /
    funding_reduction / access_problem): decided +/- counts, source /
    distinct-subject / year spread, inter-reviewer agreement, and a
    `blocking` list. Exits non-zero until every condition holds. Thresholds
    are parameters (module constants as defaults). `tests/test_nlp_gate.py`
    green. This makes the 034G gate measurable; closing it is reviewer
    labour, not code.
  - context_034f_graph: `graph_claims` has **no writer anywhere in
    `pipeline/`** — a dormant schema (migration `0050`) with
    `evidence_graph.claim_provenance()` and the Neo4j projector, but nothing
    inserts it and there is no draft → `entity_relationships`
    (`EXTRACTED_CLAIM`) lifecycle. Being its first writer is a standalone
    decision the owner has parked; the approved-candidate → draft step is
    NOT scheduled. When taken it must set the detector in
    `extractor_name`/`extractor_version`, leave `confidence` for the
    reviewer, `review_status='draft'`, never `promoted_by`.
  - next_action: Keep this item BLOCKED while reviewers build the corpus;
    rerun `pipeline nlp gate-034g` after each review tranche. **034G**
    (SetFit few-shot classifiers) is **gated**;
    `pipeline nlp gate-034g` now reports exactly how far off it is. Closing
    the gate is reviewer labour: (a) `uv sync --extra nlp` and run the chain
    on the live warehouse with a real embedder + `--extractor gliner`;
    (b) work the `semantic_claim_candidate` queue with `decide-claim`,
    favouring `corrected` over bare `reject`, until `gate-034g` exits 0
    (~50 pos + ~50 neg + a held-out margin per category, source/subject/year
    spread, ≥10 double-reviewed at ≥0.8 agreement). Only then is the SetFit
    build (setfit into the `nlp` extra; one binary head per category over
    chunk embeddings; predictions to a new versioned table with a confidence
    column; a min-precision gate before any prediction is written) worth
    doing. **034H** active learning and BERTopic remain gated/deferred. The
    owner has made the separate named decision for a local, read-only RAG
    finding aid only, fully specified as BETA-107–113; it does not authorise
    LLM-derived claims or weaken this item's human-review gate. Still open
    regardless: the `graph_claims`
    wiring decision above; browser-verify `/api/admin/search`; grow
    `retrieval_queries.json` / `gold_spans.json` / `assertion_cases.json`
    from the live warehouse; decide on medSpaCy; admin-UI surfaces for
    search / topics / mentions / the claim-candidate worklist.
  - validation_remaining: The later PostgreSQL/search series recorded the full
    offline suite green up to 2615 passed. Still outstanding: build and review
    the live representative corpus until `gate-034g` succeeds; browser-verify
    admin semantic search; expand the evaluation fixtures from live data; and
    exercise the extension paths against a disposable PostgreSQL instance.

### NEXT

_(empty — the approved BETA-068–087 programme has not yet been promoted.)_

### READY

_(empty — use the delivery sequence in the approved BETA-068–087 subsection
when the programme is started.)_

### DEFERRED

- [DEFERRED] BETA-030 | Copy-citation button in the provenance drawer
  - priority: P2
  - impact: 4
  - effort: 2
  - confidence: 4
  - risk: 1
  - area: ui
  - depends_on: none
  - objective: A "copy citation" control beside the provenance drawer's
    source links, putting title, source URL, retrieval date and licence
    on the clipboard in one action — the researcher's most common manual
    step, made one click. Uses navigator.clipboard with a fallback;
    degrades to invisible when neither is available.
  - deferred_reason: Not selected for the approved 2026-08-29 round; retain as
    a bounded future convenience rather than displacing higher-impact work.
  - reconsider_when: The BETA-038–049 round is complete or user research makes
    citation-copy friction a demonstrated priority.

- [DEFERRED] BETA-031 | Homepage first impression: is the hero earning its place?
  - priority: P2
  - question: The overview hero is deliberately conservative (its own
    header comment explains why two requested headline numbers are
    refused). Within that discipline, would a compact England coverage
    visual (boundaries payload, reusing the geography page's palette) in
    the hero measurably improve a first-time reader's understanding of
    what this portal is — or is it decoration? Needs eyeballing live in
    a browser before building; static review cannot answer it.
  - research_needed: A live look at the current homepage at desktop and
    mobile widths, then a judgement call on whether a data visual in the
    hero adds comprehension or just pixels. The "mind blowing" steer is
    satisfied by clarity plus speed, not by animation; count-up numbers
    on evidence figures were considered and rejected as theatre.
  - deferred_reason: Superseded by the BETA-033 homepage hero, region map and
    motion treatment; the original research question has been answered in
    shipped work.
  - reconsider_when: New user evidence identifies a concrete comprehension
    problem that BETA-033 did not solve.

### DONE

- [DONE] BETA-108 | Assistant provenance and run ledger
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 3
  - confidence: 5
  - risk: 2
  - area: nlp/assistant/provenance
  - depends_on: BETA-058, BETA-107
  - objective: Equivalent SQLite/PostgreSQL storage for one immutable
    assistant run: request and filters, Needle/LFM identities, prompt-template
    hashes, routing confidence and validated arguments, retrieved chunk IDs,
    answer and citation IDs, timings, outcome and error class.
  - result: New migration `0079_assistant_runs.sql` (+ postgres twin) — one
    `assistant_runs` table, append-only by the same discipline as
    `alias_decisions` (0075) and `qc_sample_findings` (0078), plus a
    `created_at` index. Columns: `run_id`, `created_at`, `code_commit`,
    `question`, `filters_json`, `needle_model` / `needle_endpoint`,
    `lfm_model` / `lfm_quant` / `lfm_endpoint`, `router_prompt_sha256` /
    `answer_prompt_sha256`, `selected_tool`, `routing_confidence`,
    `tool_args_json`, `retrieved_chunk_ids`, `answer`, `citation_ids_json`,
    `timings_json`, `outcome`
    (`ok|abstained|clarified|timeout|failed|unavailable`), `error_class`. No
    secrets, API keys or model file paths — only identities and hashes. New
    `pipeline/assistant/ledger.py`: `record()` INSERTs one row (there is no
    UPDATE/DELETE path; a `**rejected` kwarg catch raises on a credential /
    model-path key and logs anything else), returns the `run_id` or `None` on
    a write failure (a lost audit row must not lose a good answer, as with
    `run_ledger`); `one()` / `recent()` read back with the JSON columns
    parsed.
  - api/ui: none directly — written by BETA-112's service, read by
    `one()` / `recent()`.
  - validation: New `tests/test_assistant_ledger.py` (6 — a row round-trips
    with JSON columns parsed; every one of the six outcomes is recordable and
    an unknown one coerces to `failed`; `recent` is newest-first; a
    credential or model-path kwarg raises `ValueError`; the module contains no
    `UPDATE`/`DELETE` of the table; a dropped table makes `record` return
    `None` not raise). `tests/test_migration_equivalence.py` updated for the
    79th migration.

- [DONE] BETA-107 | Optional Needle 2 and LFM assistant runtimes
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 3
  - area: nlp/assistant/runtime
  - depends_on: BETA-034, BETA-046
  - objective: Add an `assistant` optional dependency/runtime boundary with a
    pinned Needle 2 adapter and an OpenAI-compatible local Ollama adapter for
    pinned `LiquidAI/LFM2.5-1.2B-Instruct` Q4_K_M; both disabled by default,
    excluded from Railway and loaded lazily on the local analysis host.
  - result: New `[project.optional-dependencies] assistant = ["openai>=1.40,<2"]`
    in `pyproject.toml` (locked; `uv.lock` updated) — the only pin, the
    client for both `/v1` endpoints. New `pipeline/assistant/` package that
    **imports with none of it installed**: `runtime.py` holds the pinned
    `LFM_MODEL` / `LFM_QUANT` constants, `AssistantUnavailable` (the one
    exception the package raises — never a bare `ImportError` or socket
    error), `openai_client_installed()` (via `find_spec`, so the check never
    imports it), `is_enabled()`, `require_enabled()` and
    `runtime_status(settings)` which reports enabled / installed / endpoints
    / model **without contacting anything**. `adapters.py` has
    `_OpenAICompatAdapter` (chat-completions over an OpenAI-compatible base
    URL; the `openai` import and the client build are lazy, inside
    `generate()`), `LFMOllamaAdapter` (local Ollama serving the LFM at
    `assistant_ollama_url`), `NeedleAdapter` (Needle 2 at
    `assistant_needle_url`), and `get_adapter(name, settings)` which
    `require_enabled()`s first. A refused connection or an un-pulled model
    surfaces as `AssistantUnavailable`, not a crash. New `Settings` fields:
    `assistant_enabled = False`, `assistant_ollama_url`,
    `assistant_needle_url`. The `Dockerfile` comment now states the extra
    list is closed and `assistant` is deliberately not installed there; a
    test pins `--extra assistant` out of the image. New read-only admin
    route `/api/admin/assistant` returning `runtime_status`.
  - api/ui: additive `/api/admin/assistant` (GET, no side effects). No UI
    panel — this is a runtime boundary, not an operator feature; the status
    endpoint is the observable surface.
  - validation: New `tests/test_assistant_boundary.py` (8, 1 skipped without
    the extra — the package imports with nothing installed; `runtime_status`
    is off by default, names the pinned model + quant, and its note says no
    endpoint was contacted; `get_adapter` raises `AssistantUnavailable` while
    the layer is disabled and, when enabled without the extra, still raises
    `AssistantUnavailable` not `ImportError`; a dead endpoint surfaces as
    `AssistantUnavailable` (skipped unless `openai` is present); an unknown
    adapter name is rejected; the extra is declared with `openai` and kept
    out of the Docker image; the admin route reports the status).
    `test_config` / `test_docs_coverage` / `test_web_admin` /
    `test_portal_isolation` green; `ruff` clean; the offline suite is
    unchanged with `openai` absent (as it is in CI). Browser/curl-verified:
    `/api/admin/assistant` returns `{enabled:false, ready:false, model:{id:
    "LiquidAI/LFM2.5-1.2B-Instruct", quant:"Q4_K_M"}, adapters:{lfm-ollama,
    needle-2}}` with the "no endpoint was contacted" note.

- [DONE] BETA-106 | Quality-control sampling workspace
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 5
  - confidence: 3
  - risk: 4
  - area: admin/review quality
  - depends_on: BETA-052, BETA-055, BETA-087
  - objective: Generate reproducible random or stratified samples of
    previously decided records for append-only second-look findings.
  - result: New migration `0078_qc_sampling.sql` (+ postgres twin) adds
    `qc_samples` (the manifest of a draw) and `qc_sample_findings`
    (append-only, same discipline as `alias_decisions`), plus an index. New
    `pipeline/web/qc_sampling.py`. `draw()` — a **deterministic** draw over
    resolved `review_queue` rows or `alias_decisions`: each candidate id is
    hashed with the seed (`sha256(seed|id)`), sorted, and the first N taken;
    a `stratified` method allocates per stratum proportionally then tops up
    in global order to hit exactly `size`. The `sample_id` is a hash of
    (seed, source, method, stratify_by, size, filter), so re-drawing with the
    same parameters returns the same manifest and writes no new row. The
    manifest records the seed, method, `population_filter`, `population_size`
    and the drawn `record_ids` in order. `record_finding()` appends one
    `qc_sample_findings` row — validated against the sample's id list and a
    fixed verdict vocabulary — and **never updates or deletes** (a test
    greps the module for `UPDATE`/`DELETE`). `get()` / `list_samples()` read
    them back with per-verdict counts and a distinct-records-reviewed count.
    New admin routes: GET `/api/admin/qc-samples` + `/api/admin/qc-samples/<id>`,
    POST `/api/admin/qc-sample/draw` + `/api/admin/qc-finding`
    (network-trust-gated).
  - api/ui: additive admin routes above. New collapsed "QC sampling
    workspace" panel on the pipeline tab — seed / source / method /
    stratify-by / size controls, a "Draw sample" button, then a manifest
    line (sample id, N of population, seed, method) and a table of the drawn
    records each with a verdict select + note + "Append finding"; a recorded
    row shows a badge and dims. `styles.css` gained a `.qc-*` block.
  - validation: New `tests/test_web_qc_sampling.py` (7 — the draw is
    reproducible and seed-sensitive and excludes unresolved items; a
    stratified draw hits the size and spreads across strata; the manifest is
    written once (re-draw = same `sample_id`, one row); findings are
    append-only (two on one ref both kept, `reviewed` counts distinct refs)
    and a bad verdict / out-of-sample ref raise; the module contains no
    `UPDATE`/`DELETE` of findings; `alias_decisions` is a valid source; the
    four HTTP routes round-trip). Updated `test_migration_equivalence.py`
    for the 78th migration. `test_web_catalogue` / `test_web_lineage` /
    `test_web_schema_graph` / `test_portal_isolation` / `test_web_admin`
    green; `ruff` clean (also fixed a stray blank line in
    `test_web_review_analytics.py`). Browser-verified on the pipeline tab:
    "Sample … — 6 of 30 · seed \"browser-demo\" · random", and clicking
    "Append finding" flips the row to "finding recorded" and updates
    "1 of 6 reviewed — 1 agree".

- [DONE] BETA-105 | Review-outcome analytics
  - completed: 2026-08-29
  - priority: P2
  - impact: 4
  - effort: 4
  - confidence: 4
  - risk: 3
  - area: admin/review operations
  - depends_on: BETA-052, BETA-053, BETA-055, BETA-087
  - objective: Show review decisions over time by source, item type, reason
    code and evidence age without scoring or ranking reviewers.
  - result: New `pipeline/web/review_analytics.py::analytics(conn, since,
    min_group)` — aggregates only, **never about people**:
    `alias_decisions.decided_by` is never selected and there is no
    per-reviewer axis. `review_queue` is grouped by source (module) ×
    item type into pending / resolved / total; resolution age is bucketed
    (`<1 day` / `1-7` / `7-30` / `30+`) over resolved items; a coarse month
    trend gives created vs resolved; `alias_decisions` is grouped by scheme
    × status and its `reason` field into reason codes. **Small groups are
    suppressed**: any fine-grained cell below `min_group` (default 5) reports
    a `null` count and `suppressed: true`, and `suppressed_groups` totals
    them, so a single reviewer's thin slice cannot be reconstructed. The note
    states the contract in words. New additive admin route
    `/api/admin/review-analytics` (network-trust-gated).
  - api/ui: additive `/api/admin/review-analytics?since=&min_group=`. New
    collapsed "Review-outcome analytics" panel on the Health tab
    (`<details id="review-analytics-panel">`) — the privacy note, the
    suppressed-group count, and five aggregate tables (by source, resolution
    age, by month, alias decisions by scheme, alias-decision reasons).
    `loadReviewAnalytics()` in `health.js`, fetched once on panel open.
    `styles.css` gained a `.ra-*` block.
  - validation: New `tests/test_web_review_analytics.py` (6 — by-source
    aggregates pending and resolved; a group below `min_group` reports a
    `null` total with `suppressed: true` while a larger one is untouched;
    the reviewer name and a `decided_by` key never reach the payload;
    resolution age is bucketed correctly; the note states "aggregates only /
    no reviewer is named / not people"; the route is registered).
    `test_web_admin` / `test_admin_navigation` / `test_portal_design_system`
    green; `ruff` clean. Browser-verified on the Health tab against
    smoke.db: "Minimum group 5 · 1 group(s) suppressed" (the single
    4-item `m10_committee_papers/committee_url_unknown` group correctly
    hidden) and the five sub-tables render.

- [DONE] BETA-103 | Parser replay sandbox
  - completed: 2026-08-29
  - priority: P2
  - impact: 4
  - effort: 5
  - confidence: 3
  - risk: 4
  - area: admin/document diagnostics
  - depends_on: BETA-060, BETA-082, BETA-085, BETA-087
  - objective: Replay one parser against one archived object and compare its
    non-persisted proposed output with the stored normalised output and
    warnings.
  - result: New `pipeline/web/parser_replay.py::replay(conn, settings,
    document_id, parser=None)` — a **read-only** contract. It reads the
    archived bytes from `data/raw/` (checking the SHA-256 against
    `evidence_records.payload_sha256`), runs a **stdlib parser in memory**
    (`html` / `docx` / `pptx` via `pipeline.documents.parsers.get_parser`),
    and diffs the proposed elements against the stored active version's:
    per-`sequence` alignment gives added / removed / changed text, and the
    table counts are compared. **Nothing is written** — the note says so and
    a test asserts the row counts are unchanged after two replays. A PDF, or
    a request for `docling` / `pymupdf`, returns `available: false` with a
    reason rather than importing a heavy optional dependency into a web
    request; a missing archived file or one over 32 MB does the same. A
    parser that raises is reported as a diagnostic result, not a 500. New
    additive admin route `/api/admin/parser-replay` (network-trust-gated).
  - api/ui: additive `/api/admin/parser-replay?document_id=&parser=`. New
    collapsed "Parser replay sandbox" panel on the pipeline tab
    (`<details id="replay-panel">`) — a document_id input, a parser select
    (auto / html / docx / pptx), and a results block showing the "nothing
    was written" note, the stored vs proposed element/table/warning counts,
    the archive-sha256 badge, the element delta, and a stored-vs-proposed
    text-change table. `loadParserReplay()` in `pipeline.js`, run only on the
    button press. `styles.css` gained a `.rp-*` block.
  - validation: New `tests/test_web_parser_replay.py` (7 — an archived HTML
    file is re-parsed and diffed against the stored version (1 element →
    `h1` + `p`, one changed + one added, seq-1 stored/proposed text shown);
    two replays write nothing; a PDF returns `available: false` without
    importing a heavy parser; a missing archive returns `available: false`;
    a tampered archive still replays but `archive.verified` is `false`; an
    unknown document raises; the admin HTTP route serves the replay).
    `test_admin_navigation` / `test_web_admin` green; `ruff` clean. The full
    suite's 3084 passing was confirmed (the transient isolation failures in
    the last sweep were files being edited mid-run and pass clean).
    Browser-verified on the pipeline tab: replaying the seeded PDF document
    shows "…nothing was written to the warehouse", "Stored: docling 1 — 2
    elements, 1 tables" and "Replay not available: replay covers the stdlib
    parsers only (docx, html, pptx)".

- [DONE] BETA-099 | Document table extraction viewer
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 5
  - confidence: 3
  - risk: 4
  - area: public/documents
  - depends_on: BETA-042, BETA-081
  - objective: Display tables detected in parsed documents with page context,
    original structure, extraction status and a structured download.
  - result: New `pipeline/web/doc_tables.py`. `tables(conn, document_id)` —
    every `document_tables` row for the active version of an
    allowlist-gated document, each with its page number, row/column counts,
    a 3-row preview, a `reading_room_link` and an `extraction_status`:
    `structured` (`table_json` parses to a non-empty grid), `markdown_only`
    (only the parser's markdown), or `empty`. `table_detail(conn,
    document_table_id)` — the **full grid straight from `table_json`** (no
    cell is re-detected or reconstructed), the nearest preceding
    heading/caption element, the surrounding elements for page context, and
    the document's source URL as the authority for anything the parse got
    wrong. New additive public route `/api/v1/document_tables` (`document_id`
    for the list, `table_id` for one) on the frozen surface, OpenAPI,
    `<noscript>` and `api.html`.
  - api/ui: additive `/api/v1/document_tables`. New `/doctables` route +
    page ("Document tables"): a document_id input, a per-table list (page,
    dimensions, status badge, preview), and a detail view rendering the grid
    with a client-built **Download CSV** (a Blob of exactly those cells), the
    parser markdown in a `<details>`, and the surrounding-element context.
    Linked from the footer nav. `styles.css` gained a `.dt-*` block.
  - validation: New `tests/test_web_doc_tables.py` (5 — the list reports the
    page and per-table status (structured vs markdown_only); the detail
    returns the `table_json` grid verbatim with its caption and the "parser's
    own extraction" note; a non-allowlisted source is refused; unknown
    document / table raise; the route is in the OpenAPI doc).
    `test_portal_isolation` / `test_portal_navigation` / `test_web_openapi` /
    `test_portal_offline_reading` / `test_portal_design_system` green;
    `ruff` clean. Browser-verified on `#/doctables?doc=…&table=…`: "Table on
    page 4", caption "Table 8: pay by staff group", the 3×2 grid (Staff
    group / Median pay / Recovery worker 24500 / Team leader 31200), a
    Download CSV action and a "HEADING: Table 8…" context line.

- [DONE] BETA-100 | Source-link resilience checker
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 3
  - area: public/provenance
  - depends_on: BETA-060, BETA-081, BETA-084
  - objective: Show whether an original source URL is live, redirected,
    changed or unavailable and whether a checksum-verified archive copy is
    held.
  - result: New `pipeline/web/link_check.py`. `check(conn, settings, url)` —
    the URL's state read **only from collection-time metadata**: the module
    imports no HTTP client and opens no socket (pinned by a test). It scans
    every table carrying `source_url` + `http_status` + `retrieved_at` (found
    from the live schema, not a hand-list) plus `evidence_records` for the
    most recent observation, and maps the recorded status to a conservative
    state — `live_at_last_check` (200), `redirected_at_last_check` (3xx),
    `gone_at_last_check` (404/410), `error_at_last_check`, `not_recorded`,
    `unknown_url`. Archive: if `evidence_records.raw_object_path` resolves to
    a file under `settings.raw_archive_dir`, it is **re-hashed** and compared
    to `payload_sha256` (`verified` true/false, or null when the file is over
    64 MB); a recorded path with no file says so. The `caveat` states the
    archive is the bytes fetched on a past date, kept as provenance, and is
    never the live publisher page. `overview(conn)` gives a corpus-wide count
    of cited rows by state (grouped counts, no per-URL scan). New additive
    public route `/api/v1/source_link` (`url`, or omit for the breakdown) on
    the frozen surface, OpenAPI, `<noscript>` and `api.html`.
  - api/ui: additive `/api/v1/source_link`. New `/links` route + page
    ("Source-link resilience"): a URL input, a per-URL card (state badge and
    sentence, last-checked date, HTTP status, which table it was seen in,
    archive held / verified / bytes), and the warehouse-wide state
    breakdown. Linked from the footer nav. `styles.css` gained a `.lk-*`
    block.
  - validation: New `tests/test_web_link_check.py` (13 — the state comes from
    the last HTTP status; 301/404/410/500/None each map to their conservative
    state; an unknown URL and a non-http URL are handled; the archive copy is
    verified by re-hashing the file and flips to `verified: false` when the
    file is tampered; a recorded-but-missing archive says "not on disk"; the
    module imports no live HTTP client; the overview counts by state; the
    route is in the OpenAPI doc). `test_portal_isolation` /
    `test_portal_navigation` / `test_web_openapi` / `test_portal_offline_reading`
    / `test_portal_design_system` green; `ruff` clean. Browser-verified on
    `#/links?url=…`: "live at last check · HTTP 200 · seen in contracts · No
    archive copy is held", and an "Across the warehouse" breakdown "live at
    last check 57 (100%)".

- [DONE] BETA-098 | Contract diary and milestone calendar
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 3
  - area: public/procurement
  - depends_on: BETA-050, BETA-072, BETA-076
  - objective: Present published tender dates, awards, contract periods,
    amendments, milestones, expected expiries and performance events in
    calendar and accessible agenda views.
  - result: New `pipeline/web/contract_diary.py::diary()` — every dated field
    a matched notice carries, flattened into a chronological agenda:
    `date_published` becomes a `published` event (or `award` when the notice
    type is an award/contract), `date_start` a `period_start`, `date_end` a
    `period_end`. **Every date is transcribed from the notice.** A
    `period_end` event's label reads "Contract period ends (as published)"
    and the `note` states plainly that this diary never predicts a renewal,
    a re-tender or a completion, and shows no milestone or performance event
    because the warehouse does not collect them — only the OCDS notice
    fields are used. Scope by `provider_key` (via `supplier_aliases`),
    `buyer_ons_code`, or `ocid`, with an optional `year`. Returns `events`,
    `months` (per-month counts for a calendar overview), `span`, `counts`.
    New additive public route `/api/v1/contract_diary` on the frozen surface,
    OpenAPI, `<noscript>` and `api.html`.
  - api/ui: additive `/api/v1/contract_diary`. New `/diary` route + page
    ("Contract diary"): a scope picker (provider / buyer / OCDS + optional
    year), an "at a glance" per-month bar strip, and an accessible agenda
    grouped by month with a kind badge and value per event. Linked from the
    footer nav. `styles.css` gained a `.dy-*` block.
  - validation: New `tests/test_web_contract_diary.py` (7 — notice dates
    become three ordered events with their source URL and a computed span;
    an award notice type marks the published event `award`; a `period_end`
    is labelled "as published" and the note forecasts nothing; the `year`
    filter keeps only that year; a scope is required; provider scope uses
    verified aliases; the route is in the OpenAPI doc). `test_portal_isolation`
    / `test_portal_navigation` / `test_web_openapi` / `test_portal_offline_reading`
    / `test_portal_design_system` green; `ruff` clean. (Restored
    `pipeline/web/server.py` and `app.js` after a bare-`python` edit wrote
    them as cp1252 and corrupted an em-dash; re-applied the route with the
    Edit tool.) Browser-verified on `#/diary?buyer=E09000007` against a
    seeded award: a 5-bar month overview and month sections Nov 2024 → Mar
    2029 with "Award notice £8.2m", "Contract period starts (as published)"
    and "Contract period ends (as published)".

- [DONE] BETA-096 | Evidence discrepancy explorer
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 5
  - confidence: 3
  - risk: 4
  - area: public/evidence comparison
  - depends_on: BETA-043, BETA-070, BETA-075, BETA-076
  - objective: Surface different values, dates, names or statuses reported by
    public sources for the same verified entity, field and compatible period.
  - result: New `pipeline/web/discrepancy.py::check()` — a **closed registry**
    (`_PROVIDER_CHECKS` / `_AUTHORITY_CHECKS`) of comparable field pairs. For
    a provider: legal/employer name across SectorTrace's canonical,
    Companies House, the CQC provider register and a gender-pay-gap filing;
    company number across the identifier register, Companies House and the
    filing; plus `_cqc_rating_rows()` — a location whose CQC syndication-API
    rating and CQC bulk-export rating disagree (the case migration 0055's own
    comment flags). For an authority: name across ONS geography, procurement
    notices and NDTMS. A check with ≥2 distinct values across its sources is
    a `discrepancy` carrying every observation (source, value, `as_of`,
    `source_url`); one that agrees is listed under `agreed`. **Nothing is
    reconciled, ranked, or called an error** — the note and caveat say so —
    and this does no cross-source arithmetic: it adds and averages nothing,
    it only shows both values. New additive public route
    `/api/v1/discrepancies` on the frozen surface, OpenAPI, `<noscript>` and
    `api.html`.
  - api/ui: additive `/api/v1/discrepancies` (provider_key XOR ons_code).
    New `/discrepancies` route + page ("Evidence discrepancies"): an entity
    picker, a finding block, one card per disagreeing field with a
    source/value/as-of/link table, and an "agree on" list beneath. Linked
    from the footer nav. `styles.css` gained a `.dx-*` block.
  - validation: New `tests/test_web_discrepancy.py` (5 — three differing name
    spellings are surfaced with every source and no discrepancy carries a
    `correct`/`resolved`/`error`/`canonical` key; an agreeing company number
    is under `agreed`; disagreeing CQC rating channels are a
    `cqc_rating:<loc>` discrepancy naming the syndication API and the bulk
    export; exactly one endpoint and an unknown entity raise; the route is in
    the OpenAPI doc). `test_portal_isolation` / `test_portal_navigation` /
    `test_web_openapi` / `test_portal_offline_reading` /
    `test_portal_design_system` green; `ruff` clean. Browser-verified on
    `#/discrepancies?provider=cgl`: a "Provider / employer name" card with
    three spellings (SectorTrace canonical / Companies House / CQC register),
    each with a source link, and "Company number: 07688213" under the
    agree-on list.

- [DONE] BETA-095 | Entity co-occurrence explorer
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 4
  - area: public/documents
  - depends_on: BETA-041, BETA-042, BETA-081
  - objective: Find documents or notices in which two or more selected tracked
    entities occur together and expose each exact passage or structured field.
  - result: New `pipeline/web/cooccurrence.py::find(conn, keys)` — for 2–5
    selected provider/supplier keys, every record that names **all** of them
    in one place. Four record types, each **same-record only**: a
    `document_elements` passage containing a verified name variant of every
    key (variants from `supplier_aliases` — the explicit review step, never
    fuzzy matching; documents gated by the `DOCUMENT_SEARCH_SOURCES`
    allowlist), a `pfd_report` with ≥2 selected keys in
    `pfd_provider_mentions`, a `tribunal_case` with ≥2 selected keys as
    respondent, and a procurement `notice_id` with ≥2 selected keys resolved
    through `supplier_aliases`. Each result carries the exact passage text or
    the matched field and a `link` (document hits go straight to the BETA-081
    reading room `#/documents?doc=…&el=…`). The `note` and `caveat` state
    plainly that **co-occurrence is location, not a relationship** — two
    names in one passage may be a list, a comparison, or unrelated — and
    point to the pathfinder for a verified connection. New additive public
    route `/api/v1/cooccurrence` (repeated `key` param) on the frozen
    surface, OpenAPI, `<noscript>` and `api.html`.
  - api/ui: additive `/api/v1/cooccurrence`. New `/cooccurrence` route +
    page ("Co-occurrence explorer"): a comma-separated key input, a finding
    block, results grouped by record type with the passage quoted verbatim
    in a `<blockquote>` and an "Open →" link per row. Linked from the footer
    nav. `styles.css` gained a `.co-*` block.
  - validation: New `tests/test_web_cooccurrence.py` (5 — a shared coroner
    report is a `coroner_report` co-occurrence with both matched names and
    the "location, not a relationship" note; documents match on verified
    variants, require every entity, and link into the reading room; a passage
    naming only one entity is not a hit; 2–5 entities enforced; the route is
    in the OpenAPI doc). `test_portal_isolation` / `test_portal_navigation` /
    `test_web_openapi` / `test_portal_offline_reading` green; `ruff` clean.
    Browser-verified on `#/cooccurrence?key=cgl&key=turning_point` against a
    seeded PFD report: "Coroner reports (1)" with the matched names
    (`cgl ("Change Grow Live") · turning_point ("Turning Point")`) and the
    caveat pinned.

- [DONE] BETA-094 | Visual research journey
  - completed: 2026-08-29
  - priority: P2
  - impact: 4
  - effort: 3
  - confidence: 4
  - risk: 2
  - area: public/research continuity
  - depends_on: BETA-072, BETA-077, BETA-088
  - objective: Render the current local session as a branching trail of
    searches, entities, documents and comparisons with named checkpoints.
  - result: New portal module `js/journey.js` — one bounded, guarded
    `localStorage` key `sectortrace.journey` (`SCHEMA_VERSION = 1`, 150-event
    cap). Each route visit is a node `{id, hash, route, label, at, parent,
    name}`; `parent` is **the node the reader was on**, so navigating back to
    an earlier page and then somewhere new makes a branch rather than a
    straight line. Revisiting an exact hash re-points `current` without
    adding a node. `checkpoint(id, name)` names a step. `_prune()` drops only
    the oldest *leaf* nodes that are neither named nor on the path from
    `current` to the root, so the shape and the checkpoints survive the cap.
    Only a hash route, the label the portal already shows, a timestamp and
    the parent id are stored. The router (`app.js render()`) calls
    `recordVisit()` after a successful render, loaded on demand and
    `.catch()`-guarded so it can never block a page; the `/journey` route is
    itself not recorded.
  - api/ui: no API — entirely local. New `/journey` route + page ("Research
    journey"): the trail as an indented tree, each node a link to its hash,
    checkpoints marked with a diamond and the current node with a caret, a
    "checkpoint / rename" control per node and a "Clear trail" action.
    Module registered in `server.py` and `test_portal_isolation`; linked from
    the footer nav. `styles.css` gained a `.jr-*` block.
  - validation: New `tests/test_portal_journey.py` (5 — the store is
    versioned, bounded and guarded and dispatches `journeychange`; a new
    node's parent is `state.current` and a revisit re-points rather than
    duplicates, and `/journey` is not recorded; prune keeps checkpoints and
    the current path and drops only leaves; recording is wired into the
    router and `.catch`-guarded; the route and module are registered).
    `test_portal_isolation` / `test_portal_navigation` /
    `test_portal_design_system` green; `ruff` clean. Browser-verified: a
    browse of `#/pay → #/contracts → #/pay?provider=cgl`, back to `#/pay`,
    then `#/geography` produces a tree `pay → {contracts → pay?provider=cgl,
    geography}` — geography branches off `pay`, not off the last node — and
    naming the contracts node renders "◆ the money trail" in the tree.

- [DONE] BETA-097 | Temporal coverage navigator
  - completed: 2026-08-29
  - priority: P2
  - impact: 4
  - effort: 3
  - confidence: 5
  - risk: 2
  - area: public/navigation and coverage
  - depends_on: BETA-043, BETA-075, BETA-076, BETA-084
  - objective: Show exactly which periods each source holds for a selected
    provider, authority or metric and link every available period to its view.
  - result: New `pipeline/web/coverage_timeline.py::timeline()` — for one
    provider (`provider_key`) or authority (`ons_code`), a closed registry of
    six source probes each runs one `SELECT DISTINCT <period>` and returns
    **exactly the periods held** — `charity_financials`, `nhs_job_adverts`,
    `gender_pay_gap_reports`, `tribunal_cases`, `pfd_provider_mentions` and
    `contracts`-as-supplier for a provider; `public_health_grants`,
    `la_revenue_budgets`, `ndtms_la_statistics`, `fingertips_la_values`,
    `contracts`-as-buyer and `council_spend` for an authority. **Nothing is
    gap-filled**: a period missing from a source's list stays "not collected /
    not published", never a zero, and a source that holds nothing for the
    entity is returned with `held: false` and an empty list, not hidden. The
    only synthesised value is `span` / `years` — a contiguous year axis for
    alignment, labelled as the axis. Each source carries a `link` into the
    view that shows it. New additive public route `/api/v1/coverage_timeline`
    on the frozen surface, OpenAPI, `<noscript>` and `api.html`.
  - api/ui: additive `/api/v1/coverage_timeline` (provider_key XOR ons_code).
    New `/timeline` route + page ("Coverage timeline"): an entity picker,
    then a per-source year grid — a filled cell is a period held (a link), a
    dashed empty cell is "not collected" with an explicit aria-label, never a
    zero — plus a chip list for sources whose periods are not plain years,
    and the note pinned beneath. Linked from the footer nav. `styles.css`
    gained a `.tl-*` block.
  - validation: New `tests/test_web_coverage_timeline.py` (6 — the held
    periods are exact with the real 2020/2021 gap preserved while the year
    axis is contiguous; a source with no data is shown with `held: false`;
    authority probes read by `ons_code`; exactly one endpoint is required;
    an unknown entity raises; the route is in the OpenAPI doc).
    `test_portal_isolation` / `test_portal_navigation` / `test_web_openapi` /
    `test_portal_offline_reading` / `test_portal_design_system` green;
    `ruff` clean. Browser-verified on `#/timeline?provider=cgl`: "Charity
    accounts" shows held cells 18/19/21/22 with five dashed gap cells (2020
    a genuine gap, not a zero); NHS Jobs / tribunals / PFD show as
    all-gaps rows rather than being dropped.

- [DONE] BETA-093 | Relationship pathfinder
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 4
  - area: public/relationships
  - depends_on: BETA-010, BETA-044, BETA-076, BETA-080
  - objective: Find and explain the shortest verified path between two
    selected entities through source-backed graph edges.
  - result: New `pipeline/web/pathfinder.py::find_path()` — BFS for the
    shortest path between two entities over `v_entity_edges`, the
    source-backed entity graph. **Verified edges only**: an edge whose
    `basis` is an unconfirmed name match (`name_only_unconfirmed`,
    `supplier_name_unmatched`, `name_match_only`, empty) has not passed the
    review gate that makes it a fact and is excluded; the restricted
    shared-officer edges are not in `v_entity_edges` and never reach the
    portal anyway. **Deterministic**: each node's edge list is pre-sorted by
    `(relationship, node id)` and the queue is FIFO, so among equally short
    paths the same one is always returned. **Bounded**: `max_hops` 1–8
    (default 6) and a frontier cap. Edges are deduplicated on
    `(source node, target node, relationship)` so a provider with fifty
    contract notices to one authority is one edge. Endpoints are limited to
    `provider` / `authority` / `supplier`; a path may pass *through* company /
    scheme / tribunal nodes but they are not queryable endpoints. The payload
    returns `found`, `hops`, `path` (one row per hop: from, relationship,
    basis, to, `source_url`, `retrieved_at` — the table equivalent),
    `nodes`, and a `note`; no path within `max_hops` is `found: false` with a
    reason, not an error. New additive public route
    `/api/v1/relationship_path` on the frozen surface, OpenAPI, `<noscript>`
    and `api.html`.
  - api/ui: additive `/api/v1/relationship_path` (from_type/from_id/to_type/
    to_id/max_hops). New `/pathfinder` route + page ("Relationship
    pathfinder"): two endpoint pickers (kind select + id), a chain visual
    (node → relationship → node …), and the per-hop table with a source link
    per row. Linked from the footer nav. `styles.css` gained a `.pf-*`
    block.
  - validation: New `tests/test_web_pathfinder.py` (6 — finds the shortest
    verified path with its `alias_matched` basis and source URL; an
    unconfirmed name-match edge is not followed (endpoint reports no verified
    edges); a genuine two-hop path is byte-identical across repeated calls
    and `max_hops=1` refuses it "within 1 hops"; same endpoint is zero hops;
    a bad endpoint kind raises; the route is in the OpenAPI doc).
    `test_portal_isolation` / `test_portal_navigation` / `test_web_openapi`
    green; `ruff` clean. Browser-verified: `#/pathfinder?from_type=authority&from_id=E09000007&to_type=supplier&to_id=cgl`
    shows the chain "authority E09000007 → supplier CHANGE GROW LIVE", a
    "Verified path · 1 hop" finding block and one table row (awarded a
    contract to · alias_matched · source ↗); an unknown authority renders
    "no verified edges" rather than an error.

- [DONE] BETA-092 | Record revision comparison
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 5
  - confidence: 4
  - risk: 3
  - area: public/version inspection
  - depends_on: BETA-050, BETA-060, BETA-081, BETA-090
  - objective: Compare successive procurement notices, documents, provider
    records and regulatory entries with field-aware and text-aware diffs.
  - result: New `pipeline/web/record_diff.py`. `ocds_diff()` — a field-aware
    diff of two procurement notices (explicit `a`/`b` notice ids, or an
    `ocid` to take its two most recently published). Each contract field is
    classed once, in `_CONTRACT_FIELDS`: **source** (verbatim from the OCDS
    release — `title`, `value_core`, `date_published`, `notice_type`, …) or
    **derived** (a match/normalisation this pipeline computes —
    `buyer_ons_code`, `psr_basis`). The payload returns every field with its
    class, `a`, `b` and `changed`, plus `counts.changed_source` /
    `counts.changed_derived` **reported apart and never added** and a
    `same_ocid` flag. `document_version_diff()` — a metadata diff (parser,
    schema, `config_hash`, `text_sha256`, status, is_active) plus a
    text-aware, **element-aligned** diff: `document_elements` from each
    version keyed by `sequence`, unchanged elements (equal `text_sha256`)
    omitted, the rest classed `added` / `removed` / `changed`, capped at 600
    elements. Documents are gated by the same `DOCUMENT_SEARCH_SOURCES`
    allowlist as `document_search` — a source not searchable there raises
    here too — and versions belonging to different documents are refused.
    New additive public route `/api/v1/record_diff` (`kind` ocds|document,
    `a`/`b`/`ocid`/`document_id`), on the frozen surface
    (`PUBLIC_API_ROUTES`), OpenAPI, `<noscript>` and `api.html`.
  - api/ui: additive `/api/v1/record_diff`. New `/revisions` route + page
    ("Compare revisions"): a kind selector + id field, then for OCDS a
    two-column field table (source/derived class pills, changed rows tinted)
    under a finding block "N source fields amended · M derived fields
    recomputed"; for a document the metadata diff plus an ordered list of
    changed/added/removed elements with their A and B text. Linked from the
    footer nav. `styles.css` gained a `.rev-*` block.
  - validation: New `tests/test_web_record_diff.py` (6 — the OCDS diff labels
    source vs derived changes and keeps the counts apart; `ocid=` takes the
    two most recent notices; a missing notice raises; the document diff is
    element-aligned with correct added/changed counts and a metadata diff; a
    non-allowlisted `source_system` is refused; the route is in the OpenAPI
    doc). Also fixed `test_portal_offline_reading` to treat `feed` as an
    EXTRA route like `export` (BETA-089 follow-up). `test_portal_isolation` /
    `test_portal_navigation` / `test_web_openapi` green; `ruff` clean.
    Browser-verified: `#/revisions?kind=ocds&ocid=…` against a seeded pair of
    notices shows "3 source fields amended · 0 derived recomputed", a "same
    OCID" badge and three tinted rows (title, value_core, date_published).

- [DONE] BETA-089 | Saved searches and change alerts
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 3
  - area: public/search and monitoring
  - depends_on: BETA-072, BETA-090
  - objective: Save complete searches locally, show new-match counts after a
    later release and provide stable Atom feeds for external subscription.
  - result: New portal module `js/savedsearch.js` — a versioned
    (`SCHEMA_VERSION = 1`), 50-entry `localStorage` list under
    `sectortrace.saved_searches`; each entry is a name plus the full `#/...`
    hash (route + whole filter query), `last_count` and `last_checked`.
    Every access is try/catch-guarded; only public identifiers are stored.
    `checkNew(search)` re-runs the route's `/api/v1` count endpoint with the
    saved params and returns `{count, delta, first}` against `last_count`
    **without persisting** — `markSeen(id, count)` is the separate, explicit
    accept. `feedURL(search)` returns the stable Atom URL only for a
    change-stream search, carrying just `kind`/`source`/`since` through.
    New backend: `pipeline/web/feeds.py::changes_atom()` renders the BETA-090
    change feed as Atom 1.0; the feed `<id>` and every entry `<id>` are
    **host-independent tag URIs** (`tag:trace.cglpay.us,2026:change/<kind>/<sha1>`)
    derived from the event content, so a subscription survives a move between
    the dev and production hosts. New raw route
    `/api/v1/feed/changes.atom` (same `kind`/`source`/`since` filter as
    `/api/v1/changes`, `application/atom+xml`, cached like the rest of
    `/api/v1/*`), served at the `_get_public` level beside `/api/v1/export`
    and added to `PUBLIC_API_EXTRA` (`{"export", "feed"}`), `openapi.ROUTES`,
    the `<noscript>` list and `api.html`.
  - api/ui: additive raw route `/api/v1/feed/changes.atom`. New "Save search"
    button in the filter-bar summary (shown whenever there are shared-filter
    chips; loads `savedsearch.js` on demand so it and `app.js` do not import
    each other). New `/saved` route + page ("Saved searches") listing each
    saved search with its query, a live match-count status (`+N new since
    last seen` / `no change` / `first check` / `run to see`), Run / Mark
    seen / Delete, and — for a change-stream search — its copyable Atom URL.
    `styles.css` gained `.ss-*` + `.filter-save`.
  - validation: New `tests/test_web_feed.py` (5 — the feed is well-formed
    Atom parsed by ElementTree; entry ids are identical across two different
    `self_url` hosts and contain neither host; the `kind` filter reaches both
    the entries and the feed id; the HTTP route returns
    `application/atom+xml` with the request host in the self link; it is in
    the OpenAPI doc and `PUBLIC_API_EXTRA`). New
    `tests/test_portal_saved_search.py` (5 — the store is versioned, bounded
    and guarded and dispatches `savedsearchchange`; `checkNew` compares
    against `last_count` and never calls `setItem`, `markSeen` does;
    `feedURL` is `changes`-only and carries just the feed params; the save
    button and the route/module are wired). `test_web_openapi` /
    `test_portal_isolation` / `test_portal_navigation` green (extended the
    openapi tail-vs-surface check to skip `feed` like `export`). `ruff`
    clean. Browser-verified: `/api/v1/feed/changes.atom` returns a valid feed
    with stable ids and a host-matched self link; on `#/pfd?yearFrom=2020` the
    "Save search" button appears and saves `{route:pfd, query:yearFrom=2020&yearTo=2024}`;
    the `#/saved` page shows a change-stream search as "7 matches now (first
    check)" with its Atom URL, and "Mark seen" then flips it to "no change
    (7)".

- [DONE] BETA-088 | Evidence notebook
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 2
  - area: public/research workspace
  - depends_on: BETA-072, BETA-077, BETA-080
  - objective: Let readers pin records, passages, charts, providers and
    authorities into named, reorderable local collections with private notes
    and lossless JSON import/export.
  - result: New portal module `pipeline/web/static/public/js/notebook.js` —
    a single-browser research workspace, no account and no server call. One
    versioned key `sectortrace.notebook` (`SCHEMA_VERSION = 1`) holds
    `{v, collections:[{id,name,created_at,updated_at,items:[{id,kind,ref,label,note,added_at}]}]}`.
    Bounds are enforced, not hoped for: `MAX_BYTES` 200 KB (a write that
    would cross it is refused, not truncated — so it cannot corrupt
    `my_area` / `recent`), `MAX_COLLECTIONS` 25, `MAX_ITEMS` 250/collection,
    `MAX_NOTE` 2000 chars. Every `localStorage` read and write is
    try/catch-guarded; `read()` returns a fresh empty notebook on corruption
    or private mode, `write()` returns `{ok:false, reason}` rather than
    throwing. Only public identifiers or hash routes are stored (`ref`), plus
    the label the portal already shows and the reader's own note. `addItem`
    is idempotent on `(kind, ref)`. Reorder is one-step up/down for both
    collections and items (the offline-safe equivalent of drag). Lossless
    JSON: `exportJSON()` is the whole cleaned notebook; `importJSON()`
    rejects anything not a `v1` notebook rather than merging partial data
    (merge mode appends collections). `notebookButton({kind,ref,label})` is a
    self-repainting toggle that pins into a default "My evidence" collection
    or removes it, listening on a `notebookchange` event so every instance on
    the page stays in sync.
  - api/ui: no API — entirely local. New `/notebook` route ("Evidence
    notebook"), a management page with per-collection rename / reorder /
    delete, per-item note editing / reorder / remove, an "Add collection"
    field, and Export / Import JSON (import via a hidden file input). Module
    registered in `server.py`'s portal-module loop and
    `test_portal_isolation` `PUBLIC_STATIC_PATHS`; linked from the footer
    nav. `notebookButton` wired into the provider hero, the authority hero
    (beside "My area"), and the document reading room (pinning the exact
    passage route as a `passage` kind). `styles.css` gained a `.nb-*` block
    using the portal's real tokens.
  - validation: New `tests/test_portal_notebook.py` (7 — the schema is
    versioned and every bound is present with a refuse-not-truncate write;
    every `localStorage` access is inside a `catch`; import rejects a
    non-`v1` object and export is the whole notebook; writes dispatch
    `notebookchange` and the button listens; only the five public kinds can
    be pinned and `addItem` refuses an unknown kind; the pin button is
    imported and used on providers/authority/documents; the route and module
    are registered). `test_portal_isolation` / `test_portal_navigation` /
    `test_portal_design_system` green (fixed a first pass that used
    `var(--muted)` / `var(--border)` — not portal tokens — to
    `--text-muted` / `--border-subtle`). `ruff` clean. Browser-verified: the
    model round-trips (create / addItem idempotent / setNote / export /
    reject bad import / good import); the `#/notebook` page renders
    collections, items with kind labels and editable note textareas (fixed
    `el()` setting `value` as an attribute, which a `<textarea>` ignores —
    note now passed as a text child); the provider hero "+ Notebook" button
    toggles to "In notebook ✓" and the pin is found in storage.

- [DONE] BETA-104 | Validation-rule explorer
  - completed: 2026-08-29
  - priority: P2
  - impact: 4
  - effort: 4
  - confidence: 4
  - risk: 2
  - area: admin/data quality
  - depends_on: BETA-059, BETA-060, BETA-067, BETA-082, BETA-085
  - objective: Catalogue validation rules with purpose, affected modules and
    fields, recent pass/failure counts and protected representative failures.
  - result: New `pipeline/web/validation.py::rules(conn, today=…)` — a
    read-only catalogue derived on the request from three enumerable sources,
    each rule given a **stable id** `<kind>:<scope>`: `trigger:<name>` and
    `check:<table>:<col>` and `provenance:<table>` from the live SQLite schema
    (`sqlite_master` + `PRAGMA table_info`), `parse:<module>:<field>` from
    grouping `parse_failures`, `review:<module>:<type>` from grouping
    `review_queue`. Each carries a purpose (generic per-kind, overridden by a
    specific line where warranted — the only hand-kept part, in the new
    `pipeline/validation_rules.py`), the modules and fields it touches, and
    recent counts against a 30-day window keyed off an optional `today`.
    **Failure examples never carry the raw fragment**: each is reduced to its
    *shape* (`_shape()` — letters→`x`, digits→`9`, punctuation kept, capped),
    plus the field, reason, source **host only** (no path or query) and date.
    `RULE_NOTES` keys are pinned to live rule ids so a stale note fails the
    build. Schema rules are SQLite-only (the payload's `backend` and `note`
    say so; empty on PostgreSQL). New additive admin route
    `/api/admin/validation-rules` (network-trust-gated, read-only).
  - api/ui: additive `/api/admin/validation-rules?today=`. New collapsed
    "Validation rules" panel on the Health tab (`<details
    id="validation-panel">`, next to Parse failures) — a search box,
    kind-filter checkboxes with counts, and a flat card list; each card shows
    the id, title, purpose, `detail` (CHECK value set / trigger RAISE
    message / which provenance columns are NOT NULL), recent-count badges,
    and for parse rules a `<details>` of shape-only examples.
    `loadValidationRules()` in `health.js`, fetched once when the panel is
    opened. `styles.css` gained a `.vr-*` block.
  - validation: New `tests/test_web_validation.py` (7 — rules are typed and
    every one has a purpose; the promotion triggers carry their specific
    `RULE_NOTES` purpose and a promotion `detail`; no `RULE_NOTES` key is
    stale; provenance is one rule per evidence table with an `enforced`
    boolean; a seeded parse failure becomes a rule whose example is `[x9\\W]`
    only — no readable content, `raw_fragment` key absent, source reduced to
    host, `chars` preserved — and `recent` respects `today`; review-queue
    rows become a gate rule with pending/resolved counts; the HTTP route
    serves the catalogue). `ruff` clean. Browser-verified on the Health tab:
    the panel shows kind chips "Trigger (8) · CHECK (5) · Provenance (70) ·
    Parse failure (1) · Review gate (1)", 85 cards; searching "parse:m08"
    shows the seeded rule "1 total · 1 in 30d" and its example renders as
    "xxxx x. xxxxx (xxxx 99) — name not parseable from title ·
    www.judiciary.uk · 2026-08-25 · 23 chars"; the cdp promotion trigger card
    shows its migrations/0030 purpose and RAISE message.

- [DONE] BETA-102 | Interactive pipeline and data-lineage map
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 5
  - confidence: 4
  - risk: 3
  - area: admin/system understanding
  - depends_on: BETA-043, BETA-058, BETA-067, BETA-082, BETA-083, BETA-085
  - objective: Map modules, sources, archives, tables, entity links, APIs,
    exports and public pages as searchable dependencies with health and
    consumer details.
  - result: New `pipeline/web/lineage.py::graph(conn, settings)` — one typed
    graph composed on the request from the machine-owned registries and the
    live schema. **Every edge is derived; none is hand-maintained.** Node
    kinds: `source` (dataset catalogue), `module` (`admin.modules` over the
    registry — wave, pending review, parse failures, missing deps, plus last
    recorded run status from the ledger), `table` (only tables actually named,
    with live row counts and a `restricted` flag), `export`
    (`exports/schema.py::TABS`). Edge kinds: `collected_by` (source→module),
    `depends_on` (module→module, from `MODULE_META`), `writes` (module→table,
    from `datasets.py` `public_tables`), `references` (table→table, from
    `catalog.foreign_key_columns` — the live foreign keys), `exported_by`
    (table→export, from a word-boundary `FROM`/`JOIN` scan of each
    `TabSpec.sql`). Each node carries a `consumer_count` (incoming edges).
    API routes and portal pages are **deliberately omitted** — the Python
    side has no registry mapping one to the tables it reads without parsing
    `public_queries` — and the payload's `omitted` list says so rather than
    the graph guessing. New additive admin route `/api/admin/lineage`
    (network-trust-gated, read-only, writes nothing).
  - api/ui: additive `/api/admin/lineage`. New collapsed "Data lineage" panel
    on the pipeline tab (`<details id="lineage-panel">`) — a search box, node-
    kind checkboxes with counts, a scrollable node list (kind badge +
    consumer count), and a detail pane that shows a node's facts (module run
    health / table rows / source publisher+licence / export description) and
    its upstream and downstream edges grouped by relationship, each target a
    link that re-focuses the pane. `loadLineage()` in `pipeline.js`, fetched
    once when the panel is first opened — the graph is registry-derived and
    does not change between runs, so it is not polled. `styles.css` gained a
    `.lin-*` block; no vendored graph library, no canvas — a DOM list and a
    detail pane, the offline-safe "table equivalent" the earlier items kept.
  - validation: New `tests/test_web_lineage.py` (6 — the graph is typed and
    every edge lands on a declared node of a declared kind; the
    source→module→table chain is present for `public-health-grant` and the
    module node carries its registry facts; every `catalog.foreign_key_columns`
    row appears as a `references` edge between two `table:` nodes; every
    `exported_by` edge targets a `TABS` entry and `authorities` feeds
    `01_Authorities`; two calls create no tables; the HTTP route serves the
    graph). `ruff` clean; `test_web_admin` / `test_admin_navigation` /
    `test_web_schema_graph` / `test_web_mission_control` green. Browser-
    verified on the admin pipeline tab: the panel lists 189 nodes
    (34 source / 34 module / 110 table / 11 export) with kind filters;
    searching "m11_public_health" and selecting the module shows "wave 2 ·
    never run in the ledger window", upstream "collected by Public health
    grant allocations", downstream "depends on m00_geography" and "writes
    public_health_grants"; selecting `authorities` shows "referenced by" its
    eight FK children and "exported by 01_Authorities, 02_Public_Health_Grant".

- [DONE] BETA-101 | Run-to-run output comparison
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 3
  - area: admin/operations
  - depends_on: BETA-058, BETA-082, BETA-085
  - objective: Compare two pipeline runs by modules, rows added/changed/removed,
    failures, review items, coverage, durations and freshness effects.
  - result: New `run_ledger.compare(conn, run_a, run_b)` — a per-module diff
    derived from the immutable ledger, **writing nothing and duplicating no
    payloads**: each module row carries the numbers the run already recorded
    (`rows`, `review`, `failures`, `elapsed_ms`) from each side plus their
    deltas, and the run headers carry `run_id` so a caller links back to the
    ledger and job logs for the detail. Per module: `status_a`/`status_b`
    (with `absent` where a run did not touch it), the four deltas, a
    `duration` delta from `finished_at - started_at`, and a
    `freshness_effect` read from the B outcome ("advanced — wrote rows in B",
    "ran in B, no new rows", "no successful run in B"). One headline `change`
    label per module from an explicit ordered precedence
    (`added` > `removed` > `regressed` > `recovered` > `rows-changed` >
    `review-changed` > `slower`/`faster` > `unchanged`) — deterministic, not
    a score. `totals` are plain operational counts (regressions, recoveries,
    modules only in A / only in B, rows added/removed, review Δ, failures Δ,
    duration Δ) — no composite index. With no ids it compares the two most
    recent runs (B newest). Missing run or fewer than two → `ValueError` →
    404. New additive admin route `/api/admin/run-comparison?a=&b=`
    (network-trust-gated, `degrade.preflight` on `run_ledger`); helper
    `run_ledger.one()` added; `recent()` refactored onto a shared `_hydrate`.
  - api/ui: additive `/api/admin/run-comparison`. New "Compare two runs"
    panel on the pipeline tab (`#run-comparison-panel`) — two run pickers
    (defaulting to auto newest / second-newest), an A/B header line each with
    `run_id`, revision and duration, a totals badge strip, and a per-module
    diff table (change label, status A→B, rows/review/failures/duration
    deltas, freshness effect). `loadRunComparison()` in `pipeline.js`,
    refreshed on `tabshown` and picker `change` only — a comparison of two
    past runs does not change, so it is not polled. `styles.css` gained a
    `.rc-*` block.
  - validation: `tests/test_run_ledger.py` +6 (defaults to the two most
    recent runs; per-module added/removed/regressed labels, `rows_removed`
    and `review_delta_total` totals, `duration_delta_ms` from the timestamps,
    and the "advanced/no successful run" freshness effect; a named missing
    run and fewer-than-two both raise; `compare` writes nothing — row count
    unchanged, note says so; the HTTP route returns the diff and 404s a bad
    id). `ruff` clean. Browser-verified on the admin pipeline tab against a
    seeded ledger: the panel shows A/B headers, totals "A→B rows +35 / −60 ·
    1 regressed · 1 only in B · failures Δ +3", and a three-row table
    (m12_fingertips added, m05_cqc regressed ok→failed, m01_procurement
    rows-changed); selecting the runs in the other order inverts every
    figure ("1 recovered", "removed", "failures Δ -3").

- [DONE] BETA-091 | Source publication calendar
  - completed: 2026-08-29
  - priority: P2
  - impact: 4
  - effort: 3
  - confidence: 4
  - risk: 2
  - area: public/source coverage
  - depends_on: BETA-043, BETA-059, BETA-084
  - objective: Show each source's stated or observed release cadence, last
    publication, next expected window and overdue/unknown status.
  - result: `Dataset` gained one nullable field, `stated_cadence_days` — the
    publisher's stated release period in days, set only where the source
    commits to a calendar in its own `cadence` prose. All 17 judgement calls
    sit in one auditable block, `datasets._STATED_CADENCE_DAYS`, folded onto
    the registry with `dataclasses.replace` so no row carries an inline guess.
    New additive read-only route `/api/v1/publication_calendar`
    (`public_queries.publication_calendar`), derived per request: for each
    dataset it reports the **stated** cadence and, separately and never
    merged, an **observed** interval — the median gap between the distinct
    `retrieved_at` calendar dates the warehouse holds, computed only with
    three or more such dates and always labelled an estimate carrying its
    sample size. `cadence_basis` is `stated` \| `observed` \| `unknown`
    (stated preferred); `next_expected` is `last_publication + cadence_days`;
    `status` is `overdue` only past a quarter-cadence grace (min one week),
    else `due` \| `current` \| `unknown`. `counts` is `by_status` + `by_basis`
    only — no cross-dataset arithmetic, no headline total. An optional `today`
    param makes the view reproducible; the `caveat` states an "overdue" row
    does not tell a stalled publisher apart from a collection that has not
    run. New `/js/pages/calendar.js` + `/calendar` route ("Publication
    calendar"): an evidence-health strip, a finding block, status filter
    chips with per-status counts, and a table with the stated cadence and the
    observed interval in their own columns; overdue rows take a left-edge
    tint that only echoes the Status column. Linked from the footer nav and
    the header lens menu's Accountability group.
  - api/ui: additive route `/api/v1/publication_calendar` (today). Added to
    the OpenAPI doc, the `<noscript>` list, `api.html` and
    `test_portal_isolation` `PUBLIC_API_ROUTES` + the page-module list. New
    portal page `calendar.js` + route `/calendar`. `styles.css` gained a
    `.cal-row-*` block.
  - validation: New `tests/test_web_publication_calendar.py` (5 — stated and
    observed cadences are separate fields and `counts` has no `total`; a
    stated cadence projects `next_expected` and flips to `overdue` by a
    counted margin far in the future; an observed interval needs three dated
    retrievals and never merges into the stated figure; `today` is
    deterministic and echoed as `as_of`; the route is in the OpenAPI doc).
    Updated `tests/test_portal_controls.py` for the BETA-078 single-`layer`
    atlas state contract that the old assertion still expected as
    `metric`/`layers`. `test_web_catalogue` / `test_web_openapi` /
    `test_portal_isolation` / `test_portal_navigation` / `test_beta_queue`
    green. `ruff` clean. Browser-verified against a seeded warehouse: the
    page shows status chips "All · 34 / Overdue · 2 / Due · 0 / Unknown · 30
    / Current · 2"; filtering to Overdue sets `#/calendar?status=overdue` and
    shows two tinted rows — statutory pay rates ("Annual, each April · ~365
    d" stated, "too few dated retrievals (n=1)" observed, "Overdue · +515 d")
    and provider corporate structure ("Continuous" stated, "~30 d est. · n=4"
    observed, "Overdue · +116 d") — the stated and observed cadences visibly
    in separate columns.

- [DONE] BETA-090 | "What changed?" evidence feed
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 5
  - confidence: 4
  - risk: 4
  - area: public/change awareness
  - depends_on: BETA-058, BETA-068, BETA-084
  - objective: Publish a filterable chronology of evidence added, changed,
    withdrawn, superseded or newly verified by source, provider, authority,
    evidence type and release.
  - result: New additive read-only route `/api/v1/changes`
    (`public_queries.change_feed`). **No persisted change-event table and no
    new collection-time write path** — the feed is *derived* on each request
    from signals the warehouse already records, each classed as one of five
    kinds: `release` (a `run_ledger` row), `refreshed` (a dataset's measured
    `last_retrieved_at`, i.e. a collection changed it), `reparsed` (a
    document got a new active `document_versions` row while an inactive one
    exists — a parser change), `superseded` (a provider with
    `superseded_by` set — verified lineage), `verified` (a confirmed
    `alias_decisions` row — a human review). The three axes the objective
    names stay apart: a collection change, a parser change and a human-review
    change are distinct kinds and `counts.by_kind` never adds them (there is
    no `total`). Filters: `kind`, `source`, `evidence_type`, `since`,
    `limit` (cap 500). Each stream is guarded so a missing table is skipped.
    A `caveat` states the feed shows what *this warehouse* recorded changing,
    not what a source published. New `/js/pages/changes.js` + `/changes`
    route ("What changed?"): a chronology table with kind and source filter
    chips (each showing its own count), linked from the footer nav and the
    lens menu's Accountability group.
  - api/ui: additive route `/api/v1/changes` (kind, source, evidence_type,
    since, limit). Added to the OpenAPI doc, `<noscript>` list, `api.html`
    and `test_portal_isolation` `PUBLIC_API_ROUTES` + the page-module list.
    New portal page `changes.js` + route `/changes`.
  - validation: New `tests/test_web_change_feed.py` (5 — events are typed and
    `counts` has only `by_kind` with no `total`; a run is a `release` event
    carrying its `run_id`; a superseded parse version is a `reparsed` event
    of its own kind, counted separately; a bad `kind` raises and `since`
    keeps only dated events on/after it; the route is in the OpenAPI doc).
    `test_web_openapi` / `test_portal_isolation` / `test_web_public` /
    `test_web_catalogue` / offline-reading / navigation suites green. `ruff`
    clean. Browser-verified: the "What changed?" page shows kind chips
    "All kinds · 5 / Release · 0 / Refreshed · 5 / Reparsed · 0 /
    Superseded · 0 / Verified · 0" (each counted separately) and a 5-row
    table; clicking "Refreshed" sets `#/changes?kind=refreshed` and keeps the
    table; no console errors.

- [DONE] BETA-087 | Split-pane review workspace
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 5
  - confidence: 4
  - risk: 4
  - area: admin/review
  - depends_on: BETA-052, BETA-054, BETA-055, BETA-080, BETA-085
  - objective: Display the queue on the left and typed context, source
    preview, alternatives, history and decision controls on the right;
    preserve keyboard operation and scroll position, with a stacked
    narrow-screen layout.
  - result: Presentation only — `renderItem` (the full item card, with its
    typed context, sidecar, resolve form, history and Approve/Reject/Reset
    controls), the `decideItems([id], …)` path, the named-reviewer
    requirement, the explicit decision and one-candidate-at-a-time are all
    unchanged. New `splitActive()` = `matchMedia('(min-width: 1000px)')`;
    `dense()` now returns `#f-dense.checked || splitActive()`, so on a wide
    screen the left `#review-list` is always the existing compact dense
    table (which already has `data-id` rows, click-to-focus, checkboxes and
    quick A/R). New `renderReviewDetail()` renders `renderItem(focusedItem())`
    into a right-hand `#review-detail` pane; `renderFocus()` calls it, so
    `j`/`k`, a row click and the pager all keep the pane in sync. The pane's
    checkbox/buttons act by item id exactly like the row's — no new route.
    A `matchMedia` `change` listener re-renders on crossing the breakpoint.
    CSS: `.review-split` is `display: block` (the familiar stacked card list)
    until 1000px, where it becomes a `minmax(300px,380px) 1fr` grid with a
    scrollable left list and a sticky, scrollable detail pane;
    `#review-detail` is `display: none` below the breakpoint.
  - api/ui: no API change, no change to the decision path. HTML: `#review-list`
    + `#review-pager` wrapped in `.review-split` with a new `#review-detail`
    aside. New CSS `.review-split`, `.review-detail`. JS: `splitActive`,
    `renderReviewDetail`, the `renderFocus` call, the breakpoint listener.
  - validation: New `tests/test_admin_review_split.py` (4 — the pane markup
    exists; wide screens use the compact list + a detail pane reusing
    `renderItem` kept in sync by `renderFocus`; `renderReviewDetail` does not
    touch the decision path or the reviewer requirement; the split stacks
    below 1000px). `test_web_admin` / review-session / -context / -sidecar /
    -clusters / console suites green. Browser-verified at 1400px (a
    `380px 768px` grid, dense 4-row list left, item 1 in the detail pane;
    `j` moves focus 1→2→3 and the detail pane follows; the pane carries the
    decision controls) and at 785px (no grid, detail pane hidden, the
    4-item stacked card list, no page overflow).
  - closes: the approved front-end refinement programme BETA-068–087.

- [DONE] BETA-086 | Operator action cockpit
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 3
  - area: admin/overview
  - depends_on: BETA-058, BETA-059, BETA-060, BETA-063, BETA-068, BETA-085
  - objective: Replace long overview tables with prioritised cards for review
    pressure, failed/stale runs, blocked sources, coverage actions, archive
    health, schema drift and resumable work; every card opens a pre-filtered
    existing workflow.
  - result: New `pipeline/web/cockpit.py` — `overview(conn, settings)`, the
    one aggregate the BETA-068–087 interface contract plans. Seven cards,
    each `{key, title, priority (0 clear … 3 act now), metric, reason,
    link}`, ranked by a **deterministic reason** — review pressure (pending
    count + oldest age), run health (last run failed/partial → 3, ≥30 days
    stale → 2), coverage actions and blocked sources (from
    `completeness_board.board`'s `by_reason`), schema state (unapplied
    migrations → 3, applied-without-file → 2, from `health.warehouse`),
    raw-archive audit (missing refs / duplicate hashes → 3), and parse
    failures. Every `link` is an admin hash to a pre-filtered workflow
    (`#review`, `#pipeline`, `#health`). It ranks **operational states only**
    — never evidence quality, never a review outcome — and decides nothing;
    the `note` says so. New route `GET /api/admin/cockpit`. The admin
    Overview tab gains a "What needs attention" cockpit above the warehouse
    counts (`loadCockpit` in `app.js`): the cards as clickable buttons
    (priority-coloured left border), sorted worst-first, each navigating to
    its link.
  - api/ui: new read-only route `GET /api/admin/cockpit` (admin boundary; no
    params). New admin HTML `#cockpit`; new CSS `.cockpit*`.
  - validation: New `tests/test_web_cockpit.py` (4 — the cards are the seven
    operational keys, each with a priority / reason / hash link, sorted
    priority-desc then key, with no "reviewer" or "quality" in the reasons
    and the note stating the boundary; review pressure reflects the pending
    queue and an old oldest → act now with `#review`; a failed last run →
    act now; the route serves the expected shape). `test_web_admin` green.
    `ruff` clean. Browser-verified: the Overview tab shows 7 cockpit cards
    (Coverage actions p2 "29 datasets need a first run" first, then the p1s,
    then p0s); clicking "Review queue" navigates to `#review`.

- [DONE] BETA-085 | Responsive admin navigation
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 5
  - risk: 2
  - area: admin/navigation
  - depends_on: BETA-049, BETA-080
  - objective: Replace twelve horizontal tabs with a grouped sidebar —
    Review, Evidence, Operations, Data and System — using a narrow-screen
    drawer while retaining Ctrl-K, badges and existing deep links.
  - result: Presentation only — every `.tab[data-tab]` button, `showTab()`,
    the `#<tab>` hash deep links, the Ctrl-K palette and the count pills are
    unchanged. The tab strip is now a fixed 208px **left rail** grouped into
    Overview (standalone), Review (review / candidates / census / claims /
    claim review), Evidence (search / exports), Operations (pipeline /
    health) and Data (database / sql), each `.tabgroup` carrying a small
    label. `main` reserves `padding-left: 224px` for it. Below 1000px the
    rail becomes a slide-in drawer (`transform: translateX(-100%)` →
    `.open`), a `#nav-toggle` hamburger appears in the topbar, `main` drops
    its left padding, and selecting a tab closes the drawer
    (`aria-expanded` tracked). The narrow `@media` block sits after the base
    `main` rule so it wins the source-order tie (found in the browser: it did
    not, and the padding stuck at 224px).
  - api/ui: no API change. HTML: the flat `<nav class="tabs">` regrouped into
    `.tabgroup` blocks + a `#nav-toggle` button. CSS: `.tabs` as a fixed
    rail, `.tabgroup*`, the `max-width: 1000px` drawer. JS: the nav-toggle
    handler and drawer-close-on-select.
  - validation: New `tests/test_admin_navigation.py` (5 — all twelve tabs
    survive the regroup as `.tab[data-tab]` buttons; they are grouped into
    the four labelled groups; the pills stay on their tabs; the rail becomes
    a drawer on narrow screens with the media override after the base rule;
    selecting a tab closes the drawer). `test_web_admin` / `test_console` /
    security-header suites green. Browser-verified at 1400px (208px left
    rail, `main` padded 224px, `#review` / `#sql` / `#health` deep links and
    grouped-button clicks all work) and 805px (hamburger shown, drawer slid
    off-screen at `translateX(-208px)`, `main` padding 16px, toggle opens it,
    picking a tab closes it; no page overflow).

- [DONE] BETA-084 | Page-level evidence health strip
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 3
  - confidence: 5
  - risk: 2
  - area: public/trust
  - depends_on: BETA-039, BETA-043, BETA-059, BETA-080
  - objective: Standardise scope, verification state, latest retrieval,
    coverage completeness, licence and known limitations at the top of every
    public evidence page.
  - result: New shared `evidenceHealthStrip(props)` in `components.js` — one
    view model, one shape, every field an explicit state. `props` are
    `{ scope, retrievedAt, verification, coverage, licence, limitation,
    catalogueSlug }`; a value the page does not pass renders as "unknown" /
    "not stated" (`.ehs-unknown`, italic), never a blank. `verification`
    (`verified` / `partly verified` / `unverified` / `n/a`) and `coverage`
    (`complete` / `partial` / `thin` / `unknown` / `not collected`) map an
    absent value to a word and amber the concerning ones; `licence` takes a
    `{name, url}` or `'varies'`. The strip always links to the dataset
    catalogue (`#/catalogue/<slug>` when the page maps to one dataset, else
    `#/catalogue`) and to `#/coverage`. Adopted on the pay, contracts and
    treatment pages (treatment fills its `retrievedAt` after the first
    fingertips load); the remaining pages can adopt it incrementally with no
    API change.
  - api/ui: no API change. New component + CSS (`.evidence-health`,
    `.ehs-*`).
  - validation: New `tests/test_portal_evidence_health.py` (5 — the strip is
    one shared component with the five labels; missing values render an
    explicit state not a blank; it links to the catalogue and the coverage
    page; at least pay/contracts/treatment adopt it; it has its own styles).
    Chart / table / isolation suites green. Browser-verified: the contracts
    strip shows scope, "Latest retrieval 2026-08-01", "Verification not
    applicable", "Coverage partial", "Licence Open Government Licence v3.0",
    the known-limitation line, and links to `#/catalogue/procurement-notices`
    and `#/coverage`; the treatment strip fills its retrieval date after the
    data loads.

- [DONE] BETA-083 | Schema-aware data explorer
  - completed: 2026-08-29
  - priority: P2
  - impact: 4
  - effort: 4
  - confidence: 4
  - risk: 3
  - area: admin/data
  - depends_on: BETA-048, BETA-080, BETA-085
  - objective: Add schema search, table descriptions, column metadata,
    foreign-key navigation, saved read-only queries, pinned columns, JSON
    inspection and links between related records to Database and SQL.
  - result: New `catalog.foreign_key_columns(conn)` — column-level FK edges
    `{child, from_col, parent, to_col}` on both backends (SQLite
    `PRAGMA foreign_key_list`; PostgreSQL `pg_constraint` unnested), where the
    existing `foreign_keys()` only gave table pairs. New
    `queries.schema_graph(conn)` composes a **read-only** graph from the
    catalogue helpers: every table/view with `type`, `rows`, `restricted`, a
    short `description` (from a `SCHEMA_DESCRIPTIONS` registry of ~24 core
    tables), and `columns` each carrying `type` / `notnull` / `pk` and an
    `fk` object when it references another table; plus table-level `edges`.
    No row reads — the table browser's restricted-table gate, timeout and row
    caps are untouched. New route `GET /api/admin/schema-graph`. The admin
    Database tab gains a "Columns & keys" `<details>` above the data table
    (fetched once, cached): the table description and a column table where an
    FK column is a link that opens the parent table. The SQL tab gains named
    **saved queries** (`sql-saved` select + a "Save" button, `localStorage`
    key `cglpay.sql.saved`) alongside the existing unnamed history — shift-
    select a saved entry to delete it.
  - api/ui: new read-only route `GET /api/admin/schema-graph` (admin
    boundary; no params). New admin HTML `#table-schema`, `#sql-save`,
    `#sql-saved`; new CSS `.schema-panel`, `.schema-cols`.
  - not done: pinned columns and JSON-cell pretty-print in the table browser
    — deferred; the schema graph, descriptions, FK navigation and saved
    queries are the substance of the first_action.
  - validation: New `tests/test_web_schema_graph.py` (4 — the graph describes
    tables/columns/keys with the `evidence_id → evidence_records` FK on
    `document_records` and the matching table edge; it reads no rows and
    keeps the `restricted_` flag with the sidebar's `rows` shape; the
    column-level FK helper drops self-references and gives
    `{child, from_col, parent, to_col}`; the route serves it).
    `test_web_admin` / `test_catalog` green. `ruff` clean. Browser-verified:
    opening `document_records` shows the "Columns & keys" panel with 17
    columns, its description and a "→ evidence_records" FK link that opens
    that table; the SQL tab has the Save button and Saved select.

- [DONE] BETA-082 | Pipeline mission control
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 5
  - confidence: 4
  - risk: 4
  - area: admin/operations
  - depends_on: BETA-058, BETA-063, BETA-080, BETA-085
  - objective: Present dependency waves, active/queued/completed states,
    progress, durable history, failure summaries, freshness consequences and
    a focused log viewer while retaining the existing run safeguards and
    polling.
  - result: New `pipeline/web/mission_control.py` — `overview(conn, settings,
    jobs)`, a **read-only** aggregate joining the three sources the operator
    otherwise reconciles across tabs: `admin.modules(conn)` (registry, waves,
    dependencies, review and parse-failure counts, cursor freshness), the
    jobs registry (`running()` / `all()`), and `run_ledger.recent(conn, 10)`.
    It returns dependency `waves` (each module with its `depends_on`,
    `missing_dependencies`, `pending_review`, `parse_failures`,
    `cursor_updated_at` and its `last_run` — status / rows / failures /
    elapsed / run_id / origin / finished_at, taken from the most recent
    ledger row that touched it), the `active` job head, `queued` (empty —
    the runner refuses concurrent jobs by design), `history` (the ledger
    rows), `last_run`, a `failure_summary` (modules with parse failures or a
    failed last run, worst first), `never_run`, and a `note` stating the
    read-only boundary. New route `GET /api/admin/mission-control`
    (preflighted for `run_ledger`); no write route, no cancellation, no SSE.
    The admin Pipeline tab gains a "Mission control" panel (`pipeline.js`
    `loadMissionControl`, polled on `tabshown` and every `HISTORY_MS` while
    the tab is active) — a wave grid with a per-module status badge
    (ok / failed / never / idle) and deps / fail / review badges, an
    active-run line, and a "Needs attention" table. The existing job-log
    pane is the focused log viewer (unchanged).
  - api/ui: new read-only route `GET /api/admin/mission-control` (admin
    boundary; no params). New admin CSS `.mc-*`. No change to the run route
    or its safeguards.
  - validation: New `tests/test_web_mission_control.py` (4 — the read model
    joins the three sources with the right per-module fields and is empty on
    a fresh warehouse; a failed last run reaches the failure summary and the
    module's `last_run`; the route is GET-only and adds no write path; the
    note states the read-only boundary). `test_web_admin` / `test_job_history`
    green. `ruff` clean. Browser-verified: the Pipeline tab shows the
    "Mission control" panel with 4 wave blocks, all 34 modules with a "never"
    status (nothing run in the smoke warehouse), and "no active run".

- [DONE] BETA-081 | Document reading room
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 5
  - confidence: 4
  - risk: 3
  - area: public/documents
  - depends_on: BETA-041, BETA-042, BETA-062, BETA-072
  - objective: Open a search result in a split reading view containing the
    matched passage, surrounding text, document metadata, element/page
    navigation, linked evidence, provenance and stable passage links;
    returning restores search and scroll state.
  - result: Built on the existing `GET /api/v1/documents/{id}` context
    endpoint (BETA-042) — the stable `document_id` / `document_element_id`
    identifiers and the `is_anchor` / `has_more_before` / `has_more_after`
    passage model already work on both databases. `_DOCUMENT_CONTEXT_MAX`
    raised 3 → 8: a single response is still a bounded window (a readable
    passage, not the document), and the reading room's "earlier / later"
    re-anchors on an edge element rather than asking for one huge window.
    `documents.js` gains `renderReadingRoom()`, opened by page-owned hash
    keys `#/documents?q=…&doc=<id>&el=<element_id>` (each search result now
    has an "Open in reading room" button). It renders a split view:
    left — a metadata/provenance panel (type, source system, published,
    retrieved, parser name+version, element count, a source-document link, a
    "Copy passage link" button that writes the full `#/documents?…&doc=…&el=…`
    URL to the clipboard, a "← Back to results" that removes only `doc`/`el`,
    and the search caveat); right — the element window with the anchor
    highlighted and scrolled to centre, and an "↑ Earlier / Later ↓" nav
    (disabled at the document ends) that re-fetches anchored on the first or
    last visible element. Returning keeps the query in the hash (so the
    search re-runs) and the router's `scrollByHash` (BETA-077) restores the
    results scroll.
  - api/ui: no new route. `_DOCUMENT_CONTEXT_MAX` 3 → 8 (still a hard
    ceiling). New CSS `.reading-room`, `.reading-split` (stacks below 900px),
    `.reading-meta`, `.reading-body`, `.reading-nav`, `.reading-anchor`.
  - validation: New `tests/test_portal_reading_room.py` (6 — a result opens
    the room via hash keys; the room shows metadata / provenance / a passage
    link / the caveat; earlier/later re-anchor on an edge element;
    back-to-results keeps the search; the context ceiling is raised but still
    a ceiling; the split layout stacks on narrow screens). Updated
    `test_web_documents.py`'s context-cap test to 8. `test_documents` /
    `test_portal_isolation` green. `ruff` clean. Browser-verified against a
    seeded committee-paper document: the split reading room renders with the
    six metadata fields, the "Officers reported…" anchor highlighted, the
    seven-element passage; "← Back to results" returns to
    `#/documents?q=treatment` with the results list.

- [DONE] BETA-080 | Shared responsive design system
  - completed: 2026-08-29
  - priority: P1
  - impact: 4
  - effort: 4
  - confidence: 5
  - risk: 2
  - area: public/admin UI foundations
  - depends_on: BETA-049
  - objective: Consolidate spacing, typography, forms, buttons, cards,
    disclosures, statuses, skeletons, focus states and breakpoints into
    reusable primitives while preserving the two front ends' distinct
    identities.
  - result: Deliberately **not** a rewrite — the two stylesheets stay
    distinct (the operator sheet has no spacing scale by design). New
    `docs/design-system.md` is the inventory + migration map: every portal
    `:root` token by group, which component classes are shared vs.
    front-end-specific, the four canonical breakpoints (340 / 720 / 900 /
    1100), and a done/left table. Two concrete consolidations landed:
    * **Spacing scale gap fixed.** `--space-5` (20px) and `--space-10` (40px)
      were referenced by five live rules (`.section-links`, `.explore-card`,
      `.chart-data`, `.lineage-edges`, the safety card) but never defined —
      an undefined custom property invalidates the whole declaration, so
      those paddings and gaps silently collapsed to nothing. Both are defined
      now and those rules render their intended 20px. The stale
      "there is no --space-5" comment is corrected.
    * **Focus ring as one primitive.** New `--focus-ring` /
      `--focus-ring-offset` on both `:root`s, each carrying its own accent
      (`--accent-teal` / `--accent`). The unscoped `:focus-visible` rule on
      each front end now derives from the token instead of a hard-coded
      `2px solid …`. The map-control variant keeps its heavier 3px ring.
  - api/ui: no API change. CSS-token additions only; one visible change — the
    five rules that referenced the missing `--space-5` now have their 20px
    spacing (a fix, not a restyle).
  - validation: New `tests/test_portal_design_system.py` (5 — every
    `--space-*` a rule references is defined and `--space-5`/`--space-10`
    exist; the scale stays a 4px step; the focus ring is one primitive per
    front end deriving from an accent token; no rule references an undefined
    custom property; the inventory/migration doc exists and keeps the two
    front ends distinct). Offline-reading / tables / charts / admin / docs
    suites green. `ruff` clean. Browser-verified: `--space-5` resolves to
    20px, `--focus-ring` to `2px solid #21d4d0`, and `.section-links`
    `margin-top` is now 20px (was 0).

- [DONE] BETA-079 | Safety and legal evidence hub
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 4
  - area: public/safety-legal
  - depends_on: BETA-043, BETA-051, BETA-065
  - objective: Bring PFD reports, safeguarding reviews, HSE notices, CQC
    inspections and tribunal evidence into a filterable chronology with
    source-specific caveats and sensitive-content treatment.
  - result: New additive route `/api/v1/safety_legal`
    (`public_queries.safety_legal`). One chronology composed from five
    streams — `pfd_provider_mentions` (recipient → **addressed_to**,
    body_text → **named_in**), `sar_provider_mentions` (**named_in**, undated),
    `hse_enforcement_notices` with a provider match (**matched_to**),
    `tribunal_cases` with a provider (**named_in**), `cqc_locations` with an
    inspection date (**regulated_by**). Each event carries exactly one of the
    four relationship labels; `SAFETY_LEGAL_LABELS` explains each and states
    that "a mention is not a finding, an allegation or a fault". `counts`
    holds only `by_source` and `by_relationship` — **no total key anywhere**
    — and the two are never added. Each stream's table is guarded so a
    missing one is skipped. Filters: `source`, `relationship`,
    `provider_key`, `year_from`/`year_to` (year bounds only touch dated
    events). An HSE `result` is the register's own text (an appeal decision
    or a withdrawal), never an inferred compliance outcome. Personal data
    stays in the `restricted_` tables this does not read. The chronology is
    capped at 2000 events with a `truncated` flag. `pfd.js` renders it as a
    "Safety & legal chronology" section above the detailed per-source panels:
    source and relationship filter chips with their counts, the four-label
    key, per-source caveats (only the filtered source's caveat when one is
    selected), and a dated table with the relationship column. Filter state
    is in the hash (`#/pfd?source=hse`).
  - api/ui: additive route `/api/v1/safety_legal` (source, relationship,
    provider_key, year_from, year_to). Added to the OpenAPI doc,
    `<noscript>` list, `api.html` and `test_portal_isolation`
    `PUBLIC_API_ROUTES`. New CSS `.sl-chiprow`, `.sl-relationship-key`.
  - validation: New `tests/test_web_safety_legal.py` (7 — events carry one
    relationship label and the counts are never summed (no total key);
    the four labels are explained and a mention is not a finding; each source
    keeps its own caveat; source and relationship filters narrow the same
    rows; the HSE result is the register's own text; year bounds only touch
    dated events; the route is in the OpenAPI doc). `test_web_safety` /
    `test_web_openapi` / `test_portal_isolation` / chart / offline-reading
    suites green. `ruff` clean. Browser-verified: the chronology renders with
    source chips (All · 1, HSE notices · 1, others · 0) and relationship
    chips (Matched to · 1, others · 0) as **separate** counts; the four-label
    key renders; clicking "HSE notices" filters the hash and narrows the
    caveats to just HSE's.

- [DONE] BETA-078 | Unified evidence atlas
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 5
  - confidence: 4
  - risk: 4
  - area: public/geography
  - depends_on: BETA-028, BETA-043, BETA-065, BETA-072
  - objective: Combine existing geography, CQC, commissioning, funding,
    treatment and coverage maps behind a layer switcher with a synchronised
    accessible table.
  - result: New additive read-only route `/api/v1/atlas_layers`
    (`public_queries.atlas_layers`) — the **closed layer registry**. Eight
    entries (six `geography` choropleths, `cqc_locations` points, `coverage`
    authority-fill), each self-describing: `key`, `label`, `kind`, the
    `endpoint` that serves it, its `param`/`layer`, `unit`, `legend`,
    `geometry_key`, `table_columns` and its `caveat`. A `note` states the
    rule: "Exactly one layer is shown at a time. The atlas performs no
    arithmetic between layers and produces no composite score." No DB read —
    it is a manifest. The geography page is rebuilt around it: the six metric
    tabs and the multi-overlay checkbox panel are replaced by **one
    `<select>`** driven by the registry. `state.layers` (a Set) becomes
    `state.layer` (one key); the URL carries `?layer=` (falling back to the
    old `?metric=` so pre-atlas links still open). `load()` branches on
    `kind`: a choropleth fetches `geography?metric=<key>` as before; a
    points / authority layer fetches `layers`, takes the one named sub-layer
    and draws it alone (a new `coverage-fill` branch in `addLayer`, and a
    `drawPointList` accessible table built from the registry's
    `table_columns`). A legend strip shows the active layer's legend + unit;
    the caveat panel shows only that layer's caveat. The year selector hides
    for non-choropleth layers.
  - api/ui: additive route `/api/v1/atlas_layers` (no params) — added to the
    OpenAPI doc, `<noscript>` list, `api.html` and the `test_portal_isolation`
    `PUBLIC_API_ROUTES`. URL param `layer` replaces `metric`/`layers` on the
    geography route (old params still read). New CSS `.atlas-layer-select`,
    `.atlas-legend`.
  - validation: New `tests/test_web_atlas_layers.py` (5 — the registry is
    closed and self-describing; it states the no-composite rule; choropleth
    layers point at a real `geography` metric; point/authority layers name a
    `layers` sub-layer; the route is in the OpenAPI doc). Updated
    `test_web_layers.py` (the map-toggle test now checks the single registry
    selector and that no multi-overlay panel survives). `test_web_openapi` /
    `test_portal_isolation` / `test_portal_charts` green. `ruff` clean.
    Browser-verified: one selector with all 8 layers; a legend strip that
    updates per layer ("Darker = larger ring-fenced allocation. Unit: gbp.");
    switching to CQC updates the legend and the accessible-table title and
    hides the year control; no multi-overlay checkboxes. (The MapLibre canvas
    itself is not exercised offline — the CARTO basemap 404s and the page
    falls back to its local style per settled decision 6, unchanged.)

- [DONE] BETA-077 | Navigation continuity
  - completed: 2026-08-29
  - priority: P2
  - impact: 4
  - effort: 3
  - confidence: 5
  - risk: 1
  - area: public/navigation
  - depends_on: BETA-024, BETA-072, BETA-076
  - objective: Add route-aware breadcrumbs, locally stored recent entities,
    scroll restoration, meaningful back links and preservation of the
    originating search/filter context around detail pages.
  - result: The central router (`app.js`) now:
    * **restores scroll** — `scrollByHash` records `window.scrollY` for each
      URL as the page is replaced, and a return to a URL it has seen
      (back/forward, a breadcrumb) restores that position after render; a
      fresh navigation still starts at the top.
    * **keeps the originating list** — `lastListHash` records the full hash
      (filters and all) of the last *bare* list route for each base, so a
      detail page's breadcrumb links back to the exact filtered list it was
      opened from, not a bare route.
    * **draws a route-aware breadcrumb** on a `/key` detail page:
      "Overview › Back to <section> › <entity>", the entity read from the
      page's own `<h1>` first text node so the router needs no per-page
      naming.
    New `js/recent.js`: `pushRecent({type, id, name})` keeps a capped (12),
    de-duplicated, most-recent-first local list of viewed providers and
    authorities — a type, a public id and a name the portal already shows,
    nothing else, every access guarded for private mode. The provider and
    authority workbenches call it on load; the overview renders a
    "Recently viewed" block (`renderRecentList`) below "My area" and drops its
    `recentchange` listener on dispose.
  - api/ui: no API change. New served module `/js/recent.js` (server static
    map + `test_portal_isolation` whitelist). New CSS `.breadcrumbs`,
    `.recent-list`.
  - validation: New `tests/test_portal_navigation_continuity.py` (5 — the
    router restores scroll for a known URL and tops a fresh one; the
    breadcrumb links back to the originating filtered list via `lastListHash`;
    `recent.js` is served, guarded and capped; it stores only public
    identifiers; the detail pages push and the overview shows and cleans up).
    `test_portal_isolation` / navigation / offline-reading / security-header /
    my-area suites green. `ruff` clean. Browser-verified: opening a provider
    renders the breadcrumb "Overview › Back to providers › Change Grow Live"
    and stores `{type:"provider", id:"cgl", name:"Change Grow Live"}`; the
    overview then lists it under "Recently viewed" linking to
    `#/providers/cgl`. (Scroll restoration verified by code inspection — the
    automation pane could not exercise programmatic scroll.)

- [DONE] BETA-076 | Navigable provider and authority workbenches
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 5
  - risk: 2
  - area: public/entity detail
  - depends_on: BETA-017, BETA-045, BETA-065, BETA-066
  - objective: Add sticky section indexes, counts, deep-link anchors,
    progressive disclosure, section search and back-to-top controls; paginate
    or collapse large collections while preserving complete exports.
  - result: Two shared helpers in `components.js`. `workbenchNav(pageRoot,
    sections, {routePath})` builds a sticky section index from
    `[{id, label, count, available}]`: a horizontally-scrollable chip bar
    (its own `overflow-x` — never the page's), a count badge per section, an
    `IntersectionObserver` scroll-spy that sets `aria-current` on the section
    in view, a fixed "↑ Top" button that appears past 600px of scroll, and a
    `?section=<id>` deep link that scrolls to a section (polling briefly for
    an async-filled one) and is written to the URL with `replaceState` — no
    re-render. `available: false` greys a section row rather than hiding it,
    so "no records" stays visible. Returns `{nav, cleanup}`; the page
    `dispose` calls `cleanup` (disconnects the observer, drops the scroll
    listener, removes the button). `collapsibleSection(id, title, count, body,
    {collapsedAbove, extra})` collapses a large collection behind a
    "Show all N" `<details>` while the `extra` slot (a Download button) stays
    in the header, outside the collapse — so a complete export never depends
    on the section being expanded. Wired into the provider workbench (11
    sections, counts from the timeline payload: identifiers, timeline,
    relationships, CQC locations, CQC reports, charity finance, disclosure,
    company filings, PFD mentions, tribunal cases) and the authority
    workbench (coverage, grant & budget, budget detail, treatment, contracts,
    homelessness comparators).
  - api/ui: no API change. New CSS `.workbench-index*`, `.workbench-totop`,
    `.section-count`, `.section-disclosure`.
  - validation: New `tests/test_portal_workbench_nav.py` (6 — the exports
    exist; the index has a scroll-spy, count badges and a back-to-top and
    greys rather than hides an empty section; deep links are a `?section=`
    key written with `replaceState`, not a re-render; progressive disclosure
    keeps the export outside the collapse; both workbenches mount the index
    and clean it up; the provider counts come from payload fields).
    `test_portal_isolation` / `test_web_authority` / `test_web_provider_compare`
    / navigation / chart suites green. `ruff` clean. Browser-verified: the
    provider index renders 11 links with counts and `is-empty` on the zero
    sections; a `?section=tribunals` deep link scrolls to that section and the
    scroll-spy marks its link `aria-current`; at 375px the index is a sticky
    horizontally-scrolling bar with no page overflow.

- [DONE] BETA-075 | Treatment metric explorer
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 3
  - area: public/treatment
  - depends_on: BETA-043, BETA-049, BETA-072
  - objective: Reframe treatment data around a searchable metric catalogue
    that exposes definitions, units, confidence intervals, periods,
    publication coverage, authority/region views and provenance before drawing
    a chart.
  - result: New additive read-only route `/api/v1/treatment_metrics`
    (`public_queries.treatment_metrics`). One catalogue row per Fingertips
    indicator and per NDTMS source table, each carrying: name, topic,
    substance, unit, definition, `has_confidence_interval` (true iff a
    `lower_ci_95` is actually present — always true for NDTMS), `periods` (the
    exact published `time_period` values, ordered by `time_period_sortable`,
    **never gap-filled or zeroed** — a metric with no values gets `[]` and a
    null range), `period_count`, `period_range`, `authority_count`,
    `england_available`, `source_url` and `retrieved_at`. Computed from the
    same `fingertips_*` / `ndtms_la_statistics` tables the treatment page
    charts, so a catalogue row cannot claim coverage the chart lacks.
    `treatment.js` renders the catalogue in a `#metric-catalogue` section
    *above* the chart: a search box (name / unit / definition), a "N of M
    metrics" count, and a scrollable list where each row shows the source and
    CI badges, a unit / periods / authorities / England / retrieved metadata
    grid, an expandable definition and a source link. Picking a Fingertips
    metric sets its topic tab and scrolls to the chart.
  - api/ui: additive route `/api/v1/treatment_metrics` (no params). Added to
    the OpenAPI document, the `<noscript>` route list, `api.html`, and the
    `test_portal_isolation` `PUBLIC_API_ROUTES`. New CSS `.metric-*`.
  - validation: New `tests/test_web_treatment_metrics.py` (4 — the catalogue
    carries unit / definition / CI / periods / coverage / provenance; a metric
    with no values reports no coverage rather than zero; periods are exactly
    what was published in order with a deleted year simply absent; the route
    is in the OpenAPI document). `test_portal_isolation` / `test_web_openapi` /
    `test_web_public` green. `ruff` clean. Browser-verified: the catalogue
    lists two seeded Fingertips metrics with the right CI badge (one "95% CI",
    one "no CI"), search narrows to "1 of 2 metrics", picking the opiates
    metric activates the "Numbers in treatment" tab; no overflow at 1440.

- [DONE] BETA-074 | Inspectable visualisations
  - completed: 2026-08-29
  - priority: P2
  - impact: 4
  - effort: 3
  - confidence: 5
  - risk: 2
  - area: public/charts
  - depends_on: BETA-020, BETA-049, BETA-080
  - objective: Standardise keyboard-accessible legends, series toggles, value
    tooltips, appropriate zoom/reset, caveat and missing-period annotations,
    image saving and direct movement between each chart and its accessible
    table.
  - result: The shared `mountChart()` wrapper in `components.js`. The ECharts
    legend is a canvas and mouse-only, so a chart with 2–12 named series now
    also gets a row of HTML `<button>` series toggles above it — keyboard- and
    screen-reader-operable, state carried as `aria-pressed`, each dispatching
    the same `legendToggleSelect` action (a hidden legend is injected when the
    chart declared none, so the action lands without changing the drawing).
    `zoom: true` adds an ECharts toolbox with `dataZoom` + `restore` and a DOM
    "Reset view" button; opt-in, because a pie or single bar has nothing to
    zoom. `saveAsImage` is deliberately kept out of the toolbox — the existing
    DOM "Save image" button (which draws the caption and caveat into the PNG)
    is the only save path. `missingNote` renders an explicit
    "no published figure for …" line under the chart rather than closing the
    gap. `tableHref` renders a "View as table" link, and `tableCard` gains an
    `anchorId` so it can be the target. Proven on the pay page: the indicative
    wage line chart (time-series — `zoom`, `missingNote` computed from
    all-null years, `tableHref`/`anchorId` to `#pay-wage-table`), the
    advertised-pay scatter (time axis — `zoom`), and every 2-series bar (the
    gender pay gap chart — auto keyboard toggles). Every other chart inherits
    the toggles and controls automatically.
  - api/ui: no API change. New `mountChart` options `zoom`, `seriesToggles`,
    `tableHref`, `missingNote`; `tableCard` option `anchorId`. New CSS
    `.chart-series-toggle*`, `.chart-controls`, `.chart-to-table`,
    `.chart-missing-note`.
  - validation: `tests/test_portal_charts.py` +5 (series toggles are keyboard
    buttons with aria-pressed and the ECharts action; zoom/reset opt-in with
    saveAsImage kept out of the toolbox; missing periods annotated not closed;
    chart↔table link with `anchorId`; the pay page proves the contract).
    Chart / table / isolation suites green. `ruff` clean. Browser-verified:
    the gender-pay-gap chart shows two keyboard toggle buttons; clicking one
    flips `aria-pressed` and hides the series, clicking again restores it; the
    control row and save button render; no console errors from the wrapper.

- [DONE] BETA-073 | My area context
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 2
  - area: public/local evidence
  - depends_on: BETA-017, BETA-043, BETA-044
  - objective: Let a reader choose and locally retain one council without an
    account, then present its funding, treatment, contracts, providers,
    relationships, homelessness comparators, coverage and freshness through
    links to the underlying evidence.
  - result: New `js/myarea.js`. `localStorage` key `sectortrace.my_area` holds
    only the nine-character ONS code, gated on `/^[A-Z][0-9]{8}$/` on both
    read and write — no name, no postcode, no personal data — and every
    access is wrapped so private mode degrades to "feature absent" rather than
    throwing. `myAreaToggle(code, name)` is a star button on the authority
    workbench hero (set / clear, `aria-pressed`, listens for `myareachange`).
    `renderMyAreaCard(container)` fetches only the existing
    `/api/v1/authorities/:code` payload and renders a compact card on the
    overview: the authority name (linked), its type/region, the latest
    `retrieved_at` across the payload as a freshness line, and five stat tiles
    — grant years, budget years, treatment indicators, contract notices,
    homelessness comparators — each linking to the matching section anchor on
    the workbench (`#grant-budget`, `#treatment`, `#contracts`,
    `#comparators`), plus workbench / compare / commissions links. No saved
    area shows a prompt to choose one on the map. The overview registers a
    `myareachange` listener and removes it on dispose.
  - api/ui: no API change; no new route. New served module `/js/myarea.js`
    (server static map + `test_portal_isolation` whitelist). New CSS
    `.myarea-*`, `.linklike`.
  - validation: New `tests/test_portal_my_area.py` (6 — the module is served
    and exports the surface; localStorage holds only the validated ONS code
    (one guarded `setItem`, ONS regex on read and write); access is guarded
    for private mode; the card reads only the existing authority route; every
    stat links into the workbench; the overview and authority pages wire it in
    and the overview removes its listener on dispose). Portal isolation /
    offline-reading, `test_web_authority`, security-header suites green.
    `ruff` clean. Browser-verified: empty prompt with no saved area; "Set as
    my area" on E08000025 stores `E08000025` and flips the star; the overview
    card then shows Birmingham with "25 contract notices" linking to
    `#/authorities/E08000025#contracts`; "Change" clears it; no console
    errors; no overflow at 1440.

- [DONE] BETA-072 | Consistent filters and URL-restored query state
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 3
  - confidence: 5
  - risk: 2
  - area: public/filtering
  - depends_on: BETA-024, BETA-049
  - objective: Standardise filter bars with active chips, result counts,
    clear-all, basic/advanced disclosure, validation and hash-query
    persistence; browser history and shared URLs must restore the exact query.
  - result: New `js/filterstate.js` — the one typed definition of the shared
    filter state. `FILTER_SCHEMA` maps each key (`provider`, `yearFrom`,
    `yearTo`) to its query-param name, type and chip label; `parseFilters`,
    `serializeFilters` (carrying page-owned keys — compare's `ons_code`,
    contracts' `q`, pay's `source` — through untouched), `validateFilters`
    (year bounds 2000..currentYear+1 and from ≤ to) and `chipLabels` are the
    only readers/writers. `app.js`'s `writeStateToUrl` / `readStateFromUrl`
    now route through it, and a `hashchange` re-syncs the shared state before
    rendering so the back/forward buttons and an edited address bar restore
    the exact query, not just the route (previously state was read from the
    URL only at boot). The filter summary resolves the provider key to its
    canonical name for the chip, shows a per-page result count beside the
    chips (`setFilterResultCount(count, noun)`, wired in contracts, providers
    and treatment; cleared by the router on route change), and shows an inline
    validation message with `aria-invalid` on the year inputs — an invalid
    year range is refused rather than sent to an endpoint. "Clear all" now
    wipes the whole hash query (shared + page-local) and keeps the route.
  - not done / N/A: basic/advanced disclosure on the *shared* bar — it holds
    only provider + year range, with nothing to tuck away. Per-page advanced
    filtering already lives in each page's own search / explorer panel
    (contracts search, the BETA-070 pay explorer).
  - api/ui: no API change. New served module `/js/filterstate.js` (added to
    the `test_portal_isolation.py` public-surface whitelist and the server
    static map). New CSS: `.filter-summary-count`, `.filter-summary-error`,
    `[aria-invalid]` year inputs.
  - validation: New `tests/test_portal_filter_state.py` (8 — the module is
    served and exports the serializer surface; the schema covers the shared
    keys; page-owned keys survive serialisation; year validation checks
    bounds and order; `app.js` re-reads state on `hashchange`; "Clear all"
    wipes the whole query; contracts/providers/treatment report a count; the
    chip resolves the provider name). `test_portal_isolation` /
    `test_portal_controls` / `test_web_meta` / security-header suites green.
    `ruff` clean. Browser-verified: a deep link restores the resolved-name
    chip + count, an invalid year range shows the inline message and is not
    applied, "Clear all" returns to a bare route, the summary hides when no
    filter is active.

- [DONE] BETA-071 | Responsive public data tables
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 2
  - area: public/tables
  - depends_on: BETA-049, BETA-080
  - objective: Give every public table a mobile card mode, priority columns,
    column chooser, density control, sticky identifiers and explicit
    full-table mode while retaining complete accessible tabular data and
    exports.
  - result: The shared `table()` / `tableCard()` in `components.js` — every
    public table goes through it. `withPriorities()` maps a column's optional
    `priority` (0 stays longest, higher collapses first; unset = column
    position, so column 0 is the identifier) onto Tabulator's `responsive`
    weight, and the table runs `responsiveLayout: 'collapse'`
    (`…CollapseUseFormatters: true`): as the viewport narrows, low-priority
    columns fold into a per-row toggle that lists them as formatted
    label/value pairs — the phone "card" reading — with the row data and the
    CSV export untouched. The first column of a wide table (>6 cols), or one
    flagged `sticky: true`, is `frozen` so the identifier stays in view while
    the rest scrolls in full-table mode. `tableCard()` gains a "Table view"
    `<details>` menu: density (comfortable / compact, a redraw), a column
    checklist (`showColumn`/`hideColumn`), and an explicit "Full table" toggle
    that shows every column and scrolls sideways. The contracts "Published
    notices" table (9 columns, the widest public table) is migrated with
    explicit priorities; narrow tables (≤4 columns) inherit the position
    default and never freeze or collapse.
  - fix in passing: `.grid.two` / `.grid.cards` used `minmax(420px, 1fr)` /
    `minmax(215px, 1fr)`, whose track keeps its stated minimum even in a
    narrower container — the contracts table panels overran a 375px viewport
    by ~60px. Now `minmax(min(420px, 100%), 1fr)`, plus `min-width: 0` on grid
    children and `.tablecard`, and `overflow-x: auto` on the table holder so
    any residual width scrolls inside the card, never the page body.
  - api/ui: no API change. New CSS: `.table-view*`, `.tablecard.density-compact`,
    `.tablecard.is-fulltable`, the grid `min()` fix.
  - validation: New `tests/test_portal_responsive_tables.py` (7 — priority →
    responsive mapping, collapse keeps the fields, the view menu carries
    density/columns/full-table and acts on the live instance, the plain-table
    fallback carries `data-priority`, `.grid.two` can shrink below its track
    minimum, table overrun is contained in the card, the contracts table
    ranks every column). Portal table / chart / control / isolation suites
    green. `ruff` clean. Browser-verified at 1440 and 375: desktop shows all
    9 contract columns with a frozen identifier and no page overflow; 375
    shows the 4 highest-priority columns with the rest behind the row toggle,
    the view menu opens, "Full table" restores every column, and the
    pre-existing ~60px mobile overrun is gone.

- [DONE] BETA-070 | Workforce pay explorer
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 3
  - area: public/workforce
  - depends_on: BETA-043, BETA-049
  - objective: Create one focused interface for salary bands, statutory
    benchmarks, workforce census measures, provider pay pages, job adverts,
    gender-pay-gap filings and Living Wage evidence, filtered by role,
    provider, source, year and pay unit.
  - result: `/api/v1/pay` gains three additive, backward-compatible filter
    params — `role` (case-insensitive substring against each source's own
    role-text field), `source` (one closed `PAY_SOURCE_GROUPS` key), and
    `pay_unit` (`hourly` / `annual` / `other`). They narrow the existing
    per-source arrays in place; a `source` the reader excludes is emptied, not
    removed, so the payload shape never changes. Nothing is joined, summed or
    scored — `PAY_SOURCE_GROUPS` names each group's arrays, its role fields
    and its legitimate units, and a `primary` subset so a derived chart
    aggregate (`nhs_job_by_band`) does not inflate the group count. The
    response now also carries `source_groups` (per-group label + post-filter
    count + units, the explorer's index) and `filters_available` (the role
    labels and units present at the current provider/year scope, computed
    *before* the role filter so choosing a role does not empty its own
    picker). `pay.js` renders a control strip above the existing layers:
    source-group chips (All + five groups, each with its count), a role
    `search`+`datalist` input, and a pay-unit select; state lives in the hash
    query (`#/pay?source=…&role=…&pay_unit=…`) so a filtered view is a link,
    and selecting one group shows only that section ("focused"). The
    workforce-census layer — fetched by this endpoint but never rendered on
    the page — now has a `renderCensus` panel, shown when its group is
    selected.
  - api/ui: additive params on `/api/v1/pay`; `source_groups` /
    `filters_available` / `filters_applied` added to the response. OpenAPI
    updated. New CSS: `.pay-explorer*`, `.filter-chip.is-active`.
  - validation: New `tests/test_web_pay_explorer.py` (7 — baseline groups and
    pickers; `source` shows one group and empties the rest without changing
    the shape; `role` is a case-insensitive substring; `pay_unit` keeps only
    rows carrying that unit; filters compose without introducing a
    rate/ratio/score key; bad `source`/`pay_unit` raise `QueryError`; the role
    picker is not shrunk by an active role filter). `test_web_public` /
    `test_web_openapi` / `test_web_exports` green. `ruff` clean.
    Browser-verified: the strip renders, chips/inputs update the hash and
    re-render, a single-source view shows only its section, deep links
    restore the exact filtered view, no console errors, no horizontal
    overflow.

- [DONE] BETA-069 | Rebuild the mobile public header
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 3
  - confidence: 5
  - risk: 1
  - area: public/responsive shell
  - depends_on: BETA-049
  - objective: At phone widths show only brand, menu and search; move council
    lookup, navigation and theme selection into the drawer; remove clipping,
    horizontal overflow and the duplicated campaign-lens label.
  - result: Root cause of the 390px clipping and of a broken section drawer
    that predated this item: `.topbar` carried `backdrop-filter`, which makes
    it the containing block for every `position: fixed` descendant — so
    `#portal-nav` (the `offcanvas-lg` section drawer) was being sized against
    the 64px topbar, and opening the menu on a phone showed a 32px sliver of
    clipped links. The glass effect moved to `.topbar::before`
    (`position: absolute; inset: 0; backdrop-filter`), which keeps the look
    and lets the drawer escape to the viewport. The council navigator
    (`.findcouncil`) moved out of the topbar flex row and into the drawer as
    a full-width row (ordered above the theme control); on desktop
    `.mainnav`'s `margin-left: auto` places it at the end of the nav row
    rather than floating centre-right as before — a deliberate, minor change
    to the wide layout, not a regression. The council field's
    `width: min(35vw, 150px)` and `width: 88px` rules — the actual clipping —
    are gone. The overview route no longer prepends its `.route-lens` strip
    (removed `'/'` from `lensByRoute` in `app.js`): the hero kicker already
    carries an "Accountability" lens badge and the two stacked into a visible
    duplicate at phone widths. `initFindCouncil`'s `go()` now closes the
    drawer after a pick, since the council list uses listbox options rather
    than the `<a>` elements the drawer's auto-close watches.
  - api/ui: No API change. Phone topbar is brand + menu + Search only; council
    lookup, nav and theme selection all live in the drawer. Theme control was
    already duplicated into the drawer (unchanged).
  - validation: New `tests/test_portal_header.py` (7 — council finder markup is
    inside `#portal-nav`, no viewport-unit width rule for the field survives,
    it is a full-width drawer row, the mobile theme control is in the drawer,
    the desktop `margin-left: auto` lift is retained, the overview route has
    no `lensByRoute` entry, the topbar still carries brand/menu/search).
    Portal + security-header suites green. Browser-verified at 375x812,
    768x1024 and 1440x900: no horizontal overflow at any width, the drawer
    now opens full height with every link, the council field fits inside the
    viewport, no duplicated lens on the overview, no console errors.

- [DONE] BETA-068 | Release compatibility and graceful degradation
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 3
  - confidence: 5
  - risk: 2
  - area: public/admin reliability
  - depends_on: BETA-039, BETA-063
  - objective: Check the build's required schema, tables, extensions and routes
    before rendering each capability; replace raw database/traceback text with a
    feature-specific unavailable state carrying retry, build/schema identity and
    a safe operator diagnostic reference.
  - result: New `pipeline/web/degrade.py`. `FeatureUnavailable` is the typed
    refusal a capability raises; `REQUIREMENTS` + `preflight(conn, feature)`
    declare the migration level, tables and PostgreSQL extensions each named
    feature needs and check them before the query runs, so a partial
    deployment fails as `{code: "missing_migration" | "missing_table" |
    "missing_extension"}` naming the feature rather than as `no such table`
    from three joins deep. `classify_db_error()` catches a raw
    `OperationalError` / psycopg `UndefinedTable` / `QueryCanceled` that is
    really schema drift or a section timeout and converts it to the same
    bounded state (timeout → `retryable: true`). `server.py` builds the wire
    envelope: `error` stays the human string the portal and older tests read;
    additive `error_detail` carries `{code, message, retryable, feature,
    build, schema, ref}` where `ref` is a short token also written to the log
    (`web.feature_unavailable`) so an operator can trace the cause without SQL
    ever reaching the reader. `document_search` and `run-ledger` — the two
    surfaces that showed raw tracebacks in live review — now preflight.
  - api/ui: `error_detail` object added beside `error` on any 4xx/5xx it
    applies to (backward compatible — no existing response default changed).
    `components.js` gains `unavailableCard()`; `errorCard()` delegates to it
    whenever the caught error carries `.detail`, and every page catch now
    passes the error object through, so the feature-specific card with an
    "Operator diagnostics" disclosure (feature, code, ref, build, schema)
    renders portal-wide. `app.js` `fetchJSON` attaches `.detail`/`.status` to
    the thrown error. Retry shown only when `retryable`.
  - validation: New `tests/test_web_degradation.py` (12 — preflight passes on a
    full schema, no-ops an unknown feature, names a dropped table, names a
    build behind on migrations; `classify_db_error` recognises a missing
    SQLite table and an interrupted query, leaves an unrelated error for the
    500 path; the wire envelope on a dropped `run_ledger` / `document_elements`
    carries the full `error_detail` while `error` stays a plain string; a
    healthy build still answers 200; an ordinary 400 keeps the flat `error`
    shape with no `error_detail`). Full offline suite + `ruff` clean.
    Browser-verified against a fresh SQLite warehouse: dropping
    `document_elements` renders the unavailable card on `#/documents` with
    feature `document_search`, code `missing_table`, a diagnostic ref, and no
    SQL text; no console errors on the healthy portal.

- [DONE] BETA-067 | Capability-documentation consistency checker
  - completed: 2026-08-29
  - priority: P2
  - impact: 4
  - effort: 3
  - confidence: 5
  - risk: 1
  - area: documentation/tooling
  - depends_on: BETA-038, BETA-048
  - objective: Add machine-owned documentation blocks generated from module,
    source, route, export, licence and caveat registries, with non-mutating
    `pipeline docs-check` for CI and explicit `pipeline docs-sync` regeneration.
  - result: New `pipeline/docs_matrix.py` — `GENERATED_BLOCKS` maps a block
    name to `(path, renderer)`; `check()` diffs the committed block against a
    fresh render (read-only, returns a unified diff per stale block),
    `sync()` rewrites it in place, `render()` emits the full marker-bounded
    block for a first insertion. `_locate()` finds the span *between* the
    `<!-- BEGIN GENERATED: name -->` / `<!-- END GENERATED: name -->` markers
    and raises if they are missing or reversed — the narrative around them is
    never touched. First (and currently only) block:
    `source-capability-matrix` in `docs/SOURCES.md`, one row per collecting
    module rendered from `pipeline/web/datasets.py::DATASETS` joined to
    `pipeline/licences.py::for_module` — module id, source, evidence layer,
    cadence, public tables, licence. A registry change without
    `pipeline docs-sync` now fails.
  - api/ui: `pipeline docs-check` (read-only; prints a diff per stale block
    and exits 1) and `pipeline docs-sync` (rewrites, reports which blocks
    changed). `docs-check` added to the CI workflow beside the beta-queue
    validation. Reconciled the stale committee-system prose in
    `docs/SOURCES.md` (the Sources row for Modules 9/10 now states plainly
    that only ModernGov is searched and other systems are recorded
    unsupported). `README.md` Development section documents the mechanism.
  - validation: New `tests/test_docs_matrix.py` (8 — the matrix is
    deterministic, every collecting module is a row carrying its registry
    licence, **the committed block is in sync** (the CI guard),
    `render()` is marker-bounded, `_locate()` raises on a missing marker,
    `check()` flags a hand-edited block and `sync()` repairs it idempotently
    without touching the surrounding text, and the CLI exits 0 on a synced
    tree / 1 on a stale block). `test_docs_coverage.py` / `test_licences.py`
    / `test_web_catalogue.py` still green. No migration, no schema change.
    Full offline suite green — **2876 passed, 113 skipped, 35 deselected, 0
    failed**. `ruff` clean. Not browser-observable (CLI + docs tooling), so
    no preview check.
  - closes: the approved successor programme BETA-050–067. No further round
    is approved.

- [DONE] BETA-066 | Provider predecessor and successor lineage
  - completed: 2026-08-29
  - priority: P2
  - impact: 4
  - effort: 3
  - confidence: 4
  - risk: 3
  - area: provider-identity
  - depends_on: BETA-056
  - objective: Add `GET /api/v1/providers/{provider_key}/lineage` and a provider
    detail timeline for explicit active, merged, dissolved, predecessor and
    successor relationships.
  - result: New `public_queries.provider_lineage(conn, provider_key)` —
    reads only `providers.status` / `superseded_by` (the lifecycle config
    from `pipeline/providers.py::PROVIDER_STATUS`, cross-checked against the
    registered company/charity record) and the `status='verified'` rows of
    `provider_identifiers` (`_public(["providers", "provider_identifiers"])`,
    a test greps for it). It returns typed, directional edges: forward
    `renamed_to` / `merged_into` (with the successor's key + name) or a
    terminal `dissolved` with no target; reverse `renamed_from` /
    `merged_from` for every provider whose config points at this one. Plus
    `chain` — this entity followed forward through `superseded_by` to the
    surviving one, with a `seen`-set cycle guard and a 20-hop cap — and
    `identifiers` (config-verified company / charity / CQC ids and their
    role). Every edge carries a `basis` string; no ownership is inferred and
    no individual is named.
  - api/ui: `GET /api/v1/providers/(provider_key)/lineage` — a parameterised
    addition to the frozen surface (`test_portal_isolation.py`
    `PUBLIC_API_PATTERNS`, `openapi.py` `ROUTES`, an `api.html` article with
    `data-route-pattern`). The portal provider page gains an "Entity lineage"
    section (`#lineage`, a second lazy fetch so the timeline payload is
    unchanged): the forward chain as a `A → B` breadcrumb, forward edges and
    a "Predecessors" list (phrased from the other end — "X renamed to this
    entity"), the config-verified identifiers, and the pinned caveat.
    `.lineage-chain` / `.lineage-edges` styles.
  - validation: New `tests/test_web_provider_lineage.py` (11 — the forward
    edge + chain, the survivor's predecessor list, a fork (two successors),
    a terminal `dissolved` with a null target, a multi-hop chain, a config
    cycle that does not spin, only config-verified identifiers, an unknown
    provider refused, the caveat wording, the `_public` table set, and the
    public cacheable HTTP route incl. a 400 for a missing provider).
    `test_portal_isolation.py` / `test_web_openapi.py` still green.
    `docs/CAVEATS.md` provider-universe section extended. No migration. Full
    offline suite — **2867 passed, 113 skipped, 35 deselected**, plus the one
    pre-existing flaky timing test
    (`test_db_concurrency.py::test_the_regression_reproduces_when_the_write_
    slot_is_not_serialised`, recorded under BETA-035, also seen at BETA-056)
    which fails intermittently under full-suite load and **passes on an
    isolated re-run** (31 passed); nothing in BETA-066 touches the write slot
    or concurrency. `ruff` clean. Browser-verified against a seeded scratch
    warehouse: `addaction` shows "Addaction → With You" and "renamed to With
    You"; `with_you` shows both predecessors ("Addaction renamed to this
    entity", "Kent Council on Addictions merged into this entity") and the
    verified company number; zero console errors.

- [DONE] BETA-065 | CQC regulated-location explorer
  - completed: 2026-08-29
  - priority: P1
  - impact: 4
  - effort: 4
  - confidence: 4
  - risk: 3
  - area: public/cqc
  - depends_on: BETA-045, BETA-049
  - objective: Add a filterable map, accessible table and paginated
    `/api/v1/cqc_locations` endpoint for tracked providers' CQC-registered
    locations, filtered by provider, authority, status, regulated activity,
    service type and rating.
  - result: New `public_queries.cqc_locations()` over an explicit column
    allowlist (`_CQC_LOCATION_COLUMNS`) — no registered-manager or contact
    field, which live in `restricted_cqc_location_contacts` and are never
    read here; only `provider_key IS NOT NULL` rows (a location matched to a
    tracked provider). Six filters: `provider_key`, `authority_ons_code`,
    `registration_status`, `regulated_activity` (a contains match, because
    CQC's activity names themselves contain commas and the comma-joined
    column cannot be split exactly), `service_type` (an exact token match on
    the comma-free gacServiceType names) and `rating` (matched against the
    API rating or the bulk-export fallback). The payload carries
    `results`, `total`, `without_coordinate` (rows in the current filter with
    no lat/long — listed in the table, not on the map), `facets`
    (`registration_status`, `overall_rating`, `region`, `service_type`, over
    the tracked scope), `filters` and `caveat`. `rating_source` is `api` /
    `bulk_export` / `null` per row.
  - api/ui: `GET /api/v1/cqc_locations` — a flat route added to the frozen
    public surface (`test_portal_isolation.py` `PUBLIC_API_ROUTES` +
    `PUBLIC_STATIC_PATHS`), `openapi.py` `ROUTES`, the `index.html`
    `<noscript>` list and an `api.html` article. New portal page
    `/js/pages/cqc.js` (route `/cqc`, in `app.js` `ROUTES` / `ROUTE_TITLES`,
    a nav link) — page-local filter selects populated from the facets, a
    MapLibre point map (self-loaded vendor script, same pattern as
    `geography.js`), an accessible `tableCard` in parity with the map, the
    without-coordinate note, pagination and provenance. `.cqc-map` style.
  - validation: New `tests/test_web_cqc_locations.py` (9 — only tracked
    locations, the column allowlist has no personal field, the bulk-rating
    fallback and its `rating_source`, each of the six filters narrows
    correctly (incl. exact-token service type vs substring, and the
    comma-bearing activity contains-match), `without_coordinate` per filter,
    facets over the tracked scope, pagination clamp, the "not a service map /
    neither coverage nor quality" caveat wording, and the public cacheable
    HTTP route). `test_portal_isolation.py` / `test_web_openapi.py` /
    `test_portal_controls.py` / `test_portal_tables.py` all still green.
    `docs/CAVEATS.md` Module 5 section extended. No migration. Full offline
    suite green — **2857 passed, 113 skipped, 35 deselected, 0 failed**.
    `ruff` clean. Browser-verified against a seeded scratch warehouse: the
    page renders the caveat, facet filters (with counts), the map, the
    parity table with `rating_source`, and the without-coordinate note;
    selecting rating "Good" narrows to one row; zero console errors.

- [DONE] BETA-064 | Temporary-accommodation B&B breakdown
  - completed: 2026-08-29
  - priority: P2
  - impact: 3
  - effort: 3
  - confidence: 4
  - risk: 2
  - area: dataset/comparators
  - depends_on: BETA-043
  - objective: Extend m31 with the source-published bed-and-breakfast household
    breakdown from H-CLIC Table TA1, stored in
    `temporary_accommodation_breakdowns` with authority, quarter, value, unit
    and full provenance.
  - result: New migration `0077_temporary_accommodation_breakdowns.sql`
    (+ postgres pair, count 76→77) — a **narrow** table, one row per
    `(ons_code, quarter_start, measure)`: `measure`, `unit` (`'households'`),
    `households` INTEGER (NULL for a `[x]`/`[z]`/`[c]` placeholder),
    `households_text` verbatim, full provenance. Narrow because the B&B
    sub-columns are not stable across the series.
    `m31_temporary_accommodation` gained `_BB_MEASURES` (a **closed set** —
    `bb_households`, `bb_households_with_children`) and
    `locate_ta1_breakdown_columns(rows, anchor, snapshot_columns)`, which
    bounds the B&B block from its first bed-and-breakfast-named column up to
    the next snapshot column (a trailing "of which" sub-header —
    `Total with children`, `Total number of households` — joins; a separate
    non-B&B group to the right does not) and classifies each column in the
    block. A B&B column matching no measure, or a measure that would be
    claimed twice, is a `temporary_accommodation_breakdown_unknown_column`
    review item for that quarter — never a guessed row. The block is
    optional: a quarter with no recognisable B&B column writes no breakdown
    rows and is not an error. The upserts sit in the module's existing
    per-quarter `conn.commit()`.
  - api/ui: `authority()` gains
    `comparators.temporary_accommodation.breakdown` (+ `breakdown_caveat`);
    `temporary_accommodation_breakdowns` added to the `_public()` allowlist.
    The portal authority page renders a "Bed-and-breakfast breakdown
    (Table TA1)" table under the existing TA comparator — measure label,
    quarter, `households_text` verbatim — with its own pinned caveat. No new
    route. `datasets.py` m31 `public_tables` extended.
  - validation: `tests/test_m31_temporary_accommodation.py` gained 5 — the
    old multi-row-header shape splits `bb_households` / `bb_households_with_
    children`, the flat-header shape has only `bb_households`, extracted
    values match the real published rows in both eras, an unrecognised B&B
    column is reported in `unknown` not guessed, and no B&B column is not an
    error. `tests/test_web_authority.py` gained the breakdown assertions
    (a `[c]` placeholder stays `[c]` with a NULL number) and the
    empty-shape check. `tests/test_migration_equivalence.py` count 76→77.
    Docs: `docs/CAVEATS.md` (Module 31 — measure absence ≠ zero; context
    only), `docs/SOURCES.md`, `README.md`. Full offline suite green —
    **2848 passed, 113 skipped, 35 deselected, 0 failed**. `ruff` clean.
    Browser-verified against a seeded scratch warehouse: the authority page
    shows the B&B table with `40` and a preserved `[c]`, its caveat pinned,
    zero console errors.

- [DONE] BETA-063 | PostgreSQL extension readiness gate
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 3
  - area: database/deployment
  - depends_on: BETA-036, BETA-039
  - objective: Add read-only `pipeline pg-capabilities` reporting PostgreSQL
    version, extensions, operator classes, expected indexes and active fallbacks;
    exercise core and extension-enabled disposable PostgreSQL paths in CI.
  - result: New `pipeline/pg_capabilities.py` — `report(conn)`, strictly
    read-only (`pg_catalog` / `information_schema` only, no `CREATE
    EXTENSION`, no `CREATE INDEX`). It carries a hand-maintained matrix,
    `BACKED_INDEXES`: for each of the five `pg_trgm` GIN indexes, the PostGIS
    GiST `authorities.geom` index and the pgvector HNSW
    `document_embeddings.embedding_vec` index, the access method, the
    operator class (`gin_trgm_ops` / `vector_cosine_ops`), the query path it
    accelerates and the fallback that runs without it. The report gives
    `server_version`, an extension list (available / installed / version /
    what it backs), a per-index row (present, `method_ok`, `opclass_ok`,
    `healthy`), the `active_fallbacks` list — one entry per query path
    currently degraded, with the reason (extension missing / index missing /
    wrong method / wrong opclass) — and `ready`, true only when every
    warehouse extension is installed and nothing is on a fallback. A note
    fires when pgvector is installed but the derived `embedding_vec` column
    is absent. On SQLite it returns `applies: false`, `ready: true` and a
    one-line explanation.
  - api/ui: `pipeline pg-capabilities [--strict]` (JSON to stdout; `--strict`
    exits non-zero unless `ready`; SQLite always exits 0).
    `GET /api/admin/pg-capabilities` (admin only). A "PostgreSQL
    capabilities" panel in the Health tab — the index table plus the active
    fallbacks list, or the "gate does not apply" line on SQLite.
  - validation: New `tests/test_pg_capabilities.py` (6 offline — the SQLite
    branch, every matrix row names a `db.WAREHOUSE_EXTENSIONS` member, every
    matrix index is declared `USING <method>` in the PostgreSQL migration
    tree with its opclass present, the CLI reports and stays exit 0 on
    SQLite with and without `--strict`, and the route is admin-only /
    404 under `/api/v1`). New `tests/test_pg_capabilities_live.py` (4,
    self-skipping without `POSTGRES_TEST_URL`, `scratch_schema` isolation
    like `test_postgres_live.py`) — the report applies and names the server,
    `ready` is exactly "no fallbacks and every extension installed", each
    extension state is described correctly (missing → a fallback per feature
    and `healthy: false`; installed with its index → `healthy: true` and no
    fallback for that feature), and the module is read-only. Added to the CI
    "tests that need the driver" job, which runs it with and without the
    optional extensions on a disposable server. `docs/DEPLOYMENT.md` updated.
    `tests/test_portal_isolation.py` pins the admin-only route. No migration.
    Full offline suite green — **2843 passed, 113 skipped, 35 deselected, 0
    failed**. `ruff` clean. Browser-verified against a SQLite scratch
    warehouse: the Health panel shows the "gate does not apply" line, zero
    console errors.

- [DONE] BETA-062 | Human-readable document titles
  - completed: 2026-08-29
  - priority: P2
  - impact: 4
  - effort: 3
  - confidence: 4
  - risk: 2
  - area: documents/public-ux
  - depends_on: BETA-041, BETA-042
  - objective: Replace hash-like labels with deterministic display titles while
    preserving raw source titles and recording `title_basis` as source label,
    PDF metadata, first heading or filename.
  - result: New migration `0076_document_display_title.sql` (+ postgres pair,
    count bump 75→76) — `document_records.display_title` and `title_basis`,
    both nullable, plus an index on `title_basis`. `TEXT` → `text` the only
    dialect difference.
    New pure module `pipeline/documents/titles.py` — `derive(source_title,
    pdf_title, headings, filename)` returns `(display_title, title_basis)` by
    a fixed precedence: the collecting module's own label
    (`source_label`) → the PDF `/Title` from inspection (`pdf_metadata`) →
    the first heading of the active parse that reads as a name (`heading`) →
    a de-slugified filename (`filename`) → `(None, "unknown")`. Every rung is
    normalised (whitespace, surrounding quotes, a 200-char cap) and screened:
    a hash-like or UUID-ish string, a bare number, a short code like `TA1`, a
    running-header artefact like `Page 1`, and generic filler words
    (`document`, `final`, `minutes`, …) are all rejected rather than shown as
    a title. No IO; `rank_of()` exposes the ordering.
    `pipeline/documents/repository.py` gained `refresh_display_title(conn,
    document_id, *, source_title, pdf_title=None)` (reads the active
    version's first headings, calls `derive`, writes the pair) and
    `backfill_display_titles(conn, *, recompute=False)` (deterministic,
    idempotent, commits per row). `pipeline/documents/service.py` calls
    `refresh_display_title` right after a successful `persist_parse`, passing
    `inspection.metadata.get("title")` for the PDF rung (`{}` for non-PDFs,
    so simply `None`). New CLI `pipeline documents backfill-titles
    [--recompute]`.
  - api/ui: `GET /api/v1/document_search` and `GET /api/v1/documents/{id}`
    now return `title` = `display_title or title or filename`, plus
    `title_basis` (nullable until the backfill runs) and `source_title` (the
    raw collecting-module label). The portal document-search result card
    shows the derived title and, when `title_basis` is not `source_label`,
    a muted "title from first heading / PDF metadata / file name" marker and
    a `source title:` tooltip — so a reader never mistakes a reconstructed
    title for the document's own words. No route added; the frozen public
    surface is unchanged (`test_portal_isolation.py` still green).
  - validation: New `tests/test_documents_titles.py` (8 — the precedence, and
    each thing `_is_identity` refuses: hash/UUID filenames, bare dates,
    `TA1`, `v2.3`, `Page 1`, generic filler, plus normalisation and
    `rank_of`). `tests/test_documents.py` gained 5 (source-label preference,
    heading fallback, an end-to-end HTML `process()` that lands
    `title_basis='heading'`, and a backfill that names the good row and
    leaves the hash-filename row `unknown`, idempotently).
    `tests/test_web_documents.py` gained 2 (the portal surfaces
    `display_title` + `title_basis` + `source_title`; an un-backfilled row
    still falls back with `title_basis=None`). `tests/test_migration_
    equivalence.py` count 75→76. Docs: `docs/CAVEATS.md` (only
    `source_label` is the document's own words; the backfill cannot reach
    `pdf_metadata` for old parses), `docs/document-analysis.md`,
    `api.html`. Full offline suite green — **2838 passed, 109 skipped, 35
    deselected, 0 failed**. `ruff` clean. Browser-verified against a seeded
    scratch warehouse: a document whose only stored name was
    `a3f91c…d8.pdf` renders in search as "Adult Substance Misuse Treatment
    Recommissioning · title from first heading", zero console errors.

- [DONE] BETA-061 | Candidate-promotion campaign workspace
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 3
  - area: evidence-promotion
  - depends_on: BETA-052, BETA-054
  - objective: Provide a campaign workspace for CDP documents, committee papers
    and FOI/SAR candidates with filters, previews, session progress and explicit
    promote/reject/reset actions.
  - result: A view over the **existing** Candidates tab and the existing
    `/api/admin/candidates` + `/api/admin/candidates/promote|reject|reset`
    endpoints — no migration, no new route, and the promote route still takes
    one URL and still refuses a list (`pipeline/promote.py`, pinned again
    here). Three additions:
    (1) **Session progress.** `#candidate-session` (aria-live) carries
    `This session: N promoted, N rejected, N reset.` — incremented in
    `bumpSession()` from the single-row promote, the opened-batch promote
    (per successful document), bulk reject (by the server's count) and reset.
    Not persisted and not a gate: the same reasoning as `state.opened` and the
    review queue's own session line — a count of what the person at the
    keyboard has done now, nothing a localStorage key should let a reload
    inherit.
    (2) **Typed triage preview.** A per-row "Preview" toggle lazily fetches
    `/api/admin/candidates/detail` once and renders the whole candidate row
    through the shared typed-context presenter (BETA-052) — Source / Entity /
    Reason / Evidence / Other sections, linkified URL keys, portal nav links,
    and the lossless raw object under `<details>`. `typedContext` was lifted
    out of the classic `app.js` into a new ES module
    `pipeline/web/static/js/context.js` (imported by `candidates.js`; app.js
    keeps its own copy — it is a classic script with no exports, the same
    trade `dom.js` records) and taught to accept either a `context_json`
    string or an already-parsed object. Opening the preview is explicitly
    **not** `markOpened`: viewing the warehouse row we already hold is not
    looking at the document on its own server, so it does not make a
    candidate batch-promotable.
    (3) The kind filter (cdp_document / committee_paper / foi_request) was
    already the chip strip; left as is.
  - api/ui: No API change. `pipeline/web/static/js/context.js` added to the
    served admin module list. Candidates tab: `#candidate-session` line,
    per-row "Preview" toggle, `.candidate-preview` style. `#candidate-session`
    added to `index.html`.
  - validation: New `tests/test_web_candidate_workspace.py` (9 — the two
    `typedContext` copies agree on the four key-bucket regexes byte-for-byte;
    `context.js` imports only `./dom.js`; the preview never calls
    `markOpened` and reads the detail route; BETA-061 adds no
    `promote-all`/`promote-matching`/`campaign` route to `server.py`; the
    session line counts all of promote/reject/reset and is not persisted;
    `index.html` has no "promote all" control; the detail route returns the
    full row that backs the preview and is not on the portal). Existing
    `tests/test_web_candidates.py` still green — the batch still promotes
    through the single-URL route exactly twice, still cannot send an unopened
    candidate, still runs one at a time. `tests/test_portal_isolation.py`
    updated (the new module is served). Also corrected a stray
    `### READY### READY` heading in this file. Full offline suite green —
    **2824 passed, 109 skipped, 35 deselected, 0 failed**. `ruff` clean.
    Browser-verified against a seeded scratch warehouse: the Preview toggle
    on a CDP candidate renders the typed sections plus the raw `<details>`,
    a bulk reject moves the line to `This session: 1 rejected.` and drops the
    tab pill from 4 to 3, zero console errors.

- [DONE] BETA-057 | Candidate URL overlap signals
  - completed: 2026-08-29
  - priority: P2
  - impact: 3
  - effort: 3
  - confidence: 4
  - risk: 2
  - area: data-quality/review
  - depends_on: BETA-052
  - objective: Show when a conservatively canonicalised URL appears across
    source tables or workflow roles.
  - result: New `pipeline/url_canon.py` — `canonical(url)`: lowercases
    scheme + host, drops the fragment, drops known tracking params
    (`utm_*`, `gclid`, `fbclid`, `mc_cid`, …), sorts the remaining query,
    strips one trailing slash, drops a default port. It deliberately does
    **not** resolve `..`, add/remove `www`, collapse `/index.html`, touch
    percent-encoding, or follow a redirect — every one of those turns
    "probably the same" into a wrong merge, and this feeds a *signal* not an
    identity decision. A non-http value comes back stripped, unchanged.
    New `pipeline/web/url_overlaps.py` — `overlaps(conn)` scans a fixed
    `(table, url column, role)` list (contract notice pages, PFD/CDP/
    committee/SAR/FOI/charity/pay-page/data.gov.uk URLs, review-item raw
    values), groups by `url_canon.canonical`, and returns only the canonical
    URLs that appear in **more than one** source table, with each
    occurrence's table/role/raw URL/row count, sorted by distinct-source
    count. Read-only (source scan test). Caveat: an overlap is a lead — the
    same document discovered twice, or two rows about one page — never proof
    to merge, discard or reprioritise.
  - api/ui: `GET /api/admin/url-overlaps` (admin only); a lazily-loaded
    "URL overlaps" `<details>` panel in the Health tab, one collapsible
    group per canonical URL.
  - validation: New `tests/test_url_canon.py` (7 — fragment dropped,
    tracking vs real params, query sorted, case + trailing slash, default
    vs real port, and the explicit "does not resolve `..` / touch `www` /
    collapse `index.html`" refusals) and `tests/test_web_url_overlaps.py`
    (5 — a URL in two tables is one overlap while a URL in one is not, two
    spellings that canonicalise the same are grouped, the caveat wording,
    the read-only source scan, the admin-only route). Full offline suite
    green — **2815 passed, 109 skipped, 35 deselected, 0 failed**. `ruff`
    clean. Browser-verified against a seeded scratch warehouse: the Health
    panel shows one overlap group (`https://docs.gov.uk/r/7` across
    `contracts` and `pfd_reports`), expandable to the two raw spellings,
    zero console errors.

- [DONE] BETA-056 | Human alias-resolution workflow
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 3
  - risk: 4
  - area: entity-quality
  - depends_on: BETA-054
  - objective: Resolve unmatched buyer and provider names through append-only
    proposed, accepted, rejected and superseded decisions, then produce a
    deterministic verified-alias registry.
  - result: New migration `0075_alias_decisions.sql` (+ postgres pair, count
    bump 74→75) — `alias_decisions`, one **append-only** row per decision
    (`decision_id`, `unmatched_name`, `target_scheme` buyer/provider,
    `canonical_id`, `canonical_name` snapshot, `status`, `decided_by`,
    `reason`, `review_item_id`, `supersedes_id`, `decided_at`), plus the
    `verified_aliases` **view** — the latest accepted decision per name that
    no later row supersedes (`CREATE VIEW IF NOT EXISTS` /
    `CREATE OR REPLACE VIEW` the only dialect change). New
    `pipeline/web/alias_resolution.py`: `unresolved()` (the review-queue
    names for a scheme with their decision history and a `resolved` flag),
    `verified()`, and `decide()` — the **only** path that resolves a name.
    It requires a named reviewer, an `accepted` decision needs a
    `canonical_id` that exists in `authorities` / `providers` (validated), a
    `rejected` decision must not carry one, and a `supersedes_id` must
    exist. No row is ever updated or deleted; a correction is a new accepted
    decision whose `supersedes_id` takes the old one out of the view. A test
    greps the module: no `name_matches` / `suggestions` call, exactly one
    `INSERT INTO alias_decisions`, no `UPDATE`/`DELETE`.
  - api: `GET /api/admin/aliases?scheme=` (unresolved + history),
    `GET /api/admin/aliases/verified`, `POST /api/admin/aliases/decide`
    (one name per request; `QueryError` → 400). All admin only.
  - ui: The Review tab gains an "Alias resolution" `<details>` panel — a
    scheme switch, and per unmatched name its resolved badge (→ canonical
    name + id), decision count, and a `canonical_id` + reason + Accept /
    Reject row. Accept auto-fills `supersedes_id` from the name's last
    accepted decision, so a correction is one click. The reviewer name
    comes from the shared box.
  - validation: New `tests/test_web_alias_resolution.py` (8) — the
    table/view exist, a named reviewer is required, `accepted` needs a real
    `canonical_id`, `rejected` must not carry one, accept-then-supersede
    updates `verified_aliases` while the old row stays in the history,
    `unresolved` lists the review names with their state, nothing applies a
    fuzzy match automatically (source scan), and the routes are admin-only
    with a working accept + a `decided_by`-blank 400. Full offline suite
    green — **2802 passed, 109 skipped, 35 deselected, 1 pre-existing flaky
    failure** (`test_db_concurrency` write-slot timing, the one BETA-035
    recorded; passed in isolation immediately after — unrelated to this
    append-only change). `ruff` clean. Browser-verified against a seeded scratch warehouse: accepting
    "Hereford Council" → E06000019 records a decision and the panel shows
    "→ Herefordshire, County of (E06000019)", zero console errors.

- [DONE] BETA-060 | Raw-archive inventory and integrity trends
  - completed: 2026-08-29
  - priority: P2
  - impact: 4
  - effort: 3
  - confidence: 4
  - risk: 2
  - area: archive/operations
  - depends_on: BETA-058
  - objective: Track archive count, size, source distribution, missing
    references, duplicate hashes, deterministic hash samples and growth through
    `pipeline archive audit` and an admin audit-history endpoint.
  - result: New migration `0074_archive_audits.sql` (+ postgres pair, count
    bump 73→74) — `archive_audits`, one append-only row per audit run:
    `object_count`, `total_bytes`, `by_source_json`, `missing_refs`
    (distinct `evidence_records.payload_sha256` with no `archive_objects`
    row), `duplicate_hashes` (a hash stored under more than one object id),
    `sample_json` (a **deterministic** sample — the objects with the
    lexicographically smallest hashes, so a value that changes between
    audits is a real change), and `git_revision`. New
    `pipeline/archive_audit.py`: `compute()` (read-only — a test greps it
    for `INSERT`/`UPDATE`/`DELETE`), `record()` (one `INSERT INTO
    archive_audits`, nothing else) and `history()`.
  - cli: `pipeline archive-audit` records one snapshot and prints it;
    `--show` prints the last ten without writing. It never deletes an
    object, compacts the archive, or changes retention — stated in the
    command's docstring.
  - surface: `GET /api/admin/archive-audits` (read-only history, admin
    only); the Health tab's Storage panel gains an "Archive audits" table
    (when / objects / size / unarchived refs / dup hashes / revision).
  - validation: New `tests/test_archive_audit.py` (6) — `compute` measures
    the index (counts, by-source bytes, the one duplicated hash, the one
    unarchived ref, the deterministic sample order), `compute` is read-only
    by source scan, `record` appends an immutable row that `history` parses,
    `record` has exactly one `INSERT INTO` and no `UPDATE`/`DELETE`, the
    history route is admin-only, and the CLI records one while `--show`
    writes nothing. Full offline suite green — **2795 passed, 109 skipped,
    35 deselected, 0 failed**. `ruff` clean. Browser-verified against a
    seeded scratch warehouse (40 objects): `pipeline archive-audit` records
    `40 objects, 820000 bytes, 5 unarchived refs, 0 duplicated hashes` and
    the Health-tab table shows the row, zero console errors.

- [DONE] BETA-059 | Coverage completion action board
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 2
  - area: admin/coverage
  - depends_on: BETA-043, BETA-058
  - objective: Distinguish run needed, review needed, source blocked, not
    published and complete; add `GET /api/admin/completeness` with links to the
    relevant run, candidate, review or dataset view.
  - result: New `pipeline/web/completeness_board.py` + route
    `GET /api/admin/completeness` (admin only). For each catalogued dataset
    (`pipeline/web/datasets.py`, BETA-043) it derives **one** reason code in
    precedence order — `run_needed` (0 rows across the dataset's public
    tables) → `review_needed` (pending `review_queue` items for its module) →
    `source_blocked` (a curated `_SOURCE_BLOCKED` note: the unvalidated HSE
    parser, the WhatDoTheyKnow robots deadline) → `not_published` (rows but
    the module is not in the curated `_PUBLICLY_ROUTED` set) → `complete` —
    and **one** non-destructive next step: a `run` link to the Pipeline tab,
    a `review` link to the Review queue filtered to the module, or a
    `dataset` link to the public catalogue entry. Nothing on the board runs
    a module, decides an item or deletes anything — a test greps the module
    for `INSERT`/`UPDATE`/`DELETE`/`run_waves`/`commit(`. Payload also
    carries `by_reason` counts and a caveat spelling out the read-only
    boundary.
  - ui: The Health tab gains a "Coverage actions" panel — a chip row of the
    reason counts and a table (reason badge / dataset / module / rows / next
    step / note), the "next step" being the appropriate link.
  - validation: New `tests/test_web_completeness_board.py` (7) — one row per
    catalogued dataset, every row has one reason + one permitted action
    kind, the reason derivation (`run_needed` with a run action,
    `review_needed` with a review action and the pending count,
    `source_blocked` with its note), the summary counts add up, the caveat
    wording, the "never writes or runs" source scan, and the admin-only
    route. Full offline suite green — **2789 passed, 109 skipped, 35
    deselected, 0 failed**. `ruff` clean. Browser-verified against a seeded
    scratch warehouse: the board shows 34 rows with the summary chips (run
    needed 27 / review needed 1 / source blocked 1 / complete 5), the
    per-row next-step links resolve to the Pipeline / Review / catalogue
    destinations, zero console errors.

- [DONE] BETA-055 | Review-session workflow polish
  - completed: 2026-08-29
  - priority: P2
  - impact: 4
  - effort: 2
  - confidence: 5
  - risk: 1
  - area: admin/ux
  - depends_on: BETA-052
  - objective: Add next-page prefetch, session progress, saved note/filter
    presets, a keyboard map and a primary-source shortcut.
  - result: `pipeline/web/static/app.js` + the admin Review tab, all
    localStorage / client-only, no change to any decision or confirmation
    path:
      * **session progress** — `#review-session`, an `aria-live="polite"`
        line that reads "N decided this session", incremented by
        `bumpReviewSession` after each successful decide (skipped for an
        undo, which is itself a recorded decision). It makes no server call
        and resets on reload — the audit trail is `review_decisions`, not
        this.
      * **primary-source shortcut** — the `o` key opens the focused item's
        primary source (`itemSourceUrl`: a URL key from `context_json`, else
        a URL `raw_value`) in a new tab; documented in the on-page key hint.
      * **saved presets** — a "Preset" `<select>` + Save/Delete, storing the
        current status/module/item_type/search/note under a name in
        `localStorage` (`cglpay.review.presets`). Loading one applies the
        filters and reloads the list; it never decides anything.
      * the key hint gains `<kbd>o</kbd> open primary source`.
  - validation: New `tests/test_web_review_session.py` (6 source pins) — the
    session line is a live region, `bumpReviewSession` makes no `/api/` call
    and is skipped for undo, the `o` shortcut opens a `_blank` window and is
    documented, `itemSourceUrl` reads context then a URL raw value, presets
    are localStorage-only (every preset function is server-free), and
    `applyPreset` reloads the list without touching a decide path. Full
    offline suite green — **2782 passed, 109 skipped, 35 deselected, 0
    failed**. `ruff` clean. Browser-verified against a seeded scratch
    warehouse: a preset saves and appears in the selector, the session line
    is `aria-live=polite`, the `o` key is in the hint, zero console errors.

- [DONE] BETA-054 | Evidence sidecars and candidate suggestions
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 3
  - area: admin/review
  - depends_on: BETA-036, BETA-052
  - objective: Show source excerpts, archive references and ranked candidate
    entities beside the decision form.
  - result: New `pipeline/web/sidecar.py` + route
    `GET /api/review/{id}/sidecar` (admin only — 404 under `/api/v1/`). It
    returns two aids, read-only:
      * **source** — the passage the item is about, taken from the item's own
        `context_json` (`sentence` / `evidence_span` / `snippet` /
        `contravention_text` / `description` / …), its URL, `retrieved_at`
        and `payload_sha256`. Nothing is re-fetched; an item type that
        stored no excerpt gets a `note` saying so.
      * **candidates** — for the two name-match types (`unmatched_buyer_name`,
        `possible_group_company`), the existing `name_matches.suggestions`
        trigram/difflib ranking, **relabelled** `similarity_percent` (the raw
        `score` field is dropped), each with `preselected: false`, and a
        `suppressed` list holding candidates whose normalised name is a
        known false match (`council`, `nhs`, `trust`, `limited`, …) so a page
        of "…Council" rows is not offered as an answer.
    Caveat: "A similarity percentage ranks candidates for a reviewer to
    choose from — it does not pick one, nothing is preselected, and
    approving the item still writes nothing to a canonical table."
  - ui: `renderItem`'s `nameMatchBlock` is replaced by `sidecarBlock` — a
    lazily-loaded "Evidence & candidates" `<details>` beside the decision
    form showing the excerpt (as a `blockquote`), the source link, the
    retrieval/hash line, and — where supported — the candidate table
    (Similarity % / Name / Id / In) with the "nothing is selected; pick one
    by hand" line and the suppressed-count note. (`nameMatchBlock` and the
    `/api/admin/review/{id}/name-matches` route are left in place, no longer
    called from the item view.)
  - validation: New `tests/test_web_review_sidecar.py` (8) — the ranking is
    relabelled and `preselected` is always false, a generic name lands in
    `suppressed` not `ranking`, the excerpt comes from the item's own
    context, an item with none says so, an unknown id is a `QueryError`, the
    caveat wording, and the route serves under `/api/review` only. Full
    offline suite green — **2775 passed, 109 skipped, 35 deselected, 0
    failed**. `ruff` clean. Browser-verified against a seeded scratch
    warehouse: an `unmatched_buyer_name` item shows the ranked authority
    table (80% Herefordshire, County of), a `semantic_claim_candidate` item
    shows the sentence + URL + retrieved/sha, zero console errors.

- [DONE] BETA-053 | Review clusters and informational grouping
  - completed: 2026-08-29
  - priority: P2
  - impact: 4
  - effort: 3
  - confidence: 4
  - risk: 2
  - area: admin/review
  - depends_on: BETA-052
  - objective: Group related items by issue type, source, organisation and shared
    evidence, with facets and an informational/not-actionable state.
  - result: New `queries.review_clusters(conn, status="pending")` — buckets
    the queue (scanned to a 5000-row cap, reported) by
    `(module, item_type, token)` where `token` is a **deterministic**
    organisation/source key: the first present of a context-JSON id key
    (`provider_key`, `ons_code`, `sab_name`, `register_name`, …), else a
    URL key's host, else the item's own short `raw_value`, else `(none)`.
    Returns clusters sorted by count with `item_ids` (capped 200),
    `sample_raw`, `scanned` / `truncated` / `cluster_count` and a caveat:
    "Grouping is a reading aid, not a judgement … every action still
    confirms its own id set." New route `GET /api/review/clusters` (admin
    only — 404 under `/api/v1/`).
  - ui: The Review tab gains a "Cluster view" checkbox that swaps the item
    list for `#review-clusters` — a collapsible `<details>` per cluster
    (module · type · token · N items) whose body has Approve N / Reject N
    buttons. Those drive the **existing** `/api/review/decide-matching`
    with `search=token` and `confirm_count=cluster.count`, so the bulk
    path's in-transaction recount is what decides — a token that
    substring-matches extra items makes the count disagree and the action
    is refused. Grouping changes what a reviewer looks at, not what a
    decision touches.
  - validation: New `tests/test_web_review_clusters.py` (6) — items sharing
    (module, type, token) form one cluster; only the requested status is
    grouped; the token prefers a context id then the URL host then the raw
    value; the caveat wording; the route serves under `/api/review` only;
    and a source-pin that the admin cluster button passes
    `confirm_count: cluster.count` into `decide-matching`. Full offline
    suite green — **2769 passed, 109 skipped, 35 deselected, 0 failed**.
    `ruff` clean. Browser-verified against a seeded scratch warehouse (10
    pending items): the cluster view shows three clusters
    (`e10000016 · 6`, `surreycc.gov.uk · 3`, an HSE near-miss · 1); an
    early `reviewerName` typo was fixed to `requireReviewer` (app.js's own
    helper) — the served file is correct and the three clusters render.

- [DONE] BETA-058 | Unified durable run ledger
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 3
  - area: operations
  - depends_on: BETA-039
  - objective: Record CLI, admin and scheduled executions through one durable
    model with origin, revision, environment, parent run, timestamps and
    per-module results; keep full logs in their current storage.
  - result: New migration `0073_run_ledger.sql` (+ postgres pair, count bump
    72→73) — `run_ledger`, one row per module-run: `run_id` (uuid4),
    `origin` (`cli` / `admin` / `scheduled`), `revision`, `environment`,
    `parent_run_id`, `module_selector`, `dry_run`, `started_at` /
    `finished_at`, `status` (`running` / `ok` / `partial` / `failed`),
    module counts and a `results_json` array of the per-module summary rows.
    It sits **beside** `job_runs`, not replacing it — the web UI keeps
    `job_runs` for live log streaming. New `pipeline/run_ledger.py`:
    `start()` / `finish()` (best-effort — a ledger write that fails is
    logged and swallowed, so losing an audit row never loses the
    collection), `git_revision()` (settings or `.git/HEAD`, no subprocess,
    no `pipeline.web` import), and `recent()`.
  - instrumentation: `runner.run_waves` — the one choke point every entry
    point already funnels through — gains `origin` / `parent_run_id`
    parameters and writes exactly one ledger row per run (start before the
    first wave, finish after the last). `cli.py`'s `run` command grows a
    hidden `--origin` (a cron wrapper passes `scheduled`); `web/admin.py`
    passes `origin="admin"`.
  - surface: `/api/v1/meta` `data.last_run` (origin / status / timestamps /
    counts of the newest row, or `null`); `test_web_meta.py`'s `data`-block
    key pin updated. New admin route `GET /api/admin/run-ledger`; the
    Pipeline tab gains a "Run ledger" section under "Recent jobs" that shows
    every run — including CLI and scheduled — with origin, status, selector,
    module counts, revision and time.
  - validation: New `tests/test_run_ledger.py` (6) — `start`/`finish` write
    one row with parsed results; `run_waves` records the origin and selector;
    a run with one failed module is `partial`; **dropping the ledger table
    does not break the run** (the summary still comes back); `/api/v1/meta`
    and `/api/admin/run-ledger` both expose the last run. Full offline suite
    green — **2763 passed, 109 skipped, 35 deselected, 0 failed**. `ruff`
    clean. Browser-verified against a seeded scratch warehouse: the Pipeline
    tab's Run ledger shows a `scheduled / partial / 33 ok / 1 failed` row
    and a `cli / running` row with revision and timestamp, zero console
    errors.

- [DONE] BETA-052 | Structured review-item context
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 2
  - confidence: 5
  - risk: 1
  - area: admin/review
  - depends_on: none
  - objective: Render source, entity, reason, evidence and navigation as typed
    sections while retaining the complete raw JSON under disclosure.
  - result: `pipeline/web/static/app.js` — the review item's `context_json`
    was rendered as one `<pre>` of pretty-printed JSON. New `typedContext(raw)`
    replaces it: a *generic* key classifier (not a per-`item_type` map, which
    would rot the first time a module adds a context key) sorts each key into
    the five things a reviewer needs — **evidence** (`sentence` /
    `evidence_span` / `snippet` / `contravention_text` / … rendered as a
    `<blockquote>`), **source** (`*_url` keys, linked when they are `http(s)`),
    **entity** (`provider_key` / `ons_code` / `register_name` / …),
    **reason** (`reason` / `selection_reason` / `match_basis` /
    `relation_score` / `assertion_status` / …) and **other** — then an
    **Open** section with portal deep-links built only from context values
    that have the right shape (`/#/providers/<key>`,
    `/#/authorities/<E########>`, the document search). The complete raw
    object stays under a `<details class="ctx-raw">` ("Raw context
    (lossless)"), so nothing is lost for audit. Values reach the DOM through
    `el()` / text nodes and real anchors — no `innerHTML`. New CSS for
    `.ctx-typed` / `.ctx-section` / `.ctx-kv` / `.ctx-evidence` / `.ctx-nav`.
  - validation: New `tests/test_web_review_context.py` (5 source-pin tests) —
    `renderItem` uses `typedContext` and no longer emits the bare `<pre>`;
    the five section buckets and four key classifiers exist by name; the raw
    JSON is kept under disclosure with `formatContext(raw)`; the view builds
    the DOM without `innerHTML`; the nav links point at real portal routes
    and only link an `ons_code` with the portal's own `^[A-Z][0-9]{8}$`
    shape. Full offline suite green — **2758 passed, 109 skipped, 35
    deselected, 0 failed**. `ruff` clean. Browser-verified against a seeded
    scratch warehouse (one `semantic_claim_candidate` item): the sections
    render — SENTENCE / SOURCE (linked) / ENTITY / REASON / OTHER / Open
    (three portal links) — with the raw JSON collapsed underneath, zero
    console errors.

- [DONE] BETA-051 | HSE enforcement-notice evidence
  - completed: 2026-08-29
  - priority: P1
  - impact: 4
  - effort: 4
  - confidence: 4
  - risk: 4
  - area: safety/legal
  - depends_on: BETA-043, BETA-049
  - objective: Add module `m33` for organisation-level HSE improvement and
    prohibition notices, publishing exact tracked-organisation matches through
    `/api/v1/safety` while excluding individuals.
  - result: New migration `0072_hse_enforcement.sql` (+ postgres pair, count
    bump 71→72 in `test_migration_equivalence.py`) — `hse_enforcement_notices`,
    one row per HSE notice number, every field stored verbatim, nullable
    `provider_key` set only on an exact tracked-name match. New module
    `pipeline/modules/m33_hse_notices.py`: one organisation-name search per
    tracked-provider name variant against the HSE notices register, a
    header-keyed table parser (`parse_notice_list` reads columns by their
    `<th>` text, so a reordered column is a NULL not a mis-store),
    `is_organisation()` (a bare personal name with no org token is dropped
    unless it exactly matches a tracked provider), and per-provider
    reconciliation across variants so a notice returned by two searches is
    one row and a near-miss is judged against the whole variant set (a
    `hse_name_near_miss` review item, keyed to upsert not duplicate).
    Individuals are excluded at parse time; the live-fetch parser is written
    to the register's documented structure and fixture-tested, not yet
    validated against real HSE HTML — flagged in the module docstring,
    `docs/SOURCES.md` and `docs/CAVEATS.md` for a human-watched first run.
  - api: `GET /api/v1/safety` (`public_queries.safety`) — only
    `provider_key IS NOT NULL` rows, joined to `providers`, ordered newest
    issue date first, plus `by_provider` / `by_type` facets. New
    `CAVEATS["hse_notices"]`: a notice is a point-in-time fact with the
    `result` verbatim (may be an appeal decision or withdrawal), no
    compliance inferred, individuals excluded, absence is not a safety
    rating. Route added to `PUBLIC_API_ROUTES`, `openapi.ROUTES`, the
    `<noscript>` list and an `api.html` article.
  - docs/plumbing: `pipeline/licences.py` gains the `hse_notices` licence
    (+ `MODULE_LICENCES["m33_hse_notices"]`, `ENDPOINT_MODULES["safety"]`),
    mirrored word-for-word into `components.js`'s drawer table (pinned by
    `test_licences.py`); `README.md` module table row; `docs/SOURCES.md`
    Module 33 section (viability check was already "VIABLE"); `docs/CAVEATS.md`
    section; a `datasets.py` catalogue entry (`hse-enforcement-notices`,
    safety layer). `pfd.js` ("Safety & legal" page) gains an "HSE
    enforcement notices" section that fetches `/api/v1/safety` — a third,
    separate stream, never summed with the coroner reports.
  - validation: New `tests/test_m33_hse_notices.py` (5) — header-keyed parse,
    column reorder resilience, individual exclusion, exact-match discipline,
    and the run storing only exact org matches + one near-miss item. New
    `tests/test_web_safety.py` (4) — only attributed notices published, the
    `result` verbatim, facets + caveat, frozen-surface pin. Full offline
    suite green — **2753 passed, 109 skipped, 35 deselected, 0 failed**.
    `ruff check pipeline tests` clean. Browser-verified against a seeded
    scratch SQLite warehouse: the pfd page's HSE section renders the two
    notices with `Under appeal` / `Complied` verbatim and the caveat, zero
    console errors.

- [DONE] BETA-050 | Procurement lifecycle and performance view
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 5
  - confidence: 4
  - risk: 4
  - area: procurement
  - depends_on: BETA-040, BETA-044
  - objective: Group notices sharing an OCID into explicit planning, tender,
    award, contract, amendment, termination and performance stages; add
    `GET /api/v1/contracts/process/{ocid}` and a public lifecycle view.
  - result: No `m01` change needed — the data is already collected.
    `contracts.notice_type` stores the OCDS release `tag` list (comma-joined,
    written by `m01._extract`), and `contracts.ocid` is the stable
    cross-release id. New `public_queries.contract_process(conn, ocid)` reads
    the rows for one OCID and buckets each notice by the stage its **own** tag
    names — `_OCDS_STAGE` maps the ~14 standard tags to
    planning / tender / award / contract / amendment / termination /
    implementation / other, and `_STAGE_PRECEDENCE` picks the most specific
    when a notice carries several (a `contractAmendment` also tagged
    `contract` is an amendment). A multi-supplier award notice is one grouped
    entry with all its suppliers (each flagged `is_tracked_provider` on an
    exact `supplier_aliases` match). Response: `ocid`, `buyer`,
    `stage_order`, `stages` (each `stage` / `present` / ordered `notices` —
    id, `ocds_tags`, title, dates, value, suppliers, source URL, constructed
    `notice_web_url`), `notice_count`, `date_range`, `caveat`. New
    `CAVEATS["contract_process"]`: a missing stage is absence of a published
    notice, never inferred completion, renewal, KPI achievement, supplier
    performance or organisational continuity.
  - route: `GET /api/v1/contracts/process/{ocid}`, pattern
    `contracts/process/([A-Za-z0-9_-]{1,100})` — added to
    `PUBLIC_API_PATTERNS`, `openapi.ROUTES` (parity test still binds both
    ways), and an `api.html` article with `data-route` / `data-route-pattern`.
    `c.ocid` appended to `_NOTICE_SELECT` (the appended-not-inserted column
    rule) so the notices table and CSV export carry it too.
  - ui: `contracts.js` — a "Lifecycle" column on the notices table links each
    row to `#/contracts?ocid=…`; that hash renders `renderProcess`, a
    dedicated view (hero + OCID + date range, the pinned caveat, one section
    per stage in fixed lifecycle order, an absent stage drawn as "No notice
    published for this stage — not evidence the stage did not happen").
  - validation: New `tests/test_web_contract_process.py` (5 tests) — grouping
    by the notice's own tag, the most-specific-tag rule, a multi-supplier
    award as one entry, an absent stage marked `present: false` (not
    inferred), the fixed `stage_order`, the caveat's forbidden inferences,
    the unknown-OCID 400, and the frozen-surface pattern pin. Full offline
    suite green — **2742 passed, 109 skipped, 34 deselected, 0 failed**.
    `ruff check pipeline tests` clean. Browser-verified against a seeded
    scratch SQLite warehouse: the lifecycle view groups a
    planning/tender/award/amendment set correctly, shows the two empty
    stages with the "not evidence" text, tracked supplier marked ✓, zero
    console errors.

- [DONE] BETA-049 | Accessibility and performance guardrails
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 2
  - area: web/quality/ci
  - depends_on: BETA-040–048
  - objective: Add repeatable mobile/desktop, light/dark, keyboard, reduced-
    motion, accessibility and performance checks for the round's public and
    admin surfaces.
  - result: New `tests/test_round_guardrails.py` — offline, repeatable checks
    over exactly the BETA-038–049 round's new surfaces
    (`js/pages/catalogue.js`, the provider layers in `compare.js`,
    `js/search.js`, `js/claimreview.js`; `/api/v1/catalogue`,
    `/catalogue/{id}`, `/provider_compare`, `/relationships/{id}`,
    `/api/openapi.json`; the claim-review admin routes):
      * **accessibility** — `#search-status` and `#claimreview-status` are
        `aria-live` regions (a search or a decision changes a count and a
        screen reader has to hear it); no `innerHTML`/`outerHTML` in any new
        JS (settled decision 9); every `<input>`/`<select>` in the new admin
        tabs has a label or `aria-label`.
      * **local assets** — no new script makes an off-origin `fetch`/`src`/
        `href`/`import`, and none carries a literal `http(s)://` at all (every
        outbound link is built from an API-returned `source_url`); the frozen
        public static surface gained no remote URL.
      * **performance** — `provider_compare` 400s past four providers;
        `catalogue` is a fixed ≤60-row set; `/api/v1/catalogue` and
        `/api/openapi.json` advertise the public `max-age`; the OpenAPI doc
        itself shows `limit`/`offset` on the paged routes.
  - fix: `public_queries.relationship_detail` (BETA-044) streamed every
    `AWARDED_TO` edge between a pair with no bound — a drawer is not a place
    to stream a five-figure set. Now `LIMIT 500` with a `truncated` flag in
    the payload and a "see the contracts page for the rest" note in
    `relationships.js`; `api.html` updated.
  - live pass: mobile (375px), desktop and dark emulation against a seeded
    scratch warehouse. The round's own new content does **not** scroll
    horizontally at 375px (`#main` clean on `#/catalogue`); the global
    `:focus-visible` outline (styles.css line 87) covers the new buttons;
    the new pages add no CSS and reuse only already-themed components, so
    dark mode is inherited.
  - flagged, not fixed (pre-existing, portal-wide, out of this round's
    scope): at ≤375px the topbar's find-council input and mobile menu
    toggle overflow the viewport by ~93px — reproduces **identically** on
    `#/` (overview, unchanged this session) and `#/documents`, so it is not
    a round regression. BETA-018 already worked the mobile topbar; a fix
    belongs in its own item. Recorded under Deferred Ideas.
  - not done here: live PostgreSQL `EXPLAIN` plan checks — `psycopg` is not
    installed in this environment (same constraint BETA-036 recorded); the
    SQLite plan assertions in `tests/test_web_performance.py` stand, and a
    disposable-PG matrix stays on the register.
  - validation: New guardrail module (11 tests) green; `test_web_relationships.py`
    still green with the `truncated` field. Full offline suite green —
    **2737 passed, 109 skipped, 34 deselected, 0 failed**. `ruff check
    pipeline tests` clean.
  - round close: **BETA-038–049 is complete.** The approved successor round
    BETA-050–067 is now promoted per its delivery sequence — BETA-050
    IN_PROGRESS, BETA-051 / BETA-052 / BETA-058 NEXT.

- [DONE] BETA-048 | OpenAPI 3.1 specification
  - completed: 2026-08-29
  - priority: P2
  - impact: 4
  - effort: 3
  - confidence: 5
  - risk: 2
  - area: api/docs
  - depends_on: BETA-040, BETA-041, BETA-042, BETA-043, BETA-044, BETA-045
  - objective: Serve `/api/openapi.json` as an OpenAPI 3.1 description of all
    public routes, parameters, pagination, errors, provenance and examples.
  - result: New `pipeline/web/openapi.py` — a compact hand-maintained
    `ROUTES` table (one entry per public route, each carrying a `surface`
    field that is its verbatim string in `test_portal_isolation.py`) and a
    `document()` that assembles the OpenAPI 3.1 dict: `openapi: "3.1.0"`,
    `info` (with the "GET only, no CORS, personal data unreachable, nothing
    inferred" contract and the OGL licence), `servers`, `paths` (GET per
    route with typed `parameters` and the shared `200`/`400`/`404`
    responses), and `components.schemas.Error` (`{error: string}`). No
    framework, no generated client — a dict and `json.dumps`.
  - route: Served at `GET /api/openapi.json` in `server.py`'s `_serve_api`,
    before the warehouse connection is opened (it reads nothing) — a sibling
    of the `/api` HTML page, deliberately **not** a `/api/v1/*` route.
    GET/HEAD only; `POST` and `/api/v1/openapi.json` are 404. `PUBLIC_MAX_AGE`
    cache header, like the rest of the read API.
  - parity: New `tests/test_web_openapi.py` (7 tests) — the decisive one binds
    `{spec["surface"] for spec in openapi.ROUTES.values()}` to
    `PUBLIC_API_ROUTES | PUBLIC_API_PATTERNS | PUBLIC_API_EXTRA` with `==`
    in both directions, so a new `/api/v1/` route that nobody described, or a
    described route the server dropped, fails. Also: every `{param}` path
    lines up with a `PUBLIC_API_PATTERNS` regex and a plain path with a
    route/EXTRA name; valid 3.1 shape; every path var is a declared `path`
    parameter; and the served bytes equal `openapi.document()`.
  - api-doc: `api.html` gains an informational `/api/openapi.json` article
    (no `data-route` attribute, so the frozen-surface parity test ignores
    it); the `<noscript>` list gains its line (the `/api/v1/([a-z_]+)` regex
    the offline-reading test uses cannot match it, so exact-equality holds).
  - validation: Full offline suite green — **2726 passed, 109 skipped, 34
    deselected, 0 failed**. `ruff check pipeline tests` clean.
    Browser-verified against the scratch warehouse: `/api/openapi.json`
    serves `openapi 3.1.0` with 26 paths, GET 200 / HEAD 200 / POST 404.

- [DONE] BETA-047 | Semantic claim review and gate dashboard
  - completed: 2026-08-29
  - priority: P2
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 4
  - area: admin/nlp/review
  - depends_on: BETA-034 (implemented 034A–034G foundation), BETA-046
  - objective: Add admin candidate list/detail/decision/gate endpoints and a
    keyboard-operable review dashboard with filters, named reviewer decisions,
    ontology validation and live gate progress.
  - result: New `pipeline/web/claim_review.py` — the one-way bridge (same
    shape as `pipeline/web/semantic.py`) over the already-implemented nlp
    functions: `decisions.decide` / `decisions.history`,
    `gate.check`, and `ontology.default()`. It adds no policy — decisions are
    one candidate at a time, nothing writes `graph_claims`, nothing trains a
    model. New admin routes:
    `GET /api/admin/claim-candidates` (filtered/paged list over
    `document_claim_candidates` joined to chunk/document/evidence, each row
    carrying its triple, `predicate_label`/`object_concept_label` resolved
    from the ontology, evidence sentence, source identity, and the latest
    decision), `GET /api/admin/claim-candidates/{id}` (detail + chunk text +
    full `decisions` history + `ontology_version`),
    `GET /api/admin/claim-gate` (the read-only 034G `gate.check` report
    verbatim), `GET /api/admin/claim-ontology` (predicate / concept /
    reason-code vocabularies for the correction dropdowns), and
    `POST /api/admin/claim-candidates/decide` (one candidate, `decided_by`
    required and never defaulted, `corrected` needs an ontology-valid
    `corrected_*` — all enforced by `decisions.decide`, its
    `ClaimDecisionError` → 400). Route not-public: added to
    `test_portal_isolation.py`'s "not reachable under `/api/v1/`" list.
  - ui: New admin tab **Claim review** (`#tab-claimreview`, `'claimreview'` in
    `app.js` `TABS`, `/admin/js/claimreview.js` registered, `initClaimReview`
    in `shell.js`). A gate strip (overall READY/not, decision counts,
    inter-reviewer agreement, per-category positive/negative/subjects/years
    and the shortfall list), a filter bar (sentence search, status,
    predicate, source), and one panel per candidate: the triple, the
    quoted sentence, source link, last decision, and a `<form>` decision
    control — approve / reject / corrected, with the correction row
    (predicate + object-concept + object-literal dropdowns, ontology-bound)
    revealed only for `corrected`, a reason-code select, a note field. The
    reviewer name comes from the operator UI's existing `#reviewer` box; a
    blank name is refused client- and server-side. No bulk control exists,
    pinned by a test.
  - validation: New `tests/test_web_claim_review.py` (9 tests) — the nlp
    chain seeds one real candidate; list labels + caveat, detail chunk +
    empty history, unknown-id 400, ontology options, the gate report's five
    categories + blocking list, the named-reviewer refusal, an approve that
    records the decision and moves the candidate (with `graph_claim_id`
    NULL — no draft), `corrected` needing an ontology-valid correction, and
    a source-scan that no `decide-all` / `bulk` / `approve-all` route
    exists. `test_portal_isolation.py`'s admin-modules and admin-not-public
    lists updated. Full offline suite green — **2720 passed, 109 skipped, 34
    deselected, 0 failed**. `ruff check pipeline tests` clean.
    Browser-verified against a seeded scratch SQLite warehouse (no
    candidates): the tab activates, the gate strip renders all five
    categories with their shortfalls, the predicate dropdown fills from the
    ontology (29 predicates), the empty-list message shows, zero console
    errors.

- [DONE] BETA-046 | Admin semantic-search workbench
  - completed: 2026-08-29
  - priority: P2
  - impact: 4
  - effort: 3
  - confidence: 5
  - risk: 2
  - area: admin/nlp/ui
  - depends_on: BETA-039, BETA-034 (implemented search foundation only)
  - objective: Surface the existing keyword, semantic and hybrid search modes
    in an admin-only workbench with filters, score components, facets, excerpts,
    sources, model identity and fallback state.
  - result: Pure front-end — the backend (`/api/admin/search`, modes
    keyword/semantic/hybrid over `document_chunks`, `pipeline/web/semantic.py`
    → `pipeline/nlp/semantic_search.search`) already returns `mode`, `query`,
    `model_key`, `count`, `filters`, `notes` (fallback lines) and `results`
    (each with a `score` component map). New admin tab **Search** (`#tab-search`
    in `pipeline/web/static/index.html`, `'search'` added to `app.js` `TABS`,
    `initSearch` added to `shell.js`, `/admin/js/search.js` registered in
    `server.py`'s admin module list). The tab is a diagnostic form — query,
    mode switch (all three), source-system and published-date filters, result
    limit — and renders, per response: a chip row of `mode` / `model` /
    `count` / active filters, the `notes` lines verbatim as warnings (the
    "hybrid degraded to keyword-only" and stub-embedder cases), and the
    retrieval caveat; then one panel per result showing the score components
    (`keyword_rank` / `semantic_rank` / `cosine` / `rrf`, each labelled),
    the snippet, source link and dates. Copy states plainly that relevance
    order is retrieval behaviour, not evidential weight; nothing here
    promotes, attributes or exports. `#search-status` is an
    `aria-live="polite"` region so result counts announce.
  - result-scope: BETA-034's `next_action` list item "browser-verify
    `/api/admin/search`" is now done as a side effect.
  - validation: New `tests/test_web_admin_search.py` (6 source-pin tests) —
    the tab/panel/controls exist, `search` is in the router `TABS`, the
    shell boots `initSearch`, the workbench names every score component +
    `model_key` + `notes` + the caveat, it builds the DOM without
    `innerHTML` (settled decision 9), and it calls only `/api/admin/*`.
    `test_portal_isolation.py`'s served-admin-modules tuple gains `search`.
    Full offline suite green — **2711 passed, 109 skipped, 34 deselected, 0
    failed**. `ruff check pipeline tests` clean. Browser-verified against a
    seeded scratch SQLite warehouse (no `document_chunks`, so zero results
    by construction): the tab activates, the form submits, the meta strip
    shows `mode: hybrid` / `model: embed:stub` / `0 results` and the
    "no embeddings … run `pipeline nlp embed`" fallback warning, the status
    region announces, zero console errors.

- [DONE] BETA-045 | Provider comparison enhancements
  - completed: 2026-08-29
  - priority: P2
  - impact: 4
  - effort: 4
  - confidence: 4
  - risk: 4
  - area: api/providers/ui
  - depends_on: BETA-039, BETA-043
  - objective: Let readers compare two to four providers across clearly
    separated Living Wage, latest gender pay gap, provider-pay and recent NHS
    advert layers, while keeping the API well-defined for larger selections.
  - result: New public route `GET /api/v1/provider_compare?provider_key=…`
    (`public_queries.providers_compare`) — a **flat** route name like
    `document_search`/`council_spend`, deliberately not `providers/compare`,
    so it stays inside the frozen-surface machinery (which assumes a route is
    either a plain `[a-z_]+` name or a `{param}` pattern) with no test-infra
    change. Takes 2–4 distinct `provider_key` values (fewer/more, or an
    unknown key, is a 400 with a clear message — "well-defined for larger
    selections" is a clean refusal, not a silent truncation). Returns
    `providers` (in the order asked) and `layers`: `living_wage`,
    `gender_pay_gap` (latest reporting year only — an older filing is a
    different figure, not a trend point), `provider_pay`
    (`provider_pay_mentions`), `nhs_jobs` (10 most recent adverts per
    provider, capped with a portable correlated-count top-N, never a
    window function). Each layer carries its own `unit`, `temporal: false`,
    a `by_provider` map (every asked key present, `[]` where a provider has
    no rows — "not evidence of a better or worse position"), and its own
    caveat; a top-level `CAVEATS["provider_compare"]` states the whole view
    produces no rank, score, difference or ratio.
  - no-csv: `provider_compare` is deliberately absent from
    `public_export.EXPORTABLE` / `WINDOWED` — the structured JSON is the
    export, and a flat CSV would imply the four layers are one measure.
  - ui: `compare.js` — when the selection is providers-only (2–4), a new
    "Pay evidence side by side" section fetches `provider_compare` and lays
    out the four layers as **tables**, not charts (a chart of unlike
    measures is the collapse the caveat forbids): per layer a pinned
    caveat, the unit, and a panel per provider with up to eight rows +
    "…and N more". More than four selected shows the first four with a note.
  - fix (pre-existing, found here): `app.js` `fetchJSON` passed an array
    param value straight to `URLSearchParams.set`, which comma-joins it —
    so `fetchJSON('compare', {provider_key: [a, b]})` sent
    `provider_key=a%2Cb` and the server saw one bogus key. `compare.js`'s
    own multi-authority / multi-provider comparison was hitting this too.
    `fetchJSON` now `append`s each array element as a repeated param, the
    shape the server's repeatable parameters expect. Verified in the
    browser: `/api/v1/compare?provider_key=a&provider_key=b` now 200 where
    the comma form 400s.
  - api-doc: `api.html` gains the `provider_compare` article; the
    `<noscript>` list gains its line; `PUBLIC_API_ROUTES` in
    `test_portal_isolation.py` updated.
  - validation: New `tests/test_web_provider_compare.py` (8 tests) — four
    separate layers each with unit + caveat + `temporal: false`, the
    latest-year-only gender pay gap pin, absent-provider = `[]`, a
    scan of the raw payload for `rank`/`score`/`ratio`/`difference`/
    `delta`/`composite`/`index`/`percentile` (none present), the 2–4
    bound (incl. duplicate collapse), the unknown-key 400, no
    `EXPORTABLE`/`WINDOWED` entry, and the frozen-surface pin. Full offline
    suite green — **2705 passed, 109 skipped, 34 deselected, 0 failed**.
    `ruff check pipeline tests` clean. Browser-verified against a seeded
    scratch SQLite warehouse: the side-by-side section renders all four
    layers with caveats/units/rows and the empty-state text, and the
    `fetchJSON` fix restored the existing compare page's multi-select.

- [DONE] BETA-044 | Commissioning-relationship detail and timeline
  - completed: 2026-08-29
  - priority: P2
  - impact: 4
  - effort: 3
  - confidence: 5
  - risk: 2
  - area: graph/api/ui
  - depends_on: BETA-039
  - objective: Add a relationship-detail endpoint, drawer and dated timeline
    for deterministic provider-to-authority `AWARDED_TO` contract edges already
    present in the evidence graph.
  - result: New public route `GET /api/v1/relationships/{relationship_id}`
    (`public_queries.relationship_detail`), pattern
    `relationships/(relationship:[0-9a-f]{64})` — a `relationship_id` from an
    `/api/v1/relationships` `edges` entry. It resolves the one edge to the
    authority/provider pair it connects (400 if the id is not an
    `AWARDED_TO` `SOURCE_FACT`/`DERIVED_RELATIONSHIP` edge, or does not join
    an authority and a provider), then returns **every** `AWARDED_TO` edge
    between that same pair as a dated `timeline`. Each timeline entry carries
    the edge's `valid_from`/`valid_to`/`confidence` and the source `notice`
    it was written from — resolved by joining `evidence_records.payload_sha256`
    + `source_system` back to `contracts` (the exact key
    `pipeline/graph/backfill.py` wrote the edge from), a `LEFT JOIN` so an
    edge whose notice is no longer held still appears with `notice: null`.
    The notice block is id/title/value/currency/buyer/supplier/published
    date/source URL + a **constructed** `notice_web_url` via
    `notice_urls.notice_page_url` (labelled as constructed in the UI). Order
    is `COALESCE(valid_from, date_published) DESC NULLS LAST`; a missing date
    stays `null`, never inferred. New `CAVEATS["commissioning_relationship_timeline"]`
    spells out that this is source events, not a relationship history, a
    value/reliance measure or evidence of organisational continuity.
  - ui: `relationships.js` — the flat per-edge table is now grouped to one
    row per authority/provider pair (Authority · Provider · matched-notice
    count · a "Show N contract events" `<details>`). Opening it lazily fetches
    `relationships/{id}` for any one of that pair's edges and renders the
    pinned caveat + an ordered list of events (title, published date, notice
    period, published value — shown raw when the currency is not GBP so
    `gbp()`'s pound sign is never misapplied — supplier-as-named, OCDS
    release link, constructed notice-page link, retrieval date). The id is
    sent unencoded: `encodeURIComponent` turns the `:` into `%3A` and the
    server route pattern then misses — caught in the browser.
  - api-doc: `api.html` gains the `relationships/{relationship_id}` article
    (with `data-route` / `data-route-pattern`). `PUBLIC_API_PATTERNS` in
    `test_portal_isolation.py` updated. No `<noscript>` change — the block
    lists base route names only and `relationships` is already there.
  - validation: 4 new tests in `tests/test_web_relationships.py` — the dated
    two-notice timeline with resolved authority/provider identifiers, the
    "never infer a missing date" pin (a notice with no `date_published`
    stays `null`), the unknown-id 400, and a `REGISTERED_AS` edge id
    refused. `test_route_is_documented_and_frozen` extended to assert the new
    pattern. Full offline suite green — **2697 passed, 109 skipped, 34
    deselected, 0 failed**. `ruff check pipeline tests` clean.
    Browser-verified against a seeded scratch SQLite warehouse (`graph
    backfill` run): the grouped table renders, "Show N contract events"
    lazy-loads the timeline with the caveat and five dated events, the
    detail route returns 200 for a real id and 400 for `relationship:` +
    64 zeros, zero console errors after the encode fix.

- [DONE] BETA-043 | Public dataset catalogue
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 2
  - area: metadata/api/ui
  - depends_on: BETA-039
  - objective: Publish a validated registry and list/detail views describing
    each dataset's title, publisher, official URL, evidence layer, geography,
    cadence, public tables, licence and caveat, with exact counts and freshness.
  - result: New checked-in registry `pipeline/web/datasets.py` — one
    `Dataset` per collecting `mNN_` module (33 rows), each with a stable
    kebab-case `dataset_id`, title, publisher, official URL, an
    `evidence_layer` from an eleven-value controlled vocabulary
    (`EVIDENCE_LAYERS`), geography, cadence, the portal-safe warehouse tables
    it writes, and the single limitation that matters most before quoting it.
    The registry is *static* only — no numbers. `public_queries.catalogue()` /
    `catalogue_detail()` add the live half at request time: `catalog.row_counts`
    per table, `MAX(retrieved_at)` for the tables that carry it (`_table_last_retrieved`
    asks the schema first so `authorities` / `sector_universe` don't raise),
    and the licence resolved through the existing `pipeline/licences.py`
    (`for_module` / `statement`), so a zero row count reads as "not collected
    here" rather than "source empty". Every table name passes the same
    `_public()` restricted-table guard every other function in that file runs.
  - api: `GET /api/v1/catalogue` (list + `evidence_layers` vocabulary +
    shared caveat) and `GET /api/v1/catalogue/{dataset_id}` (adds
    `licence_statement` and `licence_caution`; unknown id → 400 via
    `QueryError`). Route pattern `catalogue/([a-z0-9-]{1,64})`. Added to the
    frozen surfaces: `PUBLIC_API_ROUTES` + `PUBLIC_API_PATTERNS` in
    `test_portal_isolation.py`, the `api.html` articles (both with
    `data-route` / `data-route-pattern`), the `<noscript>` list, and
    `CAVEATS["catalogue"]`.
  - ui: New portal page `/js/pages/catalogue.js` + route `#/catalogue`
    (registered in `server.py` STATIC_FILES, app.js `ROUTES`/`ROUTE_TITLES`,
    the command palette `PAGES`, the footer nav and the lens menu; static
    path pinned in `test_portal_isolation.py`). List view groups datasets by
    evidence layer in vocabulary order — so the never-combine-across-layers
    boundary is visible in the layout — with a card per dataset (caveat,
    publisher/geography/cadence/holdings, official source link, licence
    link, Details button). `#/catalogue?dataset=<id>` is the detail view
    (pinned caveats, source table, per-table row counts and freshness).
    Values reach the DOM as text nodes; `sourceLink` is imported from
    `app.js` (a first draft wrongly imported it from `components.js` and the
    page failed to load — caught in the browser).
  - validation: New `tests/test_web_catalogue.py` (10 tests) — the coverage
    bind (every collecting module ↔ exactly one entry, both directions),
    unique kebab-case ids, known evidence layers, every `public_tables`
    entry portal-safe, licence + real https URL present, and the served
    routes: measured counts/freshness against a seeded SQLite warehouse
    (geography = 1, procurement = 3, an uncollected dataset = 0), the detail
    licence statement/caution, and the unknown-id 400. Full offline suite
    green — **2693 passed, 109 skipped, 34 deselected, 0 failed** (320s).
    `ruff check pipeline tests scripts` clean. Browser-verified against a
    seeded scratch SQLite warehouse: list groups 33 datasets by layer,
    detail view renders per-table counts and the NHS-Benchmarking licence
    caution, zero console errors.

- [DONE] BETA-042 | Document evidence-context view
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 3
  - confidence: 4
  - risk: 3
  - area: api/documents/ui
  - depends_on: BETA-041
  - objective: Add `GET /api/v1/documents/{id}?element_id&context=` and a
    portal view that places a matched element in bounded surrounding context
    from the active document version.
  - result: New parameterised public route
    `GET /api/v1/documents/{document_id}` → `public_queries.document_context`.
    Same `DOCUMENT_SEARCH_SOURCES` allowlist as the search (a document whose
    source is not searchable is not readable here — 400, not an empty body),
    and only the `is_active` `document_versions` row's elements are ever
    returned: an `element_id` from a superseded parse is refused rather than
    silently re-anchored. `context` is clamped to at most 3 elements either
    side — bounded scrutiny of one hit, not a way to reassemble a copyrighted
    document a window at a time (`docs/CAVEATS.md`). Payload: the document's
    identity + provenance + parser identity, an ordered `elements` window
    (each `text`/`element_type`/`page_number`/`heading_level` + an
    `is_anchor` flag), `has_more_before`/`has_more_after`, `element_count`,
    `range`, `caveat`. `document_search` results now also carry
    `document_element_id` — the anchor this route needs.
  - ui: Each document-search result gains a lazy "Show surrounding text"
    `<details>`; opening it fetches `documents/{id}?element_id=…&context=3`
    and renders the window, the matched element highlighted the same way its
    snippet is, with "…earlier/later text on this page" markers when the
    window is not the whole page.
  - api-doc: `api.html` gains the `documents/{document_id}` article (with its
    `data-route-pattern`) and the `document_search` article is refreshed for
    BETA-041's facet/offset/since parameters and richer response.
  - validation: 8 new tests in `tests/test_web_documents.py` — anchored
    window, edge clamping, the `context` cap, no-anchor head, the allowlist
    refusal, unknown-document refusal, the superseded-version refusal, and a
    search-result → context round trip. `test_portal_isolation.py`'s
    `PUBLIC_API_PATTERNS` updated. `ruff` clean; full offline suite green;
    browser-verified against a seeded SQLite warehouse (the expander loads
    the bounded window with the anchor highlighted, unknown id → 400, context
    capped, zero console errors).

- [DONE] BETA-041 | Ranked, faceted document search
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 4
  - confidence: 4
  - risk: 3
  - area: api/documents/search/ui
  - depends_on: BETA-039
  - objective: Extend public document search with `source_system`,
    `document_type`, `year_from`, `year_to` and `since_retrieved_at` facets,
    ranked results and stable pagination across PostgreSQL and SQLite.
  - result: `document_search()` gained the five filter params.
    `source_system` is validated against `DOCUMENT_SEARCH_SOURCES` and 400s
    on anything outside it (fail closed, like the allowlist itself);
    `document_type` matches `document_records.document_type`; `year_from` /
    `year_to` bound `substr(published_at,1,4)` (an undated page drops out of a
    year-bounded search); `since_retrieved_at` bounds `evidence_records.
    retrieved_at`. The SQLite branch keeps FTS5 `MATCH` and now orders
    `rank, document_id, page_number, document_element_id` for stable paging;
    the PostgreSQL branch moves `plainto_tsquery` → `websearch_to_tsquery`
    (accepts a reader's quotes/OR/-term without raising) and adds
    `ORDER BY ts_rank_cd(...) DESC` + the same tie-breakers — it had no
    `ORDER BY` at all before, so paging was plan-order. Payload gains a
    `facets` block (`source_system` and `document_type` counts over the query
    and the date scope only, so the buckets stay visible while a selection
    narrows the rows), a `filters` echo and `limit`.
  - ui: The documents page carries the four filters in the hash beside `q`
    (a shareable filtered search); a new facet bar under the results has two
    count-labelled `<select>`s, published-year from/to inputs and a "Clear
    filters" button. Changing any rewrites the hash and re-runs the search
    from the first page. A new search term resets the filters. "Show more"
    still pages by offset and now carries the filters.
  - validation: 9 new tests in `tests/test_web_documents.py` — facet counts,
    source/type filtering (results narrow, facets don't), the allowlist
    rejection, year bounds incl. undated-page exclusion, `since_retrieved_at`,
    and cross-call pagination stability. `ruff` clean; full offline suite
    green; browser-verified against a seeded SQLite warehouse (facet selects
    render with counts, selecting narrows + updates the URL, year inputs and
    clear work, zero console errors; HTTP checks confirmed the 400 and the
    stable order).

- [DONE] BETA-040 | Contract search and pagination
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 3
  - confidence: 5
  - risk: 2
  - area: api/contracts/ui
  - depends_on: BETA-039
  - objective: Add `q`, `limit`, `offset` and `since_retrieved_at` to
    `/api/v1/contracts`, matching buyer and supplier names case-insensitively,
    with URL-backed portal search, show-more pagination and export/filter
    parity apart from pagination parameters.
  - result: `_contract_filters` gained `q` and `since_retrieved_at`. `q` is a
    wildcard-escaped substring match over `buyer_name` and `supplier_name_raw`
    — `ILIKE` on PostgreSQL (the migration-0069 pg_trgm GIN indexes turn it
    into an index scan) and `LIKE` on SQLite (ASCII case-fold, the documented
    sequential-scan fallback). `since_retrieved_at` is a lexical `retrieved_at
    >=` bound. `contracts()` gained `offset` and a `page` block
    (`limit`/`offset`/`returned`/`q`/`since_retrieved_at`); `total` is still
    the full matching count so the page can show "N of M". All the page's
    charts already ran over the filter clause, so they follow `q` too.
    `all_contract_notices()` (the CSV/JSON stream) also honours `q` /
    `since_retrieved_at` but takes no `limit`/`offset` — the download is the
    complete matching set by construction. `_export` now drops `limit`/`offset`
    from `filters_applied` so an exported file never claims a page was applied.
  - ui: The contracts page owns two hash keys of its own beside the global
    provider/year filters — `q` (a buyer/supplier search box, submitted into
    `#/contracts?q=…`, a shareable link) and `since_retrieved_at` (URL-only,
    shown as a note). The notices table is now a first page of 100 with a
    "Show N more" button that pages by offset; the count line reads "Showing
    100 of M matching notices". Export button and table download carry `q` /
    `since_retrieved_at`, not the pagination.
  - validation: `tests/test_web_contract_search.py` (14 tests) — case-insensitive
    buyer/supplier `q`, wildcard escaping, chart-narrowing, `since_retrieved_at`,
    `limit`/`offset` windowing and clamping, export parity (honours `q`, ignores
    pagination, count agrees with the table), and the HTTP surface.
    `test_portal_tables.py`'s corpus-total pin updated for the paged session.
    `ruff` clean; browser-verified against a seeded SQLite warehouse (search
    rewrites the URL and re-renders, "show more" pages then disappears at the
    end, export links carry the filters, zero console errors).

- [DONE] BETA-039 | Release identity and beta smoke gate
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 2
  - confidence: 5
  - risk: 2
  - area: web/release
  - depends_on: BETA-038
  - objective: Expose a safe `GET /api/v1/meta` release identity containing
    revision, build time, environment, latest migration, latest data timestamp
    and capability flags; show it in the portal footer/admin UI and verify it
    with a read-only beta smoke gate.
  - result: New public route `GET /api/v1/meta` (`public_queries.meta`), added
    to the frozen surface in `test_portal_isolation.py`, the `/api` page and
    the `<noscript>` list. Payload: `service`, `environment`, `revision` +
    `revision_source` (`deployment` when the deploy injected `GIT_REVISION`,
    else `checkout` — read from `.git/HEAD`/`packed-refs`, no subprocess),
    `build_time`, `backend`, a `schema` block (`latest_migration`,
    `applied_count`, `migrated_at`) and a `capabilities` block (`admin_ui`,
    `api_response_cache`, `api_rate_limit`, `document_analysis`,
    `semantic_search`, `postgres_extensions` — `{}` on SQLite, name→installed
    on PostgreSQL via `health.extensions`). Deliberately cheap: reads only
    `schema_migrations` and `http_cache`; per-source retrieval times stay on
    `/api/v1/freshness`, which the `data` block points at. `/health` is
    untouched — still the plain `ok` liveness probe.
  - config: `environment` / `git_revision` / `build_time` added to `Settings`
    (all with local-dev defaults) and documented in `.env.example`.
    `deploy/railway-start.sh` now exports `ENVIRONMENT=production`,
    `GIT_REVISION` (from Railway's `RAILWAY_GIT_COMMIT_SHA`) and a
    process-start `BUILD_TIME` before serving.
  - ui: Portal footer carries a hidden `#build-identity` line that `app.js`
    (`initBuildIdentity`) fills from `/api/v1/meta` — `environment · build
    <sha10> · schema <NNNN> · deployed <ts>` — via text nodes, staying silent
    on any fetch failure.
  - validation: New `tests/test_web_meta.py` (14 tests) — payload shape,
    settings reflection, the `.git` revision fallback, idempotence, and the
    read-only smoke gate (GET/HEAD only; POST/PUT/PATCH/DELETE all refused;
    `/health` still plain text; HTTP payload equals the function output).
    `test_portal_isolation.py` updated for the new route. Full web/portal/
    cache/docs subset green (582 passed); `ruff check pipeline tests scripts`
    clean. Browser-verified against a SQLite warehouse: `/api/v1/meta` serves
    the identity, the `/api` page shows the route, the footer line renders
    with no console errors.

- [DONE] BETA-038 | Queue integrity validator
  - completed: 2026-08-29
  - priority: P1
  - impact: 5
  - effort: 2
  - confidence: 5
  - risk: 1
  - area: engineering/ci
  - depends_on: none
  - objective: Add a dependency-free validator for this queue that fails on
    duplicate item IDs, invalid states, item/state-heading mismatches, more
    than one `IN_PROGRESS` item, or a missing `next_action` on current work.
  - result: `scripts/validate_beta_queue.py` — stdlib only, no Markdown-parser
    dependency. It reads the state vocabulary from the queue's own header
    comment, then flags: unknown state (heading or `[STATE]` prefix), an item
    whose prefix disagrees with its heading, a duplicate item ID, more than one
    `IN_PROGRESS` item, an `IN_PROGRESS` item with no `next_action`, a
    malformed top-level `- [...]` bullet, and a missing `AUTONOMOUS_QUEUE_VERSION`
    marker. Softer gaps — an actionable (`IN_PROGRESS`/`NEXT`/`READY`) item
    missing a recommended scoring field, an unrecognised queue version — are
    warnings, so the pre-template `DONE` history stays valid. `--strict` also
    fails on warnings; the file argument defaults to `beta.md`.
  - ci: New "Validate the beta work queue" step in `.github/workflows/tests.yml`,
    before the test run. It exits 0 with a notice when `beta.md` is absent, so
    it is safe on `master` and on a beta→master PR build.
  - validation: `tests/test_beta_queue.py` — 15 tests: a minimal well-formed
    queue plus one fixture per failure mode, and two checks that the live
    `beta.md` has zero errors and zero warnings. `ruff check pipeline tests
    scripts` clean.

- [DONE] BETA-037 | Optional public API LRU caching and route-specific TTLs
  - completed: 2026-08-29
  - commits: `aeebdf3`, `e654e80` (`beta`)
  - priority: P2
  - impact: 4
  - effort: 3
  - confidence: 5
  - risk: 2
  - area: web/performance
  - depends_on: none
  - objective: Reduce repeated public GET query and serialization work with an
    optional bounded in-process LRU, while letting near-static routes retain
    responses longer than frequently changing ones.
  - rationale: The portal is read-heavy and process-local caching provides a
    useful low-complexity speedup without changing response contracts or
    requiring shared infrastructure.
  - suggested_first_action: Completed — implement cache keys, bounds,
    invalidation/bypass rules and configuration, then assign and test
    route-specific TTL classes.
  - result: Added the optional public API response cache, cache diagnostics and
    route-specific TTL configuration. Private/admin and unsafe requests remain
    outside the public cache path; caching is deploy-time configurable.
  - validation: Dedicated cache tests cover hits, expiry, eviction, disabled
    mode, route TTL selection and relevant job invalidation behaviour.

- [DONE] BETA-036 | PostgreSQL extensions, trigram matching, PostGIS and pgvector acceleration
  - completed: 2026-08-29
  - commits: `d613cb0`, `9bc056a`, `460725b`, `5df2307`, `cc0e869`,
    `c6aec04`, `c8d43fb`, `f11da76`, `1a1118e`, `777828a` (`beta`)
  - priority: P1
  - impact: 5
  - effort: 5
  - confidence: 4
  - risk: 3
  - area: database/postgresql/search
  - depends_on: PostgreSQL deployment path; BETA-034 embedding schema
  - objective: Provision and capability-gate `pg_trgm`, PostGIS and pgvector;
    accelerate fuzzy name matching, authority geometry and semantic vector
    search without breaking SQLite or PostgreSQL instances lacking an option.
  - rationale: These workloads were already present and had clear PostgreSQL-
    native acceleration paths. Explicit capability detection keeps portability
    and honest degradation instead of making extensions hidden requirements.
  - suggested_first_action: Completed — add deployment plumbing and health
    visibility first, then land independent migrations and fallback-tested
    consumers for trigram, geometry and vector capabilities.
  - result: Extension-aware deployment and health reporting; trigram indexes
    plus operator fuzzy-name search; PostGIS authority geometry; pgvector
    storage, backfill and ANN search. HNSW construction is serial for small
    `/dev/shm`, and vector backfill/index creation is explicit rather than a
    health-gated web-startup side effect.
  - validation: Migration-equivalence and focused name-match, geography and
    embedding tests were added; feature commits recorded the full offline suite
    green up to 2615 passed. A disposable live PostgreSQL extension matrix is
    still valuable operational validation and is recorded under Known Issues.

- [DONE] BETA-035 | Concise README + GitHub "About" pointing at the live site and the published docs
  - completed: 2026-08-28
  - commits: `208aeec` (`beta`)
  - origin: **Not drawn from this queue.** Project owner asked directly on
    2026-08-28 (see the pre-DONE entry's `origin` for the verbatim ask),
    then followed up mid-work: "Can you also include a link to the campaign
    site on the readme."
  - result: `README.md` cut from **840 lines to 177**. New shape: a title,
    a two-part "what it is" (one paragraph + the four disciplines —
    provenance-or-`NULL`, layers-stay-separate, nothing-becomes-evidence-
    without-a-person, personal-data-in-`restricted_`), then **See it live**
    (`https://trace.cglpay.us` the portal, `https://cglpay.us` the campaign
    it supports), then **Documentation**
    (`https://jonfuk.github.io/cglpay.us-SectorTrace/`) with a six-row
    table into the key method docs, then Quick start, the module table,
    a short "How it works", Development, Licence.
  - **What was deliberately kept**, because `tests/test_docs_coverage.py`
    pins it against the code: every registered `mNN_` module named (the
    module table, descriptions trimmed to one clause each — 33 modules,
    `test_every_registered_module_appears_in_the_readme`); all five export
    targets and the literal `ten CSV tabs`
    (`test_readme_documents_every_export_target`); both `./start.sh` and
    `start.cmd` (`test_readme_documents_both_entry_points`).
  - **What was cut**, and where the reasoning still lives: the run-order /
    dependency-wave mechanics (the CLI prints its resolved order; comments
    in `runner.py`/`parallel.py`), the write-slot discipline
    (`pipeline/db.py`'s own comment, `CLAUDE.md` settled decision 10,
    `tests/test_write_slot_discipline.py`), the export-provenance and
    bundle internals, the full PostgreSQL cutover/sync procedures
    (`docs/DEPLOYMENT.md`, `docs/BACKUP.md`,
    `pipeline/migrations/postgres/README.md`), and the live-smoke-test
    rationale (`docs/`… no — it is in `tests/test_integration_smoke.py`'s
    docstring; acceptable, it is a contributor-only concern). Nothing that
    was *only* in the README's prose was dropped without a home.
  - **README.md is also the docs-site home page** — `scripts/gen_ref_pages.py`
    copies it verbatim into `index.md` at build, and `scripts/mkdocs_hooks.py`
    rewrites its `docs/*.md` links to internal site links (and `CLAUDE.md`,
    source paths → GitHub blob URLs). Verified: `mkdocs build --strict`
    passes and the built `site/index.html` carries the new copy with
    `CAVEATS/`, `SOURCES/` … resolved internally and the three headline
    URLs intact.
  - GitHub **About**: `gh repo edit --homepage https://trace.cglpay.us`
    run (this session's `gh` has `repo` scope) — the About "website" now
    points at the portal. The description and the eleven topics were
    already accurate and left unchanged.
  - **Found in passing, unrelated**: `mkdocs build --strict` was **already
    aborting on `beta`** (not caused by this work — reproduced on `beta`
    HEAD with the change stashed) because `docs/semantic-analysis.md` (034)
    and `docs/m32-sab-site-crawl.md` were in neither the nav nor
    `mkdocs_hooks.UNPUBLISHED`. They are in-progress design/spec registers,
    the same category as `upgrade-roadmap.md` and `public-portal-ui-spec.md`
    already in that tuple ("a published page reads as settled; these are
    not"), so both were added to `UNPUBLISHED`. The CI `docs` workflow only
    *publishes* from `master` but its `build` job runs on any PR, so a
    beta→master PR would have failed on this.
  - validation: `uv run python -m pytest` full offline suite — **2602
    passed, 109 skipped, 34 deselected, 1 failed**; the one failure
    (`test_parallel.py::test_different_hosts_are_fetched_concurrently`, a
    `elapsed < 0.5s` timing assertion that got 0.57s) is the flaky
    concurrency test from BETA-007's baseline — **passed in isolation
    immediately after** (0.49s), and this change is docs-only. `ruff check
    pipeline tests scripts` clean. `mkdocs build --strict` clean.
    `tests/test_docs_coverage.py` + `test_register_links.py` green (21).
  - possible follow-up: `docs/semantic-analysis.md` could move from
    `UNPUBLISHED` into the nav once BETA-034 is complete — it is a genuine
    subsystem design doc, only excluded now because the gated design is not
    settled.

- [DONE] BETA-028 | The map renders with the network cable unplugged
  - completed: 2026-08-28
  - commits: `6d1be0e` (`beta`)
  - result: `geography.js`'s map workspace now has an offline path. The
    layer-adding code that was inline in the `map.on('load')` closure is
    lifted into a named `drawAuthorityLayers()` (idempotent via a
    `layersDrawn` flag), wired to `map.on('load')` unchanged for the normal
    case. A new `map.on('error')` handler covers the case settled decision 6
    is about: if the CARTO basemap style itself never loads (offline, CDN
    down), MapLibre never fires `load` and the choropleth was never added —
    the reader got the text alternative only. On the first such error the
    handler calls `map.setStyle(localMapStyle(), { diff: false })` — a
    `{version: 8, sources: {}, layers: [{background}]}` style in the theme's
    background colour via the existing `isDark()` — then draws the same
    authority fill/line and any active point/cluster layers on it once the
    new style settles (`styledata` + `isStyleLoaded()` re-arm loop).
  - **The basemap stays for online readers.** The CARTO style URLs are still
    in `geography.js` (`styleUrl()` untouched), still CSP-allowlisted
    (`server.py`), and `tests/test_web_layers.py`'s assertion that both
    positron and dark-matter URLs are present still passes. The fallback is
    additive.
  - **Guarded three ways so it can never blank a working map**: fires once
    (`styleFallbackTried`), only before the authority layers are on
    (`layersDrawn`), and only while no style has loaded
    (`!map.isStyleLoaded()`) — so a late tile or glyph 404 on an
    already-rendered map is ignored. `diff: false` because the failed style
    left nothing to diff against (MapLibre would warn and full-rebuild
    anyway). Known limitation, commented in the code: the cluster-count
    **text** layer needs the CDN's glyphs and will not label in offline
    mode; the clusters, points and choropleth all draw without it.
  - validation: full offline suite — **2622 passed, 106 skipped, 34
    deselected, 0 failed** (the pre-existing `test_documents.py`
    transformers-cache failures from earlier baselines did not reproduce
    this run, as BETA-033 also saw). `ruff check pipeline tests` clean. New
    `tests/test_web_layers.py::test_the_map_falls_back_to_a_local_style_when_the_basemap_is_unreachable`
    pins the source shape (this suite runs with no browser); the existing
    positron/dark-matter URL test and `test_portal_isolation.py` still pass.
  - **Not verified in a live browser** — carried caveat, same as
    BETA-024/027/033. This session's Browser pane reports
    `document.hidden: true` / `visibilityState: "hidden"` throughout, and
    MapLibre GL defers style loading to first paint via
    `requestAnimationFrame`, so **no** map style (online basemap or the new
    local fallback) ever finishes loading in this pane — confirmed by
    driving the online path too: the workspace mounts (canvas + nav
    controls), the text-alternative list renders all 330 authority rows, no
    console errors, but `map.isStyleLoaded()` stays false at 5s. The offline
    fallback needs an eyeball in a foregrounded tab with the CARTO URL
    blocked; the behaviour is source-pinned in the meantime.
  - possible follow-up: `docs/CAVEATS.md` / CLAUDE.md decision 6 could now
    note the `/geography` basemap as a written exception *with* its offline
    fallback, closing the documentation gap BETA-033 flagged.

- [DONE] BETA-029 | Overview stops downloading 500 notices to draw 10 bars
  - completed: 2026-08-28
  - commits: `6d1be0e` (`beta`)
  - result: `overview.js`'s `renderTopContracts()` now fetches
    `contracts?limit=10` instead of `?limit=500`. Everything the section
    draws — `value_concentration`, `largest_matched_to_provider` (already
    top-5 server-side), the corpus-wide concentration line, `matched_to_provider`
    — is computed in `public_queries.contracts()` over the whole corpus
    regardless of `limit`; the one limit-bound field it reads is `notices`,
    used only for the provenance block (deduped, at most 6 URLs shown) and
    its latest retrieval date. The homepage's single biggest transfer drops
    ~98% for an identical chart, table and caveat set.
  - **Minor, disclosed**: the provenance "retrieved" date shown in the
    finding block is now the max `retrieved_at` over the 10 most-recently-
    *published* notices rather than over 500 — on the live warehouse this
    read 2026-08-23 vs the freshness panel's "4 days ago". Still truthful
    (those notices *were* retrieved then), presentation-only, and exactly
    the tradeoff §52 finding 4 accepted when it queued this.
  - validation: full offline suite green (2622 passed, as above); `ruff`
    clean. New `tests/test_portal_overview.py` pins that the contracts fetch
    passes a bounded limit (≤ 25). **Verified live** against `./start.sh web`:
    the network request is now `GET /api/v1/contracts?limit=10`, and the
    "largest notices in the corpus" section still renders its 1 chart
    canvas, 5-row data table, concentration line, both caveats and
    provenance, with zero console errors.

- [DONE] BETA-033 | Overview hero region map, orchestrated page-load and scroll-reveal motion; fixed a dead section found along the way
  - completed: 2026-08-26T23:32:47Z
  - commits: `5adc5e6` (`beta`)
  - origin: **Not drawn from this queue**, same as BETA-032 immediately
    below. After BETA-032 shipped, the project owner asked to be
    interviewed for further design refinement of the Overview and Pay
    pages specifically — an explicit "perfect the design" ask, answered
    with several rounds of `AskUserQuestion` before any code was written
    (ambition level, hero treatment, motion appetite, palette direction,
    then the specific hero-visual concept, Pay page's own role, motion
    style, and finally a technical-cost finding that changed the hero
    visual's shape mid-conversation — see the "conflicts" note below).
  - result: the Overview hero now carries a real, if simplified,
    silhouette of England's nine regions, shaded by the same
    "authorities appearing as a contract buyer" coverage signal already
    reported nationally on the snapshot cards — darker regions have more
    of their authorities showing contract evidence, which is drawn from
    a new `authorities.regions` breakdown in `summary()`
    (`public_queries.py`), not a second measure invented for the map.
    Both the Overview and Pay heroes now play a staggered page-load
    reveal (`.hero-animated`, pure CSS, no JS), and every `.section` on
    both pages reveals as the reader scrolls to it
    (`components.js`'s new `revealOnScroll`, IntersectionObserver-based,
    one-shot per element). The Pay page did not get its own dedicated
    visual signature this round — the project owner chose to decide that
    after seeing the Overview result rather than commit to it upfront;
    it stays a plausible BETA-034+ candidate.
  - **The hero map's shape changed twice during the interview, each time
    for a concrete technical reason surfaced before committing to code,
    not a taste reversal:** (1) the project owner's first choice was to
    reuse the `/geography` page's real interactive map; researching that
    found it depends on a live CDN basemap (`cartocdn.com`) and a 14MB
    full-resolution boundary payload (`/api/v1/boundaries`) — a
    reasonable cost for a page a reader chose to visit, a bad one for
    the homepage's first paint, and a direct, undisclosed-at-the-time
    conflict with the settled "both front ends render with the network
    cable unplugged" rule (CLAUDE.md decision 6). Flagged before
    building anything. (2) Presented with that cost, the owner's next
    choice was still the literal map, accepting the tradeoff — then,
    once told the concrete 14MB figure specifically (not just the
    abstract policy conflict), chose a third option instead: dissolve
    the same already-collected, already-provenanced authority polygons
    (`authorities.geometry_geojson`) into their 9 real regions, once,
    server-side, and ship that as a small static asset. This is what
    shipped: `scripts/generate_region_outline.py` (a one-off, run by
    hand, not part of the pipeline's own module registry — regenerate
    only if Module 0 re-collects boundaries from a new ONS vintage) uses
    `shapely.ops.unary_union` per region, then drops sliver polygons
    below 0.05% of each region's dissolved area (adjacent authority
    polygons rarely share byte-identical edges, so the raw union left
    hundreds of sub-square-metre artefacts at every near-miss seam —
    East of England alone dissolved to 490 sub-polygons before this
    filter, 441 of them under 1e-5 sq degrees; after it, every region is
    1-5 real landmasses), then simplifies at 0.04 degrees. Output:
    `pipeline/web/static/public/assets/england-regions.json`, 9
    features, ~64KB on disk / ~28KB over the wire, day-cached. No
    MapLibre, no CDN request, no settled-decision conflict, and the
    resulting silhouette is real England geometry rather than an
    abstract cartogram — checked by eye against the computed bounding
    box (-5.72 to 1.76°E, 49.96 to 55.79°N, which is genuinely
    Cornwall-to-Berwick) since this session could not render a
    screenshot (see Verified, below). The frontend projects the GeoJSON
    to SVG itself (`overview.js`'s `projectRing`/`pathForGeometry`/
    `viewBoxFor`, a new `svgEl()` DOM helper in `app.js` alongside
    `el()` — `document.createElement` cannot produce real SVG elements,
    only `document.createElementNS` can), with a longitude/latitude
    aspect correction so England is drawn at roughly its true
    proportions rather than the wider-and-squatter shape a naive
    equirectangular plot would give it this far from the equator.
  - **Found and fixed in passing, unrelated to anything asked for**: the
    Overview page's "Current snapshot" section — the coverage /
    evidence-quality / sector-context cards (local authorities tracked,
    procurement notices indexed, providers tracked, human-verified
    evidence rows, contract value, sector vacancy/turnover) — has never
    actually rendered on the live site. `render()` built a `snapshot`
    div with `el('div', {})`, filled it via `renderCards(snapshot, ...)`,
    and never inserted that div into the page tree at all; a *separate*,
    permanently-empty `<div id="snapshot">` sat in its place. Confirmed
    present as far back as `HEAD~2` (well before this session), so this
    predates both BETA-032 and BETA-033 — not something either
    introduced. One-line fix: `renderCards(page.querySelector('#snapshot'), summary)`,
    matching every other section's own call pattern. No test caught it
    because no test exercises the rendered DOM of this page; the offline
    suite is fixture-backed against the Python API layer, not JS
    wiring.
  - validation: full offline suite — 2469 passed, 106 skipped, 33
    deselected, 2 failed (`test_documents.py`, the same pre-existing,
    disclosed, environment-caused failures as BETA-032's baseline — a
    third failure BETA-032 saw in `test_m04_companies.py` did not
    reproduce this run, consistent with it being the live-network
    integration test flakiness that file already carries, not a
    regression). `ruff check pipeline scripts` clean.
    `tests/test_portal_isolation.py` updated and passing: the new
    `/assets/england-regions.json` static path is registered in
    `server.py`'s `STATIC_FILES` (guarded by the same directory-origin
    and public-surface-pinning tests every other static asset is) and
    added to that test's `PUBLIC_STATIC_PATHS`.
  - **Verified live against the dev server, with one disclosed gap**:
    confirmed via DOM/network inspection (not screenshot — this
    session's browser pane reported `document.hidden: true` /
    `visibilityState: "hidden"` throughout and could not composite a
    frame) that the region map fetches and renders 9 `<path>` elements
    with correct `aria-label` (computed highest/lowest region from real
    data — London 100%, East of England 72%, on the live warehouse), the
    static asset serves at 200 with a day-long cache header, and the
    "Current snapshot" fix produces the expected 4 section headings
    where 3 showed before. **Not verified**: whether the page-load
    animation and scroll-reveal are visually correct in a real,
    foregrounded browser tab. Direct testing of raw
    `requestAnimationFrame` and `IntersectionObserver` in this same
    hidden tab showed neither ever fires — a session-specific rendering
    limitation also seen verifying BETA-032's count-up animation, not
    something diagnosable from here. The CSS itself was checked in
    isolation (a freshly-created probe element with the `.reveal` class
    correctly computed `opacity: 0`), so the mechanism is sound, but a
    live-browser eyeball of the actual motion is still owed, same as
    BETA-024's and BETA-027's carried-forward caveat.
  - possible follow-up: Pay page's own signature visual (deferred, see
    "result" above); a live-browser check of the motion work once a
    session has a compositing browser; `docs/CAVEATS.md` and CLAUDE.md's
    settled-decision list could note the `/geography` page's existing
    CDN/basemap dependency explicitly, since this conversation surfaced
    it as an undocumented exception to decision 6 rather than a written
    one — not changed this round because it was a pre-existing condition
    being worked around, not something this work touched.

- [DONE] BETA-032 | Overview & Pay page polish: count-up metrics, provider-matched highlights, statutory/gender-pay-gap cleanup, census removal
  - completed: 2026-08-26T22:45:46Z
  - commits: `ef1a4c4` (`beta`)
  - origin: **Not drawn from this queue.** The project owner gave ten
    specific UI requests directly in an interactive session (not the
    autonomous work loop), covering the Overview and Pay pages. Recorded
    here after the fact so a later session has the full picture; the
    queue's IN_PROGRESS/NEXT/READY/RESEARCH items above were not displaced
    by it.
  - result (Overview): the four "campaign view, at a glance" metrics count
    up on load; "active evidence signals" (a count of how many layers
    happened to be non-zero) replaced with the same "matched to a known
    provider" measure already shown on the Contracts page (new
    `summary()["contracts"]["matched_to_provider"]` in
    `public_queries.py`); the 8 explore cards carry a lens-coloured accent
    (money/workforce/access/safety/accountability, reusing app.js's
    existing route-lens categorisation) instead of a flat uniform style;
    Freshness now lists rough sleeping, statutory homelessness and
    temporary accommodation — missing from `FRESHNESS_TABLES` since
    Modules 29-31 shipped (BETA-014/015/016), so those three source
    tables were being collected but never shown as collected; "largest
    notices in the corpus" narrowed from the top 10 overall to the top 5
    matched to a tracked provider (new `largest_matched_to_provider`
    query in `contracts()`), since the unmatched top 10 is dominated by
    anonymous cross-government framework notices with no provider
    attached — not a useful "biggest deal we found" list for the
    campaign.
  - result (Pay): charity accounts table now sorts newest-report-first;
    statutory minimum rates table restricted to the current period (April
    2026), the incorrect "Rate (hourly)" column dropped, and the Under-18
    row excluded (not legally recruitable into a CQC-regulated adult
    substance misuse service, per the project owner directly); gender pay
    gap filings render as a grouped bar chart (median/mean hourly gap %)
    instead of a table; the workforce census section (indicators + metrics
    table, all rows unverified) removed from the page entirely per direct
    instruction, with its nav link — the `pay()` query and its
    `workforce_census`/`census_*` fields are untouched server-side, only
    the page's own rendering of them was removed; Skills for Care
    "National estimates" hides rows with no hourly-pay figure (188 of 500
    rows on the live warehouse).
  - **Conflicts with BETA-031's own research note above**, which
    considered a count-up animation on evidence figures and rejected it as
    "theatre." The project owner asked for this one directly and
    specifically, which is a different footing than the §52 research
    judgement call it overrides — noted here rather than quietly
    overwritten, in case a later session re-reads BETA-031 and wonders why
    the counters exist. The implementation respects
    `prefers-reduced-motion` (jumps straight to the final value) and is
    presentation-only — no value is altered, only how it arrives on
    screen.
  - validation: full offline suite — 2468 passed, 106 skipped, 33
    deselected, 3 failed, all three pre-existing and unrelated (documents/
    Companies House parsing, nothing this session touched — same
    disclosed category as BETA-007's baseline). `ruff check pipeline
    tests` clean. Verified live against the dev server (`./start.sh web`):
    sort order, filtered rows/columns, removed sections, the
    `matched_to_provider`/count-up wiring, and the explore-card accents
    read back via computed style rather than just class presence — an
    earlier draft put `.lens-money`/`.lens-accountability` classes
    directly on the cards, which collided with the *existing*,
    differently-scoped `.lens-accountability` rule the hero-kicker badge
    uses (components.js's `lensBadge()`), and would have silently
    mis-coloured two of the five accents; fixed by setting `--lens` as an
    inline custom property instead of a class. Could not screenshot — this
    session's browser pane did not composite frames — so visual
    confirmation used `get_page_text` and DOM/computed-style reads instead.
  - possible follow-up: the project owner has asked to be interviewed for
    further design refinement of these same two pages next. Expect a
    BETA-033+ entry, either landing directly from that conversation or
    queued here first.

- [DONE] BETA-027 | Command palette: unified search across pages, authorities, providers and documents
  - completed: 2026-08-26T17:40:00Z
  - commits: (this commit; `beta`)
  - result: One search box for the whole portal, opened from a topbar
    button beside the council search, Ctrl/Cmd-K, or "/". It finds portal
    pages, councils, providers and document text, and every choice
    navigates by hash change exactly as the existing per-surface searches
    do — the "front door" pattern the §52 reassessment identified as the
    portal's remaining discoverability gap (three separate search boxes,
    no way to search across them).
  - **Architecture is the operator UI's own palette wearing public
    clothes**, because that pattern is proven in this codebase
    (`static/js/palette.js`): lazily-built dialog, score-ranked flat list
    with inline kind labels (same `score()` — direct match beats
    subsequence — so the two palettes feel identical to anyone who uses
    both), hash-only navigation, focus restored on close, no state of its
    own. New here: the councils and providers lists come from the API
    payloads app.js already fetches and caches at boot (opening the
    palette costs no extra request), and document results arrive live
    from the BETA-022 endpoint — debounced 200ms, minimum 3 characters,
    bounded, and stale-guarded so a response for an abandoned query can
    never paint over the current one.
  - **Two data-shape findings from verifying against the live warehouse:**
    (1) document `title`s in this corpus are usually content-hash
    filenames — a palette of hashes would teach a reader nothing, and the
    documents page itself shows the same hashes (pre-existing, out of
    scope, flagged below). The palette's document rows therefore show the
    *snippet* — real match-centred evidence text, exactly why the row
    matched — with a readable document-type label as detail. (2) One
    document matches on several pages, so 12 raw rows for "recruitment"
    collapse to 4 unique documents; results are deduped by
    source_url+page and the fetch window widened (12) so five *unique*
    documents still fit the display cap.
  - Accessibility follows BETA-021's portal standard rather than the
    operator palette's lighter one: the input declares role=combobox with
    aria-expanded/aria-controls/aria-autocomplete, options carry
    aria-selected with the input's aria-activedescendant pointing at the
    roving highlight, Enter picks, Escape closes, Tab stays inside the
    aria-modal dialog. Values reach the DOM as text nodes (settled
    decision 9): document snippets are scraped council PDFs, and the
    matched-span highlighting is built from element/text nodes, never
    innerHTML.
  - Wired through the frozen surfaces the house rule requires:
    `server.py`'s module list (STATIC_FILES), `PUBLIC_STATIC_PATHS` in
    tests/test_portal_isolation.py, and a new
    tests/test_portal_palette.py pinning: every destination is a real
    route *with the router's own title* (drift fails in both directions),
    the visible trigger exists, app.js boots it, it navigates and never
    filters (no data-filter, no setState), text-node discipline, the
    debounce/bounds/stale-guard, navigation to `#/documents?q=…`, no
    external requests, the keyboard contract, focus restore (including
    the isConnected guard), and the platform-adaptive kbd hint (⌘K on a
    Mac). 104 tests across palette+isolation+navigation+controls+public+
    documents suites pass; ruff clean.
  - **Live smoke test against the dev server** (this checkout's real
    warehouse, GET-only per the Environment Note): `/js/palette.js`
    serves (200), the homepage carries the trigger, `/api/v1/authorities`
    returns 347 rows with the name/ons_code/region fields the palette
    reads, and `/api/v1/document_search` returns match-centred snippets.
    In-browser interaction (overlay opens, arrows move, Enter navigates)
    could not be exercised — no browser or node in this checkout, the
    same caveat BETA-024 carried; a structural balance check stood in for
    a syntax check. Next live session should eyeball it.
  - possible follow-up: readable display titles for committee papers on
    the documents page itself (the palette worked around the hash-title
    problem; the page still shows hashes) — a document-layer
    improvement, not a palette one. Flagged, not queued.

- [DONE] BETA-026 | Quoted phrases anchor snippets and highlight as a unit
  - completed: 2026-08-26T14:50:00Z
  - commits: `538095f` (`beta`)
  - result: `_search_terms` keeps quoted spans whole and lists them first,
    and `_match_snippet` anchors the window on a phrase occurrence before
    considering bare words — which exposed a real bug, not just polish: the
    original `min()` over every term's position let an early single word
    ("sleeping" at char 770) drag the window away from the passage that
    matched as a phrase ("sleeping duty" at char 971), leaving the phrase
    outside the snippet entirely. documents.js's highlighter mirrors the
    same tokenisation (phrases-first alternation), so where the phrase
    occurs contiguously it is marked as one unit. Unmatched lone quotes
    degrade to word behaviour identically on both sides.
  - validation: tests/test_web_documents.py now 13 (phrase anchoring pinned
    with a distractor word placed beyond one snippet radius); 93 combined
    passes across document-search + portal suites; ruff clean.

- [DONE] BETA-025 | "Show more" pagination for document search
  - completed: 2026-08-26T14:20:00Z
  - commits: `6db979a` (`beta`)
  - result: `document_search()` takes a clamped `offset` (negative clamps to
    0 rather than PostgreSQL raising / SQLite walking backwards) threaded
    through both backends' SQL and server.py's route; documents.js grows an
    accumulating "Show N more" control under the results. The button lives
    in its own slot so a failed fetch never touches the pages already on
    screen, is replaced with "Loading…" while in flight (no double-click
    duplicate windows), and the count line stays truthful as the list grows.
    Offset is deliberately *not* URL state — the shareable address stays
    `#/documents?q=…`; how far one reader has paged is transient view state.
  - validation: tests/test_web_documents.py now 12 tests (window tiling
    without overlap against an unpaged reference, offset past end empty-not-
    error, negative clamp); combined run with portal navigation/isolation/
    controls/public suites = 92 passed; ruff clean across pipeline+tests;
    live read-only PG check confirmed disjoint windows and clamping.

- [DONE] BETA-024 | Per-route document titles and focus management on navigation
  - completed: 2026-08-26T13:40:00Z
  - commits: `f2115d7` (`beta`)
  - result: app.js's router now sets a per-route `document.title`
    (ROUTE_TITLES, kept in lockstep with ROUTES by test — drift in either
    direction fails), and moves focus to `#main` with preventScroll when the
    base route changes. The move is gated on an actual route change, not on
    every render: filter edits re-render the whole page through the state
    subscription and must not yank focus out of the control being typed in,
    and first load keeps the reader's own starting point. Pinned by
    tests/test_portal_navigation.py (static-source assertions, this suite's
    offline style), including that index.html's `<main tabindex="-1">` — the
    precondition for the handoff landing anywhere at all — stays put.
  - validation: tests/test_portal_navigation.py (5) + test_portal_controls.py
    + test_portal_isolation.py pass (36 total); ruff clean. Browser check not
    possible from this checkout (no node/browser tooling; see Environment
    Note) — behaviour is deliberately simple and source-pinned; next live
    session should eyeball a nav click announcing/retitling correctly.

- [DONE] BETA-023 | Document search results that show why they matched
  - completed: 2026-08-26T13:05:00Z
  - commits: `cb4781b` (`beta`)
  - result: `document_search()` now returns, per result, a `snippet` windowed
    onto the passage that matched (computed in Python so SQLite FTS5 and
    PostgreSQL return byte-identical snippets — the two engines' native
    headline functions differ in splitting rules and a snippet that changes
    shape with the backend cannot be pinned by test), plus a route-level
    `total` counting every allowlisted match. documents.js renders the
    snippet with `<mark>` highlighting built as element/text nodes (never
    innerHTML — settled decision 9; the text is scraped council PDFs), says
    "showing N of M matching pages" when the list is cut (the client now
    asks for the server ceiling of 50 rather than silently stopping at 25),
    and degrades gracefully against an older cached API response without a
    snippet. Allowlist semantics untouched: `total` counts through the same
    WHERE clause, so excluded source systems are invisible to the count too
    (pinned by test). Full page `text` still ships per result.
  - validation: tests/test_web_documents.py extended to 9 tests (snippet
    centring, short-text whole-return, total vs limit, allowlist-aware
    count) — all pass; test_portal_isolation.py + test_portal_controls.py +
    test_web_public.py pass (76); ruff clean. PostgreSQL path confirmed live
    read-only against this checkout's configured warehouse (`total: 5652`
    for "recovery", short texts returned whole, count query instant at this
    corpus size) — see Environment Note re production data; GET-equivalent,
    nothing written.

- [DONE] BETA-022 | Public document search over committee papers and CDP documents
  - completed: 2026-08-26T02:00:00Z
  - commits: `3f8c74d` (`beta`)
  - result: `pipeline/documents/` (docs/document-analysis.md) has parsed PDFs
    into page-aware, SQLite-FTS5/PostgreSQL-tsvector-searchable text since
    before this session, and `pipeline documents search` has worked at the
    CLI the whole time — nothing before this put it behind a web route.
    `docs/upgrade-roadmap.md`'s own "Corpus-wide search" and "Full-text
    search over archived documents" entries both said to revisit "once the
    promotion work has given it verified documents to search rather than
    candidates" (§3J, §6) — confirmed against the live warehouse before
    writing anything: 13,249 documents parsed, exactly as beta.md's own
    Health-tab note already said. This was wiring an existing backend to a
    route, not building search infrastructure.
  - **The safety question beta.md's own "Questions Requiring Human Input
    #3" left open — "is a document-search UI worth building, and where,
    given some sources have restricted_ personal-data counterparts" — is
    answered by checking rather than guessing:** queried the live warehouse
    directly (`SELECT DISTINCT e.source_system FROM document_records d JOIN
    evidence_records e ...`) and found exactly two source systems bridged
    into this schema today — `committee_paper_promotion` (12,825 docs) and
    `cdp_document_promotion` (424 docs) — both public council/partnership
    governance papers, neither with a restricted_ counterpart. PFD reports
    and tribunal judgments, the two sources docs/CAVEATS.md's "Personal
    data" section actually restricts, are not bridged into this pipeline at
    all (`pipeline/documents/bridge.py` only supports committee_papers,
    cdp_documents, annual_reports, and only the first two have ever been
    run). So: safe to build, scoped tightly.
  - `pipeline/web/public_queries.py::document_search()` reads from an
    explicit `DOCUMENT_SEARCH_SOURCES` allowlist in its SQL, not "everything
    in `document_records`" — this, not `_public()` alone, is the real
    safety boundary, because `document_records`/`document_elements` are not
    `restricted_`-prefixed tables and hold a generic `text` column no export
    guard recognises as personal data. If a future session ever bridges PFD
    report bodies or tribunal judgment text into this same schema, it must
    not become searchable here just by existing in the table — fail closed,
    documented at length in the function's own comment so a future session
    does not have to rediscover the reasoning. `tests/test_web_documents.py`
    pins this with a seeded fixture: a document from an unlisted source
    system, matching the query exactly, is asserted to never come back.
  - New route `/api/v1/document_search` (`q`, `limit`, max 50), new public
    page `/js/pages/documents.js` (search box, URL-carries-query like
    `compare.js`'s own convention, result cards reusing the `.claim` card
    style rather than inventing one), a nav link, an "Explore the evidence"
    tile on the homepage, and matching entries in `api.html` and the
    `<noscript>` block (both pinned by `tests/test_portal_isolation.py`,
    updated in the same commit — the brief's own house rule).
  - Verified against real production data via `./start.sh web`: searching
    "recruitment" returns genuine council committee-paper excerpts (a
    Haringey workforce report, a Staffing and Remuneration Committee
    discussion of a recruitment-and-retention offer) with correct
    provenance links and retrieval dates; an unbalanced-quote and a
    trailing-operator query both degrade gracefully (FTS5 tokenized them
    rather than raising, so the `QueryError` wrapper around
    `sqlite3.OperationalError` was not exercised live, but stays as the
    documented failure path); a no-match query renders the existing
    `noData()` empty state. Zero console errors throughout.
  - Testing: `tests/test_web_documents.py` (5 new tests — finds committee
    paper text, finds CDP document text, **excludes an out-of-allowlist
    source system on an exact text match**, rejects an empty query, clamps
    an oversized `limit`), `tests/test_portal_isolation.py` (21, including
    the new route/page in the frozen public-surface lists),
    `tests/test_web_public.py` + `test_portal_controls.py` +
    `test_documents.py` + `test_licences.py` (86 passed, 2 pre-existing
    unrelated failures — the same `transformers` cache corruption noted in
    Current Beta Status), `tests/test_docs_coverage.py` +
    `test_register_links.py` (21, after updating two
    `docs/upgrade-roadmap.md` entries to record this as delivered). Full
    `uv run python -m pytest` run once more as a final check given this
    touches a new public route and a personal-data safety boundary — see
    below.
  - note: This is the first session-cycle item genuinely prompted by the
    "explore competing products" half of the brief rather than by
    re-checking this project's own prior audits. Comparable-product research
    (OCCRP Aleph, Tussell — see the new "Comparable Product Research" note
    below) confirmed document/full-text search is the headline feature of
    every investigative-evidence platform; this project already had the
    hard part built and unexposed.

- [DONE] BETA-021 | Arrow-key navigation and aria-activedescendant for every typeahead
  - completed: 2026-08-26T00:30:00Z
  - commits: `a28b010` (`beta`)
  - result: The other lower-confidence finding from BETA-018's frontend
    audit (see Deferred Ideas) that was actually still there on re-check.
    The audit named three call sites; re-checking found **six**, not three
    — `relationships.js`'s `entityPicker` (explicitly commented as
    "generalised from compare.js") was missed. Of the six, only two
    (`#find-council`, `#f-provider` in `index.html`) actually declared
    `role="combobox"` — `compare.js`/`treatment.js`/`relationships.js`'s
    pickers only had `role="listbox"` on the `<ul>`, and `treatment.js`'s
    had no role or keyboard handling at all. So the audit's framing
    ("overpromising ARIA") was more true of two widgets than five, but the
    underlying gap — no arrow-key nav, `aria-selected` never set — was real
    everywhere.
  - Added one shared `typeaheadKeyboard(input, list)` export in `app.js`
    (`ArrowDown`/`ArrowUp` move a roving highlight, `Escape` clears it,
    `Enter` picks the highlighted option or the first if none is
    highlighted — the existing behaviour, unchanged) rather than writing
    the same logic six times. `styles.css` already had a
    `li[aria-selected="true"]` rule waiting for this, unused, since before
    this session. Brought all six to the same `role="combobox"` +
    `aria-expanded` + `aria-controls` contract and removed each site's own
    ad-hoc "Enter picks first match" listener in favour of the shared one.
  - note on verification method: the in-app browser tool's synthetic key
    press does not populate `KeyboardEvent.key`/`.code`/`.keyCode` — caught
    by instrumenting a listener before assuming the fix was broken.
    Switched to `dispatchEvent(new KeyboardEvent(...))` with real `key`
    values for all in-browser verification instead; this is what actually
    exercised the arrow-key/Enter/Escape paths on all six widgets. No JS
    test runner exists in this project (no build step, by design — see
    `CLAUDE.md` settled decision 6), so `tests/test_portal_controls.py` +
    `test_web_public.py` + `test_portal_isolation.py` (76 tests) were run
    as a backend-contract/isolation smoke check only, not as proof of this
    change — the in-browser `dispatchEvent` checks are the real evidence.

- [DONE] BETA-020 | Data tables under every Compare-page chart
  - completed: 2026-08-26T00:00:00Z
  - commits: `fb5974e` (rebased to `f566c79` on push; `beta`)
  - result: One of the three lower-confidence findings BETA-018's frontend
    audit deferred (see Deferred Ideas): `compare.js` drew four
    chart-bearing sections (grant, budget, treatment, contracts, plus
    charity/provider-contracts once a provider is selected — six sections
    total) with no accompanying data table, unlike every other
    chart-bearing page in the portal. Re-checked against current code
    before acting, per this file's own discipline — the gap was still
    there. Added a `tableCard` beneath each chart, reusing the exact
    component every other page already uses rather than inventing a new
    one: `renderYearsChart` (shared by grant/budget/contracts/provider
    contracts) gets a `yearsTableColumns()` helper that derives columns
    from `opts` and the rows themselves, since the same function draws four
    differently-shaped series; `renderTreatment` gets one table per
    indicator chart (mirroring `treatment.js`'s own `drawTable`, England
    rows included with `authority_name: 'England'`); `renderCharity` gets a
    static Provider/Year end/Income/Expenditure table. No `exportEndpoint`
    on any of them — `compare` is not in `public_export.py`'s `EXPORTABLE`
    registry and adding one was out of scope for a UI-gap fix.
  - Verified in-browser (`./start.sh web`, not the beta deployment — this
    dev checkout's `DATABASE_URL` is live Railway production, GET-only, see
    Environment Note): selected Adur (authority) and Turning Point
    (provider), all six sections rendered with correct columns and
    GBP-formatted values (including a real negative budget figure,
    `-£411,000`, rendering correctly), zero console errors. No test file
    covers the JS frontend directly (no build step, no JS test runner in
    this project); ran `tests/test_web_compare.py` +
    `tests/test_portal_isolation.py` (31 tests) as the backend-contract and
    isolation smoke check since the endpoint itself was untouched — both
    green.
  - note: A concurrent session pushed `419171f` ("mirror: add explicit
    local PostgreSQL reset", `deploy/ansible-mirror/`) to `origin/beta`
    between this item starting and finishing — rebased cleanly, no file
    overlap. Per `CLAUDE.md`'s "several sessions share this checkout"
    warning, this is expected, not a conflict to resolve further.

- [DONE] BETA-019 | Complete-corpus CSV/JSON export for PFD reports
  - completed: 2026-08-26T00:35:00Z
  - commits: `ece19ae` (`beta`)
  - result: BETA-018's own flagged follow-up, built this cycle. `pfd.js`'s
    "Latest reports" table had no CSV export, unlike every comparable
    "recent records" table elsewhere in the portal — confirmed as a real
    backend gap, not a one-line frontend fix: `pfd()`'s `recent` array is
    `LIMIT 50`, and `public_export.py`'s `EXPORTABLE` registry had no
    `"pfd"` entry, so naively wiring one up would have silently exported
    only the 50 newest of 1,539+ reports as if it were the whole corpus —
    exactly the failure `WINDOWED = {"contracts"}` exists to refuse.
  - Mirrored the existing `contracts` complete-export pattern exactly,
    end to end: `public_queries.all_pfd_reports(conn)` (count first,
    then a streaming cursor over the unlimited query — no `deadline()`
    guard, same reasoning as `all_contract_notices`'s own docstring: a
    complete export of a six-figure-adjacent corpus is meant to take as
    long as it takes); `"pfd"` added to both `EXPORTABLE` (`recent` →
    label `"pfd"`) and `WINDOWED` in `public_export.py`; a new `elif
    endpoint == "pfd"` branch in `server.py`'s `_export_complete`
    (previously a hardcoded `if endpoint != "contracts": raise`, one
    endpoint deep); `exportEndpoint: 'pfd'` added to the frontend table.
    Also found and fixed a smaller adjacent gap while wiring this up:
    `licences.ENDPOINT_MODULES` had no `"pfd"` entry either, so the
    export's licence line would have read "not recorded for this
    endpoint" instead of the correct OGL v3.0 — added, scoped to
    `m08_pfd_reports` only (not `m28_sar_reports`, a different licence,
    since SAR data isn't part of this export).
  - **SAR's own "Latest SAR documents" table deliberately not addressed**
    — flagged as a separate, harder question in BETA-019's own queue entry
    before implementation started: it shares the same `/api/v1/pfd`
    endpoint but is a different sub-array (`data.sar.recent`), and
    `EXPORTABLE`'s one-key-per-endpoint design has no natural slot for a
    second exportable table under one endpoint. Not solved here; would
    need its own design decision, not a bent version of this fix.
  - note: **Verified against real production data, not just the fixture**
    — the live corpus is exactly 1,539 PFD reports (matching the page's
    own hero text); fetched both `/api/v1/export?endpoint=pfd&format=csv`
    and `&format=json` directly against the dev server and confirmed both
    returned all 1,539 rows with a correctly-populated OGL licence line,
    not the 50-row page window. 14 tests in `tests/test_export_completeness.py`
    (extended, not a new file — this is exactly the file `contracts`' own
    complete-export tests live in, the natural home): row-count and
    header-count agreement, licence presence, column-shape agreement
    between the windowed and complete queries (the same "one SELECT feeds
    both" discipline `all_contract_notices` established), JSON
    completeness, and the pre-existing generic guard
    (`test_every_windowed_endpoint_has_a_complete_reader`, which iterates
    `WINDOWED` and would have caught a missing `_export_complete` branch
    automatically). Full suite run clean and uninterrupted: 2441 passed,
    106 skipped, 33 deselected, 2 pre-existing unrelated failures
    (confirmed a sixth time).
  - possible follow-up: SAR export, if wanted, needs its own design
    decision on how `EXPORTABLE` should handle a second exportable table
    under one endpoint — not queued, flagged only.

- [DONE] BETA-018 | Frontend UI audit: theme-aware chart colours, mobile theme switcher, dead vendor file
  - completed: 2026-08-25T23:10:00Z
  - commits: `087c1c6` (`beta`)
  - result: Project owner asked directly to continue exploring frontend
    UI improvements (§27/§28 of the original brief), the area flagged as
    untouched since BETA-010 in this file's own Next Recommended Actions.
    Surveyed all 12 portal pages plus `styles.css` for concrete, evidenced
    gaps (not a speculative wishlist) and found two real bugs, verified and
    fixed, plus one piece of confirmed dead code:
  - **Bug 1 — five ECharts titles and one graph-node label hardcoded
    `color: '#e6edf3'` (a near-white), which overrides the registered
    per-theme colour entirely.** In light mode this made chart titles on
    `authority.js` (3), `compare.js` (1) and `treatment.js` (1), plus
    `providers.js`'s entity-relationship graph node labels, render pale
    grey on a white background. Confirmed by reading `mountChart`'s theme
    selection in `components.js` and `theme.js`'s `sectorTraceLight`
    registration (title colour `#132238`, correctly dark-on-light) — an
    inline option colour always wins over a registered theme's default, so
    these titles never picked it up. Fixed by removing the hardcoded
    colour from title `textStyle` objects (letting the theme supply it)
    and adding a new exported `chartLabelColor()` helper in `theme.js` for
    the one case (the graph label) that sets colour on something other
    than a title, so future series-label colours have a theme-aware helper
    to reach for instead of a literal. **Two similar-looking occurrences
    were deliberately left alone** after checking their context: a
    treemap segment label (`contracts.js`) and a heatmap emphasis border
    (`providers.js`) both sit on saturated fill colours from the shared
    palette, not the page background, so their contrast requirement is
    against the fill, not the theme — not the same bug, and "fixing" them
    blind without a visual check would have been a guess, not a fix.
  - **Bug 2 — the theme switcher was completely unreachable below 900px
    viewport width, with nothing replacing it.** `.theme-control` was a
    topbar-level sibling of the nav, so the mobile offcanvas (which
    relocates only nav items) never carried it, and `styles.css` set
    `.theme-control { display: none; }` outright in both sub-900px media
    queries. A phone reader had no way to override "system" theme at all.
    **First fix attempt (moving the single control into the nav) surfaced
    a second, genuinely pre-existing bug while verifying live in-browser**:
    `.mainnav`'s base rule (`flex-wrap: wrap`, unconditional) was never
    reset to `nowrap` for the mobile `flex-direction: column` layout, so
    once the offcanvas nav's vertical content got tall enough it wrapped
    into a second *column* instead of scrolling — pushing the last item
    far off-screen to the right (confirmed via `getBoundingClientRect()`
    showing x≈1309 in a 375px viewport). This is not new — it was latent
    before this session and would affect any sufficiently long nav list —
    my own addition was just enough content to trigger it for the first
    time. Fixed at the root (`flex-wrap: nowrap` added to both mobile
    `.portal-nav .mainnav` rules) independently of the theme-control fix,
    since it's a correctness issue in its own right. **Final theme-switcher
    design, after reconsidering the first attempt's desktop side-effect**
    (embedding the control in the wrapping nav-links row pushed the whole
    row over the topbar's available width at common desktop sizes,
    wrapping the nav onto two visual rows — caught by comparing
    `getBoundingClientRect()` y-coordinates before and after, not by eye):
    a second, mobile-only duplicate control (`#theme-select-mobile`,
    class `.theme-select` shared with the original) inside the offcanvas
    nav, hidden on desktop; the original stays exactly where and how it
    was. `theme.js` now applies a theme choice and binds change listeners
    to every `.theme-select` element rather than one hardcoded id, so both
    stay in sync regardless of which one a reader used — verified live by
    changing theme from the mobile control and confirming the desktop
    control's value, `<html data-bs-theme>`, and both charts' rendered
    colours all updated together.
  - **Dead code**: `vendor/leaflet.js` and `vendor/leaflet.css` (162 KB)
    were committed but referenced nowhere in any HTML or JS file, and were
    never listed in `vendor/README.md`'s own table — which the README
    itself calls "the only record of what is actually in the tree,"
    meaning their absence from it was itself evidence they didn't belong.
    Confirmed via grep across the whole frontend before deleting; likely a
    leftover from before the map moved to MapLibre. Also removed the
    matching dead `.nav-tools`/`.nav-tools a` CSS rules found while fixing
    the theme switcher — styled a class that appeared nowhere in
    `index.html` at all.
  - note: **Verified every change live in-browser, not from source reading
    alone** — this cycle hit two bugs (the desktop nav-wrap regression, the
    pre-existing flex-wrap column bug) that source inspection alone would
    not have caught, both found by checking actual computed
    `getBoundingClientRect()`/`getComputedStyle()` values against expected
    viewport bounds after the Browser pane's screenshot tool turned out to
    be unavailable in this environment (no visual compositing) — every
    check in this entry substitutes an equivalent programmatic assertion
    for what would normally be a screenshot comparison. Confirmed: desktop
    nav layout unchanged from before this session (topbar row order and
    y-coordinates match); mobile and tablet (375px, 800px) theme switcher
    reachable, functional, and correctly positioned within the viewport;
    both ECharts fixes produce the theme-correct colour in both light and
    dark mode via `chart.getOption()`, not just source inspection; no
    console errors on any of the five pages touched. No Python changed, so
    the offline suite (`test_portal_isolation.py`, `test_portal_controls.py`,
    `test_web_public.py`, `test_web_authority.py`, docs-coverage tests —
    111 tests) served only as a regression check that nothing server-side
    was affected; it was not expected to catch frontend-only bugs and did
    not need to.
  - possible follow-up: three further findings from the same audit were
    scoped and deliberately deferred rather than rushed — see BETA-019 and
    the two smaller notes in Questions/Deferred below.

- [DONE] BETA-017 | Surface Modules 29-31 as a "Comparators" section on the authority page
  - completed: 2026-08-25T22:30:00Z
  - commits: `a2b4796` (`beta`)
  - result: Direct outcome of the project owner's requested strategic
    reassessment (§52) after BETA-015/016. The reassessment's first check —
    "are users able to actually discover the new functionality" — found a
    real gap immediately: `grep`-ing `pipeline/web/` for the three tables
    Modules 29-31 built this cycle (`rough_sleeping_snapshot`,
    `statutory_homelessness_snapshot`, `temporary_accommodation_snapshot`)
    returned nothing. Three real, requested-as-comparator datasets existed
    only in the database with no way for a portal reader to ever see them —
    exactly the "data additions have outpaced the ability to understand the
    data" failure mode §52 asks a reassessment to check for, and exactly
    the same pattern BETA-009/013 found and fixed for the evidence graph
    and document-analysis subsystems (built, working, entirely invisible).
  - **Scoped to the natural home for a comparator**: the per-authority page
    (`#/authorities/<code>`), where a reader already sees that authority's
    own substance-misuse evidence — adding the comparator datasets there,
    not a new standalone page, keeps the "look at them side by side"
    framing the project owner originally requested these datasets for.
    `public_queries.authority()` gained three new row-fetches (filtered by
    `ons_code`, one per comparator table) and a `comparators` payload key;
    three new `CAVEATS` entries (one per dataset, each independently
    stating the never-combine rule — not one shared caveat, because a
    reader should not have to infer that three differently-limited
    datasets share one limitation). `authority.js` gained a `Comparators`
    section with one small table per dataset, each with its own pinned
    caveat and provenance line, following the exact existing pattern every
    other section on the page already uses (`section`/`pinnedCaveat`/
    `tableCard`/`provenanceFromRows`) — no new component, no new pattern.
  - note: **Verified live in-browser in both states**, not only via tests.
    Against this checkout's real production data (Birmingham, via the
    normal dev server), the empty state renders correctly — an honest "no
    comparators yet" message naming all three modules to run, the same
    convention every other section on this page already uses for absent
    data, since production has never actually run these modules (writing
    to it was never authorised — see the Environment Note). To verify the
    **populated** path, which production cannot currently exercise, built a
    throwaway local SQLite warehouse (`DATABASE_URL= DATABASE_RO_URL=
    DATABASE_SOURCE_URL= DATABASE_PATH=<scratch> pipeline migrate`, the
    override pattern `pipeline/config.py` itself documents), seeded one
    authority and one row per comparator table, and confirmed all three
    tables render correctly with real figures, correct captions, correct
    provenance links, and no console errors — then stopped that server and
    discarded the scratch database. 4 new backend tests (`pytest tests/
    test_web_authority.py`): payload correctness, that all three caveats
    say "never"/"not" in words (not just in code comments — the actual
    reader-facing text), and that an authority with none of this data gets
    an empty list rather than a missing key or an error. Existing authority
    tests (14 total) all still pass.
  - possible follow-up: none identified — this closes the specific gap the
    reassessment found. A future reassessment should check the same
    question again once more datasets accumulate.

- [DONE] BETA-016 | Module 31: H-CLIC temporary accommodation (TA1)
  - completed: 2026-08-25T22:05:00Z
  - commits: `1336770` (`beta`)
  - result: BETA-015's own flagged follow-up, built this cycle. Reads Table
    TA1 (households in temporary accommodation) from the same quarterly
    workbook Module 30 already reads Table A1 from. **Deliberately shares
    Module 30's discovery and file-reading code by direct import rather
    than duplicating it** — both modules read the same evergreen page, the
    same per-quarter attachment list, and the same revision-preference
    rule, which is a genuinely different situation from Modules 13/29's own
    independent `sheet_rows` copies (unrelated sources, coincidentally
    similar code). To make that sharing clean, three of Module 30's
    previously-private helpers (`_to_int`, `_to_float`,
    `_discover_publications`) and one already-touched function
    (`_read_sheet`, renamed `read_workbook_sheet` and parametrised by sheet
    name) were made module-public — a deliberate, documented API surface
    change to an already-shipped module, not an accidental one.
  - **v1 scoped to the top-level figures only**: total households in TA,
    households with children, children in TA, households in area —
    dropping the bed-and-breakfast sub-breakdown (and its own further
    "6 weeks"/"pending review"/"16-17yo" nesting within that), the same
    smallest-coherent-slice discipline Modules 29 and 30 both applied.
  - **Two real bugs found and fixed while verifying against the real
    downloaded workbooks, before either was written into a test**:
    1. A column-matching regex required a word boundary immediately after
       "ta" (`households? in ta\b`). The real source appends footnote
       digits directly with no separating space ("...in TA1,2,3,4"), and
       `\b` does not fire between two word characters — a letter and a
       digit both count. This silently failed to match the true total
       column and let the per-1,000 rate column (whose header text also
       contains "households in ta", just further right) win the claim
       instead — caught only by checking the resolved value (3.78, a rate)
       against the real published England total (88,310), not by the
       regex looking wrong in isolation. Fixed by dropping the trailing
       `\b` from both affected patterns.
    2. A real edition (January–March 2023) publishes Table TA1 under the
       sheet name `TA1_` (trailing underscore) while every other sheet in
       the same workbook, including Table A1, is named normally —
       `read_workbook_sheet` (the shared function) now resolves a single
       unambiguous trailing-underscore variant when the exact name isn't
       found, and still refuses to guess if more than one candidate would
       match after stripping.
  - Follows the established conventions: migration `0061` (SQLite +
    PostgreSQL), licence registration (OGL v3.0, two places), README's
    module table and Wave 1 (alongside Module 30, same `m00` dependency),
    `docs/SOURCES.md`, and a `docs/CAVEATS.md` entry that cross-references
    Module 30's revision/placeholder caveats rather than restating them,
    plus its own notes on the B&B scope boundary and the misnamed-sheet
    fix. Also corrected a line in Module 30's own caveat entry that had
    become stale the moment this module started existing ("temporary
    accommodation ... none of them are in this pipeline").
  - note: **Verified against five real downloaded workbooks directly**,
    not only hand-built fixtures — all five source-file eras/formats this
    cycle has now collected (2019 Q4 ods, 2023 Q1 ods with the misnamed
    sheet, 2023 Q4 ods, 2024 Q1 xlsx, 2026 Q1 ods) resolved every column
    correctly and matched MHCLG's own published England totals exactly
    after both bugs were fixed. 10 new unit tests, including regression
    tests for both bugs found (one exercises `read_workbook_sheet`'s
    fallback directly via an in-memory ODS document built with odfpy, not
    a downloaded file, so it doesn't depend on the scratch directory
    surviving a session boundary). 43 tests across both m30 and m31 pass
    together (the shared-function rename required updating two of m30's
    own existing tests, caught immediately by running them together rather
    than assuming the rename was safe). All five cross-cutting coverage
    guards updated again. Full suite, run clean and uninterrupted (no
    concurrent file edits this time — see BETA-015's own note on why that
    matters): **2434 passed, 106 skipped, 33 deselected, 2 failed** — the
    same pre-existing `transformers`/docling issue, confirmed a fifth time.
  - **What this session could not verify**: an actual live fetch-parse-
    write run, same constraint as every dataset addition this cycle
    (`.env` points at live Railway production).
  - possible follow-up: the B&B breakdown (Modules 30/31 both dropped
    sub-breakdowns this cycle) is a plausible smaller addition to this
    same module later, not a new module — flagged, not queued.

- [DONE] BETA-015 | Module 30: statutory homelessness (H-CLIC) snapshot
  - completed: 2026-08-25T21:40:00Z
  - commits: `5855ac7` (`beta`)
  - result: BETA-014's own flagged follow-up, built this cycle. Source
    researched directly against the live GOV.UK page
    (`live-tables-on-homelessness`), not assumed from docs — one evergreen
    page attaching one file per quarter (closer to m29's single-page
    discovery than m13's per-publication search). Only Table A1 (households
    by initial-assessment outcome — the flagship "statutory homelessness"
    count) is read, out of 40+ tables in the workbook, the same
    one-table-done-properly discipline m29 applied.
  - **Found and fixed a real parsing bug while verifying against actually
    downloaded files, before writing the parser**: the `sheet_rows()`
    pattern this pipeline's other ODS modules (m13, m29) use walks only
    `<table:table-cell>` elements, silently skipping
    `<table:covered-table-cell>` elements — invisible in m13/m29's own
    sources, which have no genuine multi-column-spanning merged cells, but
    H-CLIC's older-era files do (merged group-header cells), and skipping
    them shifts every later column in that row left by however many columns
    the merge spanned. Fixed locally in the new module only — not touched in
    m13/m29, whose own inputs never hit it.
  - **The sheet layout is not stable across the 2017–2026 series** — an
    older multi-row merged-header block and a newer flat single-header-row
    form both appear. `locate_a1_columns` resolves either by keyword
    (concatenating each column's own header text across all header rows,
    excluding prose rows like the title by requiring ≥2 populated cells),
    claiming fields in a specific order (relief and prevention before the
    total, which is claimed before its own "of which" sub-breakdowns can be)
    so a parent total's own sub-columns — which repeat the parent's
    group-label text as a prefix in the modern shape — cannot steal its
    claim. Verified by hand against **four real downloaded quarters**
    spanning both shapes and both file formats (2019 Q4 ods, 2023 Q1 ods,
    2024 Q1 xlsx, 2026 Q1 ods) before any test was written: every column
    position resolved correctly and matched MHCLG's own published
    England-level totals exactly.
  - **A second real finding from that same verification, not anticipated
    going in**: region (`E12…`) and England (`E92…`) aggregate rows in this
    source carry genuine ONS codes in the authority-code column, unlike
    m29's source, which marks them with a `[z]` placeholder instead. m29's
    own `^E\d{8}$` filter would have silently mis-stored a region as if it
    were a local authority here; tightened to the local-authority prefix set
    only (`E06`–`E10`, m13's own `local_authority` classification) for this
    module. A third finding, documented as its own `docs/CAVEATS.md` bullet
    rather than silently handled: in the older table layout,
    `not_threatened_no_duty` is the sole combined "no duty owed" total (no
    separate withdrew/not-eligible breakdown existed yet), while in the
    newer layout it is only the "not threatened" reason, one of three
    additive columns — confirmed against real published totals from both
    eras (72,290 − 68,520 = 3,770 exactly for Oct–Dec 2019; 4,130 + 3,600 +
    610 ≈ 92,200 − 83,850 for Jan–Mar 2026, the small remainder being
    MHCLG's own rounding).
  - Follows the established module conventions exactly:
    `pipeline/modules/m30_statutory_homelessness.py` (registered,
    auto-discovered), migration `0060` (SQLite + PostgreSQL),
    `pipeline/licences.py` + `components.js`'s mirrored copy (OGL v3.0),
    `docs/SOURCES.md`, `README.md`'s module table and Wave 1, and a
    `docs/CAVEATS.md` entry covering: the comparator-only rule (same as
    m29), the single-table scope boundary, silent overwrite on revision (a
    "(revised)" edition replaces the earlier figures on the natural-key
    upsert `(ons_code, quarter_start)` — this pipeline always prefers a
    revised edition where both are attached), `[x]`/`[z]`/`[n]`/`[c]`
    placeholder handling (`[c]` — data suppression — is new; m29's source
    does not use it), the pre-2017 `.xls` coverage gap (no reader without a
    new dependency, a bounded and documented boundary not a silent one), and
    the `not_threatened_no_duty` dual-meaning finding above. Also fixed the
    now-stale line in m29's own caveat entry that said statutory
    homelessness was "a separate MHCLG collection this pipeline does not yet
    read" — cross-references Module 30 now.
  - note: **Verified as thoroughly as this session safely could, including
    against real full downloaded workbooks, not only hand-built fixtures.**
    33 new unit tests on the pure parsing functions (fixtures built from the
    real header/data text of both shapes, locked to the exact column
    positions confirmed against the real files; title-regex inclusion and
    exclusion for every distinct attachment title pattern actually seen on
    the live page — financial-year summaries, Multiple Disadvantage tables,
    and "- Accessible" duplicates all correctly excluded; all four
    placeholder values null out; region/England/`-` rows correctly excluded
    from extraction). Separately re-ran the locator directly against all
    four downloaded real workbooks (not just fixtures) and confirmed every
    resolved value against MHCLG's own published England totals by hand.
    All five cross-cutting coverage guards BETA-014 found were touched again
    here and all caught something real: `tests/test_since_handling.py`,
    `tests/test_integration_smoke.py`, `tests/test_migration_equivalence.py`
    (migration count), `tests/test_progress_coverage.py` (module count *and*
    the progress-reporting/registration-correctness checks — see below),
    `README.md`'s module table. Full suite, run clean and uninterrupted:
    **2419 passed, 106 skipped, 32 deselected, 2 failed** — both the same
    pre-existing `transformers`/docling `UnicodeDecodeError` BETA-014
    already confirmed unrelated (reproduced again in isolation to be sure).
  - **A genuine false alarm worth recording, not because it affected the
    result but because it could confuse a future session**: an earlier full-suite
    run (started before a comment-only docstring edit) showed two spurious
    failures — `MODULE_REGISTRY['m30_statutory_homelessness']` appearing to
    resolve to a helper function rather than `run`. Root cause: editing the
    module's source file while a long-running background pytest process was
    mid-suite shifts line numbers on disk after Python has already cached
    the function's old `co_firstlineno` at import time; `inspect.getsource`
    re-reads the file from disk on each call, so it briefly read the wrong
    function's text at the old line offset. Confirmed as an artifact, not a
    real bug, by re-running those two tests in isolation (passed) and then a
    second full suite with no concurrent edits (clean). Lesson for future
    sessions: do not edit a module's source while a background test run
    covering it is still in flight.
  - **What this session could not verify**: an actual live fetch-parse-write
    run, for the same reason as every dataset addition this cycle — this
    checkout's `.env` points at live Railway production (see Environment
    Note).
  - possible follow-up: other H-CLIC tables (temporary accommodation in
    particular — TA1 — is arguably as substance-misuse-relevant as A1, and
    was seen and understood during this module's own research) are a
    plausible Module 31, not started. Not requested by the project owner;
    flagged as a discovered opportunity only.

- [DONE] BETA-014 | Module 29: rough sleeping snapshot (new dataset)
  - completed: 2026-08-25T00:00:00Z
  - commits: `47cf21c` (`beta`)
  - result: Project owner asked for homelessness/rough-sleeping/crime data
    as local-authority-level comparators, given the well-documented overlap
    with substance misuse. Researched all three properly before building
    anything (§16 of the original brief's Dataset Expansion Authority
    checklist): confirmed real, current, official sources —
    - **Rough sleeping snapshot** (MHCLG): annual, LA-level, one evergreen
      GOV.UK page whose single ODS republishes the *entire* 2010-to-current
      series every edition (verified by downloading and parsing the real
      file: 296 authorities × 16 years, 4,736 rows). Cleanest shape, most
      direct substance-misuse link — **built this cycle**.
    - **Statutory homelessness (H-CLIC)**: official, quarterly, LA-level
      ("Live tables on homelessness") — same shape family as `m13`'s MHCLG
      budgets. Confirmed viable, **not built this cycle** — one module per
      cycle done properly beats two done fast; queued as a natural
      follow-up, not started.
    - **Crime data** (`data.police.uk`): the only real option found is
      street-level/LSOA, not local-authority-level — using it as an LA
      comparator would need this pipeline's own LSOA→ONS-code crosswalk, a
      materially bigger and more sensitive undertaking (small-area crime
      data carries its own care-in-handling questions this project hasn't
      had to face yet). **Deliberately not built** — flagged as a real
      finding, not a task, in Questions Requiring Human Input.
  - **Module 29** follows the established module conventions exactly:
    `pipeline/modules/m29_rough_sleeping.py` (registered, auto-discovered),
    migration `0059` (SQLite + PostgreSQL), `pipeline/licences.py` +
    `components.js`'s mirrored copy (OGL v3.0), `docs/SOURCES.md`,
    `README.md`'s module table and Wave 1, and a `docs/CAVEATS.md` entry
    that leads with the caveat the project owner's own framing needed most:
    **methodology is not standardised between authorities** (each chooses
    its own counting approach and date), so a raw comparison between two
    authorities' figures may reflect a difference in method, not only a
    difference on the street — and, per this project's first rule, **never
    combined or computed against the sector's own substance-misuse
    evidence**, comparator only, side by side.
  - note: **Verified as thoroughly as this session safely could.** Real
    MHCLG file downloaded and parsed directly to confirm the actual sheet
    shape (`Table_1_Total`, `Table_5_Rates`, header row, year columns,
    `[x]`/`[z]`/`[n]` placeholders, region/England aggregate rows correctly
    excluded) before a line of the parser was written — not guessed at from
    documentation. 21 new tests on the parsing functions (the same
    "test the pure functions, not the odfpy I/O layer" convention `m13`
    already established), all passing against realistic fixture rows.
    Five separate offline coverage guards this addition touched (migration
    count, README module list, per-module licence in two mirrored places,
    the integration-smoke module-coverage spec, the progress-reporting and
    `--since`-declaration guards) all found and fixed — each caught a real
    doc/registration gap the way it's designed to. Full suite: 2384 passed,
    2 pre-existing unrelated failures (confirmed for the third time now).
  - **What this session could not verify**: an actual live fetch-parse-write
    run. This checkout's own `.env` has `DATABASE_URL` pointing at the live
    Railway production database (see Environment Note) — running
    `./start.sh run m29_rough_sleeping` for real would both make a live
    request under the project's identity and write to production without
    explicit authorisation for either. Not done. The parsing logic is
    verified against the real source file directly; the fetch-and-write
    integration (HTTP client wiring, `db.upsert`, commit behaviour) is
    exercised by the same code paths `m13`/`m18` already use in production,
    but a first real run of *this* module specifically should be watched,
    ideally against a local SQLite warehouse or `--dry-run`, not assumed
    correct from unit tests alone.
  - possible follow-up: statutory homelessness (H-CLIC) as Module 30, same
    shape family as this one and `m13`. Crime data needs a scoping decision
    first (see Questions Requiring Human Input) — not a next action yet.

- [DONE] BETA-013 | Health tab: surface the document-analysis layer's own status
  - completed: 2026-08-25T00:00:00Z
  - commits: (pending push — see the commit immediately following this
    entry in `git log beta`)
  - result: The "CLI-only capability with no UI" pattern that found the
    evidence graph (BETA-009) found a second, larger subsystem on the same
    scan: `pipeline/documents/` — inspection, OCR (OCRmyPDF), parsing
    (Docling), classification and quality scoring, documented in
    `docs/document-analysis.md` (migration `0053`) — with a working
    `pipeline documents search` command and zero UI exposure anywhere,
    public or admin. Explicitly scoped in its own doc as *not* creating
    claims, promoting evidence, or calling an AI service — a genuinely safe
    subsystem to surface status for, unlike the AI-promotion question.
  - **Scoped to the same safe slice as BETA-009, deliberately not more**:
    a Health tab card (`health.document_status()` — registered, parsed,
    failed, and total document counts, all cheap `COUNT(*)` reads), not a
    document search UI. **Explicitly did not build search exposure this
    cycle**: `pipeline documents search` reads parsed text from raw archived
    documents, which can include PFD reports and other sources with
    `restricted_` personal-data counterparts — unlike the relationship
    explorer's deterministic contract-award data, a search surface here
    needs its own careful check of what a search result could reveal before
    any UI is built around it, admin or public. Flagged as a discovered
    opportunity, not built.
  - note: **Verified against real production data** — this checkout's own
    warehouse shows "13,248 documents parsed of 13,283" (99.7% success),
    confirming the subsystem is in heavy real use, not dormant. 3 new tests
    (empty state, counts by parse outcome, graceful handling of a
    pre-migration warehouse); 86-test regression pass (health, security
    headers, portal isolation) green; live-browser confirmation, no console
    errors beyond the same unrelated environmental noise seen throughout
    this session.
  - possible follow-up: a document-search UI (admin first) is plausible and
    the backend already exists, but needs an explicit answer to "what could
    a search result surface" before any UI work — queued as a question, not
    a task, in Questions Requiring Human Input.

- [DONE] BETA-012 | Entry-point links into the relationship explorer
  - completed: 2026-08-25T00:00:00Z
  - commits: (pending push — see the commit immediately following this
    entry in `git log beta`)
  - result: BETA-010's own follow-up note, done same cycle rather than
    deferred. The authority page's hero now links "Who it commissions →" to
    `#/relationships?ons_code=...`; the provider deep dive's hero links
    "Who commissions it →" to `#/relationships?provider_key=...` — the same
    entry-point pattern W-11's compare view already uses from both pages
    (`#/compare?ons_code=...` / `#/compare?provider_key=...`), placed
    directly alongside it.
  - note: Verified live against real production data (this checkout's
    `DATABASE_URL`, see Environment Note) — both links carry the correct
    query parameter (`ons_code=E08000025`, `provider_key=change_grow_live`),
    and a direct navigation to each resulting URL renders "Showing:
    Birmingham" / the relationships page centred correctly. 76 existing
    tests (authority, public, portal isolation) unaffected — no test pins
    the exact entry-point link text, so none needed updating.

- [DONE] BETA-010 | Public relationship explorer over the evidence graph
  - completed: 2026-08-25T00:00:00Z
  - commits: (pending push — see the commit immediately following this
    entry in `git log beta`)
  - result: New dedicated portal section (`#/relationships`), scoped
    exactly as decided in the project owner's interview: provider↔authority
    commissioning relationships only, a one-hop neighbourhood centred on
    whichever entity the reader picks — not a whole-corpus map, which would
    invite exactly the size/importance/centrality reading this pipeline
    never asserts. New `public_queries.relationships()` reads only
    `entities`/`entity_relationships`/`evidence_records` (never Neo4j,
    which is an explicitly disposable projection of the same rows) filtered
    to `predicate = 'AWARDED_TO'` and `derivation_type IN ('SOURCE_FACT',
    'DERIVED_RELATIONSHIP')` — `REGISTERED_AS` (ownership) and
    `EXTRACTED_CLAIM`/`ANALYTICAL_SIGNAL` (BETA-009's not-yet-built
    extraction pipeline) explicitly excluded, not by their current absence.
    New frontend page (`relationships.js`) with typeahead pickers (reusing
    the compare page's pattern), an ECharts `graph`-series force diagram
    (already-vendored, no new dependency), and — because a force diagram
    has no accessible text equivalent — a citable table beneath it with
    per-edge provenance (source URL, retrieval date, licence), matching
    "everything is citable" exactly as every other page does. New caveat
    (`commissioning_relationship`) pinned above the diagram. Wired into the
    frozen route/asset lists in `tests/test_portal_isolation.py`, the `/api`
    documentation page, and the `<noscript>` block — also fixed that page's
    stale "nothing here is rate-limited" line left over from before
    BETA-007.
  - note: **Verified against real production data end-to-end, not just
    fixtures** — live in-browser, Nottinghamshire's real commissioning
    relationships to Change Grow Live and Turning Point rendered correctly
    as both the force diagram and the citable table, with real Find a
    Tender provenance and OGL licensing, no console errors. 9 new backend
    tests (both direction of lookup, an entity with no matched relationship
    returns an empty neighbourhood rather than a 404, an unknown entity is
    a clean 400, ownership and unreviewed-extraction edges are excluded
    even when present in the data, graceful handling of a warehouse that
    predates the graph tables). Full suite: 2358 passed, 2 pre-existing
    failures unrelated to this change (confirmed twice now, see BETA-007's
    entry for the first confirmation).
  - follow-up delivered same cycle: see BETA-012.

- [DONE] BETA-009 | Health tab: surface the evidence graph's own operational state
  - completed: 2026-08-25T00:00:00Z
  - commits: `f2b727a` (`beta`)
  - result: Did the comparable-product research (§3 of the original brief)
    this session had skipped in favour of internal code archaeology —
    looked at OCCRP Aleph and LittleSis for OSINT-platform patterns. Found
    something more useful than either's specific feature: `pipeline/graph/`,
    `pipeline/analytics/{graph_builder,networks}.py`, `evidence_graph.py`
    and migration `0050` are a mature, carefully-caveated entity/relationship
    graph subsystem (Neo4j projection + NetworkX structural metrics,
    documented in `docs/evidence-graph.md`) that's real, merged, and
    apparently in active use (this checkout's own warehouse shows a real
    364-entity run from 5 days ago) — but has **zero exposure anywhere in
    the UI**, not even admin-only. `docs/upgrade-roadmap.md` never mentions
    it at all; it was built entirely outside that register's phase system.
    Checked whether a fuller relationship-explorer UI was safe to build:
    confirmed `graph_claims.review_status` (a claims-review gate mirroring
    the existing Claims tab pattern) exists in the schema but nothing
    currently writes an `EXTRACTED_CLAIM`/`ANALYTICAL_SIGNAL` relationship —
    only the deterministic `graph backfill` path, using `SOURCE_FACT`/
    `DERIVED_RELATIONSHIP` from already-verified warehouse data. So the
    *data* is safe to surface; a full visual explorer is still a separately-
    scoped, bigger effort (new API endpoint, new frontend page, a rendering
    approach — ECharts' native `graph` series is already vendored and would
    need no new dependency, but that's a real design decision, not an
    obvious one to make unilaterally).
  - **Scoped down to the safe, valuable, small slice**: a Health tab
    addition, not a graph explorer. `pipeline/web/health.py` gained
    `graph_status()` — last projection run (status, entity/relationship/
    claim counts, error detail if failed) and pending sync-queue depth, both
    single cheap indexed-table reads, so (unlike storage/freshness) this
    lives in the fast `health()` bundle rather than its own route. Two new
    cards in `pipeline/web/static/js/health.js`. Handles a warehouse that
    predates migration `0050` gracefully (via the existing `_table_exists`
    pattern already used for `http_cache`).
  - note: **Verified against real data, not just fixtures** — this dev
    checkout's own warehouse (2.4 GB, real ONS/CQC/court data) rendered
    "5d ago / evidence graph" and "364 / graph entities (last run)"
    correctly in-browser, no console errors. 6 new tests in
    `tests/test_web_health.py` (never-run, most-recent-run selection, a
    failed run, queue counting, and graceful handling of a pre-migration
    warehouse) plus a broader regression pass (83 tests: health, security
    headers, portal isolation) all green.
  - possible follow-up: a real relationship-explorer UI is a legitimate,
    well-motivated next feature (this is exactly the LittleSis/Aleph
    comparable-product pattern the original brief's §3 asks to look for),
    but it's a bigger scoping decision than this session should make
    unilaterally — queued as a question, not a task, in Questions Requiring
    Human Input.

- [DONE] BETA-008 | Fix two more stale roadmap entries found while scoping BETA-007's follow-up
  - completed: 2026-08-25T00:00:00Z
  - commits: `0c82267` (`beta`)
  - result: While checking whether W-15's remaining open half (CQC location
    links) was a viable next item, found it was already shipped 2026-08-21
    (`86ef103`, four days before this session started) — by a different,
    better-fitting mechanism than the finding envisioned (per-location badge
    links from CQC's own bulk-export URL column, not the generic
    company/charity `REGISTERS` map, because a provider has many CQC
    locations rather than one). Independently reconfirmed live in-browser:
    the URL resolves cleanly, no bot-block. Corrected W-15's entry and a
    matching stale comment in `components.js`. Also marked §3J's "API rate
    cap" delivered (BETA-007), rather than leaving it as a note-to-self.
  - note: **This is the third time this session found the roadmap claiming
    "not yet done" for something already shipped** (W-23–26, then §8's
    B/C/F/G items, now W-15). Each time the actual code was correct and the
    register was behind. Raised explicitly in Questions Requiring Human
    Input — this is now a pattern, not a one-off, and worth the project
    owner's judgement on whether the register is worth keeping current going
    forward.

- [DONE] BETA-007 | Per-IP rate limit on the public API (/api/v1/*)
  - completed: 2026-08-25T00:00:00Z
  - commits: (pending push — see this file's own commit immediately after
    this entry lands)
  - result: Strategic reassessment after BETA-001–004 (queue empty of ready
    work by design — see Next Recommended Actions in the prior revision of
    this file) surfaced this from `docs/upgrade-roadmap.md` §3J ("API rate
    cap"), filed 2026-08-14 and deliberately deferred pending "the portal
    being reachable by readers the operator does not trust" — a condition
    BETA-003 just confirmed true (production is Railway, a public host).
    Implemented as specified there: a per-IP token bucket on `/api/v1/*`
    only (not `/api/admin/*`, which is gated on network trust rather than
    request rate — unchanged), `429` + `Retry-After` rather than silence.
    New `pipeline/web/ratelimit.py` (`TokenBucketLimiter`, no new
    dependency — the algorithm is a dozen lines), two new settings
    (`api_rate_limit_per_minute`, default 120; `api_rate_limit_burst`,
    default 40 — generous by design so several readers behind one shared
    NAT address never see it), `api_rate_limit_enabled` to turn it off
    entirely. Client IP resolution honours `X-Forwarded-For`'s first hop
    when present (every real deployment topology — Caddy in the Docker
    builds, Railway's edge — puts a trusted proxy in front and the app is
    not otherwise reachable), else the direct TCP peer.
  - note: **Verified thoroughly given this touches production server code**:
    14 new unit/integration tests (a fake-clock unit suite for the bucket
    algorithm itself, plus a real-server integration suite covering the
    429+Retry-After path, independent-buckets-per-IP, the admin API and
    static/health routes staying unaffected, and the disable switch);
    188 existing web tests unaffected; full suite run (first time this
    cycle) — 3 failures, all confirmed pre-existing (see Current Beta
    Status); live-browser check that ordinary interactive use (~18 API
    calls across 4 page loads) never approaches the default burst; a manual
    burst against the real dev server confirmed the defaults are generous
    enough not to trip during normal use (and, separately, confirmed the
    server's own connection handling is unaffected by the change — see
    commit message for the WinError investigation that turned out to be
    unrelated Windows/curl.exe socket behaviour, not this code).
  - possible follow-up: nothing queued. `docs/upgrade-roadmap.md` §3J's
    entry can be marked delivered in a future doc pass (not done here —
    this session already flagged, in BETA-002, that treating "corrected the
    findings register" as a standing chore rather than a one-off has its
    own cost/benefit question for the project owner to weigh).

- [DONE] BETA-004 | Audit the ~45 stale agent/codex/claude branches for anything else worth reviving
  - completed: 2026-08-25T00:00:00Z
  - commits: none (audit found nothing to merge)
  - result: **Complete, not partial** — every non-master, non-beta branch is
    now accounted for. Of ~45 total, only 11 (per `origin/*`) plus 6
    local-only branches ever had commits not in `master`; every other branch
    (~35, including all the `claude/phase-N-*` and `claude/sectortrace-*`
    ones) has zero commits ahead of `master` and needs no check — its content
    already landed. Of the 17 with real diffs:
    - 1 was BETA-001 (already merged).
    - 6 are WDTK bot-bypass branches, out of scope by policy (unchanged from
      the first pass).
    - 2 (`sectortrace-plan-review-d43b72`, `provider-research-pipeline`) are
      badly diverged, forked before ~15 later modules existed — confirmed
      again, still not worth reconciling.
    - 1 (`codex/dataset-completion-2021-2026`) is live-collection Railway
      worker operations — out of scope for an autonomous merge regardless of
      staleness (running real backfill tranches against production).
    - **7 are local-only, never pushed to origin, and every one of them
      turned out to be a stale leftover pointer whose content is already
      merged into `master` under a *different* commit hash** — confirmed by
      diffing the actual files, not just comparing commit messages (e.g.
      `archive-processor`'s `pipeline/archive_process.py` diffs empty
      against `master`'s copy). Normal residue of a PR-based workflow
      (rebase/squash-merge changes the hash; the local branch pointer is
      never cleaned up). Nothing here was unpushed original work.
  - note: The project has ~45 stale local+remote branch pointers that could
    be deleted as housekeeping. **Not done here** — branch deletion is
    visible/semi-reversible and this session was not asked to clean up, only
    to check for revivable work. Flagged as a suggestion, not an action; see
    Known Issues.

- [DONE] BETA-003 | Teach ansible-mirror to build a beta deployment, not just mirror
  - completed: 2026-08-25T00:00:00Z
  - commits: 29d07c9 (`beta`)
  - result: Project owner confirmed production is Railway directly. Added
    `mirror_role` ("dr_mirror", unchanged default, or "beta") to
    `deploy/ansible-mirror/`: a beta box pins a git branch (`deploy_git_branch`,
    default "beta"), a new `site.yml` pre-task resets the box's checkout to
    `origin/<branch>` before every build, and the database is seeded from a
    source **once** (`mirror_recurring_sync_enabled: false` by default for
    beta — reusing the mirror's existing three sync paths, including "url"
    mode which the docs already described as built for exactly a managed
    source "such as Railway") rather than wholesale-replaced nightly.
    `mirror_verify_enabled` now derives from whether recurring sync is on,
    since "does this still match the source" is meaningless for a database
    meant to diverge via test writes. Wizard, `site.yml`, the role's tasks,
    both READMEs and `docs/DEPLOYMENT.md` all updated. `bash -n`, YAML
    parsing of every touched file, and `test_register_links.py` +
    `test_docs_coverage.py` (21 tests) all pass.
  - note: **Not exercised against a real VPS** — no `ansible-playbook` in
    this dev environment. The Jinja/YAML was reviewed by hand and is
    consistent with existing patterns in the same files, but a first real run
    should be watched, not trusted blind. `deploy/ansible/`'s own live/fallback
    status relative to Railway was deliberately not investigated — out of
    scope for what was asked.

- [DONE] BETA-002 | Reconcile docs/upgrade-roadmap.md against current code
  - completed: 2026-08-25T00:00:00Z
  - commits: `81dd9d9` (§3: W-23–W-26), plus a second pass (§8: B1, B2, B3,
    F1, F2, F3, G1, G3, G4, G6, G7 — see below)
  - result: Two passes, because the first was incomplete. Pass 1 checked
    every F/D/P/U/W/O/S/T entry in §3 (the numbered findings register)
    against current code — all accurate except the four already caught.
    **Pass 2, found while starting BETA-004:** §8 ("Proposed workstreams",
    a *separate* B/C/F/G numbering scheme) had the exact same drift — its
    own top-of-file summary already said Phases 15/16/18 delivered
    B1–B3/F1–F3/G1/G3/G4/G6/G7, but every individual entry below still read
    as an open proposal. Confirmed each against the actual module/table
    (`m17`–`m23`, `eat_cases`, `company_psc`) and tagged all eleven
    `DELIVERED` in place, plus a correction note on §8's own header. §3J
    (possible futures) and §4 (quick wins) were also checked and needed no
    changes — both were already internally consistent.
  - note: **Did not retire the register** — reconciliation (both passes)
    showed it was already ~95% trustworthy in its own terms, not rotten; it
    just wasn't being kept in sync with work that landed outside its phase
    system. Whether to keep filing new work through it going forward is the
    project owner's call, not resolved here (see Questions Requiring Human
    Input). **Lesson for future sessions:** a big structured doc with more
    than one numbering scheme can be stale in one scheme and not the other —
    checking "the findings register" is not the same as checking the whole
    file, however much it looks like it at a glance.

- [DONE] BETA-001 | Fix Tabulator recursive call-stack overflow on every portal table
  - completed: 2026-08-25T00:00:00Z
  - commits: c1c3ecd (on `master`, not `beta` — see note)
  - result: Cherry-picked an already-written, already-diagnosed fix from an
    orphaned branch (`origin/claude/elated-torvalds-b5bed9`, authored by the
    project owner 2026-08-21, never merged). Tabulator only sets
    `fixedHeight = true` when `options.height` is passed; every portal table
    passed only `maxHeight`, so a holder with no intrinsic size (e.g. the
    provider deep dive) could recurse `redraw()` → `adjustTableSize()`
    without a depth guard and throw `RangeError`. One-line fix: pass
    `height` instead of `maxHeight`. Verified: `test_portal_controls.py` +
    `test_web_public.py` (55 tests) green; `/providers` and `/contracts`
    loaded in-browser with no console errors afterward.
  - note: landed directly on `master`, not staged on `beta` first. Reasoning:
    it is a pure correctness fix restoring already-intended, already-authored
    behaviour on the live public portal (a `RangeError` on table render is a
    user-facing crash), carries zero product-decision content, and the
    project owner had already written and reasoned through the fix — only
    merging it was outstanding. The brief's own §41/§43 instinct ("if you
    discover a material vulnerability/defect, prioritise fixing it") was read
    as pointing at `master` here, not at parking a live-portal crash behind a
    beta review cycle it does not need. Flagged in this session's summary to
    the project owner rather than assumed silently correct.

  - objective: This session checked 5 of ~45 non-master branches. One
    (`elated-torvalds-b5bed9`) was a clean, valuable, ready fix (BETA-001).
    Two (`sectortrace-plan-review-d43b72`, `provider-research-pipeline`) were
    badly diverged and not worth reconciling. The rest are unchecked.
  - rationale: Cheaper to recover already-done work than to redo it, but each
    branch needs the same "is this still valid against current master"
    check BETA-001 got — do not merge anything without it.
  - suggested_first_action: For each remaining branch, `git log --oneline
    master..<branch>` and `git diff master <branch> --stat`; anything whose
    diff is dominated by unrelated deletions (a sign of staleness, as with
    the two branches above) gets skipped, not forced.
  - notes: **Do not touch** `codex/m15-web-unlocker*`, `codex/m15-zenrows*`,
    `codex/wdtk-html-fallback*` without asking first — these concern bot-block
    bypass mechanisms for WDTK (`m15_foi`), which `docs/CAVEATS.md` and
    `README.md` both describe as narrow, human-permissioned exceptions
    requiring the provider's explicit sign-off, not something to autonomously
    finish and merge.

### BLOCKED

- [BLOCKED] BETA-011 | Wire up AI-authored evidence promotion
  - priority: P1
  - blocked_by: Candidate type/use case — asked directly of the project
    owner in this session, answer pending (see Questions Requiring Human
    Input #0).
  - resume_when: The project owner specifies which candidates this should
    apply to.
  - alternative_work_available: yes (BETA-010 is done; more discovery
    ongoing)
  - decided_so_far: Wire it up for real use (not remove, not
    document-as-inactive). Review requirement: one AI pass plus the
    existing human review-queue decision counts as the second independent
    review — so this does *not* need two separate AI passes, just the AI
    check plus whatever a human reviewer already decides in the normal
    queue. Project owner's decision, 2026-08-25 interview.
  - notes: This is the most sensitive item in the whole queue — it touches
    `CLAUDE.md` settled decision 4 directly. Do not start implementation
    speculatively before the candidate type is known; the predicates
    (official source, exact identity, document type, dated, archived, no
    conflicts) mean very different things depending on which candidate
    table this reads from.

- [BLOCKED] BETA-005 | WDTK robots.txt exception review
  - priority: P1
  - blocked_by: Human decision, time-boxed
  - resume_when: 2026-09-10, or sooner if mySociety replies to
    `docs/mysociety-access-request.md`
  - alternative_work_available: yes
  - notes: `m15_foi` fetches WhatDoTheyKnow's search feed against an explicit,
    logged `robots.txt` exception pending mySociety's answer. Not this
    session's decision to make or extend; flagging only so a future session
    does not miss the date. (Tracked in this account's memory independently
    of this file.)

### RESEARCH

- [RESEARCH] BETA-006 | Is `--jobs 4` worth another look now that more sources exist?
  - priority: P3
  - question: The roadmap's P-03 (parallel collection) was refused twice,
    most recently 2026-08-16, for lack of an evidenced comparison run — not
    for lack of merit. Eleven more collection-relevant commits and several
    new modules (m24–m28) have landed since. Does that change the
    cost/benefit of running the comparison?
  - research_needed: Whether a `--jobs 4` vs `--jobs 1` comparison run is
    schedulable without colliding with active campaign collection — this is
    an operational/calendar question, not a technical one, and was refused
    twice already for exactly that reason. Do not re-open without new
    information about scheduling, per the roadmap's own P-03 entry.

## Current Priorities

1. **BETA-068–072 — resilient public foundations:** capability-aware error
   states, a usable mobile header, a workforce-pay explorer, responsive data
   tables, and consistent URL-restorable filters.
2. **BETA-073–077 — local and navigable evidence:** My area, inspectable
   visualisations, a treatment-metric explorer, structured provider/authority
   workbenches, and route/history continuity.
3. **BETA-078–081 — evidence exploration:** a multi-layer evidence atlas, a
   careful safety/legal hub, shared responsive UI primitives, and a document
   reading room.
4. **BETA-082–087 — operator refinement and trust:** pipeline mission control,
   a schema-aware data explorer, page-level evidence health, responsive admin
   navigation, an action cockpit, and split-pane review.
5. **Queue state:** the programme is approved but unqueued. When implementation
   is explicitly started, promote BETA-068 to IN_PROGRESS and no more than the
   next five dependency-safe items to NEXT.
6. **BETA-088–106 — second approved refinement programme:** research
   continuity and monitoring, evidence/version exploration, contract and
   document inspection, pipeline diagnostics and quality-control workflows.
   These items remain behind BETA-068–087 unless explicitly reprioritised.
7. **BETA-107–113 — local analyst-assistant programme:** optional Needle 2
   routing and LFM grounded synthesis over public, read-only SectorTrace
   tools, with model/run provenance, citation validation and measurable
   release gates. These items remain behind BETA-068–106.

**Hard boundary:** BETA-034 stays BLOCKED until `gate-034g` succeeds on a
human-reviewed corpus. BETA-046 may expose the already-built search diagnostic;
BETA-047 may collect individual named decisions. Neither may train SetFit,
write `graph_claims`, bulk-approve candidates or publish semantic claims.
BETA-107–113 is the named decision to permit local, read-only RAG as an
operator finding aid only; it does not relax any of those boundaries.

## Candidate Feature Backlog

| Priority | Idea | Impact | Effort | Confidence | Status |
|---|---|---:|---:|---:|---|
| P1 | WDTK robots.txt exception review | — | — | — | BLOCKED (BETA-005) |
| P2 | Reconcile upgrade-roadmap.md against code | 3 | 3 | 4 | DONE (BETA-002) |
| P2 | Beta deployment via ansible-mirror, Railway confirmed as prod | 3 | 3 | 4 | DONE (BETA-003) |
| P3 | Audit remaining stale branches for revivable work | 2 | 3 | 2 | DONE (BETA-004) |
| P3 | Re-evaluate `--jobs 4` given new modules | 2 | 2 | 2 | RESEARCH (BETA-006) |
| P4 | Delete ~45 stale/superseded branch pointers | 1 | 1 | 5 | Suggested, not queued — see BETA-004 |
| P2 | Module 29: rough sleeping snapshot (dataset) | 4 | 3 | 5 | DONE (BETA-014) |
| P2 | Module 30: statutory homelessness / H-CLIC (dataset) | 4 | 4 | 4 | DONE (BETA-015) |
| P3 | Module 31: H-CLIC temporary accommodation, TA1 (dataset) | 3 | 3 | 4 | DONE (BETA-016) |
| P2 | Surface Modules 29-31 as a Comparators section on the authority page | 4 | 2 | 5 | DONE (BETA-017) |
| P2 | Frontend UI audit: theme-aware chart colours, mobile theme switcher, dead vendor file | 4 | 3 | 5 | DONE (BETA-018) |
| P3 | Complete-corpus CSV export for PFD reports | 3 | 3 | 4 | DONE (BETA-019) |
| P3 | Compare-page data tables under every chart | 3 | 2 | 5 | DONE (BETA-020) |
| P3 | Typeahead arrow-key nav + aria-activedescendant (6 widgets) | 3 | 3 | 5 | DONE (BETA-021) |
| P2 | Public document search (committee papers + CDP documents) | 4 | 3 | 5 | DONE (BETA-022) |
| P2 | Document search: match-centred snippets, highlighting, result counts | 4 | 2 | 5 | DONE (BETA-023) |
| P3 | Per-route document titles + SPA focus management | 3 | 1 | 5 | DONE (BETA-024) |
| P3 | Document search "show more" pagination (offset through both backends) | 2 | 2 | 4 | DONE (BETA-025) |
| P4 | Quoted-phrase awareness in search snippets/highlights | 1 | 1 | 5 | DONE (BETA-026) |
| P1 | Command palette: unified search (Ctrl-K) | 5 | 3 | 4 | DONE (BETA-027) |
| P1 | Map renders with the network cable unplugged | 4 | 2 | 4 | DONE (BETA-028, `6d1be0e`) |
| P2 | Overview payload: stop shipping 500 notices for 10 bars | 3 | 1 | 5 | DONE (BETA-029, `6d1be0e`) |
| P2 | Copy-citation button in provenance drawer | 4 | 2 | 4 | DEFERRED (BETA-030; not selected) |
| P2 | Homepage first-impression visual | 3 | 3 | 3 | DEFERRED (BETA-031; superseded by BETA-033) |
| P2 | Overview and pay page visual polish | 4 | 3 | 5 | DONE (BETA-032) |
| P2 | Overview hero region map and motion treatment | 4 | 3 | 5 | DONE (BETA-033) |
| P2 | Semantic-analysis layer over the document archive | 5 | 5 | 3 | BLOCKED (BETA-034; `gate-034g`) |
| P2 | Concise README, live-site links and GitHub About | 3 | 2 | 5 | DONE (BETA-035) |
| P1 | PostgreSQL extension and search acceleration | 5 | 5 | 4 | DONE (BETA-036) |
| P2 | Optional public API LRU and route TTLs | 4 | 3 | 5 | DONE (BETA-037) |
| P1 | Queue integrity validator | 5 | 2 | 5 | DONE (BETA-038) |
| P1 | Release identity and beta smoke gate | 5 | 2 | 5 | DONE (BETA-039) |
| P1 | Contract search and pagination | 5 | 3 | 5 | DONE (BETA-040) |
| P1 | Ranked, faceted document search | 5 | 4 | 4 | DONE (BETA-041) |
| P1 | Document evidence-context view | 5 | 3 | 4 | DONE (BETA-042) |
| P1 | Public dataset catalogue | 5 | 4 | 4 | DONE (BETA-043) |
| P2 | Commissioning-relationship detail and timeline | 4 | 3 | 5 | DONE (BETA-044) |
| P2 | Provider comparison enhancements | 4 | 4 | 4 | DONE (BETA-045) |
| P2 | Admin semantic-search workbench | 4 | 3 | 5 | DONE (BETA-046) |
| P2 | Semantic claim review and gate dashboard | 5 | 4 | 4 | DONE (BETA-047) |
| P2 | OpenAPI 3.1 specification | 4 | 3 | 5 | DONE (BETA-048) |
| P1 | Accessibility and performance guardrails | 5 | 4 | 4 | DONE (BETA-049) |
| P1 | Procurement lifecycle and performance view | 5 | 5 | 4 | DONE (BETA-050) |
| P1 | HSE enforcement-notice evidence | 4 | 4 | 4 | DONE (BETA-051) |
| P1 | Structured review-item context | 5 | 2 | 5 | DONE (BETA-052) |
| P2 | Review clusters and informational grouping | 4 | 3 | 4 | DONE (BETA-053) |
| P1 | Evidence sidecars and candidate suggestions | 5 | 4 | 4 | DONE (BETA-054) |
| P2 | Review-session workflow polish | 4 | 2 | 5 | DONE (BETA-055) |
| P1 | Human alias-resolution workflow | 5 | 4 | 3 | DONE (BETA-056) |
| P2 | Candidate URL overlap signals | 3 | 3 | 4 | DONE (BETA-057) |
| P1 | Unified durable run ledger | 5 | 4 | 4 | DONE (BETA-058) |
| P1 | Coverage completion action board | 5 | 4 | 4 | DONE (BETA-059) |
| P2 | Raw-archive inventory and integrity trends | 4 | 3 | 4 | DONE (BETA-060) |
| P1 | Candidate-promotion campaign workspace | 5 | 4 | 4 | DONE (BETA-061) |
| P2 | Human-readable document titles | 4 | 3 | 4 | DONE (BETA-062) |
| P1 | PostgreSQL extension readiness gate | 5 | 4 | 4 | DONE (BETA-063) |
| P2 | Temporary-accommodation B&B breakdown | 3 | 3 | 4 | DONE (BETA-064) |
| P1 | CQC regulated-location explorer | 4 | 4 | 4 | DONE (BETA-065) |
| P2 | Provider predecessor and successor lineage | 4 | 3 | 4 | DONE (BETA-066) |
| P2 | Capability-documentation consistency checker | 4 | 3 | 5 | DONE (BETA-067) |
| P1 | Release compatibility and graceful degradation | 5 | 3 | 5 | DONE (BETA-068) |
| P1 | Mobile public-header rebuild | 5 | 3 | 5 | DONE (BETA-069) |
| P1 | Workforce pay explorer | 5 | 4 | 4 | DONE (BETA-070) |
| P1 | Responsive public data tables | 5 | 4 | 4 | DONE (BETA-071) |
| P1 | Consistent filters and URL-restored query state | 5 | 3 | 5 | DONE (BETA-072) |
| P1 | My area context | 5 | 4 | 4 | DONE (BETA-073) |
| P2 | Inspectable visualisations | 4 | 3 | 5 | DONE (BETA-074) |
| P1 | Treatment metric explorer | 5 | 4 | 4 | DONE (BETA-075) |
| P1 | Navigable provider and authority workbenches | 5 | 4 | 5 | DONE (BETA-076) |
| P2 | Navigation continuity | 4 | 3 | 5 | DONE (BETA-077) |
| P1 | Unified evidence atlas | 5 | 5 | 4 | DONE (BETA-078) |
| P1 | Safety and legal evidence hub | 5 | 4 | 4 | DONE (BETA-079) |
| P1 | Shared responsive design system | 4 | 4 | 5 | DONE (BETA-080) |
| P1 | Document reading room | 5 | 5 | 4 | DONE (BETA-081) |
| P1 | Pipeline mission control | 5 | 5 | 4 | DONE (BETA-082) |
| P2 | Schema-aware data explorer | 4 | 4 | 4 | DONE (BETA-083) |
| P1 | Page-level evidence health strip | 5 | 3 | 5 | DONE (BETA-084) |
| P1 | Responsive admin navigation | 5 | 4 | 5 | DONE (BETA-085) |
| P1 | Operator action cockpit | 5 | 4 | 4 | DONE (BETA-086) |
| P1 | Split-pane review workspace | 5 | 5 | 4 | DONE (BETA-087) |
| P1 | Evidence notebook | 5 | 4 | 4 | DONE (BETA-088) |
| P1 | Saved searches and change alerts | 5 | 4 | 4 | DONE (BETA-089) |
| P1 | “What changed?” evidence feed | 5 | 5 | 4 | DONE (BETA-090) |
| P2 | Source publication calendar | 4 | 3 | 4 | DONE (BETA-091) |
| P1 | Record revision comparison | 5 | 5 | 4 | DONE (BETA-092) |
| P1 | Relationship pathfinder | 5 | 4 | 4 | DONE (BETA-093) |
| P2 | Visual research journey | 4 | 3 | 4 | DONE (BETA-094) |
| P1 | Entity co-occurrence explorer | 5 | 4 | 4 | DONE (BETA-095) |
| P1 | Evidence discrepancy explorer | 5 | 5 | 3 | DONE (BETA-096) |
| P2 | Temporal coverage navigator | 4 | 3 | 5 | DONE (BETA-097) |
| P1 | Contract diary and milestone calendar | 5 | 4 | 4 | DONE (BETA-098) |
| P1 | Document table extraction viewer | 5 | 5 | 3 | DONE (BETA-099) |
| P1 | Source-link resilience checker | 5 | 4 | 4 | DONE (BETA-100) |
| P1 | Run-to-run output comparison | 5 | 4 | 4 | DONE (BETA-101) |
| P1 | Interactive pipeline and data-lineage map | 5 | 5 | 4 | DONE (BETA-102) |
| P2 | Parser replay sandbox | 4 | 5 | 3 | DONE (BETA-103) |
| P2 | Validation-rule explorer | 4 | 4 | 4 | DONE (BETA-104) |
| P2 | Review-outcome analytics | 4 | 4 | 4 | DONE (BETA-105) |
| P1 | Quality-control sampling workspace | 5 | 5 | 3 | DONE (BETA-106) |
| P1 | Optional Needle 2 and LFM assistant runtimes | 5 | 4 | 4 | DONE (BETA-107) |
| P1 | Assistant provenance and run ledger | 5 | 3 | 5 | DONE (BETA-108) |
| P1 | Public-safe read-only analyst tool catalogue | 5 | 3 | 5 | APPROVED, not queued (BETA-109) |
| P1 | Needle routing and confidence gate | 5 | 4 | 4 | APPROVED, not queued (BETA-110) |
| P1 | LFM grounded answers and citation validation | 5 | 5 | 3 | APPROVED, not queued (BETA-111) |
| P1 | Single-turn assistant API and CLI | 5 | 4 | 4 | APPROVED, not queued (BETA-112) |
| P1 | Assistant evaluation and release gate | 5 | 5 | 4 | APPROVED, not queued (BETA-113) |

This table is a skimmable index reconciled on 2026-08-29. The Autonomous Work
Queue above remains authoritative for queued work; the approved-programme
subsections below preserve the owner's selected scope before promotion. The
second programme contains nineteen items because its final reference-network
candidate was explicitly discarded rather than replaced. The third programme
contains seven items and follows both approved front-end programmes.

### Approved successor round (BETA-050–067)

These are persistent, owner-approved IDs, but they are **not queue-state
entries yet**. This preserves the active BETA-038–049 round, the one-primary-
item invariant and the queue's bounded NEXT/READY set. Promote them only under
the delivery sequence at the end of this subsection.

#### BETA-050 | Procurement lifecycle and performance view

- priority: P1
- impact: 5
- effort: 5
- confidence: 4
- risk: 4
- area: procurement
- depends_on: BETA-040, BETA-044
- objective: Group notices sharing an OCID into explicit planning, tender,
  award, contract, amendment, termination and performance stages; add
  `GET /api/v1/contracts/process/{ocid}` and a public lifecycle view.
- rationale: A defensible procurement history must connect official related
  notices without turning missing stages into inferred completion, renewal,
  KPI achievement or supplier performance.
- suggested_first_action: Define archived OCDS lifecycle fixtures, then extend
  m01 for explicit stages, milestones, amendments, performance fields and
  linked documents.

#### BETA-051 | HSE enforcement-notice evidence

- priority: P1
- impact: 4
- effort: 4
- confidence: 4
- risk: 4
- area: safety/legal
- depends_on: BETA-043, BETA-049
- objective: Add module `m33` for organisation-level HSE improvement and
  prohibition notices, publishing exact tracked-organisation matches through
  `/api/v1/safety` while excluding individuals.
- rationale: Official enforcement notices add attributable safety evidence,
  but ambiguous names and register limitations require the same human-review
  and caveat discipline as the rest of the project.
- suggested_first_action: Capture offline HSE search/detail fixtures and encode
  coverage, appeal and withdrawal caveats before defining storage or routes.

#### BETA-052 | Structured review-item context

- priority: P1
- impact: 5
- effort: 2
- confidence: 5
- risk: 1
- area: admin/review
- depends_on: none
- objective: Render source, entity, reason, evidence and navigation as typed
  sections while retaining the complete raw JSON under disclosure.
- rationale: Reviewers should not have to decode implementation-shaped JSON to
  make a careful decision, but the lossless underlying context must remain
  available for audit.
- suggested_first_action: Build typed presenters for every current review-item
  type and validate all derived internal and source links.

#### BETA-053 | Review clusters and informational grouping

- priority: P2
- impact: 4
- effort: 3
- confidence: 4
- risk: 2
- area: admin/review
- depends_on: BETA-052
- objective: Group related items by issue type, source, organisation and shared
  evidence, with facets and an informational/not-actionable state.
- rationale: Coherent batches reduce reviewer navigation without allowing
  grouping itself to become a judgement.
- suggested_first_action: Define deterministic cluster keys and require a
  transactional recount before every grouped action.

#### BETA-054 | Evidence sidecars and candidate suggestions

- priority: P1
- impact: 5
- effort: 4
- confidence: 4
- risk: 3
- area: admin/review
- depends_on: BETA-036, BETA-052
- objective: Show source excerpts, archive references and ranked candidate
  entities beside the decision form.
- rationale: Side-by-side evidence and alternatives improve decision quality,
  provided ranking remains a finding aid rather than an automatic verdict.
- suggested_first_action: Define sidecars and candidate-generation rules for
  each supported review type; label rankings as similarity, never preselect a
  candidate and suppress known false-match patterns.

#### BETA-055 | Review-session workflow polish

- priority: P2
- impact: 4
- effort: 2
- confidence: 5
- risk: 1
- area: admin/ux
- depends_on: BETA-052
- objective: Add next-page prefetch, session progress, saved note/filter
  presets, a keyboard map and a primary-source shortcut.
- rationale: These reduce mechanical work without altering the review audit
  trail or confirmation boundaries.
- suggested_first_action: Pin focus, history and navigation behaviour in
  browser tests before introducing shortcuts.

#### BETA-056 | Human alias-resolution workflow

- priority: P1
- impact: 5
- effort: 4
- confidence: 3
- risk: 4
- area: entity-quality
- depends_on: BETA-054
- objective: Resolve unmatched buyer and provider names through append-only
  proposed, accepted, rejected and superseded decisions, then produce a
  deterministic verified-alias registry.
- rationale: Repeated unresolved names reduce coverage, but fuzzy matches must
  never silently become canonical identity.
- suggested_first_action: Design the decision schema and SQLite/PostgreSQL
  invariants around named reviewer, timestamp, evidence and canonical entity
  ID; automatic fuzzy application remains forbidden.

#### BETA-057 | Candidate URL overlap signals

- priority: P2
- impact: 3
- effort: 3
- confidence: 4
- risk: 2
- area: data-quality/review
- depends_on: BETA-052
- objective: Show when a conservatively canonicalised URL appears across
  source tables or workflow roles.
- rationale: Overlap can expose duplicate discovery or related evidence, but
  it is not proof that records should be merged, discarded or reprioritised.
- suggested_first_action: Define fixtures for fragments, tracking parameters,
  redirects and genuinely distinct documents before writing the normaliser.

#### BETA-058 | Unified durable run ledger

- priority: P1
- impact: 5
- effort: 4
- confidence: 4
- risk: 3
- area: operations
- depends_on: BETA-039
- objective: Record CLI, admin and scheduled executions through one durable
  model with origin, revision, environment, parent run, timestamps and
  per-module results; keep full logs in their current storage.
- rationale: Browser-started job history alone cannot explain every collection
  path or support reliable operational handoff.
- suggested_first_action: Add a backward-compatible migration and instrument
  the shared module runner used by every entry point.

#### BETA-059 | Coverage completion action board

- priority: P1
- impact: 5
- effort: 4
- confidence: 4
- risk: 2
- area: admin/coverage
- depends_on: BETA-043, BETA-058
- objective: Distinguish run needed, review needed, source blocked, not
  published and complete; add `GET /api/admin/completeness` with links to the
  relevant run, candidate, review or dataset view.
- rationale: Coverage measurements become operationally useful only when each
  gap has an honest reason and a permitted, non-destructive next action.
- suggested_first_action: Map every current completeness state to one reason
  code and one action destination.

#### BETA-060 | Raw-archive inventory and integrity trends

- priority: P2
- impact: 4
- effort: 3
- confidence: 4
- risk: 2
- area: archive/operations
- depends_on: BETA-058
- objective: Track archive count, size, source distribution, missing
  references, duplicate hashes, deterministic hash samples and growth through
  `pipeline archive audit` and an admin audit-history endpoint.
- rationale: A point-in-time size scan cannot reveal integrity drift or future
  storage pressure.
- suggested_first_action: Define immutable summaries and deterministic sampling
  rules; this item measures only and never deletes, compacts or chooses
  retention policy.

#### BETA-061 | Candidate-promotion campaign workspace

- priority: P1
- impact: 5
- effort: 4
- confidence: 4
- risk: 3
- area: evidence-promotion
- depends_on: BETA-052, BETA-054
- objective: Provide a campaign workspace for CDP documents, committee papers
  and FOI/SAR candidates with filters, previews, session progress and explicit
  promote/reject/reset actions.
- rationale: Candidate promotion is a separate audited human act from general
  review-queue decisions and needs a focused workflow rather than unattended
  batching.
- suggested_first_action: Reuse the existing promotion API through the shared
  typed presenters; retain one-candidate-at-a-time confirmation and prohibit
  `promote all`.

#### BETA-062 | Human-readable document titles

- priority: P2
- impact: 4
- effort: 3
- confidence: 4
- risk: 2
- area: documents/public-ux
- depends_on: BETA-041, BETA-042
- objective: Replace hash-like labels with deterministic display titles while
  preserving raw source titles and recording `title_basis` as source label,
  PDF metadata, first heading or filename.
- rationale: Search results need readable identity, but a derived title must
  remain explainable rather than being presented as source text.
- suggested_first_action: Add fixtures for blank, misleading, duplicated and
  personal-name-heavy metadata, then specify deterministic precedence.

#### BETA-063 | PostgreSQL extension readiness gate

- priority: P1
- impact: 5
- effort: 4
- confidence: 4
- risk: 3
- area: database/deployment
- depends_on: BETA-036, BETA-039
- objective: Add read-only `pipeline pg-capabilities` reporting PostgreSQL
  version, extensions, operator classes, expected indexes and active fallbacks;
  exercise core and extension-enabled disposable PostgreSQL paths in CI.
- rationale: BETA-036 has focused coverage but its optional extension matrix
  has not yet been proven in a disposable live PostgreSQL deployment.
- suggested_first_action: Codify the trigram, PostGIS and pgvector capability
  matrix and its fallback expectations.

#### BETA-064 | Temporary-accommodation B&B breakdown

- priority: P2
- impact: 3
- effort: 3
- confidence: 4
- risk: 2
- area: dataset/comparators
- depends_on: BETA-043
- objective: Extend m31 with the source-published bed-and-breakfast household
  breakdown from H-CLIC Table TA1, stored in
  `temporary_accommodation_breakdowns` with authority, quarter, value, unit
  and full provenance.
- rationale: The data was deliberately omitted from the smallest coherent v1
  and is now a bounded extension of the same official comparator source.
- suggested_first_action: Verify archived workbook header variants and define
  the exact permitted measure codes; surface contextually without rankings or
  provider-performance comparison.

#### BETA-065 | CQC regulated-location explorer

- priority: P1
- impact: 4
- effort: 4
- confidence: 4
- risk: 3
- area: public/cqc
- depends_on: BETA-045, BETA-049
- objective: Add a filterable map, accessible table and paginated
  `/api/v1/cqc_locations` endpoint for tracked providers' CQC-registered
  locations, filtered by provider, authority, status, regulated activity,
  service type and rating.
- rationale: Existing location evidence is difficult to explore, but CQC
  registration is not a complete service map and location counts are neither
  coverage nor quality scores.
- suggested_first_action: Define the public-column allowlist, map/table parity
  and missing-coordinate behaviour; exclude every restricted contact field.

#### BETA-066 | Provider predecessor and successor lineage

- priority: P2
- impact: 4
- effort: 3
- confidence: 4
- risk: 3
- area: provider-identity
- depends_on: BETA-056
- objective: Add `GET /api/v1/providers/{provider_key}/lineage` and a provider
  detail timeline for explicit active, merged, dissolved, predecessor and
  successor relationships.
- rationale: Older evidence remains attached to historical provider entities;
  users need the verified lineage without inferred ownership or personal
  officer data.
- suggested_first_action: Normalise existing `status` and `superseded_by`
  configuration into explicit, testable lineage edges with verified identifier
  roles only.

#### BETA-067 | Capability-documentation consistency checker

- priority: P2
- impact: 4
- effort: 3
- confidence: 5
- risk: 1
- area: documentation/tooling
- depends_on: BETA-038, BETA-048
- objective: Add machine-owned documentation blocks generated from module,
  source, route, export, licence and caveat registries, with non-mutating
  `pipeline docs-check` for CI and explicit `pipeline docs-sync` regeneration.
- rationale: Capability prose has already drifted behind implemented committee
  system support; machine-owned factual matrices can prevent recurrence while
  narrative documentation remains manually reviewed.
- suggested_first_action: Reconcile the stale committee-system statements and
  define the first generated source-capability matrix.

**Delivery sequence:** After BETA-049 completes, promote BETA-050 to
IN_PROGRESS and BETA-051, BETA-052 and BETA-058 to NEXT. Wave 2 is BETA-053,
BETA-054, BETA-055, BETA-059 and BETA-060. Wave 3 is BETA-056, BETA-057,
BETA-061, BETA-062 and BETA-063. Wave 4 is BETA-064–067. Maintain exactly one
IN_PROGRESS item and no more than five NEXT items.

### Approved front-end refinement programme (BETA-068–087)

Approved by the project owner on 2026-08-29 after inspecting the populated
public portal and operator console at desktop and 390px widths. These are
persistent, selected IDs but are **not execution-queue entries yet**. The
owner explicitly discarded the proposed homepage hierarchy, public download
centre and terminology/methodology layer. Do not reintroduce those ideas under
different names without new direction.

The programme must retain the settled architecture: stdlib HTTP server,
vanilla JavaScript, no build step, local/offline assets, SQLite/PostgreSQL
parity, existing hash-route bookmarks, no public writes, no authentication
change, and no inferred evidence, composite scoring, automatic matching,
promotion or review decision.

#### BETA-068 | Release compatibility and graceful degradation

- priority: P1
- impact: 5
- effort: 3
- confidence: 5
- risk: 2
- area: public/admin reliability
- depends_on: BETA-039, BETA-063
- objective: Check the build's required schema, tables, extensions and routes
  before rendering each capability; replace raw database/traceback text with a
  feature-specific unavailable state carrying retry, build/schema identity and
  a safe operator diagnostic reference.
- rationale: Live review exposed schema drift as raw PostgreSQL errors on the
  document-search and run-ledger surfaces. A partial deployment should degrade
  by feature rather than making internal SQL part of the user interface.
- suggested_first_action: Define a stable additive error envelope
  `{error: {code, message, retryable, feature, build, schema}}` and fixtures for
  missing migration, missing extension, timeout and partial-section failure.

#### BETA-069 | Rebuild the mobile public header

- priority: P1
- impact: 5
- effort: 3
- confidence: 5
- risk: 1
- area: public/responsive shell
- depends_on: BETA-049
- objective: At phone widths show only brand, menu and search; move council
  lookup, navigation and theme selection into the drawer; remove clipping,
  horizontal overflow and the duplicated campaign-lens label.
- rationale: At 390px the current council field is clipped beyond the viewport
  and the page repeats its lens before the hero. This is a first-screen defect,
  not a cosmetic preference.
- suggested_first_action: Pin the 390x844, 768x1024 and desktop header layouts
  in browser tests before changing the shared shell.

#### BETA-070 | Workforce pay explorer

- priority: P1
- impact: 5
- effort: 4
- confidence: 4
- risk: 3
- area: public/workforce
- depends_on: BETA-043, BETA-049
- objective: Create one focused interface for salary bands, statutory
  benchmarks, workforce census measures, provider pay pages, job adverts,
  gender-pay-gap filings and Living Wage evidence, filtered by role, provider,
  source, year and pay unit.
- rationale: The project now holds several complementary pay layers, but the
  reader must discover them page by page. The explorer should expose their
  combined breadth while keeping unlike populations and units separate.
- suggested_first_action: Inventory the exact fields, units, coverage and
  caveats of each pay source and define explicit source-group panels before
  composing any cross-source screen.

#### BETA-071 | Responsive public data tables

- priority: P1
- impact: 5
- effort: 4
- confidence: 4
- risk: 2
- area: public/tables
- depends_on: BETA-049, BETA-080
- objective: Give every public table a mobile card mode, priority columns,
  column chooser, density control, sticky identifiers and explicit full-table
  mode while retaining complete accessible tabular data and exports.
- rationale: The portal's evidence is table-heavy; horizontal scrolling is
  necessary for full fidelity but should not be the default reading experience
  on a phone.
- suggested_first_action: Extend the shared table component with declarative
  priority metadata, then migrate one narrow and one very wide table as the
  contract tests.

#### BETA-072 | Consistent filters and URL-restored query state

- priority: P1
- impact: 5
- effort: 3
- confidence: 5
- risk: 2
- area: public/filtering
- depends_on: BETA-024, BETA-049
- objective: Standardise filter bars with active chips, result counts,
  clear-all, basic/advanced disclosure, validation and hash-query persistence;
  browser history and shared URLs must restore the exact query.
- rationale: Filters currently vary by page and lose context unevenly during
  navigation. Evidence views should be reproducible by URL.
- suggested_first_action: Define one typed filter-state serializer and migrate
  providers, treatment and contracts before applying it portal-wide.

#### BETA-073 | My area context

- priority: P1
- impact: 5
- effort: 4
- confidence: 4
- risk: 2
- area: public/local evidence
- depends_on: BETA-017, BETA-043, BETA-044
- objective: Let a reader choose and locally retain one council without an
  account, then present its funding, treatment, contracts, providers,
  relationships, homelessness comparators, coverage and freshness through
  links to the underlying evidence.
- rationale: "Find your council" currently navigates once; it does not turn
  the England-wide corpus into a durable local starting point.
- suggested_first_action: Define the minimum local summary exclusively from
  existing authority/public routes, with localStorage containing only the ONS
  code and no personal data.

#### BETA-074 | Inspectable visualisations

- priority: P2
- impact: 4
- effort: 3
- confidence: 5
- risk: 2
- area: public/charts
- depends_on: BETA-020, BETA-049, BETA-080
- objective: Standardise keyboard-accessible legends, series toggles, value
  tooltips, appropriate zoom/reset, caveat and missing-period annotations,
  image saving and direct movement between each chart and its accessible table.
- rationale: Charts already have table parity, but interaction and explanatory
  affordances differ by page.
- suggested_first_action: Extend the shared chart wrapper and prove the
  contract on time-series, bar and map-backed views.

#### BETA-075 | Treatment metric explorer

- priority: P1
- impact: 5
- effort: 4
- confidence: 4
- risk: 3
- area: public/treatment
- depends_on: BETA-043, BETA-049, BETA-072
- objective: Reframe treatment data around a searchable metric catalogue that
  exposes definitions, units, confidence intervals, periods, publication
  coverage, authority/region views and provenance before drawing a chart.
- rationale: Selecting a technically named indicator is currently the entry
  price to understanding the treatment page. Metric meaning and availability
  should precede visualisation.
- suggested_first_action: Build the metric metadata model from existing
  endpoint fields and catalogue records; preserve missing periods as missing,
  never zero or interpolated.

#### BETA-076 | Navigable provider and authority workbenches

- priority: P1
- impact: 5
- effort: 4
- confidence: 5
- risk: 2
- area: public/entity detail
- depends_on: BETA-017, BETA-045, BETA-065, BETA-066
- objective: Add sticky section indexes, counts, deep-link anchors,
  progressive disclosure, section search and back-to-top controls; paginate or
  collapse large collections while preserving complete exports.
- rationale: The populated Change Grow Live profile contains hundreds of
  records across many evidence types, making the page powerful but difficult
  to navigate as one continuous document.
- suggested_first_action: Define stable section IDs and availability/count
  metadata, then refactor provider CQC and filing sections before authorities.

#### BETA-077 | Navigation continuity

- priority: P2
- impact: 4
- effort: 3
- confidence: 5
- risk: 1
- area: public/navigation
- depends_on: BETA-024, BETA-072, BETA-076
- objective: Add route-aware breadcrumbs, locally stored recent entities,
  scroll restoration, meaningful back links and preservation of the
  originating search/filter context around detail pages.
- rationale: Deep evidence pages should behave like a research workspace, not
  reset the reader's place each time an entity is opened.
- suggested_first_action: Specify history and scroll semantics for list →
  detail → back, then apply them through the central router.

#### BETA-078 | Unified evidence atlas

- priority: P1
- impact: 5
- effort: 5
- confidence: 4
- risk: 4
- area: public/geography
- depends_on: BETA-028, BETA-043, BETA-065, BETA-072
- objective: Combine existing geography, CQC, commissioning, funding,
  treatment and coverage maps behind a layer switcher with a synchronised
  accessible table.
- rationale: The project has several geographic capabilities but no single
  place to discover them. The atlas exposes breadth without flattening unlike
  evidence into one score.
- suggested_first_action: Define a closed layer registry with endpoint,
  legend, units, caveat, geometry key and table columns; render only one
  evidence layer at a time and forbid composite scoring.

#### BETA-079 | Safety and legal evidence hub

- priority: P1
- impact: 5
- effort: 4
- confidence: 4
- risk: 4
- area: public/safety-legal
- depends_on: BETA-043, BETA-051, BETA-065
- objective: Bring PFD reports, safeguarding reviews, HSE notices, CQC
  inspections and tribunal evidence into a filterable chronology with
  source-specific caveats and sensitive-content treatment.
- rationale: These sources answer related accountability questions but encode
  materially different relationships and standards.
- suggested_first_action: Define distinct visual and data labels for
  "addressed to", "named in", "matched to" and "regulated by"; never merge
  those counts or imply culpability from a mention.

#### BETA-080 | Shared responsive design system

- priority: P1
- impact: 4
- effort: 4
- confidence: 5
- risk: 2
- area: public/admin UI foundations
- depends_on: BETA-049
- objective: Consolidate spacing, typography, forms, buttons, cards,
  disclosures, statuses, skeletons, focus states and breakpoints into reusable
  primitives while preserving the two front ends' distinct identities.
- rationale: Both surfaces have grown incrementally; shared interaction
  contracts reduce drift and make the responsive programme tractable.
- suggested_first_action: Inventory existing CSS tokens/components and create
  a migration map; change primitives incrementally with visual/browser checks,
  not through a wholesale stylesheet rewrite.

#### BETA-081 | Document reading room

- priority: P1
- impact: 5
- effort: 5
- confidence: 4
- risk: 3
- area: public/documents
- depends_on: BETA-041, BETA-042, BETA-062, BETA-072
- objective: Open a search result in a split reading view containing the
  matched passage, surrounding text, document metadata, element/page
  navigation, linked evidence, provenance and stable passage links; returning
  restores search and scroll state.
- rationale: Search now finds and contextualises passages, but the reader
  still lacks a coherent environment for examining the document around them.
- suggested_first_action: Pin stable document/element identifiers and passage
  anchors across SQLite and PostgreSQL before building the split layout.

#### BETA-082 | Pipeline mission control

- priority: P1
- impact: 5
- effort: 5
- confidence: 4
- risk: 4
- area: admin/operations
- depends_on: BETA-058, BETA-063, BETA-080, BETA-085
- objective: Present dependency waves, active/queued/completed states,
  progress, durable history, failure summaries, freshness consequences and a
  focused log viewer while retaining the existing run safeguards and polling.
- rationale: Modules, browser jobs and durable ledger data now exist, but the
  operator must mentally join them into one run state.
- suggested_first_action: Define one read model over module registry, active
  job and run ledger; do not add cancellation, SSE, WebSockets or new write
  semantics.

#### BETA-083 | Schema-aware data explorer

- priority: P2
- impact: 4
- effort: 4
- confidence: 4
- risk: 3
- area: admin/data
- depends_on: BETA-048, BETA-080, BETA-085
- objective: Add schema search, table descriptions, column metadata,
  foreign-key navigation, saved read-only queries, pinned columns, JSON
  inspection and links between related records to Database and SQL.
- rationale: The warehouse has 100+ objects; raw table names and cells no
  longer provide enough orientation for safe inspection.
- suggested_first_action: Generate a read-only schema graph from existing
  metadata routes; retain restricted-table confirmation, timeout and row caps.

#### BETA-084 | Page-level evidence health strip

- priority: P1
- impact: 5
- effort: 3
- confidence: 5
- risk: 2
- area: public/trust
- depends_on: BETA-039, BETA-043, BETA-059, BETA-080
- objective: Standardise scope, verification state, latest retrieval,
  coverage completeness, licence and known limitations at the top of every
  public evidence page.
- rationale: The data exists in catalogue, freshness and page payloads, but
  readers should not have to hunt for whether a page is current or partial.
- suggested_first_action: Define one evidence-health view model with explicit
  unknown/not-collected states and links to the authoritative catalogue and
  coverage records.

#### BETA-085 | Responsive admin navigation

- priority: P1
- impact: 5
- effort: 4
- confidence: 5
- risk: 2
- area: admin/navigation
- depends_on: BETA-049, BETA-080
- objective: Replace twelve horizontal tabs with a grouped sidebar — Review,
  Evidence, Operations, Data and System — using a narrow-screen drawer while
  retaining Ctrl-K, badges and existing deep links.
- rationale: The desktop header is crowded and the 390px view requires page-
  level horizontal scrolling before work begins.
- suggested_first_action: Define the exact old-tab → group/destination map and
  make the router accept both old and new links before changing presentation.

#### BETA-086 | Operator action cockpit

- priority: P1
- impact: 5
- effort: 4
- confidence: 4
- risk: 3
- area: admin/overview
- depends_on: BETA-058, BETA-059, BETA-060, BETA-063, BETA-068, BETA-085
- objective: Replace long overview tables with prioritised cards for review
  pressure, failed/stale runs, blocked sources, coverage actions, archive
  health, schema drift and resumable work; every card opens a pre-filtered
  existing workflow.
- rationale: The current overview reports volume but does not answer the
  operator's first question: what needs attention now?
- suggested_first_action: Add a read-only `/api/admin/cockpit` aggregate with
  deterministic priority reasons; the UI may rank operational states, never
  evidence quality or review outcomes.

#### BETA-087 | Split-pane review workspace

- priority: P1
- impact: 5
- effort: 5
- confidence: 4
- risk: 4
- area: admin/review
- depends_on: BETA-052, BETA-054, BETA-055, BETA-080, BETA-085
- objective: Display the queue on the left and typed context, source preview,
  alternatives, history and decision controls on the right; preserve keyboard
  operation and scroll position, with a stacked narrow-screen layout.
- rationale: Existing context and sidecars are powerful but still rendered as
  long rows. Persistent evidence beside the decision should reduce navigation
  without changing the judgement boundary.
- suggested_first_action: Refactor presentation around the existing single-
  item APIs and keep named reviewer, explicit decision and one-candidate-at-a-
  time safeguards unchanged.

**Interface and compatibility contract:** Add only backward-compatible public
metadata/filter parameters and the BETA-068 error fields; existing response
defaults remain valid. Hash-query state owns filters, map layers, selected
metrics, workbench sections and document passages. The only planned new
aggregate is read-only `/api/admin/cockpit`; run and review writes continue to
use their existing routes and guards.

**Acceptance contract:** Exercise principal routes at 1440x900, 768x1024 and
390x844 with no unintended viewport overflow; verify keyboard navigation,
focus restoration, contrast, reduced motion, chart/table parity, drawers,
split panes and print output; verify deep links restore filters, metrics,
layers, sections, passages and scroll; and test missing migrations, unavailable
extensions, partial failures, timeouts, empty datasets and offline operation.
Pay, treatment, safety and geographic layers must remain separate wherever
their units, populations or meanings are not comparable.

**Delivery sequence:** On explicit implementation start, promote BETA-068 to
IN_PROGRESS and BETA-069–072 to NEXT. Wave 2 is BETA-073–077, Wave 3 is
BETA-078–081, and Wave 4 is BETA-082–087. BETA-080 is a dependency for several
later UI items but must be incremental, not a blocking rewrite. Maintain one
IN_PROGRESS item and no more than five NEXT items.

### Second approved front-end refinement programme (BETA-088–106)

Approved by the project owner on 2026-08-29 after auditing the first refinement
round and completing three explicit selection passes. These nineteen IDs are
persistent, approved backlog items but are **not execution-queue entries**.
BETA-068–087 remains the next programme. The proposed explicit-reference
network and all ideas discarded from the first round remain excluded.

This programme inherits the existing architecture and evidence boundaries. It
adds no public account or write path. Personal research state stays local and
exportable. Change, discrepancy, co-occurrence, path and quality-control views
must expose their deterministic basis and must not infer identity, causation,
culpability, evidence quality or reviewer performance.

#### BETA-088 | Evidence notebook

- priority: P1
- impact: 5
- effort: 4
- confidence: 4
- risk: 2
- area: public/research workspace
- depends_on: BETA-072, BETA-077, BETA-080
- objective: Let readers pin records, passages, charts, providers and
  authorities into named, reorderable local collections with private notes and
  lossless JSON import/export.
- rationale: The portal supports discovery and sharing but not sustained
  collection of evidence across routes; an account system is unnecessary for
  a useful single-browser workspace.
- suggested_first_action: Define a versioned, size-bounded local collection
  schema using stable public identifiers and explicit missing-item states.

#### BETA-089 | Saved searches and change alerts

- priority: P1
- impact: 5
- effort: 4
- confidence: 4
- risk: 3
- area: public/search and monitoring
- depends_on: BETA-072, BETA-090
- objective: Save complete searches locally, show new-match counts after a
  later release and provide stable Atom feeds for external subscription.
- rationale: Repeat researchers should not need to reconstruct queries or
  manually rescan unchanged result sets; local state and feeds avoid accounts
  and email infrastructure.
- suggested_first_action: Specify canonical query fingerprints, release
  cursors and an additive read-only feed endpoint with explicit retention.

#### BETA-090 | “What changed?” evidence feed

- priority: P1
- impact: 5
- effort: 5
- confidence: 4
- risk: 4
- area: public/change awareness
- depends_on: BETA-058, BETA-068, BETA-084
- objective: Publish a filterable chronology of evidence added, changed,
  withdrawn, superseded or newly verified by source, provider, authority,
  evidence type and release.
- rationale: Current pages show the latest warehouse state but do not reveal
  what changed between collections or decisions.
- suggested_first_action: Define an append-only change-event model that
  distinguishes source changes, parser changes and human-review changes.

#### BETA-091 | Source publication calendar

- priority: P2
- impact: 4
- effort: 3
- confidence: 4
- risk: 2
- area: public/source coverage
- depends_on: BETA-043, BETA-059, BETA-084
- objective: Show each source's stated or observed release cadence, last
  publication, next expected window and overdue/unknown status.
- rationale: A publisher not releasing data and SectorTrace not collecting it
  are different conditions that freshness alone cannot explain.
- suggested_first_action: Add nullable cadence and expectation metadata to the
  dataset catalogue, labelling observed estimates separately from stated dates.

#### BETA-092 | Record revision comparison

- priority: P1
- impact: 5
- effort: 5
- confidence: 4
- risk: 3
- area: public/version inspection
- depends_on: BETA-050, BETA-060, BETA-081, BETA-090
- objective: Compare successive procurement notices, documents, provider
  records and regulatory entries with field-aware and text-aware diffs.
- rationale: Readers need to distinguish a source amendment from parser or
  normalisation changes rather than treating the latest row as timeless.
- suggested_first_action: Prove stable version identity and before/after
  fixtures for one OCDS record and one parsed document on both databases.

#### BETA-093 | Relationship pathfinder

- priority: P1
- impact: 5
- effort: 4
- confidence: 4
- risk: 4
- area: public/relationships
- depends_on: BETA-010, BETA-044, BETA-076, BETA-080
- objective: Find and explain the shortest verified path between two selected
  entities through source-backed graph edges.
- rationale: Neighbourhood views answer what surrounds one entity but not how
  two known entities are connected.
- suggested_first_action: Define permitted edge types, deterministic tie
  breaking, path limits and a table equivalent; exclude extracted or
  analytical edges that have not passed their existing review gates.

#### BETA-094 | Visual research journey

- priority: P2
- impact: 4
- effort: 3
- confidence: 4
- risk: 2
- area: public/research continuity
- depends_on: BETA-072, BETA-077, BETA-088
- objective: Render the current local session as a branching trail of
  searches, entities, documents and comparisons with named checkpoints.
- rationale: Browser back history is linear and does not preserve the branches
  a researcher follows while testing different evidence paths.
- suggested_first_action: Define a bounded local event model that records only
  SectorTrace route state, supports selective deletion and exports with the
  notebook without server telemetry.

#### BETA-095 | Entity co-occurrence explorer

- priority: P1
- impact: 5
- effort: 4
- confidence: 4
- risk: 4
- area: public/documents
- depends_on: BETA-041, BETA-042, BETA-081
- objective: Find documents or notices in which two or more selected tracked
  entities occur together and expose each exact passage or structured field.
- rationale: Co-occurrence can locate relevant source material without
  asserting that the entities have a relationship.
- suggested_first_action: Restrict v1 to verified entity aliases and same-
  record co-occurrence, with fixtures that prevent cross-document joining and
  labels that explicitly deny inferred relationships.

#### BETA-096 | Evidence discrepancy explorer

- priority: P1
- impact: 5
- effort: 5
- confidence: 3
- risk: 4
- area: public/evidence comparison
- depends_on: BETA-043, BETA-070, BETA-075, BETA-076
- objective: Surface different values, dates, names or statuses reported by
  public sources for the same verified entity, field and compatible period.
- rationale: Disagreement between sources is material evidence context, but it
  must not be silently resolved or automatically labelled an error.
- suggested_first_action: Define a closed registry of comparable field pairs,
  equality/normalisation rules and fixtures for legitimate semantic difference.

#### BETA-097 | Temporal coverage navigator

- priority: P2
- impact: 4
- effort: 3
- confidence: 5
- risk: 2
- area: public/navigation and coverage
- depends_on: BETA-043, BETA-075, BETA-076, BETA-084
- objective: Show exactly which periods each source holds for a selected
  provider, authority or metric and link every available period to its view.
- rationale: Readers currently discover gaps only after opening sections or
  selectors; absence must remain distinguishable from a published zero.
- suggested_first_action: Define a shared coverage-interval response with
  available, suppressed, not-collected and unknown states.

#### BETA-098 | Contract diary and milestone calendar

- priority: P1
- impact: 5
- effort: 4
- confidence: 4
- risk: 3
- area: public/procurement
- depends_on: BETA-050, BETA-072, BETA-076
- objective: Present published tender dates, awards, contract periods,
  amendments, milestones, expected expiries and performance events in calendar
  and accessible agenda views.
- rationale: Lifecycle records are easier to monitor as dated events than as
  disconnected notice rows, provided no renewal or completion is predicted.
- suggested_first_action: Map only explicit OCDS and source dates into typed
  events, preserving unknown dates and extension caveats.

#### BETA-099 | Document table extraction viewer

- priority: P1
- impact: 5
- effort: 5
- confidence: 3
- risk: 4
- area: public/documents
- depends_on: BETA-042, BETA-081
- objective: Display tables detected in parsed documents with page context,
  original structure, extraction status and a structured download.
- rationale: Important evidence often sits in tables that paragraph search and
  plain-text snippets make difficult to inspect accurately.
- suggested_first_action: Audit the current Docling element payloads and build
  fixtures for merged cells, repeated headers, OCR tables and extraction
  failure before defining a public table shape.

#### BETA-100 | Source-link resilience checker

- priority: P1
- impact: 5
- effort: 4
- confidence: 4
- risk: 3
- area: public/provenance
- depends_on: BETA-060, BETA-081, BETA-084
- objective: Show whether an original source URL is live, redirected, changed
  or unavailable and whether a checksum-verified archive copy is held.
- rationale: A citation should remain inspectable when publishers move or
  remove files, without presenting the archive as the current publisher page.
- suggested_first_action: Define conservative link states from collection-time
  observations and archive references; do not probe external URLs on page load.

#### BETA-101 | Run-to-run output comparison

- priority: P1
- impact: 5
- effort: 4
- confidence: 4
- risk: 3
- area: admin/operations
- depends_on: BETA-058, BETA-082, BETA-085
- objective: Compare two pipeline runs by modules, rows added/changed/removed,
  failures, review items, coverage, durations and freshness effects.
- rationale: A durable ledger explains each run independently but not why two
  runs produced materially different warehouse outcomes.
- suggested_first_action: Define immutable per-module comparison summaries;
  retain drill-down links to existing records and logs rather than duplicating
  full payloads.

#### BETA-102 | Interactive pipeline and data-lineage map

- priority: P1
- impact: 5
- effort: 5
- confidence: 4
- risk: 3
- area: admin/system understanding
- depends_on: BETA-043, BETA-058, BETA-067, BETA-082, BETA-083, BETA-085
- objective: Map modules, sources, archives, tables, entity links, APIs,
  exports and public pages as searchable dependencies with health and consumer
  details.
- rationale: The expanded system is difficult to reason about from separate
  registries even though most dependency metadata already exists.
- suggested_first_action: Generate a read-only typed graph from machine-owned
  registries and migrations; forbid hand-maintained edges where a registry can
  be authoritative.

#### BETA-103 | Parser replay sandbox

- priority: P2
- impact: 4
- effort: 5
- confidence: 3
- risk: 4
- area: admin/document diagnostics
- depends_on: BETA-060, BETA-082, BETA-085, BETA-087
- objective: Replay one parser against one archived object and compare its
  non-persisted proposed output with the stored normalised output and warnings.
- rationale: Diagnosing extraction changes currently requires CLI context and
  risks confusing a test run with a committed warehouse change.
- suggested_first_action: Create an isolated read-only replay contract with
  strict time, memory and output limits and no promotion or database-write path.

#### BETA-104 | Validation-rule explorer

- priority: P2
- impact: 4
- effort: 4
- confidence: 4
- risk: 2
- area: admin/data quality
- depends_on: BETA-059, BETA-060, BETA-067, BETA-082, BETA-085
- objective: Catalogue validation rules with purpose, affected modules and
  fields, recent pass/failure counts and protected representative failures.
- rationale: Validation outcomes are visible in scattered logs and worklists,
  but operators cannot see the active rule set or recurring failure shape.
- suggested_first_action: Add stable rule IDs and a read-only registry; redact
  restricted values before any failure example reaches the browser.

#### BETA-105 | Review-outcome analytics

- priority: P2
- impact: 4
- effort: 4
- confidence: 4
- risk: 3
- area: admin/review operations
- depends_on: BETA-052, BETA-053, BETA-055, BETA-087
- objective: Show review decisions over time by source, item type, reason code
  and evidence age without scoring or ranking reviewers.
- rationale: Aggregate outcomes can reveal recurring source and workflow
  problems while individual productivity metrics would distort careful review.
- suggested_first_action: Define minimum aggregate group sizes and omit named
  reviewer dimensions from the analytics endpoint and UI.

#### BETA-106 | Quality-control sampling workspace

- priority: P1
- impact: 5
- effort: 5
- confidence: 3
- risk: 4
- area: admin/review quality
- depends_on: BETA-052, BETA-055, BETA-087
- objective: Generate reproducible random or stratified samples of previously
  decided records for append-only second-look findings.
- rationale: Review audit history records what happened but provides no focused
  interface for checking a defensible sample after the fact.
- suggested_first_action: Define seeded sampling, sample manifests and a new
  append-only quality-control finding that never edits or silently supersedes
  the original decision.

**Interface and compatibility contract:** Implementation may add only additive
read-only public routes for change events, feeds, publication expectations,
versions/diffs, paths, co-occurrences, discrepancies, coverage intervals,
calendar events, document tables and source-link states. Local notebook,
saved-search and journey formats are versioned, size-bounded and contain no
server-side personal profile. Admin comparison, lineage, replay, validation,
analytics and sampling routes retain the existing admin boundary. Parser replay
cannot persist. Quality-control findings are append-only and cannot mutate an
original review decision.

**Acceptance contract:** Verify stable identifiers and equivalent SQLite/
PostgreSQL results; deterministic change classification, paths, comparison and
sampling; honest unavailable/unknown/suppressed states; no cross-document
co-occurrence; no automatic discrepancy resolution; no reviewer ranking; no
external link probes during page rendering; import/export round trips for local
research state; keyboard, mobile, print and reduced-motion behaviour inherited
from BETA-049/BETA-080; and safe empty, stale, partial and pre-migration states.

**Delivery sequence:** Do not promote this programme while BETA-068–087 remains
approved and unfinished unless the owner explicitly reprioritises it. After the
first programme, start with the change/operations foundations BETA-090,
BETA-091, BETA-101, BETA-102 and BETA-104. Wave 2 is BETA-088, BETA-089,
BETA-092, BETA-093 and BETA-097. Wave 3 is BETA-094–096, BETA-098 and BETA-100.
Wave 4 is BETA-099, BETA-103, BETA-105 and BETA-106. Maintain exactly one
IN_PROGRESS item and no more than five NEXT items.

### Approved local analyst-assistant programme (BETA-107–113)

Approved by the project owner on 2026-08-29 after repository inspection and
current-product research. These seven IDs are persistent, approved backlog
items but are **not execution-queue entries**. They follow BETA-068–106 and do
not displace either approved front-end programme.

The approved design adds two optional local models alongside, not instead of,
`pipeline/nlp`. Needle 2 is the small, confidence-gated router over a closed
read-only tool catalogue; `LiquidAI/LFM2.5-1.2B-Instruct` is the answer and
summarisation model over passages and status payloads returned by those tools.
Existing chunking, `all-MiniLM-L6-v2` embeddings, pgvector, ontology labels,
GLiNER, assertion context and human claim review remain authoritative.

This programme is the named decision BETA-034 required before any RAG/LLM
work, but only for an **operator finding aid**. It does not authorise model-
generated claims, automated review decisions, writes to `graph_claims`, public
answers, collection-time model calls or a paid/cloud AI dependency. SetFit and
claim publication remain blocked by `pipeline nlp gate-034g`.

#### BETA-107 | Optional Needle 2 and LFM assistant runtimes

- priority: P1
- impact: 5
- effort: 4
- confidence: 4
- risk: 3
- area: nlp/assistant/runtime
- depends_on: BETA-034 (implemented retrieval foundation), BETA-046
- objective: Add an `assistant` optional dependency/runtime boundary with a
  pinned Needle 2 adapter and an OpenAI-compatible local Ollama adapter for
  pinned `LiquidAI/LFM2.5-1.2B-Instruct` Q4_K_M; both disabled by default,
  excluded from Railway and loaded lazily on the local analysis host.
- rationale: Needle's bounded router and LFM's 32K-context synthesis can add a
  natural-language operator layer without enlarging collection processes or
  replacing the existing NLP stack.
- acceptance: A checkout without the extra, model files or Ollama starts and
  passes the offline suite unchanged; enabling the feature reports exact
  model/runtime versions and artifact hashes; missing or unhealthy runtimes
  fail with a bounded operator-facing unavailable state, never a web crash.
- next_action: Define settings, adapter protocols, health checks, fixed model
  identities, local-only defaults and telemetry opt-out before installing any
  runtime package.

#### BETA-108 | Assistant provenance and run ledger

- priority: P1
- impact: 5
- effort: 3
- confidence: 5
- risk: 2
- area: nlp/assistant/provenance
- depends_on: BETA-058, BETA-107
- objective: Add equivalent SQLite/PostgreSQL storage for one immutable
  assistant run: request and filters, Needle/LFM identities, prompt-template
  hashes, routing confidence and validated arguments, retrieved chunk IDs,
  answer and citation IDs, timings, outcome and error class.
- rationale: Model names are not reproducible identities, and an analyst must
  be able to reconstruct which stored evidence and configuration produced an
  answer without storing unrestricted hidden model state.
- acceptance: Successful, abstained, clarified, timed-out and failed runs are
  recorded without secrets or model files; citation and chunk references are
  auditable; migration equivalence and fallback pre-migration behaviour are
  tested; no ledger row is treated as evidence or a review decision.
- next_action: Specify the minimum append-only schema and redaction rules,
  reusing the BETA-058 run identity where it fits without copying full logs.

#### BETA-109 | Public-safe read-only analyst tool catalogue

- priority: P1
- impact: 5
- effort: 3
- confidence: 5
- risk: 2
- area: nlp/assistant/tools
- depends_on: BETA-046, BETA-059, BETA-084, BETA-107
- objective: Expose exactly five typed in-process tools to the router:
  `search_document_passages`, `inspect_claim_candidates`,
  `inspect_claim_gate`, `inspect_source_coverage` and `inspect_freshness`.
  Each wraps existing query code and accepts only documented, bounded filters.
- rationale: A closed catalogue gives analysts one language front door while
  retaining the database's existing read-only, caveated and provenance-rich
  views instead of teaching a model arbitrary SQL or HTTP access.
- acceptance: Every tool is side-effect free, source/date/result limits are
  validated, output contains only public-corpus or non-sensitive aggregate
  data, restricted tables and internal annotations are unreachable, and
  SQLite/PostgreSQL fixtures return the same contract.
- next_action: Define JSON schemas and adapters over existing query functions;
  reject arbitrary table names, URLs, SQL, filesystem paths and write verbs.

#### BETA-110 | Needle routing and confidence gate

- priority: P1
- impact: 5
- effort: 4
- confidence: 4
- risk: 3
- area: nlp/assistant/routing
- depends_on: BETA-107, BETA-109
- objective: Route a single analyst question to at most one allowlisted tool
  using Needle 2's schema-constrained output and calibrated confidence head;
  validate the returned name and arguments independently before execution.
- rationale: Needle's small local footprint, built-in tool retrieval and
  confidence signal make it a better bounded dispatcher than spending LFM
  context on the whole tool catalogue, provided SectorTrace's own evaluation
  determines the execution threshold.
- acceptance: Below-threshold, ambiguous, out-of-scope and invalid calls return
  a clarification without tool execution; above-threshold calls conform to a
  closed schema; timeouts fail closed; telemetry is disabled; no document text
  is shown to Needle, preventing retrieved prompt injection from changing the
  selected action.
- next_action: Create a development routing set, tune the threshold there and
  freeze it before scoring the held-out BETA-113 suite.

#### BETA-111 | LFM grounded answers and citation validation

- priority: P1
- impact: 5
- effort: 5
- confidence: 3
- risk: 4
- area: nlp/assistant/grounding
- depends_on: BETA-107–110
- objective: Give LFM only the validated tool result and produce a concise
  answer whose factual statements cite result-local identifiers; return an
  explicit abstention when the supplied evidence is insufficient.
- rationale: LFM can summarise and connect retrieved passages locally, but its
  prose must remain a reading aid: stored SectorTrace provenance, not model
  fluency, determines what can be displayed as supported.
- acceptance: The model receives no executable tools; retrieved text is
  delimited as untrusted data; generated citation IDs are checked against the
  result set; unresolved citations or grounding-check failures suppress the
  answer; every displayed citation resolves to chunk, document, page, source
  URL, retrieval time and archived payload provenance.
- next_action: Define the fixed system prompt, result envelope, abstention
  shape and deterministic post-generation citation/grounding checks before
  tuning answer style.

#### BETA-112 | Single-turn assistant API and CLI

- priority: P1
- impact: 5
- effort: 4
- confidence: 4
- risk: 3
- area: admin/assistant
- depends_on: BETA-108–111
- objective: Add `POST /api/admin/assistant` and `pipeline nlp assistant` for
  one question plus optional source-system, publication-date and result-limit
  filters; return answer, citations, tool, model identities, timings, outcome
  and the existing finding-aid caveat.
- rationale: A single-turn operator contract is enough to test value and
  safety without prematurely introducing conversation storage, public access
  or autonomous multi-tool loops.
- acceptance: The route uses the existing admin-enabled and same-origin write
  guards, is absent when admin or assistant support is disabled, never appears
  under `/api/v1`, permits one read-only call only, applies a short router
  timeout and a 30-second overall timeout, and degrades to explicit
  unavailable/clarify/abstain states. The CLI returns the same domain payload.
- next_action: Build one orchestration service shared by HTTP and CLI; neither
  entry point may bypass schema, confidence, citation or provenance checks.

#### BETA-113 | Assistant evaluation and release gate

- priority: P1
- impact: 5
- effort: 5
- confidence: 4
- risk: 3
- area: nlp/assistant/evaluation
- depends_on: BETA-108–112
- objective: Add frozen routing, grounding, adversarial and performance suites
  plus operator documentation and a machine-readable gate controlling whether
  the experimental assistant may be enabled.
- rationale: Vendor benchmarks do not establish usefulness or safety on
  SectorTrace's vocabulary, evidence boundaries, hardware or source corpus;
  promotion must depend on representative local measurements.
- acceptance: At least 100 routing prompts cover all five tools, ambiguity,
  malformed filters, injection and forbidden actions; automatically executed
  routes achieve >=95% held-out precision with zero write/destructive calls.
  At least 50 human-authored analyst questions test answer correctness,
  citation entailment/resolution, unsupported claims and abstention. Every
  displayed factual statement is supported, every citation resolves and zero
  evidence IDs are invented. Record p50/p95 latency, peak RAM and timeout rate
  on the target local host; adversarial retrieved instructions cannot affect
  routing or execution.
- next_action: Freeze fixtures and scoring rubrics before any fine-tuning or
  threshold adjustment; keep the feature experimental and disabled until the
  gate passes.

**Interface and compatibility contract:** The only new web interface is the
admin-only single-turn POST route; `/api/v1`, public search, exports,
collectors, review decisions and graph writes are unchanged. The assistant
accepts `question`, optional `source_system`, `date_from`, `date_to` and a
bounded `limit`; it returns `outcome`, optional `answer`, citations, selected
tool, model identities, timings, caveat and run ID. All additions are optional
and backward compatible.

**Data, deployment and licence contract:** Only already-public document text
and non-sensitive aggregates may enter either model. Processing remains local;
Needle telemetry is disabled and no cloud fallback is permitted. Model weights
and Ollama are not installed in the Railway image. Pin artifacts and retain
required notices. Liquid's LFM Open License permits free commercial use only
while annual revenue remains below USD 10 million; crossing that threshold
requires a commercial licence. Recheck the licence before each model upgrade.

**Deferred by design:** LFM embedding and ColBERT models do not replace the
current 384-dimensional pgvector path in this programme; they require a
separate retrieval benchmark and migration decision. LFM/Needle extraction,
classification, multi-turn memory, autonomous tool loops and public assistant
access are also out of scope and require separate named decisions and gates.

**Delivery sequence:** Do not promote BETA-107–113 until BETA-068–106 is
complete unless the owner explicitly reprioritises it. Then deliver BETA-107,
followed by BETA-108 and BETA-109, then BETA-110, BETA-111, BETA-112 and
BETA-113. Maintain exactly one IN_PROGRESS item and no more than five NEXT
items; do not enable the feature merely because BETA-112 is code-complete.

## Features Under Investigation

BETA-006 remains RESEARCH-only and must not restart without new operational
scheduling information. BETA-034's remaining model work is BLOCKED, not an
open-ended investigation; its SetFit/claim resumption condition is the explicit
gate. BETA-107–113 is a separately bounded, approved finding-aid programme.

## Implemented Features

See the authoritative DONE queue above. The most recent completed additions
are BETA-067 (capability-documentation consistency), BETA-066 (provider
lineage), BETA-065 (CQC regulated-location explorer), BETA-064 (temporary-
accommodation B&B measures), BETA-063 (PostgreSQL capability gate) and
BETA-062 (human-readable document titles). BETA-068–113 are approved plans,
not implemented features.

## Dataset Additions

**BETA-016: Module 31, temporary accommodation (H-CLIC, MHCLG)** —
BETA-015's own flagged follow-up, built this cycle. Table TA1 from the same
quarterly workbook Module 30 reads, sharing that module's discovery/file-
reading code by direct import. See its DONE entry for the full research,
including two real bugs found and fixed (a regex word-boundary bug, and a
real edition's misnamed `TA1_` sheet).

**BETA-015: Module 30, statutory homelessness (H-CLIC, MHCLG)** — BETA-014's
own flagged follow-up, built this cycle. Quarterly, LA-level, Table A1 only
(the flagship "households assessed / duty owed" count). See its DONE entry
for the full research, including a real parsing bug found and fixed
(covered-table-cell alignment), a region/England-code filtering fix m29's
own pattern would have gotten wrong on this source, and a documented
dual-meaning finding in one field across the series' two table layouts.

**BETA-014: Module 29, rough sleeping snapshot (MHCLG)** — requested
directly by the project owner as a local-authority-level comparator against
the sector's own substance-misuse evidence, given the documented overlap
between the two populations. Annual, 2010-to-current, one evergreen source.
See its DONE entry for the full research (homelessness H-CLIC confirmed
viable but not built this cycle; crime data researched and deliberately not
built — flagged in Questions Requiring Human Input instead).

Earlier in the session (before this request): no new dataset was proposed
autonomously, on the reasoning that this project's existing modules and the
roadmap's own "Rejected"/"Open questions" already covered the obvious
candidates and inventing one without a specific need would be speculative.
That reasoning held until asked directly — this entry is the difference
between inventing a dataset and building one that was actually requested.

### Provider identifiers hand-verified (`9b3fe06`, `eb1799f`, 2026-08-27)

Project-owner-directed, out of queue. `pipeline/providers.py` (the
reference-config seed for `providers` / `provider_identifiers`) previously
carried exactly one verified identifier — CGL's charity number, from the
brief — with everything else left for Modules 3/4/5 to discover as
`'unverified'`. The owner asked for the details of all 13 tracked
providers to be researched and verified. Now seeded as `'verified'`:

- **Charity numbers** (E&W register) for the 8 comparators that are
  registered charities, and **company numbers** (Companies House,
  8-char form) for those 8 plus Delphi Medical Limited. Every number
  checked against the primary register itself, with the full
  previous-name history read so a rename could not be mistaken for a
  different legal entity.
- **CQC provider IDs** for all 10 distinct entities (including
  `inclusion` = Midlands Partnership University NHS FT, whose CQC id is
  its ODS trust code `RRE`), each checked against the provider's current
  page on cqc.org.uk.

Findings recorded in `PROVIDER_NOTES` and the module docstring:

- Three `provider_key`s are historical names of an entity that also has a
  current-name key — `addaction`→`with_you`, `humankind`→`waythrough`,
  `westminster_drug_project`→`via`. Identifiers live on the current key;
  the historical key stays a bare name variant so a notice bearing the
  old name still resolves to its own row.
- `richmond_fellowship` remains a separately registered charity/company
  but its **CQC** registration was archived 2024-06-04 (services moved to
  Waythrough). `delphi_medical` resolved by the owner to Delphi Medical
  Limited (`06944767` / CQC `1-2448282802`); the predecessor "Delphi
  Medical Consultants Limited" CQC registration was archived 2024-11-15.
- `inclusion` is a service brand of an NHS trust — no Companies House or
  Charity Commission registration.

**Behaviour change this locks in:** `m03` and `m04` seed from
`provider_identifiers`, so they now fetch and fully walk every seeded
entity (Companies House profile / officers / filings / PSC, charity
financials) rather than only what name-search and cross-references turn
up. `tests/test_m04_companies.py` and `tests/test_m04_viability.py` gained
a fixture that scopes which companies each `ch.run()` walks; the
`test_m20` `_add_company_number` helper became `INSERT OR IGNORE` (CGL's
company number is now a seeded row). Full offline suite after both
commits: **2469 passed, 106 skipped**, unchanged 2 pre-existing
`test_documents.py` failures (the corrupted `transformers` cache, see
BETA-007).

**Follow-up flagged:** a scan for substance-misuse providers still
missing from the tracked 13 — Cranstoun (charity 1061582), Changing Lives
(500640, a Collective Voice sponsor), The Alcohol & Drug Service / ADS
Hull (1108595), Spectrum Community Health CIC (07300133), and the
group/NHS-trust and merged-entity long tail. See Questions Requiring
Human Input.

### Provider set expanded to 21; lifecycle status on the portal (`fc97e66`, 2026-08-27)

Project-owner-directed follow-up to the two commits above ("add tiers
1-3", "where a provider has merged / dissolved / renamed make this clear
on the web UI"). Eight `provider_key`s added to
`keywords.SUPPLIER_NAME_VARIANTS` and `pipeline/providers.py`, with the
same hand-verification (primary registers + each provider's current CQC
page):

- **Active national peers:** `cranstoun` (charity 1061582, company
  03306337, CQC 1-101678209), `changing_lives` (500640 / 00995799 / CQC
  1-144519557 — registered as "The Cyrenians Ltd"; a Collective Voice
  member), `alcohol_and_drug_service` (ADS Hull — 1108595 / 05375809 /
  CQC 1-152340136), `spectrum_community_health` (CIC, company 07300133 /
  CQC 1-183173152).
- **Merged, still-registered:** `aquarius` (into the Waythrough group),
  `action_on_addiction` (into The Forward Trust, 2021 — corrected from
  the earlier assumption of With You), `swanswell` (into Cranstoun,
  2022).
- **Dissolved:** `lifeline_project` (administration 2017, company
  dissolved 25 Jan 2024; already an `m04_viability` fixture).

Name collisions checked and documented in `PROVIDER_NOTES`: the Hull ADS
vs Greater Manchester's "ADS (Addiction Dependency Solutions)" (charity
702559, dissolved 2026); "Changing Lives" the charity vs unrelated
"Changing Lives UK Quality Care Limited" at CQC.

Migration `0062` (see Database / Migration Changes) adds
`providers.status` + `providers.superseded_by`, seeded from a new
`PROVIDER_STATUS` map that also formalises the three renames already
tracked (`addaction`, `humankind`, `westminster_drug_project`) and
`richmond_fellowship`. `public_queries.providers()` and
`provider_timeline()` return the status and the successor's display name;
`js/pages/providers.js` renders a lifecycle badge in the provider heading
and a one-line note linking the successor, and a **Status** column in the
provider list ("MERGED → Waythrough"). Verified in a browser against the
running portal. Evidence is never re-pointed onto the successor key — the
note states this.

Full offline suite after the change: **2469 passed, 106 skipped**,
unchanged 2 pre-existing `test_documents.py` failures.

Still open (Questions Requiring Human Input #4): Tier 4, the NHS-trust
comparators beyond `inclusion`/MPFT (CNTW, RDaSH, GMMH, Surrey &
Borders, Humber) — a deliberate scope call, not taken.

### Second expansion — set now 28 (`b64ff10`, 2026-08-27)

Project-owner-directed follow-up ("add 1, 2 except The Nelson Trust, 3,
5"; "continue exploring"). Seven more `provider_key`s, same hand
verification:

- **Absorbed into the Humankind/Waythrough line:** `blenheim_cdp` (large
  London charity, charity 293959 / company 01694712 dissolved 2022 / CQC
  1-516591398; merged 2019) and `edp_drug_alcohol` (Devon/Dorset, charity
  297370 / company 02145656 / CQC 1-587977840; fully merged 1 Jul 2023).
  That line now swallows five prior identities — DISC, Blenheim, EDP,
  Richmond Fellowship, Aquarius — noted in the `waythrough` note and the
  module docstring.
- **Active independent peers:** `bristol_drugs_project` (291714 / 01902326
  / CQC 1-126776288; delivers Bristol ROADS), `developing_health_
  independence` ('DHI', 1078154 / 03830311 / CQC 1-927177975),
  `neca` (North East Council on Addictions, 516516 / 01828287 / CQC
  1-126776368).
- **Subsidiary:** `ley_community` (Oxford residential rehab, charity
  1074874 / company 03736193 / CQC 1-101610029; wholly-owned by Phoenix
  House → `phoenix_futures`).
- **For-profit prison healthcare:** `practice_plus_group` (Health in
  Justice arm, company 10498997 / CQC 1-3757899473; no charity).

Corrections made during verification: KCA merged into **Addaction** (not
CGL); NECA is **independent** (the earlier "merged into Humankind" was
Blenheim). No schema or portal change — 0062's columns and
`js/pages/providers.js` already handle the new merged keys. Full offline
suite: **2469 passed, 106 skipped**, unchanged 2 pre-existing failures.

Further exploration handed back to the project owner (see Questions
Requiring Human Input #4): NHS trusts (Tier 4, still open); `compass`
(York YP + adult charity, 518048 / 02054594); `kca` (Kent Council on
Addictions → `with_you`, historical); residential-rehab charities
(Broadway Lodge, Yeldall Manor, Kenward Trust, Bosence Farm, Trevi, The
Amber Foundation); recovery-support CICs (Emerging Futures, The Well
Communities); historical group brands (Recovery Focus → Waythrough line,
Blue Sky → Forward Trust).

### Third batch — set now 32 (`583476d`, 2026-08-27)

Compass, KCA, Blue Sky and Recovery Focus, from the further-exploration
list above:

- `compass` — active national charity (York, est. 1986; YP-specialist +
  adult substance misuse + wider health), charity 518048 / company
  02054594 / CQC 1-126775082 (CQC name 'Compass - Services To Improve
  Health And Wellbeing').
- `kca` — Kent Council on Addictions (registered 'Kent Council on
  Alcoholism', charity 270532 / company 01955497 'KCA (UK)'). Became a
  wholly-owned subsidiary of Addaction on 1 Jan 2015; company dissolved
  25 Apr 2017. `merged` → `with_you`.
- `blue_sky` — Blue Sky Development and Regeneration (ex-offender
  employment social enterprise, charity 1118372 / company 05639379).
  Merged into The Forward Trust 2017, now 'Blue Sky Services'; company
  dissolved 7 Feb 2023. `merged` → `forward_trust`.
- `recovery_focus` — **not a legal entity**: the group brand for Richmond
  Fellowship + Aquarius (and formerly DViP, 2Care, CAN, Croftlands Trust,
  My Time) from 2015 until the 2024 merger renamed the group 'Waythrough'.
  No registration of its own; seeded with no identifiers. `renamed` →
  `waythrough`. Appears on pre-2024 contracts and CQC quality accounts.

More verification corrections: NECA is independent (not merged into
Humankind — that was **Blenheim CDP**); Recovery Focus, not Aquarius, was
the pre-2024 group brand. `with_you` / `forward_trust` /
`richmond_fellowship` notes updated. No schema or portal change.

**How the reference data lands:** `seed_providers()` runs at the start of
`run()` in m02/m03/m04/m05/m08/m14/m16/m19/m20/m23/m28 — any module run
upserts the new `providers` / `provider_identifiers` rows and the portal
then shows them. `pipeline web` / `pipeline migrate` apply 0062's columns
but do **not** seed. Collecting evidence *for* the new providers (their
Companies House filings, charity accounts, CQC locations, re-matched
notices) needs the collection modules rerun — `m04` walks each
newly-seeded company number, `m03` the charity numbers, `m05` re-matches
by name, `m01`/`m02` re-filter/re-match. `./start.sh backup` then
`./start.sh run all` against the PostgreSQL warehouse (per `.env`). The
LAN Postgres was hand-seeded at the 21-provider stage and will catch up
on the next module run.

## Architecture Decisions

**Decision (2026-08-29): BETA-088–106 are a second approved, unqueued
front-end refinement programme behind BETA-068–087.** The nineteen selected
items turn the expanded portal into a stronger local research and monitoring
workspace and make run, parser, validation and review quality easier to inspect.
They do not displace the first refinement round or enter the authoritative
execution queue through this documentation update. The proposed explicit-
reference network was discarded and has no reserved ID.

**Decision (2026-08-29): research continuity remains local; monitoring remains
read-only.** Notebooks, saved searches and journey history use versioned,
size-bounded browser storage and lossless import/export, not accounts or server-
side profiles. Public change feeds and Atom subscriptions expose published
evidence state only and create no notification or personal-data store.

**Decision (2026-08-29): second-round analytical views expose observations,
not conclusions.** Co-occurrence is same-record presence, never a relationship;
discrepancies show compatible source statements without choosing a winner;
relationship paths use permitted reviewed edge types only; expected publication
windows distinguish publisher statements from observed cadence. Review outcome
analytics omit named-reviewer rankings, and quality-control findings append to
rather than rewrite the original audit trail.

**Decision (2026-08-29): diagnostic execution is isolated from production
writes.** Parser replay is bounded, non-persistent and admin-only. Pipeline and
validation maps are generated from authoritative registries where possible.
Source-link states come from collection-time observations and never trigger
external probes during public page rendering.

**Decision (2026-08-29): BETA-068–087 are the owner-approved front-end
refinement programme, preserved but not auto-started.** The round follows a
live desktop/mobile inspection and two explicit selection passes. It keeps
release degradation, mobile shell, pay/treatment/safety explorers, responsive
tables/filters, My area, chart inspection, workbench navigation, continuity,
atlas, design-system, document-reading and operator-workspace improvements.
The discarded homepage hierarchy, public download centre and terminology
layer are not backlog items. Promotion begins only when implementation is
explicitly started; then BETA-068 is the sole IN_PROGRESS item.

**Decision (2026-08-29): the refinement round exposes existing evidence
without weakening evidence boundaries.** Pay, treatment, safety/legal and map
layers retain their own populations, units, match meanings, caveats and
provenance. The atlas never computes a composite; the safety hub never merges
"addressed to", "named in", "matched to" or "regulated by"; UI ranking is
limited to operational attention in admin and never ranks evidence quality.

**Decision (2026-08-29): client continuity remains local and non-personal.**
My area and recent-entity state may store an ONS code or canonical entity key
in browser storage. They do not create accounts, profiles, public writes or a
new personal-data store. Filters, sections, layers, metrics and passages remain
shareable hash-query state.

**Decision (2026-08-29): BETA-050–067 are approved successor-backlog items,
not current queue entries.** Reserving persistent IDs now preserves the owner's
decisions, while waiting to promote them until BETA-049 is DONE keeps the
authoritative execution queue bounded and recoverable. The first promotion is
BETA-050 to IN_PROGRESS with BETA-051, BETA-052 and BETA-058 to NEXT.

**Decision (2026-08-29): similarity, clustering and overlap remain review
aids.** BETA-053, BETA-054, BETA-056 and BETA-057 may order or group work and
record a person's alias decision, but may not preselect, auto-merge,
auto-promote or silently change canonical identity. BETA-061 retains the
existing one-candidate-at-a-time promotion boundary.

**Decision (2026-08-29): BETA-107–113 permits a local analyst finding aid,
not an evidentiary actor.** Needle 2 may choose one closed read-only tool and
LFM may summarise only its returned public evidence. Neither model may write,
review, promote, collect, execute arbitrary SQL/HTTP/filesystem operations or
appear in `/api/v1`. Unsupported or uncited output is suppressed, and BETA-034
remains blocked for SetFit and semantic-claim work.

**Decision (2026-08-29): existing NLP retrieval stays authoritative for the
assistant pilot.** LFM embedding/ColBERT models, model-based extraction,
multi-turn memory and autonomous tool loops are not hidden parts of this
programme. Each would require its own representative evaluation and named
decision. Assistant inference is local, disabled by default, excluded from
Railway and limited to the public corpus; telemetry and cloud fallback are
off.

**Decision (2026-08-29): the third approved programme follows both front-end
programmes.** BETA-107–113 remains unqueued until BETA-068–106 is complete
unless the owner explicitly reprioritises it. Its final release gate, not code
completion of the endpoint, determines whether operators may enable it.

**Decision (2026-08-29): successor-round public evidence remains explicit and
caveated.** BETA-050 uses only published procurement lifecycle facts;
BETA-051 publishes only exact organisation-level HSE matches and no
individuals; BETA-064 keeps H-CLIC measures contextual; BETA-065 states that
CQC-regulated locations are not a complete service map or quality score; and
BETA-066 exposes verified predecessor/successor facts without inferred
ownership or officer data.

**Decision (2026-08-29): operational additions observe before they act.**
BETA-058 records runs without copying full logs, BETA-059 links coverage gaps
to non-destructive actions, BETA-060 audits the archive without deletion or
retention decisions, and BETA-063 inspects PostgreSQL capabilities read-only.

**Decision (2026-08-29): generated documentation covers factual matrices, not
narrative judgement.** BETA-067 may generate and verify machine-owned module,
source, route, export, licence and caveat blocks. Human-authored reasoning and
caveat prose remain manually reviewed.

**Decision (2026-08-29): the approved BETA-038–049 round improves access,
reviewability and release confidence before adding more datasets.** Contract
and document discovery, bounded source context and a public catalogue make the
existing evidence base more useful without widening it speculatively.

**Decision (2026-08-29): BETA-034 is BLOCKED on the human-review gate, not on
more model or infrastructure code.** `194ea33` and the pgvector follow-ups
improve completed machinery, but SetFit, `graph_claims` writes and public
semantic claims remain out of scope until `pipeline nlp gate-034g` succeeds.
BETA-046 may diagnose existing search; BETA-047 may record individual named
review decisions only.

**Decision (2026-08-29): commissioning timelines contain only existing,
provenanced `AWARDED_TO` contract events.** Missing dates are omitted and no
`REGISTERED_AS`, continuity, claim or signal edge is inferred. This keeps
BETA-044 inside the graph's deterministic evidence layer.

**Decision (2026-08-29): provider comparison preserves evidence layers.**
BETA-045 may place Living Wage, gender pay gap, provider-pay and NHS-advert
evidence side by side, but may not rank providers, calculate cross-layer
differences/ratios, convert unlike measures or emit a composite score. Export
is structured JSON; a flat CSV that would erase those boundaries is refused.

**Decision (2026-08-29): release identity is additive and read-only.**
`/health` remains plain `ok`; BETA-039 adds `/api/v1/meta` and GET-only beta
smoke checks. It does not authorise a production deployment or a write against
the production-backed development configuration.

**Decision: BETA-001 landed on `master`, not `beta`.** See its DONE entry.

**Decision: `deploy/ansible-mirror/` grew a `mirror_role`, rather than a new
top-level `deploy/ansible-beta/` tree.** Reasoning: six of the mirror's seven
roles are already `deploy/ansible/`'s, unmodified; the mirror role is
already "the same stack, seeded from a source" for both dr_mirror and beta —
only what happens *after* seeding differs. A parallel tree would have
triplicated the preflight/hardening/tuning/docker/firewall roles for zero
benefit. See BETA-003.

**Decision: a beta deployment does not get module API keys or a collection
schedule.** It inherits the mirror's "no collection" property regardless of
role. Reasoning: a beta box testing portal/query changes should not also
start crawling live public sources a second time, doubling load on them
without any campaign benefit. If a future queue item specifically needs to
exercise collection-module changes against real sources, that needs its own
explicit decision (rate-limit coordination, whether it's polite at all) —
not something to fall out of this default silently.

**Decision: Module 31 imports Module 30's discovery/parsing helpers
directly rather than duplicating them, and four of Module 30's functions
were made module-public (renamed off their leading underscore) to support
that.** Reasoning: unlike Modules 13/29's `sheet_rows` copies — genuinely
independent code that happens to look similar because both read ODS files
— Modules 30 and 31 read the *same* evergreen page, the *same* per-quarter
attachment, and need the *same* revision-preference rule; duplicating that
would create two copies that must be kept in sync by hand, which is a real
maintenance and correctness risk this project's house style (`CLAUDE.md`:
"don't add abstractions beyond what the task requires") doesn't actually
argue against — the task here *is* one shared source. See BETA-016.

## Database / Migration Changes

BETA-014: migration `0059` adds `rough_sleeping_snapshot` (SQLite +
PostgreSQL dialect trees, kept in sync). Purely additive; no existing table
touched.

BETA-015: migration `0060` adds `statutory_homelessness_snapshot` (SQLite +
PostgreSQL dialect trees, kept in sync). Purely additive; no existing table
touched.

BETA-016: migration `0061` adds `temporary_accommodation_snapshot` (SQLite +
PostgreSQL dialect trees, kept in sync). Purely additive; no existing table
touched.

Provider-set expansion (`fc97e66`, out of queue, 2026-08-27): migration
`0062` adds two columns to the reference-config `providers` table —
`status` (`'active'` default, or `'renamed'` / `'merged'` / `'dissolved'`)
and `superseded_by` (the surviving entity's `provider_key`, where there is
one). Both dialect trees, kept in sync; `ALTER TABLE ADD COLUMN` with a
default, non-destructive. Seeded from a new `PROVIDER_STATUS` map in
`pipeline/providers.py`. Note: applied to the LAN PostgreSQL warehouse
during this session (a seed script run under `.env`, which sets
`DATABASE_URL`), so that database already carries `0062` + the re-seed —
consistent with the committed code, but done a step ahead of a normal
post-merge run.

## Deployment / Infrastructure Changes

BETA-003: `deploy/ansible-mirror/` now builds a beta deployment as well as a
disaster-recovery mirror. See its DONE entry and Architectural Summary above.
Not yet run against a real VPS.

## Wording Pass (per project owner's mid-session request)

Asked to explore front-end wording, taking inspiration from comparable
projects while researching BETA-010/BETA-009. Findings:

- **Comparable products' copy was not a source of improvement.** LittleSis
  is bot-blocked from automated fetching; OpenSanctions' actual page copy is
  thin on caveats and sourcing detail compared to what this portal already
  does on every page. Adopting their tone would be a downgrade, not an
  upgrade — this portal's existing caveat/citation discipline is already
  more rigorous than either comparator's public-facing language.
- **A systematic scan for typos and repeated words across all public JS
  pages and `index.html` found none.** The existing copy is already clean.
- **One genuine, concrete inconsistency found and fixed**: every other
  page's `<h1>` is a descriptive phrase ("Where public money is going",
  "Find provider evidence", "Understand treatment data") — the new
  relationships page's was a bare single word, "Relationships". Retitled to
  "Who commissions whom", matching house style, plus a tightened lede.
- No broader rewording done. The existing copy's caveat language is
  precisely calibrated (several lines exist because of a specific incident
  — see `docs/CAVEATS.md` and multiple roadmap entries) and a wholesale
  pass risks introducing an error into wording that has been deliberately
  refined, for a return this scan did not find evidence of needing.

## UI / UX Changes

- BETA-001: portal tables no longer crash with `RangeError` under Tabulator's
  "fill" renderer when their holder has no intrinsic size (the provider deep
  dive was the reproducing case; the fix applies to every table via the
  shared `table()` component).
- BETA-009: two new Health tab cards (evidence-graph last-run status, graph
  entity count).
- BETA-017: a new "Comparators" section on every authority page — three
  small tables (rough sleeping, statutory homelessness, temporary
  accommodation), each with its own pinned caveat and provenance line,
  surfacing Modules 29-31's data for the first time anywhere in the portal.
- BETA-018: chart titles/labels now correctly follow the light/dark theme
  instead of hardcoding a colour that only worked in dark mode; the theme
  switcher is reachable on mobile/tablet for the first time (a second,
  synced control inside the offcanvas nav); a pre-existing flex-wrap bug
  that could push the last offcanvas nav item off-screen is fixed at the
  root, independent of the theme-switcher fix that surfaced it.
- BETA-020: every chart-bearing section on the Compare page (grant, budget,
  treatment × N indicators, contracts, charity, provider contracts) now has
  a `tableCard` data table beneath its chart, matching every other
  chart-bearing page in the portal.
- BETA-021: all six typeahead widgets (council search, provider filter,
  compare's two pickers, treatment's area picker, relationships' two
  pickers) now support arrow-key navigation with `aria-activedescendant`/
  `aria-selected`, not just "Enter picks the first match".
- BETA-022: a new "Document search" page and nav entry — full-text search
  over committee papers and CDP documents, the first search surface over
  document *text* anywhere in the portal (every other search is over
  structured rows).
- BETA-023: document-search results now show the passage that matched,
  highlighted, instead of the top of the page — and say "showing N of M
  matching pages" when the result list is cut. A mid-page match used to be
  invisible: the client truncated from character 0 with no indication the
  page matched anywhere else.
- BETA-024: every route names itself in the browser tab (history entries and
  bookmarks are distinguishable for the first time), and navigating between
  sections hands focus to the page content so screen readers announce the
  change instead of silence. Filter edits deliberately do not move focus.
- BETA-025: document search results longer than one window are reachable —
  an accumulating "Show N more" button under the list, with the count line
  kept truthful as it grows and failures confined to the button's own slot.
- BETA-026: quoted phrases in a search anchor the result snippet and are
  highlighted as one unit. Fixing this properly exposed a real bug: an
  early lone word could drag the snippet window away from the passage that
  matched as a phrase, leaving the phrase outside what the reader saw.
- BETA-027: the command palette — one search box (topbar button, Ctrl-K,
  or "/") across pages, councils, providers and document text, with live
  match-centred document snippets in the results and full keyboard
  navigation. The portal's front door.

## Performance Improvements

None this cycle.

## Observability

- BETA-009: the evidence graph subsystem (`docs/evidence-graph.md`,
  migration `0050`) had no answer anywhere in the UI to "has this ever run,
  how stale is it" before a CLI-only `pipeline graph status`. Now on the
  Health tab.
- BETA-013: same pattern, the document-analysis subsystem
  (`docs/document-analysis.md`, migration `0053`). Now on the Health tab
  too — 13,248 of 13,283 documents parsed in this checkout's real warehouse.

## Security Improvements

BETA-007: a per-IP token bucket on `/api/v1/*`, `429` + `Retry-After`.
See its DONE entry. Does not touch `/api/admin/*`'s security model (network
trust / bind address), which is unchanged and out of scope here.

## Testing Decisions

- BETA-019: extended `tests/test_export_completeness.py` rather than
  writing a new file — it is already the contracts complete-export tests'
  home, and the whole point of this change was "do the same thing again
  for a second endpoint." 14 tests total (10 pre-existing plus 4 new),
  including one pre-existing generic guard
  (`test_every_windowed_endpoint_has_a_complete_reader`) that would have
  failed automatically had `_export_complete` not gained a `pfd` branch.
  Verified against real production data as well as the fixture (the live
  corpus is exactly 1,539 reports) — HIGH end of the brief's own §22 scale
  for touching the export/download path, tested accordingly.
- BETA-018: no Python changed, so the offline suite served only as a
  regression check (111 tests across portal isolation/controls/public/
  authority/docs-coverage — it could not have caught any of this cycle's
  actual bugs, which were frontend-only). All real verification was live
  in-browser: computed `getBoundingClientRect()`/`getComputedStyle()` and
  `chart.getOption()` assertions substituting for screenshot comparison,
  since the Browser pane's screenshot tool was unavailable in this
  environment (no visual compositing). Checked both light and dark theme,
  and three viewport widths (375px, 800px, desktop), for every change.
- BETA-017: 4 new backend tests plus a full live-browser check in both the
  empty and populated states — the populated state needed a throwaway local
  SQLite warehouse since production has never run Modules 29-31 for real
  (see its DONE entry for the exact override commands). MEDIUM risk per
  the brief's own §22 scale: new public API payload fields and a new portal
  section, but reusing existing, already-tested components rather than a
  new rendering pattern.
- BETA-016: 10 new unit tests, two of them regression tests for real bugs
  caught during verification (a regex word-boundary bug, a real misnamed
  sheet). Both m30 and m31's test files run together (43 tests) to catch
  the cross-module breakage the shared-function rename could otherwise have
  caused silently — and did, once, before the two affected m30 tests were
  updated to the new names. Full suite run clean and uninterrupted (no
  concurrent edits, learning from BETA-015's own race artifact): 2434
  passed, 2 pre-existing unrelated failures, confirmed a fifth time.
- BETA-015: 33 new unit tests on the pure parsing functions, using fixtures
  built from the real header/data text of both source-file eras (not
  invented text), plus the locator re-run directly against four full real
  downloaded workbooks and cross-checked by hand against MHCLG's own
  published totals — HIGH end of the brief's own §22 scale for a new
  parser reading two genuinely different real-world file shapes. All five
  coverage guards BETA-014 found were exercised again and each caught
  something real for this module too. Full suite run twice: once
  concurrently with a docstring edit (produced two spurious failures from
  editing a file while pytest was importing it mid-run — see the DONE
  entry's note on this), then once clean — 2419 passed, 2 pre-existing
  unrelated failures, confirmed a fourth time now.
- BETA-001: targeted tests (`test_portal_controls.py`, `test_web_public.py`
  — 55 tests) rather than the full suite, plus a live in-browser check —
  isolated one-line JS fix, LOW/MEDIUM risk per the brief's own §22 policy.
- BETA-002: `test_register_links.py` + `test_docs_coverage.py` (21 tests) —
  docs-only change, no code path affected.
- BETA-003: no Python changed, so no pytest run applies. Validated with
  `bash -n` on the wizard script, `yaml.safe_load` on every touched YAML
  file, and the same 21 doc tests (the READMEs and `docs/DEPLOYMENT.md`
  changed). **Could not** run `ansible-playbook --syntax-check` — not
  installed in this dev environment — so the Jinja conditionals inside
  `when:`/`msg:` blocks are reviewed by hand only, not executed. Flagged
  explicitly in BETA-003's DONE entry; do not treat as equivalent to a real
  syntax check.

- BETA-007: full suite run for the first time this cycle (see Current Beta
  Status for the 3 pre-existing, unrelated failures), plus 14 new tests
  (`tests/test_ratelimit.py` — fake-clock unit tests for the token bucket;
  `tests/test_web_rate_limit.py` — real-server integration tests), plus
  `ruff check` on every touched file, plus a live-browser check and a manual
  burst against the real dev server. This is the MEDIUM/HIGH end of the
  brief's own §22 risk scale — new middleware on every public API
  request — and was tested accordingly, unlike BETA-001–004's lighter,
  proportionate checks.

## Deferred Ideas

- **Topbar overflow at ≤375px** (found by BETA-049's live pass, pre-existing
  and portal-wide): the find-council input and the mobile menu toggle
  overflow the viewport by ~93px, identically on `#/`, `#/documents` and
  every other route. BETA-018 already worked the mobile topbar and this is a
  separate layout fix — its own item, not folded into a guardrails pass.
- Building out a genuine beta staging deployment (Ansible role or Railway
  environment) — deferred until the project owner confirms they want one;
  see Architecture Decisions.
- Any new dataset/source — deferred; see Dataset Additions.
- AI-assisted features (summarisation, semantic search, etc.) — the brief
  authorises these but nothing in this session's discovery pointed at a
  concrete need for one, and the roadmap's own §3J/§8 sections (still
  possibly stale — see BETA-002) may already cover this ground better than a
  fresh pass would.
- **From BETA-018's frontend audit, found but not fixed this cycle** (lower
  confidence or bigger scope than the two bugs that were fixed and
  verified; a future session should re-check each against current code
  before acting, the same discipline this file applies everywhere else):
  - ~~The Compare page (`compare.js`) draws charts with no accompanying
    data table~~ — **done, see BETA-020.**
  - The Claims page (`claims.js`) has no search/filter/sort control,
    unlike the Tabulator-backed directory tables elsewhere; only a concern
    if the claims registry is expected to grow past what browser
    find-in-page comfortably handles.
  - ~~The typeahead widgets ... declare full `role="combobox"`/
    `role="listbox"` ARIA but only implement "Enter selects the first
    match"~~ — **done, see BETA-021** (which also found three more
    instances than this note named).
  - Some map/graph JS (`geography.js`'s MapLibre layer paints,
    `providers.js`'s entity-graph colours) uses inline hex literals rather
    than the `--accent-*` CSS custom properties the rest of the stylesheet
    disciplines itself to. Functionally harmless today (the literals match
    the palette); a maintainability nit, not a bug.

## Rejected Ideas

Deferring to `docs/upgrade-roadmap.md`'s own "6. Rejected" table (auth on
`/admin`, a web framework, auto-promotion, cross-layer ratios, SSE/WebSockets
for the job log, a `retrieved_at` freshness index, `parse_failures`
mark-as-noted, an ORM/non-SQLite engine, full-text search over archived
documents pre-Phase-4). Nothing new rejected this cycle.

## Environment Note

**This dev checkout's `.env` has `DATABASE_URL` pointing at the live Railway
production PostgreSQL database**, not a local sample warehouse — discovered
incidentally from `./start.sh web`'s own startup log ("warehouse:
postgresql://postgres:***@altaria.proxy.rlwy.net:20580/railway") while
verifying BETA-010 in-browser. Every live-browser check this session
(BETA-001, BETA-009, BETA-010) therefore ran against real production data,
not a fixture — which is *why* it looked so real (Nottinghamshire, CGL,
Turning Point are genuine). All requests made were `GET` (public portal
pages, admin health reads) — nothing this session wrote to it. Flagged
because it changes the risk profile of "start the dev server and click
around" for any future session: it is not a sandbox, and a future session
should not assume otherwise, especially before testing anything that writes
(a POST route, a review-queue decision, a module run).

## Known Issues

- BETA-034 cannot advance to SetFit or claim publication until named human
  reviewers produce a representative corpus and `pipeline nlp gate-034g`
  succeeds. pgvector acceleration does not change this evidence gate.
- The new PostgreSQL extension paths have focused and migration-equivalence
  coverage, but should still be exercised against a disposable live PostgreSQL
  instance with the extension matrix enabled before relying on them in a new
  deployment.
- The BETA-068 live review found two release-drift symptoms worth preserving as
  reproductions: document search exposed a missing `display_title` column and
  the admin run-ledger request exposed a missing `run_ledger` table when beta
  code read a warehouse that had not received the matching migrations. The
  underlying deployment must still be migrated correctly; BETA-068 adds the
  feature-level compatibility/degradation contract so drift is not rendered as
  raw SQL to a reader.
- **2026-08-26: `refs/heads/beta` was found corrupted** (a file of spaces,
  not a SHA) immediately after the BETA-027 commit, blocking `git push`,
  `git log` and `git status` ("your current branch appears to be broken";
  every file reported as newly staged). Repaired non-destructively by
  rewriting the ref to the verified commit `8da06a6` (chain checked against
  its parent and `origin/beta` before writing); nothing was lost and the
  push then succeeded. Cause unknown — this checkout is shared by several
  sessions (CLAUDE.md), and the corruption happened between a successful
  commit and a push seconds later. If it recurs: verify the commit still
  exists with `git cat-file -p <sha>` before touching anything, fix the
  ref, never re-commit over a broken ref blind.
- BETA-003's ansible-mirror changes are unverified against a real VPS —
  static checks only. First real run should be watched.
- `deploy/ansible/`'s status relative to Railway (live fallback? unused?
  something else?) is still genuinely unknown — not asked about, since the
  question that was asked (is Railway production) is now answered.
- ~45 stale branch pointers (local and remote) whose content is already in
  `master` — safe to delete, not done here. See BETA-004.

## Risks

- This project's evidence-quality discipline (`CLAUDE.md` settled decisions,
  `docs/CAVEATS.md`) is unusually strict and unusually well-reasoned for good
  reason (a union pay campaign that must survive dispute). Any future session
  working this queue should read both in full before touching anything that
  produces or displays a figure — this is not optional, per `CLAUDE.md`
  itself.
- A beta deployment now has a working (if unexercised) path to pull real
  production data via `mirror_sync_mode: url` against the Railway database.
  Treat that URL/credential with the same care production secrets get — it
  is still production's data, just copied once instead of nightly. Nothing
  in this session's work weakens that; flagged so it stays front-of-mind for
  whoever runs the wizard for real.

## Decisions (from the project owner's interview, 2026-08-25)

- **`deploy/ansible/` is the maintained DR/host-migration path** — kept and
  maintained going forward, confirming BETA-003's approach was correct in
  spirit. **`deploy/ansible-mirror` is specifically for building beta and
  mirror environments away from production** — exactly BETA-003's design.
  No code change needed; this closes former Question 1.
- **`docs/upgrade-roadmap.md` stays, but only for major work.** Lighter
  discipline than the F/D/P/U/W/O-for-everything approach that visibly
  lapsed — file findings/phases for significant initiatives, not every
  small fix. This closes former Question 2. (Not yet written down as an
  explicit rule anywhere else — worth a one-line note at the top of the
  roadmap itself if a future session has a spare minute.)
- **Relationship explorer: yes, public-facing.** New dedicated portal
  section. First version scoped to provider↔authority commissioning
  relationships only (the deterministic data `graph backfill` already
  produces) — not company/PSC ownership edges yet. See BETA-010 below.
- **AI-authored promotion: yes, wire it up.** Review requirement: one AI
  pass plus the existing human review-queue decision as the second
  independent review. Candidate type/use case: **awaiting the project
  owner's explanation** — asked directly rather than via multiple choice,
  since this is a "let me explain" case, not a pick-from-a-list one.

## Questions Requiring Human Input

0. **Which candidates should AI-authored promotion apply to first?**
   `pipeline/ai_promotion.py`/`docs/AI_PROMOTION_POLICY.md` exist, are
   carefully guarded (objective predicates, sampling audits, a
   quarantine-on-false-promotion breaker), and the project owner has
   confirmed: wire it up, with one AI pass plus the existing human
   review-queue decision as the second independent review. What's still
   needed before implementation starts: which candidate type/backlog this
   should actually apply to — asked directly of the project owner, answer
   pending. See BETA-011.
1. **WDTK robots.txt exception** (BETA-005) — time-boxed to 2026-09-10,
   already tracked, not this session's call.
2. **Is crime data (BETA-014's research) worth pursuing given the real
   effort involved?** `data.police.uk` is the only real public source found
   and it is street-level/LSOA, not local-authority-level — using it as an
   authority comparator needs this pipeline's own LSOA→ONS-code crosswalk
   (ONS does publish an official lookup, so it's buildable, but it is a
   materially bigger module than rough sleeping or homelessness, and
   small-area crime data raises its own care-in-handling questions —
   whether aggregating up to LA level is enough distance from individual
   incidents, what a defensible comparator shape even looks like here —
   that this project has not had to answer for any existing source. Worth
   the project owner's view on whether the value justifies that effort
   before any code gets written, not a default yes.
3. ~~**Is a document-search UI (BETA-013's follow-up) worth building, and
   where?**~~ **Answered and delivered, 2026-08-26 (BETA-022):** checked
   rather than guessed — only two source systems are actually bridged into
   the document-analysis schema (committee papers, CDP documents), neither
   with a restricted_ personal-data counterpart; PFD reports and tribunal
   judgments are not in this pipeline at all. Public, scoped to those two
   sources via an explicit allowlist. See its DONE entry for the full
   reasoning and how the allowlist is enforced and tested.
4. ~~**Which further substance-misuse providers should be added to the
   tracked set?**~~ **Tiers 1-3 added, 2026-08-27 (`fc97e66`, see Dataset
   Additions → "Provider set expanded to 21").** Cranstoun, Changing
   Lives, ADS (Hull) and Spectrum Community Health CIC as active peers;
   Aquarius, Action on Addiction, Swanswell and Lifeline Project as
   merged/dissolved entities that still surface in older evidence. Two
   assumptions in the original scan were wrong and were corrected during
   verification: Action on Addiction merged into **The Forward Trust**
   (not With You), and Swanswell into **Cranstoun** in 2022 (not CGL in
   2017). A second batch (`b64ff10`) added Blenheim CDP, EDP, Bristol
   Drugs Project, DHI, NECA, The Ley Community and Practice Plus Group —
   set now 28. **Still open — Tier 4:** NHS-trust comparators beyond
   `inclusion`/MPFT (CNTW, RDaSH, GMMH, Surrey & Borders, Humber, CNWL,
   SLaM, Nottinghamshire Healthcare). The project has one NHS provider as
   the pattern; adding more widens the entity model deliberately and was
   left for the project owner's steer. A third batch (`583476d`) added
   Compass, KCA, Blue Sky and Recovery Focus — set now 32. Still not
   taken: the NHS trusts, the residential-rehab charity sub-sector,
   recovery-support CICs, and the private residential-rehab groups (a
   private-vs-third-sector pay contrast, a separate decision).

## Recent Commits

- `b5ff6a9` — approve and fully specify the second front-end refinement
  programme BETA-088–106 (`beta`, documentation only).
- `b6aba7b` — approve and fully specify the first front-end refinement
  programme BETA-068–087 (`beta`, documentation only).
- `980b681` — machine-owned capability documentation blocks and consistency
  checker (BETA-067).
- `a2ccce4` — verified provider predecessor/successor lineage (BETA-066).
- `60d3e00` — public CQC regulated-location explorer (BETA-065).
- `b5e4a76` — H-CLIC temporary-accommodation B&B breakdown (BETA-064).
- `e1ca1bb` — read-only PostgreSQL extension readiness gate (BETA-063).
- `6a5d206` — deterministic human-readable document titles (BETA-062).
- `e1602a5` — reconcile the queue through BETA-049, restore the handoff
  snapshot and record BETA-036/037 as completed (`beta`, documentation only).
- `d2c4bc7` — close a missing parenthesis in the operator name-match renderer;
  reconciled `beta` / `origin/beta` HEAD for this handoff.
- `777828a` — move pgvector backfill off health-gated web startup and make
  index construction an explicit one-time operation (BETA-036).
- `1a1118e` — build the pgvector HNSW index serially for small `/dev/shm`
  deployments (BETA-036).
- `e654e80` — assign longer TTLs to near-static public routes (BETA-037).
- `aeebdf3` — optional bounded in-process LRU caching for public API responses
  (BETA-037).
- `f11da76` / `c8d43fb` — merge and implementation of pgvector ANN semantic
  search acceleration (BETA-036).
- `194ea33` — keep batch semantic entity resolution idempotent below backend
  bind-parameter limits (BETA-034 current state).
- `c6aec04` / `cc0e869` — merge and implementation of PostGIS authority
  geometry (BETA-036).
- `5df2307` / `460725b` — merge and implementation of trigram indexes and
  operator fuzzy-name search (BETA-036).
- `9bc056a` / `d613cb0` — merge and implementation of PostgreSQL extension
  provisioning/capability plumbing (BETA-036).
- `6d1be0e` — BETA-028 offline map fallback and BETA-029 overview payload
  reduction; both queue items DONE.
- `583476d` — add Compass, KCA, Blue Sky, Recovery Focus (set now 32):
  Compass an active charity, the other three merged/renamed into With You
  / Forward Trust / the Waythrough line (out-of-queue,
  project-owner-directed; `beta`). See Dataset Additions.
- `fd82152` — beta.md: record the second provider expansion (`b64ff10`)
  (`beta`).
- `b64ff10` — add 7 more providers (set now 28): Blenheim CDP + EDP as
  merged→waythrough, Bristol Drugs Project / DHI / NECA as active peers,
  The Ley Community as a phoenix_futures subsidiary, Practice Plus Group
  (for-profit prison healthcare) (out-of-queue, project-owner-directed;
  `beta`). See Dataset Additions.
- `2ca03a6` — beta.md: record the provider-set expansion (`fc97e66`) and
  migration 0062 (`beta`).
- `fc97e66` — add 8 more substance-misuse providers (tiers 1-3); portal
  shows renamed / merged / dissolved status with a link to the successor;
  migration 0062 adds `providers.status` / `providers.superseded_by`
  (out-of-queue, project-owner-directed; `beta`). See Dataset Additions.
- `2b264c2` — beta.md: record the two provider-identifier commits
  (`beta`).
- `eb1799f` — seed hand-verified CQC provider IDs for all 13 providers
  (out-of-queue, project-owner-directed; `beta`). See Dataset Additions.
- `9b3fe06` — seed hand-verified charity + company numbers for all 13
  providers; scope m04 tests to the companies each run walks
  (out-of-queue, project-owner-directed; `beta`). See Dataset Additions.
- `5adc5e6` — BETA-033: overview hero region map, orchestrated motion,
  scroll reveals; fixed a dead "Current snapshot" section found along the
  way (out-of-queue, project-owner-directed; `beta`).
- `d1f1f43` — beta.md: record BETA-032, fix stale queue notes (`beta`).
- `ef1a4c4` — BETA-032: overview and pay page polish — count-up metrics,
  provider-matched highlights, census removal (out-of-queue,
  project-owner-directed; `beta`).
- `8da06a6` — BETA-027: command palette — unified search across pages,
  councils, providers and documents (`beta`).
- `538095f` — BETA-026: quoted phrases anchor snippets and highlight as a
  unit (`beta`).
- `6db979a` — BETA-025: show-more pagination for document search via offset
  windows (`beta`).
- `f2115d7` — BETA-024: per-route titles and focus handoff on portal
  navigation (`beta`).
- `e8b6ed4` — beta.md: record BETA-023, queue BETA-024 (`beta`).
- `cb4781b` — BETA-023: match-centred snippets and honest result counts in
  document search (`beta`).
- `3f8c74d` — BETA-022: public full-text search over committee papers and
  CDP documents (`beta`).
- `a28b010` — BETA-021: arrow-key navigation and aria-activedescendant for
  every typeahead (`beta`).
- `f566c79` — BETA-020: data tables under every Compare-page chart
  (`beta`).
- `419171f` — mirror: add explicit local PostgreSQL reset (concurrent
  session, `beta`).
- `ece19ae` — BETA-019: complete-corpus CSV/JSON export for PFD reports
  (`beta`).
- `087c1c6` — BETA-018: theme-aware chart colours, mobile theme switcher,
  dead vendor file (`beta`).
- `a2b4796` — BETA-017: surface Modules 29-31 as a Comparators section on
  the authority page (`beta`).
- `1336770` — BETA-016: Module 31, temporary accommodation (H-CLIC)
  snapshot (`beta`).
- `5855ac7` — BETA-015: Module 30, statutory homelessness (H-CLIC) snapshot
  (`beta`).
- `47cf21c` — BETA-014: Module 29, rough sleeping snapshot (`beta`).
- (BETA-010–013 commits landed between `f2b727a` and `47cf21c`; see their
  own DONE entries above for detail — this list was not kept current for
  every intermediate commit, the same disclosed gap as the Candidate
  Feature Backlog table above.)
- `f2b727a` — BETA-009: surface the evidence graph's own status on the
  Health tab (`beta`).
- `0c82267` — docs: W-15's CQC half and the API-rate-cap possible-future
  were already delivered (BETA-008; `beta`).
- `e2c6766` — BETA-007: per-IP token-bucket rate limit on the public API
  (`beta`).
- `8e59063` — beta.md, roadmap: BETA-004 complete; fix §8 staleness
  (`beta`).
- `f879e1b` — beta.md: close out BETA-002 and BETA-003, promote BETA-004
  (`beta`).
- `29d07c9` — deploy: teach ansible-mirror to build a beta deployment, not
  just mirror (BETA-003; `beta`).
- `81dd9d9` — beta: set up autonomous work queue; correct stale roadmap
  entries (BETA-002 pass 1 + initial queue setup; `beta`).
- `c1c3ecd` — Fix Tabulator recursive call-stack overflow on every table
  (BETA-001; on `master`).

## Next Recommended Actions

*(Handoff snapshot reconciled against local/origin `beta` at `b5ff6a9` before
this roadmap-only working-tree update, 2026-08-29.)*

**What is currently being worked on?** Nothing. BETA-067 completed the prior
implemented programme. BETA-068–087, BETA-088–106 and BETA-107–113 are
approved and fully specified in Candidate Feature Backlog but have
deliberately not been promoted into the execution queue by these roadmap-only
updates.

**What was the last successful queue item?** BETA-067 (`980b681`), the
capability-documentation consistency checker. Immediately before it,
BETA-066 (`a2ccce4`) delivered provider predecessor/successor lineage and
BETA-065 (`60d3e00`) delivered the public CQC location explorer.

**What should happen next?** When implementation is explicitly started,
promote BETA-068 to IN_PROGRESS and BETA-069–072 to NEXT. BETA-068 first
establishes safe compatibility/error contracts observed missing during the
live review; BETA-069 then fixes the 390px first-screen defect. Continue under
the recorded waves and dependencies, with BETA-080 delivered incrementally as
a shared prerequisite rather than attempted as a blocking rewrite.

**What follows that programme?** BETA-088–106 is the approved second refinement
programme. Unless the owner explicitly reprioritises it, complete BETA-068–087
first, then promote BETA-090 as the first change-awareness foundation and no
more than five dependency-safe items under the recorded delivery sequence.

**What follows both front-end programmes?** BETA-107–113 is the approved
local analyst-assistant programme. Start with BETA-107, then BETA-108/109,
then BETA-110–113 in order. It remains disabled until BETA-113's routing,
grounding, adversarial and target-host performance gates pass.

**What is blocked and why?** BETA-034 is blocked pending a successful
human-review corpus from `pipeline nlp gate-034g`. `194ea33` and the pgvector
follow-up commits are recorded improvements to its current implementation, not
permission to bypass the gate. BETA-011 and BETA-005 retain their older blockers
in the queue; BETA-006 remains research-only absent new scheduling information.

**Which constraints must survive the round?** Existing routes and response
defaults stay backward compatible; public state remains read-only and browser-
local where specified; unlike pay, treatment, safety and geographic evidence
is never flattened into composite claims; the safety hub preserves distinct
relationship meanings; restricted-table and review-decision safeguards stay
intact; polling remains the job-log transport; and every public chart retains
an accessible data path, provenance and caveat. No authentication, web
framework, build step, SSE/WebSockets, automatic matching, auto-promotion or
semantic-claim publication is introduced.

Do not touch the `m15-web-unlocker`/`zenrows`/`wdtk-html-fallback` branches
without asking — see BETA-004's notes. `docs/upgrade-roadmap.md` claims
should still be checked against actual code before being trusted (BETA-008's
DONE entry records this as a recurring pattern).
