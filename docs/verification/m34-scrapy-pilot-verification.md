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

## Remaining Phase 2 gate

The next action is a manually watched live m34 sample for the verified
Nottingham and Nottinghamshire ICB board page. Record request count, pages,
documents, elapsed time, peak memory, failures, candidate ordering and archive
hash/provenance checks before considering any production transport change.

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
held several large board packs. Phase 2 is therefore **not approved for a
production transport cutover yet**. The next engineering action is to profile
and reduce peak memory (or tighten the pilot's document/response retention
boundary), then repeat the watched sample before any writer or transport
default changes.
