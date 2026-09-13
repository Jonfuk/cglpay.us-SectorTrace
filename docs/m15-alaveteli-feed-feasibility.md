# Module 15 — Alaveteli feed feasibility (JON-8)

**Status: feasibility only. No code changed by this document.** JON-8 is
labelled `Post-V1` / `Not scheduled`; this is the bounded research deliverable
for that ticket, not an implementation. Executor/acceptance owner: Jon Firth.

**This document does not authorise WDTK collection.** The robots.txt
exception that lets `m15_foi` fetch `/feed/search/` at all is a separate,
live decision tracked in JON-89 (deferred 2026-09-12 to 2026-10-12, no
renewal implied). Everything below describes what could be built *if* that
access basis is confirmed; it changes nothing about whether it currently is.

## Verdict up front

Most of what JON-8 asks for already exists. `pipeline/alaveteli.py` already
parses both Alaveteli JSON shapes (feed and full read API) and an HTML
fallback; `pipeline/modules/m15_foi.py` already collects the feed, the
authority CSV and council disclosure logs with full provenance; promotion
already goes through a human (`pipeline/promote.py`). The real gaps are
narrow and specific:

1. **No incremental/checkpointed discovery.** Every run re-searches every
   term from page 1. Alaveteli's query syntax supports date-range filtering,
   so a checkpoint is buildable, but nothing does it today.
2. **No structured filtering by authority, file type or status in the
   query itself.** The collector filters *after* the fact (by GSS code
   against `authorities`) rather than asking Alaveteli to narrow the search.
   Alaveteli's syntax supports this too (confirmed against source, below).
3. **No attachment acquisition at all.** `foi_attachments` (migration
   `0019`) has been an empty table since it was created — nothing in
   `pipeline/` inserts into it. Attachments live behind the same 403 that
   blocks full response text, so this gap cannot close without the same
   access decision JON-89 is tracking.
4. **Atom vs JSON is very unlikely to matter.** No evidence either format
   carries more than the other; both are believed to be serialisations of the
   same `InfoRequestEvent` search results. Treat this as unconfirmed rather
   than assumed — see "Open questions."

None of 1–3 requires new access. 1 and 2 are query-string changes inside the
already-permitted `/feed/search/` fetch (subject to JON-89 continuing to
regard that fetch as permitted at all). 3 is blocked on the same Cloudflare
403 documented since 2026-08-11 and is not a m15 engineering problem to solve
by itself — see `docs/upgrade-roadmap.md` on the `codex/m15-web-unlocker*` /
`codex/m15-zenrows*` / `codex/wdtk-html-fallback*` branches: bypassing that
403 without the provider's sign-off is explicitly out of scope by policy.

## What already exists (audit)

| Piece | State | Where |
|---|---|---|
| Alaveteli JSON parsing (feed shape: discovery, snippet-only) | Built, tested | `pipeline/alaveteli.py::parse_feed_event`, `parse_feed_page` |
| Alaveteli JSON parsing (read-API shape: full request/authority) | Built, tested, **unreachable** (403) | `pipeline/alaveteli.py::parse_info_request`, `parse_authority`, `extract_response_texts` |
| Canonical-HTML fallback parser (for the 502 case, human promotion only) | Built, tested | `pipeline/alaveteli.py::parse_info_request_html` |
| Authority register (mySociety CSV → `authority_foi_profiles`) | Built | `pipeline/modules/m15_foi.py::parse_authorities_csv` |
| Feed search, one phrase per configured term, 4 pages/term cap | Built | `pipeline/modules/m15_foi.py::_collect_feed_candidates` |
| Council disclosure-log crawl (same-host links, term match) | Built | `pipeline/modules/m15_foi.py::crawl_disclosure_log`, `extract_foi_candidates` |
| Human promotion path (candidate → `foi_requests`, requires a person) | Built | `pipeline/promote.py` (`kind == "foi_request"`) |
| m15-only Bright Data / ZenRows transport for one detail page during promotion | Built, disabled by default, requires explicit key + setting | `pipeline/modules/m15_foi.py::fetch_with_web_unlocker`, `fetch_with_zenrows` |
| `foi_attachments` schema | Present, **never written to** | `pipeline/migrations/postgres/0019_foi.sql` |
| Test coverage | 26 tests (`test_alaveteli.py`) + 31 tests (`test_m15_foi.py`), fixture-backed | `tests/test_alaveteli.py`, `tests/test_m15_foi.py` |
| robots.txt exception for `/feed/search/` | Live, logged, time-boxed, **now past its original 2026-09-10 deadline, deferred by JON-89 to 2026-10-12 pending no renewal of collection scope** | `pipeline/config.py::Settings.robots_exceptions`, `docs/mysociety-access-request.md` |

There is no separate "old FOI collector" to compare against — `m15_foi` *is*
the module the ticket asks to strengthen; there is nothing else discovering
FOI evidence today.

## Source and access terms (verified 2026-09-12)

