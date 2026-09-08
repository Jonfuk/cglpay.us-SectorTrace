"""The local, read-only contract for Open Jobs artifacts.

Open Jobs publishes both a current snapshot and historical lightweight diff
parts.  The two shapes share the source identity fields, while only a diff
row has an ``op``.  This module validates the facts needed by a reader and
does not decide whether a row is relevant, attributable, or publishable.

The names below are the source's names (``slug`` is the board/tenant and
``id`` is the upstream job identifier).  They are intentionally kept as
strings: separators and case can be meaningful to a board or ATS.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping


class ContractError(ValueError):
    """An artifact, release, schema, or row violates the source contract."""


class SchemaError(ContractError):
    """A Parquet schema is missing a required field or has an invalid type."""


class IntegrityError(ContractError):
    """An artifact does not match its declared bytes or release identity."""


class ResourceLimitError(ContractError):
    """A local artifact exceeds a caller's explicitly chosen read budget."""


SUPPORTED_SCHEMA_VERSIONS = frozenset({"v1", "diff-v1", "snapshot-v1"})
OPERATIONS = frozenset({"added", "changed", "changed_prev", "removed", "carried"})
REMOVAL_REASONS = frozenset({"closed", "left_dataset", "unknown"})
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class OpenJobsContract:
    """Required columns and validation rules for one artifact family."""

    required_columns: frozenset[str] = frozenset({"ats", "slug", "id"})
    require_operation: bool = False
    supported_schema_versions: frozenset[str] = SUPPORTED_SCHEMA_VERSIONS
    operations: frozenset[str] = OPERATIONS

    def validate_columns(self, columns: Iterable[str]) -> tuple[str, ...]:
        """Validate field names and return their stable source order.

        Extra columns are allowed because Open Jobs adds enrichment fields over
        time.  They are carried as data, never interpreted as evidence by this
        reader.  Missing identity fields fail before any row is consumed.
        """
        names = tuple(columns)
        if any(not isinstance(name, str) or not name for name in names):
            raise SchemaError("Parquet field names must be non-empty strings")
        missing = sorted(self.required_columns.difference(names))
        if self.require_operation and "op" not in names:
            missing.append("op")
        if missing:
            raise SchemaError("Open Jobs artifact is missing required columns: "
                              + ", ".join(missing))
        if len(set(names)) != len(names):
            raise SchemaError("Parquet field names must be unique")
        return names

    def validate_schema_version(self, version: str | None) -> str | None:
        if version is None:
            return None
        if not isinstance(version, str) or version not in self.supported_schema_versions:
            raise SchemaError(f"unsupported Open Jobs schema_version: {version!r}")
        return version

    def validate_arrow_schema(self, schema: Any) -> tuple[str, ...]:
        """Validate identity field types exposed by Arrow.

        New nullable enrichment fields are allowed, but identity and lifecycle
        values must remain strings.  Numeric values are refused rather than
        converted because board and job identifiers can contain separators or
        significant case.
        """
        names = self.validate_columns(schema.names)
        required = tuple(self.required_columns) + (("op",) if self.require_operation else ())
        for name in required:
            field = schema.field(name)
            type_name = str(field.type)
            if type_name not in {"string", "large_string"}:
                raise SchemaError(f"{name} must use an Arrow string type, got {type_name}")
        return names

    def validate_row(self, row: Mapping[str, Any], *, row_number: int | None = None) -> None:
        """Validate identity and lifecycle fields without coercing values."""
        missing = sorted(self.required_columns.difference(row))
        if self.require_operation and "op" not in row:
            missing.append("op")
        if missing:
            suffix = "" if row_number is None else f" at row {row_number}"
            raise SchemaError("row is missing required columns" + suffix + ": "
                              + ", ".join(missing))
        for name in self.required_columns:
            value = row[name]
            if not isinstance(value, str) or not value:
                raise SchemaError(f"{name} must be a non-empty string")
        if "op" in row:
            op = row["op"]
            if not isinstance(op, str) or op not in self.operations:
                raise ContractError(f"unknown Open Jobs operation: {op!r}")
            if op == "removed" and "removal_reason" in row:
                reason = row["removal_reason"]
                if reason is not None and reason not in REMOVAL_REASONS:
                    raise ContractError(f"unknown removal_reason: {reason!r}")

    def validate_rows(self, rows: Iterable[Mapping[str, Any]], *, allow_empty: bool = True) -> int:
        count = 0
        seen: set[tuple[str, str, str, str | None]] = set()
        for count, row in enumerate(rows, 1):
            self.validate_row(row, row_number=count)
            identity = (*natural_key(row), row.get("op"))
            if identity in seen:
                raise ContractError(f"duplicate source row identity at row {count}: {identity!r}")
            seen.add(identity)
        if count == 0 and not allow_empty:
            raise ContractError("a complete Open Jobs release must contain rows")
        return count


