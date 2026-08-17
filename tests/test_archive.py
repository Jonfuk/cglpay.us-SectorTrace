import hashlib
import io

import pytest

from pipeline.archive import ArchiveError, S3Archive
from pipeline.config import Settings


class FakeS3:
    def __init__(self):
        self.objects = {}

    def list_objects_v2(self, Bucket, Prefix="", ContinuationToken=None):
        keys = sorted(k for k in self.objects if k.startswith(Prefix))
        start = int(ContinuationToken or 0)
        page = keys[start:start + 1000]
        response = {"Contents": [{"Key": k, "Size": len(self.objects[k])} for k in page],
                    "IsTruncated": start + 1000 < len(keys)}
        if response["IsTruncated"]:
            response["NextContinuationToken"] = str(start + 1000)
        return response

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objects[Key] = Body

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[Key])}


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
