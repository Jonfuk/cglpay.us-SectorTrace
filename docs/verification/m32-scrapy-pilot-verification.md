# m32_sab_site_reviews Scrapy pilot — verification (scrapy.md Phase 2)

Status: offline pilot complete and live-sample measured on 2026-09-04
(Europe/London). The bounded live document crawl passed parity; its initial
homepage encoding discrepancy was fixed and rechecked below. The pilot still
remains comparison-only pending owner review.

## What this is

scrapy.md's Phase 2 ("first crawl pilot") ported `m32_sab_site_reviews`'s
per-board crawl onto the Scrapy transport built in Phase 0/1, as a parallel,
comparison-only implementation — not a replacement. The existing HTTPX
module (`pipeline/modules/m32_sab_site_reviews.py`, run via
`pipeline run m32_sab_site_reviews`) is unchanged in behaviour and remains
the only one that writes evidence. Nothing here is wired into
`pipeline/registry.py`.

## What changed

- **`pipeline/modules/m32_sab_site_reviews.py`** — behaviour-preserving
  refactor. The hybrid-ingest gate that used to be inline in `run()` (board
  mismatch / candidate / duplicate-of-library / ingest) is now
  `classify_document()`, a pure function with no database access. `run()`
  calls it and branches on the result exactly as before; the existing 14
  tests in `tests/test_m32_sab_site_reviews.py` pass unchanged, plus 6 new
  ones test `classify_document` directly.
- **`pipeline/transports/scrapy_transport.py`** — two small extractions so
  the pilot could reuse them rather than duplicate them: `drain_subprocess()`
  (the deadlock-avoiding queue-drain loop, previously inlined in
  `fetch_via_scrapy`) and `transport_result_from_response`/
  `transport_result_from_failure` (the response/failure → `TransportResult`
  conversion, previously inlined in `_BoundedFetchSpider`). Both are
  behaviour-preserving; the full `test_transports_scrapy.py` suite (37 tests)
  passes unchanged.
- **`pipeline/transports/pilots/m32_sab_site_reviews_pilot.py`** (new) — the
  pilot itself. See its module docstring for the design in full; in brief:
  - Reuses `m32.SAR_PATHS`, `MAX_SUBPAGES_PER_SAB`, `MAX_PAGES_PER_SAB`,
    `MAX_DOCS_PER_SAB`, `sar_links_on_page`, `sar_subpages_on_page`, and
    `classify_document` directly (imported, not reimplemented).
  - Expresses `crawl_board`'s two phases (discover pages, then fetch the
    deduplicated document set) through Scrapy's `spider_idle` signal —
    schedule the document requests once the page-discovery scheduler is
    idle, `raise DontCloseSpider` to keep the crawl open for them.
  - Splits fetching (subprocess, via the same robots/guard/retry/provenance
    middleware stack Phase 0/1 built) from body-text extraction and
    classification (parent process, pure, no database) — see the module
    docstring's "Network vs. classification" section for why.
  - Writes nothing to the database. `fetch_m32_pilot()` returns a
    `PilotCrawl`; `classify_pilot_documents()` turns it into classified
    `PilotDocument`s. A caller with a connection supplies `sab_index` and
    `existing_sha` itself — the pilot has no connection to derive them from.
- **`tests/test_m32_scrapy_pilot.py`** (new) — 8 tests, all against a real
  local `http.server` fixture (not `httpx_mock`; the Scrapy crawl runs in a
  subprocess that cannot see a mock in this process).

## Offline parity results

Both paths call the *same* `sar_links_on_page`, `sar_subpages_on_page` and
`classify_document` — so the only thing a parity test can actually be
checking is discovery: does the Scrapy pilot's two-phase, signal-driven
crawl find the same documents, in the same `from_index` state, with the
same bytes, as `crawl_board`'s sequential one does. It does, on every
scenario mirrored from `test_m32_sab_site_reviews.py`:

