"""Storage for mutable derived artifacts, deliberately separate from raw archive."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


class DerivedArtifactStore:
    """A small local store whose content-addressed paths preserve lineage."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def put(self, source_system: str, artifact_type: str, suffix: str, body: bytes) -> tuple[str, str]:
        if not _SAFE_SEGMENT.fullmatch(source_system) or not _SAFE_SEGMENT.fullmatch(artifact_type):
            raise ValueError("source_system and artifact_type must be safe path segments")
        sha256 = hashlib.sha256(body).hexdigest()
        suffix = suffix if suffix.startswith(".") else f".{suffix}"
        relative = Path(source_system) / artifact_type / f"{sha256}{suffix}"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(body)
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
            raise RuntimeError(f"derived artifact hash verification failed: {path}")
        return f"data/derived/{relative.as_posix()}", sha256
