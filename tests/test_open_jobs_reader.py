"""Offline contract and bounded-reader tests for Open Jobs artifacts."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

from pipeline.open_jobs.contract import (
    DIFF_CONTRACT,
    SNAPSHOT_CONTRACT,
    ContractError,
    IntegrityError,
    ResourceLimitError,
    SchemaError,
    natural_key,
    parse_release_metadata,
    verify_artifact,
)
from pipeline.open_jobs.reader import DependencyUnavailable, ReaderError, ReaderLimits, read_rows


def _row(**overrides):
    row = {"ats": "greenhouse", "slug": "example", "id": "id/with-separators",
           "op": "added", "title": "Recovery worker"}
    row.update(overrides)
    return row


def test_source_identity_is_lossless_and_case_sensitive():
    assert natural_key(_row()) == ("greenhouse", "example", "id/with-separators")
    assert natural_key(_row(id="ID/with-separators")) != natural_key(_row())


def test_snapshot_and_diff_contracts_have_distinct_operation_requirements():
    SNAPSHOT_CONTRACT.validate_row({"ats": "a", "slug": "b", "id": "c"})
    with pytest.raises(SchemaError, match="op"):
        DIFF_CONTRACT.validate_row({"ats": "a", "slug": "b", "id": "c"})
    with pytest.raises(ContractError, match="unknown Open Jobs operation"):
        DIFF_CONTRACT.validate_row(_row(op="reopened"))


def test_rows_reject_unknown_removal_reason_and_duplicate_event():
    with pytest.raises(ContractError, match="removal_reason"):
        DIFF_CONTRACT.validate_row(_row(op="removed", removal_reason="filled"))
    with pytest.raises(ContractError, match="duplicate"):
        DIFF_CONTRACT.validate_rows([_row(), _row()])


def test_release_metadata_requires_exact_parts_and_preserves_mapping():
    digest = "a" * 64
    raw = {"schema_version": "diff-v1", "release_id": "2026-09-08",
           "parent": "previous", "parts": [{"path": "lite/data_0.parquet",
           "sha256": digest, "size_bytes": 12}], "row_count": 1}
    release = parse_release_metadata(raw)
    assert release.parts[0].sha256 == digest
    assert release.metadata is raw
    with pytest.raises(ContractError, match="parts list"):
        parse_release_metadata({"schema_version": "diff-v1", "release_id": "x", "parts": []})


def test_artifact_verification_checks_bytes_and_limits(tmp_path: Path):
    artifact = tmp_path / "part.parquet"
    artifact.write_bytes(b"fixture bytes")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    verified = verify_artifact(artifact, digest, expected_size=13)
    assert verified.sha256 == digest
    assert verified.size_bytes == 13
    with pytest.raises(IntegrityError, match="sha256"):
        verify_artifact(artifact, "b" * 64)
    with pytest.raises(ResourceLimitError, match="limit"):
        verify_artifact(artifact, digest, max_bytes=2)


def test_reader_import_is_safe_without_pyarrow(tmp_path: Path):
    # The package imports the reader but never imports the optional decoder.
    # This assertion remains meaningful on both dependency-present and absent
    # test hosts because importlib checks the module's load state directly.
    import pipeline.open_jobs.reader as reader

    assert "pyarrow" not in reader.__dict__
    if importlib.util.find_spec("pyarrow") is None:
        artifact = tmp_path / "missing-dependency.parquet"
        artifact.write_bytes(b"fixture")
        with pytest.raises(DependencyUnavailable):
            read_rows(artifact)


def test_reader_rejects_urls_before_optional_dependency_lookup():
    with pytest.raises(ReaderError, match="local path"):
        read_rows("https://example.test/data.parquet")


def test_synthetic_parquet_rows_and_projection_are_bounded(tmp_path: Path):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    path = tmp_path / "diff.parquet"
    table = pa.table({
        "ats": ["greenhouse", "lever"], "slug": ["a", "b"],
        "id": ["one", "two"], "op": ["added", "changed"],
        "title": ["Recovery worker", None],
    })
    pq.write_table(table, path)
    rows = read_rows(path, columns=("ats", "id", "title"),
                     limits=ReaderLimits(max_artifact_bytes=path.stat().st_size + 1,
                                         max_record_bytes=1024, decode_batch_rows=1))
    assert rows == [{"ats": "greenhouse", "id": "one", "title": "Recovery worker"},
                    {"ats": "lever", "id": "two", "title": None}]


def test_synthetic_parquet_oversize_record_is_rejected(tmp_path: Path):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    path = tmp_path / "oversize.parquet"
    pq.write_table(pa.table({"ats": ["a"], "slug": ["b"], "id": ["c"],
                             "op": ["added"], "title": ["x" * 100]}), path)
    with pytest.raises(ResourceLimitError, match="record"):
        read_rows(path, limits=ReaderLimits(max_artifact_bytes=path.stat().st_size + 1,
                                            max_record_bytes=10, decode_batch_rows=1))