| Scenario | HTTPX (`crawl_board`) | Scrapy pilot | Agree? |
| --- | --- | --- | --- |
| Strong link, board-consistent text | 1 candidate, `ingest` | 1 candidate, `ingest` | yes — URLs, SHA-256s and outcome all match |
| Weak link, not on an index page | 1 candidate, `candidate` | 1 candidate, `candidate` | yes |
| Link naming a different board | 1 candidate, `board_mismatch` | 1 candidate, `board_mismatch` | yes |
| One-hop subpage discovery | 1 candidate via subpage, `from_index=True`, `ingest` | same | yes |
| robots.txt disallows the whole site | 0 pages fetched, `robots_blocked=True` | same | yes |
| No SAR links found anywhere | 0 candidates, `pages_fetched >= 1` | same | yes |

Plus: full provenance (`requested_url`, `retrieved_at`, `payload_sha256`,
`raw_archive_ref`) on every fetched document, verified via
`TransportResult.require_provenance()`; the pilot refuses to run while
`SCRAPY_ENABLED` is unset, same as the transport itself.

One genuine, expected difference surfaced and is documented in the test
file: httpx and Scrapy disagree on whether a literal space in a URL path
gets percent-encoded before the request is sent (httpx sends it literally;
Scrapy encodes it). Both are defensible HTTP client behaviour; the fixture
server and the test assertions normalise with `urllib.parse.unquote()` so
the comparison is about the document found, not the transport's URL string
formatting.

**Validation commands and results** (this branch, `codex/scrapy-transport`):

```
uv run python -m pytest tests/test_m32_sab_site_reviews.py tests/test_m32_scrapy_pilot.py \
  tests/test_transports_types.py tests/test_transports_httpx.py tests/test_transports_scrapy.py -q
# 83 passed

uv run ruff check pipeline tests
# All checks passed!
```

Full offline suite (`uv run python -m pytest -q`): no new failures relative
to the baseline recorded when the Scrapy transport landed — the same
pre-existing failures (verified independently against a clean `beta`
worktree, unrelated to any of this work: SQLite-vs-PostgreSQL schema
mismatches in a handful of test fixtures) and the same errors, unchanged in
count.

## Live sample: watched result (2026-09-04)

The watched target was **Kent & Medway Safeguarding Adults Board**
(`https://www.kmsab.org.uk`), using the existing `/assets/` robots exception.
The run used the production HTTPX crawl and the comparison-only
`fetch_m32_pilot()` crawl with the same bounded paths and document limits. The
measurement harness wrote its uncommitted raw captures under the isolated
worktree's `data/live-verification/`; no database rows were written and those
captures are not part of CI or the beta commit.

| Metric | HTTPX production crawl | Scrapy pilot |
| --- | ---: | ---: |
| Elapsed | 142.547 s | 196.828 s |
| Peak process RSS | 85.9 MiB | 247.2 MiB |
| Successful content requests | 73 | 77-estimate (37 pages + 40 documents) |
| HTML pages fetched | 33 | 37 |
| Candidate documents | 40 | 40 |
| robots-blocked / unreachable / timed out | no / no / — | no / no / no |

Parity across the 40 candidate documents was **yes** for document URLs,
SHA-256 payloads, `from_index`, and classification outcomes. The first run
found that provenance ran before Scrapy's `HttpCompressionMiddleware`, so the
homepage was archived as 5,654 gzip bytes instead of the 15,599 decoded bytes
used by HTTPX. `ProvenanceArchiveMiddleware` now runs after decompression
(priority 500); a watched homepage recheck returned 15,599 bytes with the
same SHA-256 as HTTPX:
`8e75f1e43dfbf246e594ed65fe9861cdab0eff903af1c7f8babebc76efd83105`.
The fix is covered by an offline gzip fixture test.

Versions: Scrapy 2.18.0, scrapy-playwright 0.0.48, Playwright 1.62.0. The
pilot was invoked explicitly with `SCRAPY_ENABLED` enabled; this remains a
comparison-only measurement and is not wired into the registry or CI.

## What this does not establish

Per scrapy.md's own caution: a pilot passing its acceptance gates is not by
itself a decision to migrate `m32_sab_site_reviews` onto Scrapy in
production. That is Phase 4, a separate task, after the live-sample step
above has actually run and been reviewed.
