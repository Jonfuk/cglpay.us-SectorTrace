# scrapy-playwright browser pilot — verification (scrapy.md Phase 3)

Status: offline scaffolding complete and fixture-verified against a real
browser. The live measurement step scrapy.md's Phase 3 actually asks for
(known browser-dependent m09/m10 pages, HTTPX vs. Scrapy vs.
scrapy-playwright, elapsed time, memory, request volume, JS-dependent vs.
merely bot-blocked) has not been run — see
[Live measurement](#live-measurement-not-run-in-this-session) below for why
and how to run it.

## What this is

scrapy.md's Phase 3 ("browser pilot") adds an experimental
`scrapy-playwright` leg on top of the Scrapy transport built in Phase 0/1.
It is off by default behind two independent flags
(`Settings.scrapy_enabled` and `Settings.scrapy_playwright_enabled`), is not
called from anywhere in the pipeline, and is not wired into
`pipeline/registry.py` or any module. Nothing here changes production
collection.

## What changed

- **`pipeline/transports/types.py`** — `TransportResult` gained
  `derived_archive_ref`/`derived_kind`, typed fields for a browser-rendered
  DOM (or any future derived artefact from the same fetch attempt), kept
  deliberately separate from `body`/`payload_sha256`/`raw_archive_ref` and
  never required by `require_provenance()` — most transports have no
  derived artefact, and that is a complete result, not a missing one.
- **`pipeline/archive.py`** — `archive_derived_artifact()` (new, additive):
  writes a derived artefact under `Settings.derived_archive_dir`,
  content-addressed exactly like the raw archive, through its own small
  function rather than widening `FilesystemArchive`/`S3Archive` (which are
  baked to the `data/raw/...` shape).
- **`pipeline/config.py`** — `scrapy_playwright_enabled` (default `False`,
  independent of `scrapy_enabled`) plus bounds: `scrapy_playwright_max_contexts`,
  `scrapy_playwright_max_pages_per_context`,
  `scrapy_playwright_navigation_timeout_seconds`,
  `scrapy_playwright_memory_limit_mb`, and
  `scrapy_playwright_executable_path` (pins a specific Chromium binary —
  needed in this checkout's own sandbox, where the installed `playwright`
  package's automatic version-matched browser lookup fails against the
  pre-provisioned build).
- **`pipeline/transports/browser_pilot.py`** (new) — the pilot itself. See
  its module docstring for the design in full; in brief:
  - **Two fetches, not one.** `scrapy-playwright`'s download handler
    populates `response.body` from `page.content()` (the DOM *after*
    JavaScript runs), not the original bytes the server sent — confirmed
    directly against this checkout's pre-installed Chromium. So
    `fetch_via_scrapy_playwright()` calls the ordinary, no-browser
    `fetch_via_scrapy()` for the original response, and a second,
    browser-only crawl for the rendered DOM, merging the two by URL. The
    original `TransportResult` is untouched except for gaining
    `derived_archive_ref`/`derived_kind="rendered_dom"` where rendering
    succeeded.
  - Bounded and monitored: `PLAYWRIGHT_MAX_CONTEXTS`/
    `PLAYWRIGHT_MAX_PAGES_PER_CONTEXT` default to 1/1; `MEMUSAGE_ENABLED`
    is on with `MEMUSAGE_LIMIT_MB` from `Settings`.
  - A page is always closed, in both the success (`parse`) and failure
    (`on_failure`) paths.
  - Reuses `drain_subprocess()` from `scrapy_transport.py` for the
    render-only crawl's subprocess pattern (same reactor-restart
    constraint as the rest of this package).
  - Deliberately excludes `ProvenanceArchiveMiddleware` (would mislabel the
    rendered DOM as source bytes) and `RetryWithBackoffMiddleware`
    (retrying a partially-rendered navigation is a real design question
    this scaffolding phase does not answer) from the render-only crawl.
- **`tests/test_transports_browser_pilot.py`** (new) — 9 tests, run against
  both a real local `http.server` fixture and this checkout's real,
  pre-installed Chromium (`/opt/pw-browsers/chromium`) — not a mocked
  Playwright API. Skipped outright if `scrapy`/`scrapy_playwright` are not
  installed or the pinned Chromium binary is absent. The navigation-timeout
  test caught a real bug while writing it: `_run_render_crawl` had passed
  `PLAYWRIGHT_NAVIGATION_TIMEOUT` to Scrapy's settings, but the installed
  scrapy-playwright (0.0.48) reads `PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT` —
  the wrong key was silently ignored, so a deliberately short timeout in the
  first version of this test kept passing anyway (Playwright's own 30s
  default absorbed a 2s fixture delay). Fixed by reading `handler.py`
  directly to find the actual key name, then re-confirming the test fails
  without the fix and passes with it.

## Fixture-verified results

All against a real browser, not a mock:

