"""scrapy.md Phase 2 pilots: one crawl-heavy module ported onto the Scrapy
transport for comparison against its existing HTTPX implementation.

Nothing here writes to the database, and nothing here is wired into
`pipeline/registry.py` — a pilot is a parallel, comparison-only
implementation, not a replacement. The existing HTTPX module (`pipeline
run m32_sab_site_reviews`, for example) stays the one that actually
collects evidence until a pilot's results have been reviewed and a
separate, explicit migration task promotes it (scrapy.md Phase 4).
"""
