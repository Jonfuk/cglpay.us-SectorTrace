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
