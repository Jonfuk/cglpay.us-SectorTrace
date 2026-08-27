# Module 32 — per-SAB website crawling

**Status:** built (migration `0064`, `pipeline/modules/m32_sab_site_reviews.py`).
The three decisions in §7 were taken: **hybrid auto-ingest**, **England-only**,
**with the `sab_site_crawls` state table**. This document is now the design
record; what shipped matches it, with the notes below.

**As built, notes on the scope:**

* `library_year` on a `sab_website` row is a best-effort year read from the
  filename or link text, falling back to the crawl year — a rebuild of
  `sar_documents` to make the column nullable was not worth it, and the SAR
  export caveat says so.
* Discovery is `SAR_PATHS` (a set widened 2026-08-27 from the real
  structure of boards that returned nothing on the first run — `/published-sars`,
  `/professionals/safeguarding-adult-review-sar-reports`, `/case-reviews/...`
  and so on) plus **one hop**: a same-host link whose text says SAR but
  points at a page is followed once. `www.` and the bare host are treated as
  one site, and a homepage that redirects to another domain is followed. On
  a page reached via a SAR link, every document is a candidate even if its
  link text is only a pseudonym — the hybrid gate still decides ingest vs.
  review.
* First-run robots blocks: seven board hosts disallowed either the listing
  paths or the asset directory the SAR PDFs sit in. Added to
  `Settings.robots_exceptions` (fourth batch) on the same footing as the
  council batches.
* Review-item types shipped: `sab_website_unknown`,
  `sab_site_collection_failed`, `sab_site_robots_disallowed`,
  `sab_site_doc_unavailable`, `sab_no_sars_found`, `sab_site_sar_candidate`,
  `sab_site_sar_board_mismatch`, `possible_duplicate_of_library_sar`.

## Why this is a new module, not more of m28

Module 28 reads SAR documents from the National SAR Library
(`nationalnetwork.org.uk`) and its SCIE 2015–2018 collection. Its founding
decision — stated in migration `0057` and the module docstring — is *one
aggregator with real coverage beats crawling ~150 independent Safeguarding
Adults Board websites*, the same call `m08` makes for judiciary.uk over 150
coroners' courts.

Adding a 150-site crawl **to m28** would contradict that in place. A separate
module keeps m28's identity intact, makes the new layer separately runnable
and skippable, and lets it carry its own review-item vocabulary and its own
"this yielded nothing" accounting without muddying m28's.

`m32_sab_site_reviews` **depends on `m28_sar_reports`**: it needs
`safeguarding_adults_boards` populated with a `website_url` per board, which
m28 fills from the Ann Craft Trust directory.

## What it adds, and what it costs

**Adds:** SARs a board published on its own site but never submitted to the
National Network library. On a spot check of the directory, most English
boards have a "Safeguarding Adults Reviews" or "publications" page; a
minority of the documents on them are not in the library.

**Costs:** ~142 English board sites to crawl politely every run, each a
bespoke layout, and a steady stream of `sab_no_sars_found` review items for
the boards whose pages a bounded crawl cannot find or read — the same
coverage-vs-noise trade the m28 founding decision was avoiding, now taken
deliberately for the incremental documents.

## Design

Mirrors `m24_council_spend` (discover on the authority's own domain, fetch
through the shared client, parse) and `m09_cdp_documents` (bounded path set,
link scoring, a 404 is unremarkable).

### Input

`safeguarding_adults_boards` rows where `nation = 'England'` and
`website_url` is set. England-only for the same reason `build_sab_index`
is: the campaign is England-wide, and a Welsh or Scottish board is out of
scope. A board with no `website_url` → `sab_website_unknown` review item.

### Discovery

For each board, try a bounded set of likely paths on its own host:

```
/  /safeguarding-adults-reviews  /safeguarding-adult-reviews  /sar  /sars
/publications  /reviews  /serious-case-reviews  /learning-reviews
/safeguarding/reviews  /about/safeguarding-adults-reviews
```

Follow a link when its URL **or** anchor text matches SAR vocabulary
—

```
safeguarding adults? review | \bSAR\b | serious case review |
learning review | learning brief | 7[\s-]?minute briefing
```

