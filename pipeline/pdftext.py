"""Extracted PDF page text, cached by the hash of the bytes it came from.

Measured on this project's own archived accounts PDFs, pdfplumber takes 16–23
seconds to extract text from one document — and the cost tracks page
complexity rather than file size, so a 0.9 MB report can be slower than a
9.9 MB one. It is comfortably the most expensive thing the pipeline does.

It was also being done twice. m03_charity_finance opens each filed accounts
PDF to find the staff-costs note; m14_annual_reports then opens *the same
archived file again* to index workforce passages. Two full extractions per
document, for text that cannot have changed in between.

The cache is keyed on `payload_sha256` — the hash already recorded in the
provenance of every row that came from the document. That is the point: a
cache hit is not "probably the same file", it is provably the same bytes, by
the same digest the audit trail is built on. A path-keyed or mtime-keyed cache
would be a guess, and this pipeline does not do guesses about identity.

Cached text lives beside the raw archive, under `data/text/`, for the same
reasons `data/raw/` does: it is derived, regenerable, gitignored, and far too
large to belong in the warehouse. Deleting it costs time on the next run and
nothing else.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import structlog

from pipeline.meters import DISK

log = structlog.get_logger()


def cache_dir(settings) -> Path:
    """`data/text/`, alongside `data/raw/`."""
    return Path(settings.raw_archive_dir).parent / "text"


def cache_path(settings, source_system: str, sha256: str) -> Path:
    return cache_dir(settings) / source_system / f"{sha256}.json"


def _read_cached(path: Path) -> list[str] | None:
    try:
        pages = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A truncated or corrupt cache file is not worth a failed run: it is
        # derived data, so the correct response is to re-extract and overwrite.
        return None
    if not isinstance(pages, list) or not all(isinstance(p, str) for p in pages):
        return None
    return pages


def _write_cached(path: Path, pages: list[str]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write-then-rename, so an interrupted run cannot leave a half-written
        # cache file that a later run would read as a short document.
        temporary = path.with_suffix(".json.partial")
        payload = json.dumps(pages)
        temporary.write_text(payload, encoding="utf-8")
        DISK.add(len(payload.encode("utf-8")))
        temporary.replace(path)
    except OSError as exc:      # pragma: no cover - disk full, permissions
        log.warning("pdftext.cache_write_failed", path=str(path), error=str(exc))


def page_texts(settings, source_system: str, sha256: str,
                source: bytes | str | Path) -> list[str]:
    """Text of every page, in order, extracted once per unique document.

    `source` is the PDF bytes or a path to them. `sha256` must be the digest
    of exactly those bytes — it is the cache key, and passing anything else
    would associate one document's text with another's provenance.
    """
    import pdfplumber

    path = cache_path(settings, source_system, sha256)
    if sha256:
        cached = _read_cached(path)
        if cached is not None:
            log.debug("pdftext.cache_hit", sha256=sha256[:12], pages=len(cached))
            return cached

    opener = io.BytesIO(source) if isinstance(source, bytes) else str(source)
    with pdfplumber.open(opener) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]

    if sha256:
        _write_cached(path, pages)
    log.debug("pdftext.extracted", sha256=(sha256 or "")[:12], pages=len(pages))
    return pages


def numbered_pages(settings, source_system: str, sha256: str,
                    source: bytes | str | Path) -> list[tuple[int, str]]:
    """`page_texts` as (index, text) pairs, the shape most callers want."""
    return list(enumerate(page_texts(settings, source_system, sha256, source)))