Verified directly against `mysociety/alaveteli`'s own source
(`lib/xapian_queries.rb`, `app/models/search/adapters/xapian/indexing.rb`,
fetched via `gh api` on 2026-09-12) rather than inferred from third-party
summaries, because the ticket flags API claims as unverified and
`www.whatdotheyknow.com/help/api` itself 403s to automated fetches — the same
Cloudflare challenge `pipeline/modules/m15_foi.py` already documents.

* **Query syntax is real and richer than what m15 currently sends.** The
  Xapian index behind `InfoRequestEvent` (what `/feed/search/` searches)
  carries term prefixes for `status:`, `latest_status:`, `variety:`,
  `latest_variety:`, `requested_from:` (authority), `filetype:`, `tag:`,
  and `request_public_body_tag:`, plus a `created_at` range value queryable
  as `DD/MM/YYYY..DD/MM/YYYY` in the query text. All four capabilities the
  ticket names — authority, dates, file type, status — are real Alaveteli
  features, confirmed at the source-code level, not assumptions.
* **The feed and the main site search share one query parser.** `/feed/search/<query>.json`
  takes the same query string as the HTML advanced search — no separate
  "feed query language" to learn.
* **No documented rate limit or read-side API key requirement was found**
  for `/feed/search/` — consistent with the pipeline's own 2026-08-11
  measurement (200 OK, no auth). The only API key mentioned in mySociety's
  docs (`api/v2/request`) is the *write* API for authorities submitting
  responses, which is irrelevant to discovery.
* **Licensing**: `pipeline/licences.py` already records `mysociety_mixed`
  (CC BY-SA for mySociety's own register/search data, generally OGL v3.0 for
  authority responses). Nothing found in this research contradicts that; the
  mySociety open-data catalogue page for the WhatDoTheyKnow API does not
  state a license for the live API itself (only a license-selector field for
  bulk datasets), so treat the existing `mysociety_mixed` entry as the
  considered position rather than something this ticket changes.
* **Access is not the same question as capability.** All of the above is
  about what Alaveteli's query language *can* express. Whether this
  pipeline may keep using `/feed/search/` at all is JON-89's question, not
  this document's — see the disposition note at the top.

## Gaps against the ticket's ask, and what closing each would need

