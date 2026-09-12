"""HTTP and release-feed boundary for the Open Jobs collector."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping

from pipeline.http import FetchResult, PipelineHTTPClient

from .policy import OpenJobsPolicy, PolicyError, artifact_parts, index_entries

INDEX_PATHS = {"diffs": "/data/diffs/index.json", "ledger": "/data/ledger/index.json"}


@dataclass(frozen=True)
class Artifact:
    release_kind: str
    release: dict[str, Any]
    ordinal: int
    filename: str
    byte_size: int
    sha256: str
    url: str

    @property
    def artifact_kind(self) -> str:
        return f"{self.release_kind}_part"


class OpenJobsClient:
    """Calls Open Jobs only through the shared HTTP client."""

    def __init__(self, http: PipelineHTTPClient, policy: OpenJobsPolicy):
        policy.validate()
        self.http = http
        self.policy = policy

    def fetch_index(self, kind: str) -> tuple[FetchResult, list[dict[str, Any]]]:
        try:
            path = INDEX_PATHS[kind]
        except KeyError as exc:
            raise PolicyError(f"unknown Open Jobs release kind: {kind!r}") from exc
        result = self.http.get(self.policy.url(path))
        self.policy.accept_size(len(result.body), kind="release")
        if not result.ok:
            return result, []
        return result, index_entries(result.body)

    def artifacts(self, kind: str, entry: dict[str, Any], *, lite: bool = True) -> list[Artifact]:
        parts = artifact_parts(entry, lite=lite)
        release_dir = str(entry["dir"])
        tier = "lite/" if lite and isinstance(entry.get("lite"), Mapping) else ""
        out: list[Artifact] = []
        for ordinal, part in enumerate(parts):
            filename = part["file"]
            if not filename or "/" in filename or "\\" in filename or filename in (".", ".."):
                raise PolicyError("Open Jobs artifact filename is not a simple file name")
            path = f"/data/{release_dir.strip('/')}/{tier}{filename}"
            out.append(Artifact(kind, entry, ordinal, filename, part["bytes"], part["sha256"],
                                self.policy.url(path)))
        return out

    def fetch_artifact(self, artifact: Artifact, *, used_bytes: int = 0) -> FetchResult:
        self.policy.accept_size(artifact.byte_size, used=used_bytes)
        result = self.http.get(artifact.url)
        self.policy.accept_size(len(result.body), used=used_bytes)
        actual = hashlib.sha256(result.body).hexdigest() if result.body else ""
        if result.ok and artifact.sha256 and actual != artifact.sha256:
            raise PolicyError(
                f"Open Jobs artifact hash mismatch for {artifact.url}: "
                f"expected {artifact.sha256}, got {actual}")
        return result

    @staticmethod
    def json_metadata(result: FetchResult) -> dict[str, Any]:
        """Small JSON metadata suitable for a provenance row."""
        return {"url": result.url, "status": result.status_code,
                "content_type": result.content_type, "bytes": len(result.body)}