— **and** it points at a document (`.pdf` `.docx` `.odt`) or at one
intermediate HTML page that itself links to documents. Same-host only (the
`m09` rule). `MAX_PAGES_PER_SAB` ≈ 10, `MAX_DOCS_PER_SAB` ≈ 25.

robots.txt respected. SAB sites are frequently council subdomains, several
of whose roots are already in `Settings.robots_exceptions`; a blocked board
is a `sab_site_robots_disallowed` review item, not a guess.

### Parse and attribute

Reuse m28's `_read_pdf` / `_read_docx`, `find_provider_mentions`,
`index_concern_terms`.

`sab_name` is **known** here — it is the board whose site is being crawled —
so it is set to that board's official directory name with a new, highest-
confidence `sab_name_source = 'sab_website'`. As a cross-check,
`resolve_sab_name` still runs on the fetched text: if the text names a
*different* board strongly, the document is **not** auto-ingested and
becomes a `sab_site_sar_board_mismatch` review item (a board site linking
to a neighbouring board's review is the expected false positive).

### Auto-ingest vs. confirm

Recommended hybrid:

* **Auto-ingest** into `sar_documents` when the link vocabulary is
  unambiguous **and** the fetched document's own text names *this* board
  (`resolve_sab_name` returns it). The board naming itself in its own SAR
  is strong signal.
* **Otherwise** → `sab_site_sar_candidate` review item, promoted by a
  person, the way `m09` gates `cdp_documents`.

### De-duplication against the library

A board's own copy of a SAR already in `sar_documents` from the library:

* **Exact bytes** (`payload_sha256` matches an existing row) → not stored
  again; the existing row gains nothing.
* **Same review, different file** (a re-paginated PDF, an accessible
  version) → stored as its own row (different URL, different bytes) with a
  `possible_duplicate_of_library_sar` review item when board + title
  pseudonym + year line up. Not auto-merged — deciding two files are "the
  same review" is a judgement.

### Schema — migration 0064

* `ALTER TABLE sar_documents ADD COLUMN discovered_via TEXT;`
  values `national_library` | `scie_library` | `sab_website`. Backfill the
  existing rows from `source_url` / `library_year`. Surface it in the SAR
  export beside `sab_name_source`.
* `sab_site_crawls` (optional, like `council_spend_files`): one row per
  board — `last_crawled`, `pages_fetched`, `docs_found`, `status`
  (`ok` | `no_sars_found` | `unreachable` | `robots_disallowed`) — so
  "which boards yield nothing" is queryable rather than only inferable from
  review items.

### New review-item types

`sab_website_unknown`, `sab_site_unreachable`, `sab_site_robots_disallowed`,
`sab_no_sars_found`, `sab_site_sar_candidate`, `sab_site_sar_board_mismatch`,
`possible_duplicate_of_library_sar`.

### Execution

Parallel across boards (`fetch_in_parallel`, `worker_count`), as `m24`.
`supports_since = False` — SAR pages carry no per-document date, and the
crawl is bounded, so a full pass every run is affordable: ~142 boards ×
~20 fetches ≈ 2,800 requests, ~10–15 min at 8 hosts in flight and the
standard per-host interval.

## Cost / yield estimate

| | |
|---|---|
| Sites crawled per run | ~142 |
| Requests per run | ~2,800 (bounded) |
| Wall time | ~10–15 min |
| Boards expected to yield a findable SAR page | ~40–60% |
| Net-new documents beyond the ~840 library set | order of 50–150 (rough) |
| Boards recorded `sab_no_sars_found` | the rest — a fact about the board |

## §7 — decisions for the project owner

1. **Auto-ingest with the "board names itself" filter, or review-queue-gated
   for everything?** Recommendation: the hybrid in *Auto-ingest vs.
   confirm* above.
2. **England-only, or all four nations?** Recommendation: England-only,
   consistent with `build_sab_index` and the campaign scope.
3. **`sab_site_crawls` state table — build it, or lean on review items
   alone?** Recommendation: build it; "which boards yield nothing" is worth
   one clean query.
4. **Effort:** ~1–2 days for the module, migration, tests and the first
   round of per-board path tuning, then ongoing tuning as real sites push
   back.