| Scenario | Result |
| --- | --- |
| Feature flags off (either `scrapy_enabled` or `scrapy_playwright_enabled`) | Refuses to run (`ScrapyDisabled`/`ScrapyPlaywrightDisabled`), same as the transport itself |
| `scrapy_playwright` not installed | Refuses to run (`ScrapyPlaywrightNotInstalled`), checked separately from `scrapy` itself |
| A page whose script mutates the DOM on load | `body`/`payload_sha256`/`raw_archive_ref` are the exact pre-JS bytes; a *separate* `derived_archive_ref` (different hash) holds the post-JS DOM, `derived_kind="rendered_dom"` |
| A bare TCP connection failure (both legs) | One labelled failure per URL, no derived artefact, no hang |
| A navigation that exceeds `PLAYWRIGHT_NAVIGATION_TIMEOUT` while the original fetch still succeeds | Original result comes back intact; render leg gives up cleanly, page still closes, no derived artefact, no hang |
| No URLs | Empty list, no crawl started |

Full provenance (`requested_url`, `retrieved_at`, `payload_sha256`,
`raw_archive_ref`) verified via `TransportResult.require_provenance()` on
every successful fetch, exactly as the Phase 0/1 transport and the Phase 2
pilot are.

**Validation commands and results** (this branch, `codex/scrapy-transport`):

```
uv run python -m pytest tests/test_transports_browser_pilot.py tests/test_transports_types.py \
  tests/test_transports_httpx.py tests/test_transports_scrapy.py -q
# 64 passed

uv run ruff check pipeline tests
# All checks passed!

uv run python -m compileall -q pipeline tests
# clean
```

Full offline suite (`uv run python -m pytest -q`): no new failures relative
to the baseline recorded when the Scrapy transport landed (the same
pre-existing, independently-verified-against-clean-`beta` failures —
SQLite-vs-PostgreSQL schema mismatches in a handful of unrelated fixtures —
unchanged in count).

## Live measurement: not run in this session

scrapy.md's Phase 3 asks the pilot to be pointed at a small number of known
browser-dependent pages from `m09`/`m10` and measured against HTTPX:
page success, rendered-content correctness, original-response completeness,
elapsed time, peak memory, request volume per navigation, and — critically —
whether a page is actually JavaScript-dependent or merely bot-blocked
(scrapy.md is explicit that a browser succeeding is not itself evidence of
either).

**It could not be run in this session**: the same outbound network
restriction documented in `docs/verification/m32-scrapy-pilot-verification.md` for
Phase 2 applies here — this session's network reaches only package
registries and Anthropic's own API. No m09/m10 page was fetched, rendered,
or measured against; nothing left this session's network boundary.

**To run it**, from a machine or session with ordinary outbound network
access, with `SCRAPY_ENABLED=true`, `SCRAPY_PLAYWRIGHT_ENABLED=true`, a
real `CONTACT_EMAIL`, and a Chromium binary available (either
`playwright install chromium` or a pinned `scrapy_playwright_executable_path`
as this sandbox uses):

```python
import time

from pipeline.config import get_settings
from pipeline.http import PipelineHTTPClient
from pipeline.transports.browser_pilot import fetch_via_scrapy_playwright

settings = get_settings()

# Replace with a small, deliberately chosen set of pages already known or
# suspected to need JavaScript to render their useful content — not an
# arbitrary sample. scrapy.md: "Select a small number of known
# browser-dependent pages from m09/m10."
CANDIDATE_URLS = [
    # "https://example-m09-source/...",
]

# HTTPX baseline — what production already does.
client = PipelineHTTPClient("m09_or_m10_source_system", settings=settings)
httpx_results = {}
for url in CANDIDATE_URLS:
    started = time.monotonic()
    httpx_results[url] = (client.get(url), time.monotonic() - started)
client.close()

# Browser pilot.
started = time.monotonic()
browser_results = fetch_via_scrapy_playwright(
    CANDIDATE_URLS, source_system="m09_or_m10_source_system", settings=settings)
elapsed = time.monotonic() - started
```

For each URL, record: whether HTTPX's response already contains the useful
content (if so, the page did not need a browser at all); whether the
rendered DOM contains content the original bytes lack (a real
JavaScript-dependency signal) or is byte-identical apart from
boilerplate (a sign the site was merely slow or transiently blocking,
not JS-dependent); elapsed time and peak RSS for the browser leg versus
the HTTPX baseline; and how many subrequests one navigation generated
(Chromium's own network log, or `PLAYWRIGHT_ABORT_REQUEST` if asset
blocking is added later). Append the results to this document before
treating any page as a genuine browser-migration candidate.

## What this does not establish

Per scrapy.md's own caution: a pilot passing its offline acceptance gates
is not a decision to migrate any m09/m10 page onto the browser leg in
production, and "the browser returned a page" is explicitly not sufficient
justification on its own — the live measurement above, showing an actual
JavaScript dependency rather than a transient block, is required first.
That measurement, and any migration decision built on it, is separate work
this phase does not do.
