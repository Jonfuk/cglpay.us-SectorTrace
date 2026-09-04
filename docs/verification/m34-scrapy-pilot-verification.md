# Module 34 Scrapy pilot verification

Date: 2026-09-04

## Scope and persistence decision

The first crawl-heavy follow-up uses `m34_icb_board_papers`. The selected
persistence model is adapter-only: the pilot returns m34-shaped fetch results
for comparison, with no staging-table migration and no writes to
`icb_board_paper_candidates`, `icb_site_crawls` or review tables. The existing
HTTPX-backed `m34.run()` remains the production collector.

The pilot is implemented in
`pipeline/transports/pilots/m34_icb_board_papers_pilot.py`. It reuses m34's
bounded path list, governance link rules, date cut-off, document ceiling and
candidate metadata. Scrapy is only used for the fetch/archive leg in a fresh
subprocess; document parsing and evidence persistence are intentionally out of
scope.

## Offline parity result

`tests/test_m34_scrapy_pilot.py` runs both crawlers against the same local
socket fixture. It verifies:

- the candidate URL, link text, index flag, discovery method, status and
  payload SHA-256 agree with HTTPX;
- the Scrapy result carries complete provenance and its archive bytes are
  byte-identical to the fixture payload;
- the pilot is disabled unless `SCRAPY_ENABLED` is explicitly enabled.

Result: **2 passed** (`uv run python -m pytest tests/test_m34_scrapy_pilot.py -q`).
No test fetches a live source or writes a database row.

## Phase 2 live gate

The first run below exposed high memory because the comparison mode retains
document bodies. The pilot now has an explicit low-memory fetch/archive mode:
the middleware still archives the exact response, while the returned result
retains only its provenance metadata.

## Watched live sample

Run date: 2026-09-04. Target:
`https://notts.icb.nhs.uk/about-us/our-icb-board/`. The sample used the
adapter-only pilot with the existing m34 bounds, a two-second Scrapy delay and
one request per host. It was run manually from a one-off harness; it is not a
CI test and did not write the database.

Observed result:

- elapsed time: 127.90 seconds;
- Scrapy requests: 49 (20 bounded path probes plus 29 documents);
- pages fetched: 3;
- documents fetched: 29;
- ceiling reached: no;
- robots blocked / unreachable: no / no;
- review items: none;
- raw archive files: 47, totalling 297,000,876 bytes;
- candidate payload hashes: 29 unique hashes;
- provenance checks: 29/29 passed;
- archived bytes matched fetched bytes: 29/29 passed;
- peak monitored working set across the runner process tree: approximately
  766 MB.

The fetch and provenance gates passed, but the memory observation is material:
the pilot retains fetched results until it returns the crawl, and this sample
held several large board packs. At that point Phase 2 was **not approved for a
production transport cutover**; the low-memory change and watched repeat are
recorded below.

## Watched repeat with low-memory mode

Run date: 2026-09-04, same target and rate policy, with
`retain_bodies=False`.

- elapsed time: 127.59 seconds;
- Scrapy requests: 49;
- pages fetched: 3;
- documents fetched: 29;
- review items: none;
- bodies retained in returned results: no;
- candidate payload hashes: 29 unique hashes;
- archive hash checks: 29/29 passed;
- raw archive files: 47, totalling 297,000,876 bytes;
- peak monitored working set across the runner process tree: approximately
  122.8 MB.

This repeat passes the watched fetch, ordering, provenance and memory gates
for the fetch-only adapter. The default parity mode remains intentionally
body-retaining for parser comparisons and measured 766 MB on the first run;
that mode must not be used as an unbounded production crawl. A production
cutover still requires an explicit parser/finalisation design that preserves
the low-memory property, followed by owner review.
