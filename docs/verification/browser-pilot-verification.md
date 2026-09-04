# scrapy-playwright browser pilot — verification (scrapy.md Phase 3)

Status: offline scaffolding complete and live pages watched on 2026-09-04
(Europe/London). Neither selected page showed a JavaScript-dependency signal;
the Windows event-loop issue in the `scrapy-playwright` integration was fixed
and both live rechecks now produce derived DOM captures.

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

## Live measurement: watched result (2026-09-04)

The watched pages were deliberately chosen m09/m10 candidates: Liverpool's
JSNA landing page and Kent's ModernGov drug-search results page. HTTPX was
measured as the production baseline; a fresh system Chromium 152.0.7977.76
process was then watched with Playwright, including its network event log.
The parser counts below are the module parsers' useful-content signal, not a
claim that every byte in the rendered DOM is evidence.

| Page | HTTPX baseline | Direct Chromium watch | Useful-content result |
| --- | --- | --- | --- |
| m09 Liverpool `/jsna` | 200; 23,019 bytes; 1.234 s; 68.9 MiB RSS; SHA-256 `b27636c7826948a3f97d176e9c52fddbe4e4da0c35f85758a708d4d6ae5d34db` | 200; 4.844 s; 775.7 MiB RSS; 22 requests, 1 failed | m09 parser: 2 candidates from raw HTML and 2 from rendered DOM; no JS-dependency signal |
| m10 Kent ModernGov search | 200; 31,706 bytes; 2.406 s; 69.0 MiB RSS; SHA-256 `bf40920231751bbbbde05991b9d519ae5ad0e874508ccfde932cfec24a788bc7` | 200; 9.906 s; 761.7 MiB RSS; 20 requests, 3 failed | m10 parser: 10 results from raw HTML and 10 from rendered DOM; no JS-dependency signal |

The rendered DOM was larger (m09 42,685 UTF-8 bytes vs 22,687 raw HTML;
m10 64,334 vs 31,540), but it did not reveal additional candidates/results.
Both pages therefore appear server-rendered for the useful content tested;
neither is a browser-migration candidate on this evidence. Chromium's peak
RSS was about 0.76–0.78 GiB and its navigation was about 2–4 times slower,
with 20–22 subrequests versus one HTTPX request per page.

The comparison wrapper `fetch_via_scrapy_playwright()` was initially unable
to return a derived DOM because the Windows Scrapy callback loop directly
awaited a Page owned by scrapy-playwright's dedicated Proactor loop. The
wrapper now schedules Page operations on the owning loop, and the watched
recheck succeeded for both pages:

| Page | Original response | Derived DOM |
| --- | --- | --- |
| m09 Liverpool `/jsna` | 200; 23,019 bytes; SHA-256 `b27636c7826948a3f97d176e9c52fddbe4e4da0c35f85758a708d4d6ae5d34db` | `data/derived/authority_websites_cdp/fa7dcae4b0c0c082c4189fc24e69f9a72e9c7de9b72fdead3fd866635ca511c9.html`, `rendered_dom` |
| m10 Kent ModernGov search | 200; 31,706 bytes; SHA-256 `bf40920231751bbbbde05991b9d519ae5ad0e874508ccfde932cfec24a788bc7` | `data/derived/council_committee_systems/6d13730aa606542988faa8507013c977905ef4a47005b8f1cab1b55eb011b369.html`, `rendered_dom` |

The derived captures were written to the isolated, uncommitted live-recheck
archive and are not committed. The direct browser measurements remain the
relevant migration evidence: neither page gained useful parser results after
rendering.

No live browser measurement was added to CI. The raw captures remain in the
isolated, uncommitted `data/live-verification/` worktree directory only.

## What this does not establish

Per scrapy.md's own caution: this watched result does not justify migrating
any m09/m10 page onto the browser leg in production. The measured pages did
not show an actual JavaScript dependency, and the wrapper's render-leg
integration issue must be resolved separately before another browser pilot.