SNAPSHOT_CONTRACT = OpenJobsContract(require_operation=False)
DIFF_CONTRACT = OpenJobsContract(require_operation=True)
DEFAULT_CONTRACT = DIFF_CONTRACT


def natural_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    """Return the lossless ``(ats, slug, id)`` source identity tuple."""
    missing = [name for name in ("ats", "slug", "id") if name not in row]
    if missing:
        raise SchemaError("source identity is missing: " + ", ".join(missing))
    values = tuple(row[name] for name in ("ats", "slug", "id"))
    if any(not isinstance(value, str) or not value for value in values):
        raise SchemaError("ats, slug, and id must be non-empty strings")
    return values  # type: ignore[return-value]


@dataclass(frozen=True)
class ArtifactSpec:
    """One exact byte artifact listed by a release manifest."""

    path: str
    sha256: str
    size_bytes: int | None = None
    kind: str = "parquet"
    digest_kind: str = "artifact_bytes"

    def __post_init__(self) -> None:
        if not self.path or not isinstance(self.path, str):
            raise ContractError("artifact path is required")
        if not _SHA256.fullmatch(self.sha256):
            raise ContractError("artifact sha256 must be a 64-character hex digest")
        if self.size_bytes is not None and (
            isinstance(self.size_bytes, bool) or self.size_bytes < 0
        ):
            raise ContractError("artifact size_bytes must be a non-negative integer")
        if self.kind != "parquet":
            raise ContractError(f"unsupported Open Jobs artifact kind: {self.kind!r}")
        if self.digest_kind != "artifact_bytes":
            raise ContractError("only exact artifact_bytes digests are readable")


@dataclass(frozen=True)
class ReleaseMetadata:
    """Validated identity and parts for one complete logical release."""

    release_id: str
    schema_version: str
    parts: tuple[ArtifactSpec, ...]
    parent: str | None = None
    content_sha256: str | None = None
    expected_rows: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.release_id:
            raise ContractError("release_id is required")
        if not self.schema_version:
            raise ContractError("schema_version is required")
        if not self.parts:
            raise ContractError("release must list at least one artifact part")
        if len({part.path for part in self.parts}) != len(self.parts):
            raise ContractError("release lists the same artifact part more than once")
        if self.content_sha256 is not None and not _SHA256.fullmatch(self.content_sha256):
            raise ContractError("content_sha256 must be a 64-character hex digest")
        if self.expected_rows is not None and (
            isinstance(self.expected_rows, bool) or self.expected_rows < 0
        ):
            raise ContractError("expected_rows must be a non-negative integer")

    def validate_predecessor(self, previous: "ReleaseMetadata | None") -> None:
        """Require the declared parent to be the committed prior release."""
        if self.parent is None:
            if previous is not None:
                raise IntegrityError("release has no parent but a prior head exists")
            return
        if previous is None:
            raise IntegrityError("release declares a parent but no prior head exists")
        expected = previous.content_sha256 or previous.release_id
        if self.parent not in {previous.release_id, expected}:
            raise IntegrityError("release predecessor does not match committed head")


