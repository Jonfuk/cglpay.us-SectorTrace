"""Content-addressed raw archive backends."""
from __future__ import annotations

import base64
import hashlib
import mimetypes
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from pipeline.config import Settings
from pipeline.meters import DISK

_KEY = re.compile(r"^data/raw/([^/]+)/([0-9a-f]{64})(\.[^/]*)$")


class ArchiveError(RuntimeError):
    """The archive cannot provide or prove a payload."""


@dataclass(frozen=True)
class ArchiveObject:
    logical_path: str
    size: int
    _reader: object

    def read_bytes(self) -> bytes:
        return self._reader()


class Archive(Protocol):
    backend: str
    def lookup(self, source_system: str, sha256: str) -> ArchiveObject | None: ...
    def get_by_ref(self, logical_path: str) -> ArchiveObject | None: ...
    def put(self, source_system: str, sha256: str, content_type: str | None, body: bytes) -> str: ...
    def put_file(self, source_system: str, sha256: str, content_type: str | None,
                 path: Path) -> ArchiveObject: ...
    def put_stream(self, source_system: str, sha256: str, content_type: str | None,
                   stream) -> ArchiveObject: ...
    def read(self, logical_path: str) -> bytes: ...
    def inventory(self, verify_hashes: bool = False) -> dict: ...
    def verify(self) -> dict: ...


def logical_path(source_system: str, sha256: str, content_type: str | None) -> str:
    ext = mimetypes.guess_extension((content_type or "").split(";", 1)[0].strip()) or ".bin"
    return f"data/raw/{source_system}/{sha256}{ext}"


def _b64_checksum(sha256_hex: str) -> str:
    """S3's `ChecksumSHA256` wire format: base64 of the raw digest bytes,
    not the hex string this codebase stores everywhere else."""
    return base64.b64encode(bytes.fromhex(sha256_hex)).decode("ascii")


def _is_not_found(exc: Exception) -> bool:
    """True when an S3 client exception means "no such key" rather than a
    real failure worth surfacing. Matches `botocore.exceptions.ClientError`'s
    `exc.response["Error"]["Code"]` shape by duck typing rather than
    importing botocore at module scope — it sits behind the optional
    `storage` extra, and the offline test suite's fakes need only mimic this
    one attribute, not the whole botocore exception hierarchy.
    """
    error = getattr(exc, "response", None)
    code = error.get("Error", {}).get("Code") if isinstance(error, dict) else None
    return code in ("404", "NoSuchKey", "NotFound")


def _parts(path: str) -> tuple[str, str, str]:
    match = _KEY.fullmatch(path.replace("\\", "/"))
    if not match:
        raise ArchiveError(f"invalid raw archive reference: {path!r}")
    return match.group(1), match.group(2), match.group(0)


