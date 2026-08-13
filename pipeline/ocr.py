"""Reading a PDF that was scanned rather than typed.

Seven of every twelve reports in m08's backlog are paper: pdfplumber opens
them, reports four pages, and every page comes back empty because there is no
text layer to extract. The document is a picture of a document.

Four things about this are worth knowing before relying on it.

  * **It is optional and off by default.** The engine is an extra
    (`uv sync --extra ocr`) *and* `Settings.ocr_enabled` must be true. Two
    switches for one feature looks redundant until you price it: at about nine
    seconds a page, m08's backlog of scans is several hours of CPU. That is a
    thing someone chooses, not a thing that starts happening because a package
    manager ran.

  * **The engine is English-trained, and that was not a free choice.** The
    first implementation used rapidocr-onnxruntime, which has the better
    property of bundling its models rather than downloading them. Its
    recogniser is trained on Chinese, and on tightly-set English it welds
    words together: a real report came back as
    "foraperiodofaboutsixmonthsatdoublethestipulatedmaximumdose". OnnxTR reads
    the same line correctly, and faster.

  * **First use needs the network.** OnnxTR fetches its models on demand,
    around 105 MB into ~/.cache/onnxtr, and every run after that is local.

  * **The output is still not a transcript.** It is good English now, and it
    still mistakes the occasional word. Anything stored from it records that
    it came from OCR so a reader can weigh it, and m08 checks the redaction
    against the result rather than trusting it.

Cached by the hash of the PDF bytes, in the same place and shape as
pipeline/pdftext.py, under a separate source-system key so OCR output is never
mistaken for an extracted text layer.
"""
from __future__ import annotations

import structlog

from pipeline import pdftext

log = structlog.get_logger()

# Rendering resolution for the page images OnnxTR reads. Its own default is
# lower; 200 dpi reads these photocopies cleanly without doubling the cost.
RENDER_DPI = 200

# A guard against a pathological document rather than a real limit: PFD
# reports run to a handful of pages, and a hundred-page scan in this corpus
# would be a sign something else is wrong.
MAX_PAGES = 40


class OCRUnavailable(RuntimeError):
    """The OCR extra is not installed."""


def available() -> bool:
    """Whether the OCR extra is installed. Checked, never assumed: the whole
    point of an extra is that most installations will not have it."""
    try:
        import onnxtr.io  # noqa: F401
        import onnxtr.models  # noqa: F401
    except ImportError:
        return False
    return True


def enabled(settings) -> bool:
    """Installed *and* switched on. See the module docstring for why both."""
    return bool(getattr(settings, "ocr_enabled", False)) and available()


_PREDICTOR = None


def _predictor():
    """One predictor for the process. Building it loads (and on the first ever
    run downloads) the models, which is far too slow to do per document."""
    global _PREDICTOR
    if _PREDICTOR is None:
        try:
            from onnxtr.models import ocr_predictor
        except ImportError as exc:  # pragma: no cover - guarded by available()
            raise OCRUnavailable(
                "OCR needs the optional extra: uv sync --extra ocr") from exc
        log.info("ocr.loading_models")
        _PREDICTOR = ocr_predictor(det_arch="fast_base", reco_arch="crnn_vgg16_bn",
                                    assume_straight_pages=True)
    return _PREDICTOR


def page_texts(settings, source_system: str, sha256: str,
                pdf_bytes: bytes) -> list[str]:
    """OCR text for every page, in order, done once per unique document.

    Shares pdftext's on-disk cache, keyed by the same digest but filed under
    `<source_system>_ocr`, so a document that has been read once is never read
    again and OCR output can never be confused with a real text layer.
    """
    if not available():
        raise OCRUnavailable("OCR needs the optional extra: uv sync --extra ocr")

    from onnxtr.io import DocumentFile

    cache_key = f"{source_system}_ocr"
    if sha256:
        cached = pdftext._read_cached(pdftext.cache_path(settings, cache_key, sha256))
        if cached is not None:
            log.debug("ocr.cache_hit", sha256=sha256[:12], pages=len(cached))
            return cached

    document = DocumentFile.from_pdf(pdf_bytes, scale=RENDER_DPI / 72)
    if len(document) > MAX_PAGES:
        log.warning("ocr.page_limit", sha256=sha256[:12], pages=len(document))
        document = document[:MAX_PAGES]

    result = _predictor()(document)

    pages: list[str] = []
    for page in result.pages:
        lines = []
        for block in page.blocks:
            for line in block.lines:
                # Words carry their own spacing decision; joining on a single
                # space is what makes this readable English rather than the
                # run-together text the previous engine produced.
                lines.append(" ".join(word.value for word in line.words))
        pages.append("\n".join(lines))

    if sha256:
        pdftext._write_cached(pdftext.cache_path(settings, cache_key, sha256), pages)
    log.info("ocr.extracted", sha256=(sha256 or "")[:12], pages=len(pages),
              chars=sum(len(p) for p in pages))
    return pages
