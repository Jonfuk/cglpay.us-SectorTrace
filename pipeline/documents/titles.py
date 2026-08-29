"""Deriving a human-readable display title for a document, basis recorded.

`document_records.title` is whatever the collecting module handed the
document service: a CDP document's link text (usually good), an archived
object's hash-like filename (useless to a reader), or nothing at all. The
portal was rendering `title OR filename`, so a search over the
~27k-document archive returned "a3f91c…pdf" as the name of a result.

`derive()` picks a display title by a fixed precedence and returns which
rung it came from, so the value stays auditable and is never mistaken for
verbatim source text:

    source_label  the collecting module's own title
    pdf_metadata  the PDF's /Title (only seen at parse time)
    heading       the first usable heading in the active parsed version
    filename      a de-slugified archived-object filename (last resort)
    unknown       nothing usable — the caller keeps its own raw fallback

Pure: no database, no IO. The caller assembles the four inputs.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

# The order is the contract, and it is a claim about identity, not quality:
# the source's own label is the most trustworthy name for the document, and a
# filename we had to de-slugify is the least. `_BASIS_RANK` lets a caller keep
# the stronger basis when it re-derives with fewer signals.
TITLE_BASES = ("source_label", "pdf_metadata", "heading", "filename", "unknown")
_BASIS_RANK = {basis: rank for rank, basis in enumerate(TITLE_BASES)}

_MAX_LEN = 200
_WS_RE = re.compile(r"\s+")
_EXT_RE = re.compile(r"\.[A-Za-z0-9]{1,5}$")
_SLUG_SEP_RE = re.compile(r"[_\-\s]+")
_HEX_RUN_RE = re.compile(r"^[0-9a-f]{16,}$", re.IGNORECASE)
_UUIDISH_RE = re.compile(r"^[0-9a-f]{8,}(?:[-_][0-9a-f]{3,}){2,}$", re.IGNORECASE)
# A real name has a run of at least three letters somewhere — enough to reject
# "TA1", "v2.3", "12-04-a" while keeping "Q3 staffing" or "Kent JSNA 2024".
_LETTERS_RE = re.compile(r"[A-Za-z]{3,}")
# Running-header artefacts that are technically headings but name nothing.
_PLACEHOLDER_RE = re.compile(
    r"^(page|slide|section|chapter|part|figure|table|appendix|annex)\s*\d+$",
    re.IGNORECASE)

# Words that are technically a title but tell a reader nothing. Matched only
# when they are the *entire* candidate, so "Final report on staffing" is kept.
_GENERIC = {
    "document", "documents", "download", "attachment", "attachments",
    "untitled", "file", "final", "draft", "copy", "pdf", "doc", "report",
    "minutes", "agenda", "appendix", "annex", "cover", "cover sheet",
}


def rank_of(basis: str) -> int:
    """Lower is stronger. Unknown/unlisted bases sort last."""
    return _BASIS_RANK.get(basis, len(TITLE_BASES))


def _normalise(value: object) -> str | None:
    if value is None:
        return None
    text = _WS_RE.sub(" ", str(value).replace("\x00", " ")).strip()
    text = text.strip("\"'　 \t.-_·|")
    if not text:
        return None
    if len(text) > _MAX_LEN:
        text = text[:_MAX_LEN].rstrip() + "…"
    return text or None


def _is_identity(text: str | None) -> bool:
    """True when `text` reads as a name a person would recognise, rather than
    a hash, a bare reference number or a generic filler word."""
    if not text:
        return False
    if text.lower() in _GENERIC:
        return False
    if _PLACEHOLDER_RE.match(text):
        return False
    compact = text.replace(" ", "")
    if _HEX_RUN_RE.match(compact) or _UUIDISH_RE.match(compact):
        return False
    if compact.isdigit():
        return False
    # A run of real letters — rejects "2024-04-01", "TA1", "v2.3".
    return _LETTERS_RE.search(text) is not None


def _from_filename(filename: str | None) -> str | None:
    if not filename:
        return None
    base = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem = _EXT_RE.sub("", base)
    # A de-slugified filename is a guess at a title: separators to spaces,
    # collapse, trim. Casing is left as the source had it — "Kent-JSNA-2024"
    # must not become "Kent Jsna 2024".
    return _normalise(_SLUG_SEP_RE.sub(" ", stem))


def _first_usable_heading(headings: Iterable[object]) -> str | None:
    for raw in headings or ():
        candidate = _normalise(raw)
        if _is_identity(candidate):
            return candidate
    return None


def derive(*, source_title: object = None, pdf_title: object = None,
           headings: Iterable[object] = (), filename: str | None = None
           ) -> tuple[str | None, str]:
    """Return `(display_title, title_basis)`.

    `headings` is an ordered iterable of heading-element texts from the active
    parse; the first one that reads as a real name wins. Every rung is
    normalised (whitespace, surrounding quotes, a length cap) and screened by
    `_is_identity`, so a hash-like filename is rejected and the result is
    `(None, "unknown")` rather than a title nobody can read.
    """
    source = _normalise(source_title)
    if _is_identity(source):
        return source, "source_label"

    pdf = _normalise(pdf_title)
    if _is_identity(pdf):
        return pdf, "pdf_metadata"

    heading = _first_usable_heading(headings)
    if heading is not None:
        return heading, "heading"

    name = _from_filename(filename)
    if _is_identity(name):
        return name, "filename"

    return None, "unknown"