class FilesystemArchive:
    backend = "filesystem"

    def __init__(self, root: Path):
        self.root = Path(root)

    def lookup(self, source_system: str, sha256: str) -> ArchiveObject | None:
        if not sha256 or not (directory := self.root / source_system).is_dir():
            return None
        for path in directory.glob(f"{sha256}.*"):
            if path.is_file():
                return ArchiveObject(f"data/raw/{source_system}/{path.name}", path.stat().st_size,
                                     path.read_bytes)
        return None

    def get_by_ref(self, logical_path: str) -> ArchiveObject | None:
        """Locate an object by the exact key a prior write already proved
        correct — a stored `http_cache.archive_ref`, or a row this backend's
        own inventory already named — rather than re-deriving it with
        `lookup()`'s glob. A directory listing is cheap here, but a 304
        revalidation used to pay for one on every single cache hit for a
        find it had already made once; this is the single `stat`+read that
        ought to cost instead.
        """
        _, _, full = _parts(logical_path)
        path = self.root / full.removeprefix("data/raw/")
        if not path.is_file():
            return None
        return ArchiveObject(full, path.stat().st_size, path.read_bytes)

    def put(self, source_system: str, sha256: str, content_type: str | None, body: bytes) -> str:
        if hashlib.sha256(body).hexdigest() != sha256:
            raise ArchiveError("payload hash does not match archive key")
        logical = logical_path(source_system, sha256, content_type)
        path = self.root / logical.removeprefix("data/raw/")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(body)
            DISK.add(len(body))
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
            raise ArchiveError(f"filesystem archive verification failed for {logical}")
        return logical

    def put_stream(self, source_system: str, sha256: str,
                   content_type: str | None, stream) -> ArchiveObject:
        """Spool, hash, and atomically install a body in one pass."""
        logical = logical_path(source_system, sha256, content_type)
        target = self.root / logical.removeprefix("data/raw/")
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temp:
            temporary = Path(temp.name)
            digest = hashlib.sha256()
            size = 0
            try:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    size += len(chunk)
                    temp.write(chunk)
                temp.flush()
                os.fsync(temp.fileno())
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        if digest.hexdigest() != sha256:
            temporary.unlink(missing_ok=True)
            raise ArchiveError("payload hash does not match archive key")
        if not target.exists():
            os.replace(temporary, target)
            DISK.add(size)
        else:
            temporary.unlink(missing_ok=True)
            size = target.stat().st_size
        return ArchiveObject(logical, size, target.read_bytes)

    def put_file(self, source_system: str, sha256: str,
                 content_type: str | None, path: Path) -> ArchiveObject:
        with Path(path).open("rb") as stream:
            return self.put_stream(source_system, sha256, content_type, stream)

    def read(self, logical: str) -> bytes:
        if Path(logical).is_absolute():
            try:
                logical = f"data/raw/{Path(logical).relative_to(self.root).as_posix()}"
            except ValueError as exc:
                raise ArchiveError(f"archive path is outside RAW_ARCHIVE_DIR: {logical}") from exc
        source, sha, full = _parts(logical)
        obj = self.lookup(source, sha)
        if obj is None:
            raise FileNotFoundError(full)
        body = obj.read_bytes()
        if hashlib.sha256(body).hexdigest() != sha:
            raise ArchiveError(f"corrupt filesystem archive object: {full}")
        return body

    def inventory(self, verify_hashes: bool = False) -> dict:
        rows = []
        if self.root.is_dir():
            for path in sorted(self.root.rglob("*")):
                if path.is_file():
                    item = {"key": f"data/raw/{path.relative_to(self.root).as_posix()}",
                            "bytes": path.stat().st_size}
                    if verify_hashes:
                        item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                    rows.append(item)
        return _inventory(rows, self.root.is_dir())

    def verify(self) -> dict:
        return _verify_inventory(self.inventory(True))


