import hashlib
import io

import pytest

from pipeline.archive import ArchiveError, FilesystemArchive, S3Archive
from pipeline.config import Settings


class _NotFound(Exception):
    """Shaped like `botocore.exceptions.ClientError` (a `.response` dict with
    an `Error.Code`) so `pipeline.archive._is_not_found` recognises it without
    this test needing the real (optional, `storage`-extra) botocore package.
    """

    def __init__(self, key: str):
        self.response = {"Error": {"Code": "404", "Message": f"no such key: {key}"}}
        super().__init__(self.response["Error"]["Message"])


class FakeS3:
    """A minimal S3-compatible client double.

    `checksum_capable` toggles whether `head_object` echoes back a checksum
    it was given on `put_object` — the one signal `S3Archive._supports_
    checksum()` trusts. Off models a real, encountered class of endpoint:
    one that accepts `ChecksumAlgorithm`/`ChecksumSHA256` without erroring
    but never actually validates or returns them.
    """

    def __init__(self, checksum_capable: bool = True):
        self.objects: dict[str, bytes] = {}
        self.checksums: dict[str, str] = {}
        self.checksum_capable = checksum_capable
        self.put_calls: list[dict] = []
        self.head_calls: list[str] = []

    def list_objects_v2(self, Bucket, Prefix="", ContinuationToken=None):
        keys = sorted(k for k in self.objects if k.startswith(Prefix))
        start = int(ContinuationToken or 0)
        page = keys[start:start + 1000]
        response = {"Contents": [{"Key": k, "Size": len(self.objects[k])} for k in page],
                    "IsTruncated": start + 1000 < len(keys)}
        if response["IsTruncated"]:
            response["NextContinuationToken"] = str(start + 1000)
        return response

    def put_object(self, Bucket, Key, Body, ContentType=None,
                    ChecksumAlgorithm=None, ChecksumSHA256=None):
        self.put_calls.append({"Key": Key, "ChecksumAlgorithm": ChecksumAlgorithm,
                                "ChecksumSHA256": ChecksumSHA256})
        self.objects[Key] = Body
        if self.checksum_capable and ChecksumSHA256:
            self.checksums[Key] = ChecksumSHA256
        else:
            self.checksums.pop(Key, None)

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[Key])}

    def head_object(self, Bucket, Key, ChecksumMode=None):
        self.head_calls.append(Key)
        if Key not in self.objects:
            raise _NotFound(Key)
        head = {"ContentLength": len(self.objects[Key])}
        if ChecksumMode == "ENABLED" and Key in self.checksums:
            head["ChecksumSHA256"] = self.checksums[Key]
        return head

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)
        self.checksums.pop(Key, None)


def settings():
    return Settings(contact_email="test@example.com", archive_s3_bucket="bucket",
                    archive_s3_endpoint="https://s3.example", archive_s3_region="ams",
                    archive_s3_url_style="virtual", archive_s3_access_key="key",
                    archive_s3_secret="secret")


def test_s3_write_read_and_paginated_inventory():
    client = FakeS3()
    archive = S3Archive(settings(), client=client)
    body = b"payload"
    sha = hashlib.sha256(body).hexdigest()
    archive.put("source", sha, "text/plain", body)
    for i in range(1001):
        client.objects[f"other/{i:04d}"] = b"x"
    assert archive.read(f"data/raw/source/{sha}.txt") == body
    assert archive.inventory()["files"] == 1002


def test_s3_rejects_corrupt_bytes():
    client = FakeS3()
    archive = S3Archive(settings(), client=client)
    sha = hashlib.sha256(b"good").hexdigest()
    client.objects[f"source/{sha}.bin"] = b"bad"
    with pytest.raises(ArchiveError):
        archive.read(f"data/raw/source/{sha}.bin")


# --- get_by_ref (exact-reference lookup, no prefix/bucket listing) ---------


def test_filesystem_get_by_ref_finds_an_object_by_its_exact_key(tmp_path):
    archive = FilesystemArchive(tmp_path)
    body = b"hello"
    sha = hashlib.sha256(body).hexdigest()
    logical = archive.put("source", sha, "text/plain", body)

    obj = archive.get_by_ref(logical)

    assert obj is not None
    assert obj.logical_path == logical
    assert obj.size == len(body)
    assert obj.read_bytes() == body


