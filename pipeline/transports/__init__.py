"""Transport-neutral collection contract (scrapy.md Phase 0).

Every collector eventually asks the same three questions of whatever fetched
a page for it: did a response come back, what exactly were the bytes, and can
those bytes be produced again from the archive. `types.TransportResult` is
that contract, independent of which transport answered it.

`pipeline.http.PipelineHTTPClient` remains the transport HTTPX modules call
directly — nothing here changes its behaviour. `httpx.fetch_via_httpx()`
wraps it to prove the *same* fetch can be read through the contract, and
`scrapy_transport.py` is the second, optional implementation (scrapy.md
Phase 1). Neither is wired into `pipeline.registry`/`pipeline.runner`; a
production module that has not been explicitly migrated keeps calling
`PipelineHTTPClient` exactly as before.
"""
