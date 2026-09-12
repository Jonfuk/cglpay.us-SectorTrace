# Scrapy module pilots — verification

This document records the adapter-only implementation for the next three
Scrapy candidates in `scrapy.md` Phase 4. The production collectors remain
HTTPX-backed. The pilots do not write evidence tables, and no CI test fetches
a real source.

## Implemented adapters

| Module | Scrapy adapter | Preserved behavior |
| --- | --- | --- |
| `m22_provider_pay_pages` | `pipeline/transports/pilots/m22_provider_pay_pages_pilot.py` | registered pages, same-host vocabulary links, ten-page followed-page ceiling, existing pay parser |
| `m24_council_spend` | `pipeline/transports/pilots/m24_council_spend_pilot.py` | bounded path probes, same-host spend-file links, three-file authority ceiling, existing CSV/XLSX/ODS parsers |
| `m28_sar_reports` | `pipeline/transports/pilots/m28_sar_reports_pilot.py` | library/SCIE index parsing, URL de-duplication, document-extension gate, existing index and URL parsers |

Each adapter runs in the same spawned-process model as the existing Scrapy
transport, archives exact response bytes, returns `TransportResult` objects,
and exposes explicit robots, unavailable, timeout and parser outcomes. The
`retain_bodies=False` option allows watched runs to keep provenance and archive
references without accumulating document bodies in the result queue.

## Rate policy

The shared Scrapy settings now enable AutoThrottle whenever Scrapy itself is
explicitly enabled:

- `DOWNLOAD_DELAY = 0.0` — no inherited two-second fixed floor;
- `AUTOTHROTTLE_START_DELAY = 1.0` seconds;
- `AUTOTHROTTLE_TARGET_CONCURRENCY = 0.5`;
- `AUTOTHROTTLE_MAX_DELAY = 60.0` seconds;
- `CONCURRENT_REQUESTS_PER_DOMAIN = 1`.

The custom retry middleware still applies exponential backoff and numeric
`Retry-After`; the custom robots middleware and provenance archive middleware
remain active. HTTPX's existing per-host rate policy is unchanged.

## Offline validation

```text
uv run ruff check pipeline/transports pipeline/config.py tests/test_scrapy_pilot_adapters.py
# All checks passed!

uv run python -m compileall -q pipeline/transports pipeline/config.py tests/test_scrapy_pilot_adapters.py
# passed

uv run python -m pytest tests/test_scrapy_pilot_adapters.py -q
# 5 passed
```

The tests use loopback fixture servers and `tmp_path` archives. They cover
default-off behavior, the shared rate policy, m22 link and pay parsing, m24
two-phase discovery and file parsing, and m28 index de-duplication plus
document provenance.

## Still open

No watched live measurements have been run for these three adapters yet.
Before any production cutover, run one manually watched sample per module and
record request counts, elapsed time, peak memory, robots/retry outcomes,
archive hashes and parity with the HTTPX collector. Those measurements must
remain verification records, not CI tests.