class S3Archive:
    backend = "s3"

    # A dedicated key outside `data/raw/` — never collides with a real
    # content-addressed object, and small enough that probing costs nothing
    # worth measuring.
    _CHECKSUM_PROBE_KEY = "_sectortrace_checksum_probe"

    def __init__(self, settings: Settings, client=None):
        if client is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover
                raise ArchiveError("S3 archive requires `uv sync --extra storage`") from exc
        else:
            boto3 = None
        self.bucket = settings.archive_s3_bucket
        if client is None:
            kwargs = {"region_name": settings.archive_s3_region,
                      "endpoint_url": settings.archive_s3_endpoint,
                      "config": boto3.session.Config(s3={"addressing_style": settings.archive_s3_url_style}),
                      "aws_access_key_id": settings.archive_s3_access_key,
                      "aws_secret_access_key": settings.archive_s3_secret}
            client = boto3.client("s3", **kwargs)
        self.client = client
        # Probed once and cached for the life of this instance (performance.md
        # Phase 5): not every S3-compatible endpoint that this project talks
        # to implements checksum-on-write (self-hosted MinIO/Ceph deployments
        # predate it), and there is no capability-discovery API — the only
        # way to find out is to try one and see whether it comes back.
        self._checksum_supported: bool | None = None

    def _key(self, logical: str) -> str:
        if Path(logical).is_absolute():
            marker = "data/raw/"
            normal = logical.replace("\\", "/")
            position = normal.find(marker)
            if position >= 0:
                logical = normal[position:]
        _parts(logical)
        return logical.removeprefix("data/raw/")

    def lookup(self, source_system: str, sha256: str) -> ArchiveObject | None:
        response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=f"{source_system}/{sha256}.")
        objects = response.get("Contents", [])
        if not objects:
            return None
        logical = f"data/raw/{objects[0]['Key']}"
        return ArchiveObject(logical, int(objects[0]["Size"]), lambda: self.read(logical))

    def get_by_ref(self, logical_path: str) -> ArchiveObject | None:
        """Locate an object by the exact key a prior write already proved
        correct, via one exact HEAD — the counterpart to `lookup()`'s
        `list_objects_v2` call, which exists only because a bare
        (source, sha256) pair does not know the extension `logical_path()`
        chose. Once a caller already holds the key (a stored
        `http_cache.archive_ref`, the archive audit's own index), paying for
        a bucket listing to refind it is unnecessary cost and, on a bucket
        with many objects sharing a source/hash prefix, unnecessary latency
        per lookup.
        """
        key = self._key(logical_path)
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if _is_not_found(exc):
                return None
            raise
        return ArchiveObject(logical_path, int(response["ContentLength"]),
                             lambda: self.read(logical_path))

    def _supports_checksum(self) -> bool:
        """Whether this endpoint accepts a transport checksum on write and
        echoes it back on an exact HEAD. A false negative here only costs
        falling back to the slower full-byte-compare verification this
        backend used before checksums existed; trusting a put that merely
        did not *reject* `ChecksumAlgorithm` would be a false positive — some
        S3-compatible servers accept and silently ignore parameters they
        don't implement — so the probe insists on seeing the checksum
        actually echoed back, not merely on the put succeeding.
        """
        if self._checksum_supported is None:
            probe_body = b"sectortrace-checksum-capability-probe"
            probe_sha256 = hashlib.sha256(probe_body).hexdigest()
            try:
                self.client.put_object(
                    Bucket=self.bucket, Key=self._CHECKSUM_PROBE_KEY, Body=probe_body,
                    ChecksumAlgorithm="SHA256", ChecksumSHA256=_b64_checksum(probe_sha256))
                head = self.client.head_object(
                    Bucket=self.bucket, Key=self._CHECKSUM_PROBE_KEY, ChecksumMode="ENABLED")
                self._checksum_supported = head.get("ChecksumSHA256") == _b64_checksum(probe_sha256)
            except Exception:
                self._checksum_supported = False
            finally:
                try:
                    self.client.delete_object(Bucket=self.bucket, Key=self._CHECKSUM_PROBE_KEY)
                except Exception:
                    pass  # Best-effort cleanup; a stray probe key breaks nothing.
        return self._checksum_supported

    def _verify_by_head(self, logical: str, key: str, sha256: str, expected_size: int) -> None:
        """Confirm a write landed intact via one exact HEAD rather than a
        re-download-and-compare. Only reachable once `_supports_checksum()`
        has proven this endpoint returns `ChecksumSHA256` on request, so the
        echoed checksum is trustworthy evidence the bytes are correct — not
        merely evidence the key exists.
        """
        try:
            head = self.client.head_object(Bucket=self.bucket, Key=key, ChecksumMode="ENABLED")
        except Exception as exc:
            raise ArchiveError(f"S3 archive HEAD verification failed for {logical}: {exc}") from exc
        if (head.get("ChecksumSHA256") != _b64_checksum(sha256)
                or int(head.get("ContentLength", -1)) != expected_size):
            raise ArchiveError(f"S3 archive verification failed for {logical}")

    def put(self, source_system: str, sha256: str, content_type: str | None, body: bytes) -> str:
        if hashlib.sha256(body).hexdigest() != sha256:
            raise ArchiveError("payload hash does not match archive key")
        logical = logical_path(source_system, sha256, content_type)
        key = self._key(logical)
        checksummed = self._supports_checksum()
        if self.lookup(source_system, sha256) is None:
            kwargs = {"Bucket": self.bucket, "Key": key, "Body": body,
                      "ContentType": (content_type or "application/octet-stream").split(";", 1)[0]}
            if checksummed:
                # A transport checksum lets S3 itself reject a corrupted
                # upload before it is ever stored, rather than this pipeline
                # finding out only when it next reads the object back.
                kwargs["ChecksumAlgorithm"] = "SHA256"
                kwargs["ChecksumSHA256"] = _b64_checksum(sha256)
            self.client.put_object(**kwargs)
        if checksummed:
            self._verify_by_head(logical, key, sha256, len(body))
        else:
            # No proven checksum support at this endpoint: the only way left
            # to know the bytes are intact is to read them back and compare,
            # the synchronous full verification this backend always did
            # before checksums existed here.
            checked = self.lookup(source_system, sha256)
            if checked is None or checked.read_bytes() != body:
                raise ArchiveError(f"S3 archive verification failed for {logical}")
        return logical

    def put_stream(self, source_system: str, sha256: str,
                   content_type: str | None, stream) -> ArchiveObject:
        # S3-compatible clients differ in whether Body accepts a seekable
        # stream. Buffer only for this backend's upload call, while the caller
        # still avoids a separate archive lookup and receives the exact object.
        body = stream.read()
        logical = self.put(source_system, sha256, content_type, body)
        return ArchiveObject(logical, len(body), lambda: self.read(logical))

    def put_file(self, source_system: str, sha256: str,
                 content_type: str | None, path: Path) -> ArchiveObject:
        with Path(path).open("rb") as stream:
            return self.put_stream(source_system, sha256, content_type, stream)

    def read(self, logical: str) -> bytes:
        key = self._key(logical)
        logical_for_hash = f"data/raw/{key}"
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        body = response["Body"].read()
        _, sha, _ = _parts(logical_for_hash)
        if hashlib.sha256(body).hexdigest() != sha:
            raise ArchiveError(f"corrupt S3 archive object: {logical_for_hash}")
        return body

    def _objects(self) -> list[dict]:
        rows, token = [], None
        while True:
            kwargs = {"Bucket": self.bucket}
            if token:
                kwargs["ContinuationToken"] = token
            page = self.client.list_objects_v2(**kwargs)
            rows.extend({"key": f"data/raw/{x['Key']}", "bytes": int(x["Size"])}
                         for x in page.get("Contents", []))
            if not page.get("IsTruncated"):
                return rows
            token = page.get("NextContinuationToken")
            if not token:
                raise ArchiveError("S3 listing was truncated without a continuation token")

    def inventory(self, verify_hashes: bool = False) -> dict:
        rows = self._objects()
        if verify_hashes:
            for row in rows:
                body = self.read(row["key"])
                row["actual_bytes"] = len(body)
                row["sha256"] = hashlib.sha256(body).hexdigest()
        return _inventory(rows, True)

    def verify(self) -> dict:
        return _verify_inventory(self.inventory(True))