def _first(mapping: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    return None


def _artifact(value: Mapping[str, Any]) -> ArtifactSpec:
    path = _first(value, "path", "url", "key", "name")
    digest = _first(value, "sha256", "sha", "hash", "content_sha256")
    size = _first(value, "size_bytes", "bytes", "size", "byte_length")
    return ArtifactSpec(path=path, sha256=digest, size_bytes=size,
                        kind=value.get("kind", "parquet"),
                        digest_kind=value.get("digest_kind", "artifact_bytes"))


def parse_release_metadata(value: Mapping[str, Any] | bytes | str) -> ReleaseMetadata:
    """Parse and validate a release index/sidecar without performing I/O.

    The parser accepts the spelling variants used by published indexes while
    retaining the original mapping in ``metadata`` for provenance.  It does
    not fetch URLs or treat an absent ``parts`` list as an empty release.
    """
    if isinstance(value, bytes):
        try:
            value = json.loads(value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractError("release metadata is not valid UTF-8 JSON") from exc
    elif isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ContractError("release metadata is not valid JSON") from exc
    if not isinstance(value, Mapping):
        raise ContractError("release metadata must be a JSON object")
    version = _first(value, "schema_version", "schemaVersion")
    if not isinstance(version, str) or version not in SUPPORTED_SCHEMA_VERSIONS:
        raise SchemaError(f"unsupported Open Jobs schema_version: {version!r}")
    release_id = _first(value, "release_id", "releaseId", "id", "date")
    if not isinstance(release_id, str) or not release_id:
        raise ContractError("release metadata needs a non-empty release_id")
    raw_parts = _first(value, "parts", "artifacts")
    if not isinstance(raw_parts, (list, tuple)) or not raw_parts:
        raise ContractError("release metadata needs a non-empty parts list")
    parts: list[ArtifactSpec] = []
    for index, raw in enumerate(raw_parts):
        if not isinstance(raw, Mapping):
            raise ContractError(f"release part {index} is not an object")
        try:
            parts.append(_artifact(raw))
        except (TypeError, ContractError) as exc:
            raise ContractError(f"invalid release part {index}: {exc}") from exc
    parent = _first(value, "parent", "predecessor", "previous", "parent_sha256")
    if parent is not None and (not isinstance(parent, str) or not parent):
        raise ContractError("release parent must be a non-empty string when present")
    content_sha256 = _first(value, "content_sha256", "contentSha256", "digest")
    if content_sha256 is not None and not isinstance(content_sha256, str):
        raise ContractError("release content_sha256 must be a string")
    expected_rows = _first(value, "row_count", "rows", "expected_rows", "count")
    if expected_rows is not None and (isinstance(expected_rows, bool) or not isinstance(expected_rows, int)):
        raise ContractError("release row count must be an integer")
    return ReleaseMetadata(release_id=release_id, schema_version=version,
                           parts=tuple(parts), parent=parent,
                           content_sha256=content_sha256,
                           expected_rows=expected_rows, metadata=value)


@dataclass(frozen=True)
class ArtifactVerification:
    path: Path
    sha256: str
    size_bytes: int


def verify_artifact(path: str | Path, expected_sha256: str, *, expected_size: int | None = None,
                    max_bytes: int | None = None, chunk_size: int = 1024 * 1024) -> ArtifactVerification:
    """Hash a local artifact and enforce declared and configured byte bounds."""
    local = Path(path)
    if not local.is_file():
        raise IntegrityError(f"artifact is not a regular local file: {local}")
    if not _SHA256.fullmatch(expected_sha256):
        raise IntegrityError("expected sha256 must be a 64-character hex digest")
    advertised = local.stat().st_size
    if expected_size is not None and advertised != expected_size:
        raise IntegrityError(f"artifact size is {advertised}, expected {expected_size}")
    if max_bytes is not None and advertised > max_bytes:
        raise ResourceLimitError(f"artifact is {advertised} bytes, over {max_bytes}-byte limit")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = sha256()
    read = 0
    with local.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            read += len(chunk)
            if max_bytes is not None and read > max_bytes:
                raise ResourceLimitError("artifact exceeded byte limit while being read")
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual.lower() != expected_sha256.lower():
        raise IntegrityError(f"artifact sha256 is {actual}, expected {expected_sha256}")
    if expected_size is not None and read != expected_size:
        raise IntegrityError(f"artifact read {read} bytes, expected {expected_size}")
    return ArtifactVerification(path=local, sha256=actual, size_bytes=read)


def row_size_bytes(row: Mapping[str, Any]) -> int:
    """Return a conservative UTF-8 size for a row before persistence."""
    try:
        encoded = json.dumps(row, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), default=str).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError("row cannot be represented for bounded validation") from exc
    return len(encoded)
