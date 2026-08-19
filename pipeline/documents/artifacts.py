"""Storage for mutable derived artifacts, deliberately separate from raw archive."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


class DerivedArtifactStore:
    """Local or S3 derived storage with content-addressed, non-raw keys."""

    def __init__(self, settings, client=None):
        self.settings = settings
        self.root = Path(settings.derived_archive_dir)
        self._client = client

    def put(self, source_system: str, artifact_type: str, suffix: str, body: bytes) -> tuple[str, str]:
        if not _SAFE_SEGMENT.fullmatch(source_system) or not _SAFE_SEGMENT.fullmatch(artifact_type):
            raise ValueError("source_system and artifact_type must be safe path segments")
        sha256 = hashlib.sha256(body).hexdigest()
        suffix = suffix if suffix.startswith(".") else f".{suffix}"
        relative = Path(source_system) / artifact_type / f"{sha256}{suffix}"
        if self.settings.derived_archive_s3_bucket:
            return self._put_s3(relative, body, sha256)
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(body)
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
            raise RuntimeError(f"derived artifact hash verification failed: {path}")
        return f"data/derived/{relative.as_posix()}", sha256

    def _put_s3(self, relative: Path, body: bytes, sha256: str) -> tuple[str, str]:
        if self._client is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover - installation-specific
                raise RuntimeError("S3 derived storage needs `uv sync --extra storage`.") from exc
            self._client = boto3.client(
                "s3", region_name=self.settings.derived_archive_s3_region,
                endpoint_url=self.settings.derived_archive_s3_endpoint,
                aws_access_key_id=self.settings.derived_archive_s3_access_key,
                aws_secret_access_key=self.settings.derived_archive_s3_secret,
                config=boto3.session.Config(s3={"addressing_style": self.settings.derived_archive_s3_url_style}),
            )
        key = relative.as_posix()
        self._client.put_object(Bucket=self.settings.derived_archive_s3_bucket, Key=key, Body=body)
        actual = self._client.get_object(Bucket=self.settings.derived_archive_s3_bucket, Key=key)["Body"].read()
        if hashlib.sha256(actual).hexdigest() != sha256:
            raise RuntimeError(f"derived S3 artifact hash verification failed: {key}")
        return f"s3://{self.settings.derived_archive_s3_bucket}/{key}", sha256
