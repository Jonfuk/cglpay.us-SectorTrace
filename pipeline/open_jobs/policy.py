"""Boundaries for the operator-only Open Jobs shadow collector.

The source publishes a daily release index and immutable Parquet parts.  This
module contains policy and validation only: it does not fetch, decode, infer,
or enrich a job.  Keeping those concerns here makes a source-contract change
visible in one small file and gives the offline suite a pure seam to exercise.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit


class PolicyError(ValueError):
    """The source response or configured bounds cannot be accepted safely."""


@dataclass(frozen=True)
class OpenJobsPolicy:
    """Explicit resource and selection limits for one collector run."""

    base_url: str = "https://backend.dehnbostele.workers.dev"
    max_artifact_bytes: int = 128 * 1024 * 1024
    max_release_bytes: int = 512 * 1024 * 1024
    max_run_bytes: int = 1024 * 1024 * 1024
    max_temp_bytes: int = 1024 * 1024 * 1024
    max_record_bytes: int = 1024 * 1024
    decode_batch_rows: int = 256
    run_timeout_seconds: int = 1800
    max_releases_per_run: int = 2
    status_batch_size: int = 100
    status_max_requests: int = 10
    archive_budget_bytes: int = 5 * 1024 * 1024 * 1024

    @classmethod
    def from_settings(cls, settings: object) -> "OpenJobsPolicy":
        """Read only the Open Jobs settings, with safe defaults for doubles."""
        defaults = cls()
        values = {
            name: getattr(settings, f"open_jobs_{name}", getattr(defaults, name))
            for name in (
                "base_url", "max_artifact_bytes", "max_release_bytes", "max_run_bytes",
                "max_temp_bytes", "max_record_bytes", "decode_batch_rows",
                "run_timeout_seconds", "max_releases_per_run", "status_batch_size",
                "status_max_requests", "archive_budget_bytes",
            )
        }
        policy = cls(**values)
        policy.validate()
        return policy

    def validate(self) -> None:
        parsed = urlsplit(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise PolicyError("open_jobs_base_url must be an HTTPS origin without credentials")
        if parsed.query or parsed.fragment:
            raise PolicyError("open_jobs_base_url must not contain a query or fragment")
        positive = (
            "max_artifact_bytes", "max_release_bytes", "max_run_bytes", "max_temp_bytes",
            "max_record_bytes", "decode_batch_rows", "run_timeout_seconds",
            "max_releases_per_run", "status_batch_size", "status_max_requests",
            "archive_budget_bytes",
        )
        for name in positive:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise PolicyError(f"{name} must be a positive integer")
        if self.max_artifact_bytes > self.max_run_bytes:
            raise PolicyError("max_artifact_bytes cannot exceed max_run_bytes")
        if self.max_release_bytes > self.max_run_bytes:
            raise PolicyError("max_release_bytes cannot exceed max_run_bytes")
        if self.max_temp_bytes < self.max_artifact_bytes:
            raise PolicyError("max_temp_bytes cannot be below max_artifact_bytes")
        if self.archive_budget_bytes < self.max_artifact_bytes:
            raise PolicyError("archive_budget_bytes cannot be below max_artifact_bytes")

    @property
    def origin(self) -> str:
        parsed = urlsplit(self.base_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def url(self, path: str) -> str:
        """Resolve a source-relative path and reject cross-origin URLs."""
        if not isinstance(path, str) or not path:
            raise PolicyError("Open Jobs path must be a non-empty string")
        parsed = urlsplit(path)
        if parsed.scheme or parsed.netloc:
            if f"{parsed.scheme}://{parsed.netloc}" != self.origin:
                raise PolicyError("Open Jobs artifact URL leaves the configured origin")
            return path
        if not path.startswith("/"):
            path = "/" + path
        return self.origin + path

    def accept_size(self, size: int, *, kind: str = "artifact", used: int = 0) -> None:
        """Raise before storing a response that exceeds a run bound."""
        if not isinstance(size, int) or size < 0:
            raise PolicyError(f"{kind} byte size is invalid")
        limit = self.max_release_bytes if kind == "release" else self.max_artifact_bytes
        if size > limit:
            raise PolicyError(f"{kind} is {size} bytes; limit is {limit}")
        if used < 0 or used + size > self.max_run_bytes:
            raise PolicyError("Open Jobs run byte budget exceeded")

    def select_entries(self, entries: Iterable[Mapping[str, Any]], *, since: str | None = None,
                       limit: int | None = None) -> list[dict[str, Any]]:
        """Select a bounded newest window and return it oldest-first for replay.

        ``to`` is the end date for a diff and ``date`` is the date for a
        ledger.  Missing dates are retained because dropping an unparseable
        release would be silent loss; such entries sort after dated entries.
        """
        boundary = _parse_since(since)
        selected: list[dict[str, Any]] = []
        for raw in entries:
            if not isinstance(raw, Mapping):
                continue
            entry = dict(raw)
            if not isinstance(entry.get("dir"), str) or not entry["dir"]:
                continue
            if not _parts(entry):
                continue
            release_date = _entry_date(entry)
            if boundary and release_date and release_date < boundary:
                continue
            selected.append(entry)
        # Select the newest bounded window, then replay it oldest-first so
        # predecessor checks and the current head advance in release order.
        selected.sort(key=lambda row: (_entry_date(row) is not None,
                                       _entry_date(row) or date.min), reverse=True)
        cap = self.max_releases_per_run if limit is None else min(limit, self.max_releases_per_run)
        if cap <= 0:
            return []
        window = selected[:cap]
        return sorted(window, key=lambda row: (_entry_date(row) is None,
                                               _entry_date(row) or date.max))


def _parse_since(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except (TypeError, ValueError) as exc:
        raise PolicyError(f"since must be an ISO date (YYYY-MM-DD); got {value!r}") from exc


def _entry_date(entry: Mapping[str, Any]) -> date | None:
    value = entry.get("to") or entry.get("date") or entry.get("from")
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _parts(entry: Mapping[str, Any]) -> list[dict[str, Any]]:
    parts = entry.get("parts")
    if not isinstance(parts, list):
        return []
    out: list[dict[str, Any]] = []
    for part in parts:
        if not isinstance(part, Mapping):
            continue
        filename, size, digest = part.get("file"), part.get("bytes"), part.get("sha256")
        if (isinstance(filename, str) and filename and isinstance(size, int) and size >= 0
                and isinstance(digest, str) and len(digest) == 64):
            out.append({"file": filename, "bytes": size, "sha256": digest.lower()})
    return out


def index_entries(payload: bytes | str | Mapping[str, Any]) -> list[dict[str, Any]]:
    """Decode an index and return only structurally valid release entries."""
    if isinstance(payload, Mapping):
        value = payload
    else:
        try:
            value = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise PolicyError("Open Jobs release index is not valid JSON") from exc
    if not isinstance(value, Mapping) or value.get("schema_version") != 1:
        raise PolicyError("unsupported Open Jobs release index schema")
    entries = value.get("entries")
    if not isinstance(entries, list):
        raise PolicyError("Open Jobs release index has no entries list")
    return [dict(entry) for entry in entries if isinstance(entry, Mapping)]


def artifact_parts(entry: Mapping[str, Any], *, lite: bool = False) -> list[dict[str, Any]]:
    """Return listed artifact parts, preferring the lite tier when present."""
    chosen = entry.get("lite") if lite and isinstance(entry.get("lite"), Mapping) else entry
    return _parts(chosen) if isinstance(chosen, Mapping) else []