def test_filesystem_get_by_ref_returns_none_for_a_missing_object(tmp_path):
    archive = FilesystemArchive(tmp_path)
    sha = hashlib.sha256(b"never written").hexdigest()
    assert archive.get_by_ref(f"data/raw/source/{sha}.bin") is None


def test_s3_get_by_ref_uses_head_not_a_bucket_listing():
    client = FakeS3()
    archive = S3Archive(settings(), client=client)
    body = b"payload"
    sha = hashlib.sha256(body).hexdigest()
    logical = archive.put("source", sha, "text/plain", body)
    client.head_calls.clear()

    obj = archive.get_by_ref(logical)

    assert obj is not None
    assert obj.logical_path == logical
    assert obj.size == len(body)
    assert obj.read_bytes() == body
    # An exact HEAD, never a Prefix listing — the whole point of a stored
    # reference over a re-derived (source, sha256) lookup.
    assert client.head_calls == [f"source/{sha}.txt"]


def test_s3_get_by_ref_returns_none_for_a_missing_key():
    client = FakeS3()
    archive = S3Archive(settings(), client=client)
    sha = hashlib.sha256(b"never written").hexdigest()
    assert archive.get_by_ref(f"data/raw/source/{sha}.bin") is None


# --- checksum capability probing and HEAD-based verification --------------


def test_s3_put_uses_checksum_and_head_verification_when_supported():
    client = FakeS3(checksum_capable=True)
    archive = S3Archive(settings(), client=client)
    body = b"payload"
    sha = hashlib.sha256(body).hexdigest()

    logical = archive.put("source", sha, "text/plain", body)

    assert archive._checksum_supported is True
    # The real put carried a transport checksum, not only the probe's.
    real_put = next(c for c in client.put_calls if c["Key"] == f"source/{sha}.txt")
    assert real_put["ChecksumAlgorithm"] == "SHA256"
    assert real_put["ChecksumSHA256"]
    assert archive.read(logical) == body
    # The probe object cleaned up after itself.
    assert archive._CHECKSUM_PROBE_KEY not in client.objects


def test_s3_put_falls_back_to_full_verification_when_checksum_unsupported():
    client = FakeS3(checksum_capable=False)
    archive = S3Archive(settings(), client=client)
    body = b"payload"
    sha = hashlib.sha256(body).hexdigest()

    logical = archive.put("source", sha, "text/plain", body)

    assert archive._checksum_supported is False
    assert archive.read(logical) == body


def test_s3_put_raises_when_head_verification_disagrees():
    """A checksum-capable endpoint whose HEAD disagrees with what was
    written must fail loudly rather than accept a corrupted upload —
    exercised here without a real network round trip by writing an object
    whose recorded checksum already does not match its bytes."""
    client = FakeS3(checksum_capable=True)
    archive = S3Archive(settings(), client=client)
    body = b"payload"
    sha = hashlib.sha256(body).hexdigest()
    key = f"source/{sha}.txt"
    client.objects[key] = body
    client.checksums[key] = "not-the-right-checksum"

    with pytest.raises(ArchiveError):
        archive.put("source", sha, "text/plain", body)


def test_s3_checksum_support_is_probed_once_and_cached():
    client = FakeS3(checksum_capable=True)
    archive = S3Archive(settings(), client=client)
    body1, body2 = b"one", b"two"
    sha1, sha2 = hashlib.sha256(body1).hexdigest(), hashlib.sha256(body2).hexdigest()

    archive.put("source", sha1, "text/plain", body1)
    probe_puts_after_first = sum(1 for c in client.put_calls
                                  if c["Key"] == archive._CHECKSUM_PROBE_KEY)
    archive.put("source", sha2, "text/plain", body2)
    probe_puts_after_second = sum(1 for c in client.put_calls
                                   if c["Key"] == archive._CHECKSUM_PROBE_KEY)

    assert probe_puts_after_first == 1
    assert probe_puts_after_second == 1  # not probed again on the second put
