"""OCRmyPDF adapter: raw bytes in, separately stored derived PDF out."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


class OCRUnavailable(RuntimeError):
    """OCRmyPDF or its system dependencies are unavailable."""


def version() -> str:
    executable = shutil.which("ocrmypdf")
    if executable is None:
        raise OCRUnavailable("OCRmyPDF needs `uv sync --extra documents` and its system dependencies.")
    result = subprocess.run([executable, "--version"], check=True, capture_output=True, text=True)
    return result.stdout.strip() or result.stderr.strip() or "unknown"


def create_searchable_pdf(body: bytes, language: str) -> tuple[bytes, str]:
    executable = shutil.which("ocrmypdf")
    if executable is None:
        raise OCRUnavailable("OCRmyPDF needs `uv sync --extra documents` and its system dependencies.")
    with tempfile.TemporaryDirectory(prefix="sectortrace-ocr-") as directory:
        source = Path(directory) / "raw.pdf"
        output = Path(directory) / "ocr.pdf"
        source.write_bytes(body)
        try:
            subprocess.run(
                [executable, "--skip-text", "--output-type", "pdf", "--language", language,
                 str(source), str(output)],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "OCRmyPDF failed").strip()
            raise RuntimeError(detail[:2000]) from exc
        return output.read_bytes(), version()
