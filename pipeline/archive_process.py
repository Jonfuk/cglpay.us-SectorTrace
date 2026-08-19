"""Manual, deterministic processing of content-addressed raw archive objects.

This module deliberately stops at derived text and parser metadata. It never
infers or promotes claims. The raw archive remains the byte-level authority;
every object is hashed again before a derived extraction is recorded.
"""
from __future__ import annotations

import hashlib
import html.parser
import json
import mimetypes
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.archive import Archive, ArchiveError
from pipeline.pdftext import page_texts

EXTRACTOR_NAME = "deterministic-docs"
EXTRACTOR_VERSION = "1"
PARSER_VERSION = "1"
MAX_TEXT_CHARS = 2_000_000
_SHA = re.compile(r"^[0-9a-f]{64}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _object_parts(key: str) -> tuple[str, str] | None:
    parts = key.replace("\\", "/").split("/")
    if len(parts) != 4 or parts[0:2] != ["data", "raw"]:
        return None
    source, filename = parts[2:]
    sha, dot, _extension = filename.partition(".")
    if not source or not dot or not _SHA.fullmatch(sha):
        return None
    return source, sha


class _TextParser(html.parser.HTMLParser):
    _BLOCKS = {"br", "div", "li", "p", "section", "article", "h1", "h2", "h3", "h4", "tr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        lines = (" ".join(line.split()) for line in "".join(self.parts).splitlines())
        return "\n".join(line for line in lines if line).strip()


def _text_from_bytes(settings, source_system: str, sha: str, path: str,
                     body: bytes) -> tuple[str, str, dict[str, Any]]:
    extension = Path(path).suffix.lower()
    mime_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    metadata: dict[str, Any] = {"mime_type": mime_type, "extension": extension}
    if extension == ".pdf" or mime_type == "application/pdf":
        pages = page_texts(settings, source_system, sha, body)
        text = "\n\n".join(page for page in pages if page).strip()
        metadata.update({"parser": "pdfplumber", "page_count": len(pages)})
        return text, "pdfplumber", metadata
    if extension in {".html", ".htm", ".xhtml"} or mime_type == "text/html":
        parser = _TextParser()
        parser.feed(body.decode("utf-8", errors="replace"))
        metadata["parser"] = "stdlib.html.parser"
        return parser.text(), "html-text", metadata
    if extension in {".txt", ".csv", ".xml", ".ndjson", ".md"} or mime_type.startswith("text/"):
        text = body.decode("utf-8", errors="replace")
        metadata["parser"] = "utf-8"
        metadata["replacement_characters"] = text.count("\ufffd")
        return text.strip(), "plain-text", metadata
    if extension == ".json" or mime_type == "application/json":
        value = json.loads(body.decode("utf-8"))
        metadata.update({"parser": "json", "root_type": type(value).__name__})
        if isinstance(value, dict):
            metadata["top_level_keys"] = sorted(str(key) for key in value)[:200]
        elif isinstance(value, list):
            metadata["item_count"] = len(value)
        return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2), "json", metadata
    metadata["parser"] = "none"
    return "", "unsupported", metadata


def _bounded_text(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_TEXT_CHARS:
        return text, False
    return text[:MAX_TEXT_CHARS], True


def _text_path(settings, source: str, sha: str, extractor_version: str) -> Path:
    safe_version = re.sub(r"[^A-Za-z0-9_.-]", "_", extractor_version)
    return Path(settings.raw_archive_dir).parent / "text" / "archive" / source / f"{sha}.{safe_version}.txt"


def _upsert_object(conn, object_id: str, source: str, sha: str, logical: str,
                   mime_type: str, size: int, now: str) -> None:
    conn.execute(
        "INSERT INTO archive_objects "
        "(object_id, source_system, payload_sha256, logical_path, mime_type, size_bytes, first_seen_at, last_seen_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (object_id) DO UPDATE SET last_seen_at = excluded.last_seen_at, "
        "mime_type = excluded.mime_type, size_bytes = excluded.size_bytes",
        (object_id, source, sha, logical, mime_type, size, now, now),
    )


def process_archive(conn, settings, archive: Archive, *, source_system: str | None = None,
                    limit: int | None = None, force: bool = False,
                    extractor_name: str = EXTRACTOR_NAME,
                    extractor_version: str = EXTRACTOR_VERSION) -> dict[str, Any]:
    """Process a bounded archive inventory and return a run summary."""
    if limit is not None and limit < 1:
        raise ValueError("limit must be at least 1")
    if not extractor_name.strip() or not extractor_version.strip():
        raise ValueError("extractor name and version must be non-empty")

    inventory = archive.inventory(False)
    candidates = []
    for row in inventory.get("objects", []):
        parsed = _object_parts(row.get("key", ""))
        if parsed is None:
            continue
        source, sha = parsed
        if source_system and source != source_system:
            continue
        candidates.append((row, source, sha))
    candidates.sort(key=lambda item: item[0]["key"])
    if limit is not None:
        candidates = candidates[:limit]

    # A run is an event, not a content identity. UUID4 prevents two rapid
    # manual invocations from sharing a primary key on clocks with coarse
    # resolution.
    run_id = str(uuid.uuid4())
    started = _now()
    conn.execute(
        "INSERT INTO archive_extraction_runs "
        "(run_id, started_at, status, extractor_name, extractor_version, object_count) "
        "VALUES (?, ?, 'running', ?, ?, ?)",
        (run_id, started, extractor_name, extractor_version, len(candidates)),
    )
    conn.commit()
    counts = {"run_id": run_id, "objects": len(candidates), "processed": 0,
              "skipped": 0, "failed": 0}

    for row, source, sha in candidates:
        logical = row["key"]
        object_id = hashlib.sha256(logical.encode()).hexdigest()
        mime_type = mimetypes.guess_type(logical)[0] or "application/octet-stream"
        now = _now()
        try:
            body = archive.read(logical)
            actual = hashlib.sha256(body).hexdigest()
            if actual != sha:
                raise ArchiveError(f"archive hash mismatch for {logical}: {actual}")
            _upsert_object(conn, object_id, source, sha, logical, mime_type, len(body), now)
            existing = conn.execute(
                "SELECT extraction_id FROM archive_extractions "
                "WHERE object_id = ? AND extractor_name = ? AND extractor_version = ?",
                (object_id, extractor_name, extractor_version),
            ).fetchone()
            if existing is not None and not force:
                counts["skipped"] += 1
                conn.commit()
                continue

            text, parser_name, metadata = _text_from_bytes(settings, source, sha, logical, body)
            text, truncated = _bounded_text(text)
            metadata.update({"logical_path": logical, "byte_count": len(body), "truncated": truncated})
            status = "unsupported" if parser_name == "unsupported" else ("metadata_only" if not text else "extracted")
            storage_path = None
            text_sha = None
            if text:
                destination = _text_path(settings, source, sha, extractor_version)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(text, encoding="utf-8")
                storage_path = destination.relative_to(Path(settings.raw_archive_dir).parent).as_posix()
                text_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
            evidence = conn.execute(
                "SELECT evidence_id FROM evidence_records WHERE payload_sha256 = ? "
                "ORDER BY evidence_id LIMIT 1", (sha,)).fetchone()
            evidence_id = evidence[0] if evidence else None
            extraction_id = hashlib.sha256(
                f"{object_id}|{extractor_name}|{extractor_version}".encode()).hexdigest()
            conn.execute(
                "INSERT INTO archive_extractions "
                "(extraction_id, run_id, object_id, evidence_id, extractor_name, extractor_version, "
                "parser_name, parser_version, status, text_storage_path, text_sha256, character_count, "
                "metadata_json, error_detail, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?) "
                "ON CONFLICT (object_id, extractor_name, extractor_version) DO UPDATE SET "
                "extraction_id = excluded.extraction_id, run_id = excluded.run_id, evidence_id = excluded.evidence_id, "
                "parser_name = excluded.parser_name, parser_version = excluded.parser_version, status = excluded.status, "
                "text_storage_path = excluded.text_storage_path, text_sha256 = excluded.text_sha256, "
                "character_count = excluded.character_count, metadata_json = excluded.metadata_json, "
                "error_detail = NULL, created_at = excluded.created_at",
                (extraction_id, run_id, object_id, evidence_id, extractor_name, extractor_version,
                 parser_name, PARSER_VERSION, status, storage_path, text_sha,
                 len(text), json.dumps(metadata, sort_keys=True), now),
            )
            counts["processed"] += 1
            conn.commit()
        except Exception as exc:  # record a failed object and continue the run
            counts["failed"] += 1
            conn.execute("INSERT INTO archive_objects "
                         "(object_id, source_system, payload_sha256, logical_path, mime_type, size_bytes, first_seen_at, last_seen_at) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                         "ON CONFLICT (object_id) DO UPDATE SET last_seen_at = excluded.last_seen_at",
                         (object_id, source, sha, logical, mime_type, int(row.get("bytes", 0)), now, now))
            extraction_id = hashlib.sha256(
                f"{object_id}|{extractor_name}|{extractor_version}".encode()).hexdigest()
            evidence = conn.execute(
                "SELECT evidence_id FROM evidence_records WHERE payload_sha256 = ? "
                "ORDER BY evidence_id LIMIT 1", (sha,)).fetchone()
            conn.execute(
                "INSERT INTO archive_extractions "
                "(extraction_id, run_id, object_id, evidence_id, extractor_name, extractor_version, "
                "parser_name, parser_version, status, character_count, metadata_json, error_detail, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'error', ?, 'failed', 0, ?, ?, ?) "
                "ON CONFLICT (object_id, extractor_name, extractor_version) DO UPDATE SET "
                "extraction_id = excluded.extraction_id, run_id = excluded.run_id, evidence_id = excluded.evidence_id, "
                "parser_name = excluded.parser_name, parser_version = excluded.parser_version, status = excluded.status, "
                "text_storage_path = NULL, text_sha256 = NULL, character_count = 0, "
                "metadata_json = excluded.metadata_json, error_detail = excluded.error_detail, created_at = excluded.created_at",
                (extraction_id, run_id, object_id, evidence[0] if evidence else None,
                 extractor_name, extractor_version, PARSER_VERSION,
                 json.dumps({"logical_path": logical}, sort_keys=True), str(exc)[:2000], now),
            )
            conn.commit()
            # A failed extraction is visible in the run summary and log; the
            # raw object is never altered or deleted.
            continue

    completed = _now()
    conn.execute(
        "UPDATE archive_extraction_runs SET completed_at = ?, status = ?, processed_count = ?, "
        "skipped_count = ?, failed_count = ? WHERE run_id = ?",
        (completed, "failed" if counts["failed"] else "completed", counts["processed"],
         counts["skipped"], counts["failed"], run_id),
    )
    conn.commit()
    return counts