def _inventory(rows: list[dict], present: bool) -> dict:
    sources: dict[str, dict[str, int]] = {}
    for row in rows:
        parts = row["key"].split("/")
        source = parts[2] if len(parts) > 2 else "(root)"
        entry = sources.setdefault(source, {"files": 0, "bytes": 0})
        entry["files"] += 1
        entry["bytes"] += row["bytes"]
    return {"sources": sources, "files": len(rows), "bytes": sum(r["bytes"] for r in rows),
            "present": present, "objects": rows}


def _verify_inventory(inventory: dict) -> dict:
    failures = []
    for row in inventory["objects"]:
        try:
            _, expected, _ = _parts(row["key"])
        except ArchiveError as exc:
            failures.append({"key": row["key"], "error": str(exc)})
            continue
        if row.get("sha256") != expected or row.get("actual_bytes", row["bytes"]) != row["bytes"]:
            failures.append({"key": row["key"], "expected": expected, "actual": row.get("sha256"),
                             "expected_bytes": row["bytes"], "actual_bytes": row.get("actual_bytes")})
    return {"ok": not failures, "files": inventory["files"], "bytes": inventory["bytes"],
            "failures": failures, "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def get_archive(settings: Settings) -> Archive:
    return S3Archive(settings) if settings.archive_backend == "s3" else FilesystemArchive(settings.raw_archive_dir)


def archive_derived_artifact(settings: Settings, source_system: str, sha256: str,
                              content_type: str | None, body: bytes) -> str:
    """Writes a derived artefact — never the exact bytes a source served, see
    `pipeline.transports.types.TransportResult.derived_kind` — under
    `DERIVED_ARCHIVE_DIR`, content-addressed exactly like the raw archive
    (`FilesystemArchive.put`), but through its own small function rather
    than that class: `FilesystemArchive`/`S3Archive` and the `data/raw/...`
    shape `logical_path()`/`_parts()` parse are baked together, and widening
    them to a second prefix is a larger, riskier change than a Phase 3
    scaffolding pilot (a browser-rendered DOM, currently the only derived
    artefact anything produces) should make to code every module's fetch
    already depends on.

    Filesystem only for now — `DERIVED_ARCHIVE_S3_*` (`Settings`) stays
    reserved for whichever consumer moves derived storage to S3 first;
    Phase 3 needs an archive reference, not full backend parity with
    `get_archive()`.
    """
    if hashlib.sha256(body).hexdigest() != sha256:
        raise ArchiveError("payload hash does not match archive key")
    ext = mimetypes.guess_extension((content_type or "").split(";", 1)[0].strip()) or ".bin"
    out_dir = settings.derived_archive_dir / source_system
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sha256}{ext}"
    if not out_path.exists():
        out_path.write_bytes(body)
        DISK.add(len(body))
    return f"data/derived/{source_system}/{sha256}{ext}"