**Incremental discovery by date (buildable now, subject to JON-89).**
Store a per-term (or per-topic) checkpoint — the `event_date`/`request_date`
of the newest record already seen — and add `<checkpoint>..` to the query
sent to `feed_search_url`. This is a schema change (a small state table or
columns, mirroring the pattern other incremental modules use — see
`supports_since` on other modules in `pipeline/registry.py`) plus a change to
`_collect_feed_candidates`. `m15_foi` is currently registered with
`supports_since=False` and an explicit `since_note` explaining why
("disclosure logs publish whatever is currently listed; candidates carry
`discovered_at` rather than a source date") — that reasoning covers the
disclosure-log half of the module, not the feed half, which does have a real
source date (`request_date`/`event_date`) to checkpoint against. Changing
`supports_since` is a real API/behaviour decision for module registration,
not a trivial edit — flag it rather than assume it.

**Filtering by authority, file type and status in the query itself
(buildable now, subject to JON-89).** Two independent uses:
  - *Authority*: `requested_from:<wdtk_body_slug>` would let the module ask
    Alaveteli to restrict results to authorities it already knows, instead of
    fetching broad term matches and discarding rows whose GSS code doesn't
    join (current behaviour in `_collect_feed_candidates`). This trades
    request count (one search per authority per term, a large multiplier
    against ~317 authorities × ~25 terms) for precision — almost certainly
    not worth it as a blanket change; more plausibly useful for a narrow,
    manually-triggered re-run against a specific authority under review.
  - *File type / status*: `filetype:pdf`, `status:`/`latest_status:` would
    let a saved query pre-filter to (for example) `latest_status:successful`
    disclosures, or `filetype:pdf` when hunting for a specific published
    document. Useful for building an ad hoc/manual saved-query feature later,
    lower priority than checkpointing for routine collection.

**Attachment acquisition (blocked, not an engineering gap).**
`/request/<slug>.json` and the attachment routes sit behind the same
Cloudflare 403 as full response text. `foi_attachments` was shaped in
migration `0019` in anticipation of an access grant that has not arrived.
Nothing here changes until JON-89 resolves (or the mySociety request in
`docs/mysociety-access-request.md` gets an answer) — this is the same
constraint already documented in `docs/CAVEATS.md` under "FOI evidence
(Module 15)," not a new finding.

**Saved queries as a durable/user-facing concept.** Alaveteli's own "track a
search" feature is the same feed URL with a subscription wrapped around it —
it adds no server-side capability this pipeline doesn't already have access
to. A "saved query" here would just mean: a named, versioned entry in
`FOI_TOPICS` (or a sibling structure) that carries a full Alaveteli query
string (term text + `filetype:`/`status:`/date-range operators) instead of a
bare phrase. That is a configuration-shape decision, not a new integration.

## Provenance requirements

No new provenance work: `_provenance()` in `m15_foi.py` already captures
`source_url`, `retrieved_at`, `http_status`, `source_system`,
`payload_sha256` for every fetch, and `PipelineHTTPClient` archives raw bytes
under `data/raw/`. Any of the above changes (checkpointed queries, richer
filters) reuse the same fetch → parse → `_provenance()` → `upsert_many` path
already in place; they do not add a new source system or change what a row
must carry. Checkpointing only adds *state* (last-seen date per term/topic),
which is a new small table or columns, not a provenance change.

## Integration approach (if JON-89 confirms continued/renewed access)

1. Add a checkpoint table (or per-topic columns) recording the newest
   `event_date` seen per search term, written alongside the existing
   `foi_request_candidates` upsert in `_collect_feed_candidates`.
2. Extend `feed_search_url` (or a new query-builder) to append a date-range
   term once a checkpoint exists, falling back to the current unbounded
   4-page search on first run.
3. Leave authority/file-type/status query filters as a separate, later
   decision — they serve a different use case (targeted/manual lookups)
   than routine incremental discovery, and mixing them into the same change
   would widen scope.
4. Leave attachment acquisition alone entirely until the access question
   resolves; there is no code to write against a 403.
5. Any of this needs its own bounded implementation ticket, scoped no wider
   than step 1–2, with `supports_since` and the checkpoint schema named
   explicitly as the "new API/schema contract" `agent/README.md`'s bounded-fix
   policy requires stopping for.

## Draft acceptance criteria (for a future implementation ticket, not this one)

| Case | Expected result | Check |
|---|---|---|
| First run, no checkpoint | Behaves exactly as today — unbounded 4-page search per term | Existing `test_m15_foi.py` coverage, unchanged |
| Second run, checkpoint present | Query includes `<last_seen_date>..`; pages stop once results are older than the checkpoint | New fixture-backed test asserting the built query string and page-stop condition |
| Checkpoint advances only on success | A run that hits `foi_feed_unavailable`/`foi_feed_not_json` does not advance the stored checkpoint past the last *fully processed* page | New test forcing a mid-run failure and asserting the stored checkpoint is unchanged |
| robots exception absent | Module degrades to authority CSV + disclosure logs, checkpoint logic does not run, `foi_feed_robots_disallowed` still recorded | Existing behaviour, re-verify unchanged |
| Malformed/unexpected date field | Falls back to unbounded search for that term rather than silently skipping it; failure recorded via `db.record_parse_failure` | New negative-case test |

## Open questions requiring a human decision or further verification

1. **JON-89's disposition** is the actual gate on all of the above being
   worth implementing at all, including whether the feed fetch continues
   past 2026-10-12 in any form.
2. **Atom vs JSON content parity is unconfirmed.** This document did not
   find or fetch a live Atom feed response to compare against the JSON shape
   already parsed (WDTK itself 403s to automated fetches, including this
   research). If Atom is ever preferred, verify it against a real response
   before assuming parity — don't extend `pipeline/alaveteli.py` to Atom on
   the strength of this document alone.
3. **Whether `requested_from:`-scoped per-authority queries are worth the
   request-count multiplier** is a product/coverage trade-off for Jon to
   make, not an engineering default.
4. **`supports_since=False` on `m15_foi`** currently covers both the feed and
   disclosure-log halves with one flag and one justification. Splitting the
   module's since-behaviour by source (feed: checkpointable; disclosure logs:
   not) is itself a small design decision worth a sentence in whatever ticket
   picks this up, not something to silently flip.

## Sources

* This repository: `pipeline/alaveteli.py`, `pipeline/modules/m15_foi.py`,
  `pipeline/promote.py`, `pipeline/migrations/postgres/0019_foi.sql`,
  `pipeline/config.py`, `pipeline/licences.py`, `docs/CAVEATS.md`,
  `docs/SOURCES.md`, `docs/mysociety-access-request.md`,
  `tests/test_alaveteli.py`, `tests/test_m15_foi.py` (read 2026-09-12).
* `mysociety/alaveteli` GitHub repository, `lib/xapian_queries.rb` and
  `app/models/search/adapters/xapian/indexing.rb`, fetched via `gh api`
  2026-09-12 — the primary source for the query-syntax claims above.
* `http://alaveteli.org/docs/developers/api/` (fetched 2026-09-12) — confirms
  the read/write API split and JSON/Atom availability at a high level; light
  on rate-limit and licensing detail, hence the source-code check above.
* `https://www.whatdotheyknow.com/help/api` — returned HTTP 403 to automated
  fetch on 2026-09-12, the same Cloudflare posture `m15_foi.py` already
  documents. Not read; nothing in this document relies on it.
* `https://data.mysociety.org/datasets/whatdotheyknow-api/` (fetched
  2026-09-12) — catalogue entry only, no independent licensing statement.
