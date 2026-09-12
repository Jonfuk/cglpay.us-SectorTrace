"""The transport-neutral contract itself (scrapy.md Phase 0), independent of
any transport that implements it.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from pipeline.transports.types import FailureClass, MissingProvenance, TransportResult

NOW = datetime.now(timezone.utc)


def _ok(**overrides) -> TransportResult:
    fields = dict(
        transport="test", source_system="test_source", requested_url="https://x.example/a",
        retrieved_at=NOW, ok=True, failure_class=FailureClass.NONE,
        final_url="https://x.example/a", status_code=200, body=b"hello",
        payload_sha256="a" * 64, raw_archive_ref="data/raw/test_source/aaaa.bin",
    )
    fields.update(overrides)
    return TransportResult(**fields)


def _failed(**overrides) -> TransportResult:
    fields = dict(
        transport="test", source_system="test_source", requested_url="https://x.example/a",
        retrieved_at=NOW, ok=False, failure_class=FailureClass.TIMEOUT,
        failure_detail="took too long",
    )
    fields.update(overrides)
    return TransportResult(**fields)


def test_ok_result_must_carry_failure_class_none():
    with pytest.raises(ValueError):
        TransportResult(
            transport="test", source_system="s", requested_url="https://x.example/",
            retrieved_at=NOW, ok=True, failure_class=FailureClass.TIMEOUT,
        )


def test_failed_result_must_not_carry_failure_class_none():
    with pytest.raises(ValueError):
        TransportResult(
            transport="test", source_system="s", requested_url="https://x.example/",
            retrieved_at=NOW, ok=False, failure_class=FailureClass.NONE,
        )


def test_content_type_reads_headers_case_insensitively():
    result = _ok(headers={"Content-Type": "text/plain; charset=utf-8"})
    assert result.content_type == "text/plain; charset=utf-8"


def test_content_type_absent_is_none():
    assert _ok(headers={}).content_type is None


# --- require_provenance(): the persistence gate ------------------------------

def test_successful_result_with_full_provenance_passes():
    _ok().require_provenance()  # must not raise


def test_missing_payload_hash_is_rejected_when_body_present():
    result = _ok(payload_sha256="")
    with pytest.raises(MissingProvenance):
        result.require_provenance()


def test_missing_archive_ref_is_rejected_when_body_present():
    result = _ok(raw_archive_ref=None)
    with pytest.raises(MissingProvenance):
        result.require_provenance()


def test_missing_requested_url_is_always_rejected():
    result = _ok(requested_url="")
    with pytest.raises(MissingProvenance):
        result.require_provenance()


def test_failed_result_with_no_body_does_not_need_a_hash_or_archive_ref():
    # A robots-disallowed or timed-out fetch never received bytes to hash.
    # Only requested_url/retrieved_at are required of it.
    _failed().require_provenance()  # must not raise


def test_failed_result_with_a_body_still_needs_hash_and_archive_ref():
    # e.g. a 404 page with an HTML body: PipelineHTTPClient archives that
    # body regardless of status, and this contract holds every transport to
    # the same rule.
    result = _failed(failure_class=FailureClass.HTTP_ERROR, status_code=404,
                      body=b"<html>not found</html>")
    with pytest.raises(MissingProvenance):
        result.require_provenance()

    result = replace_provenance(result, payload_sha256="b" * 64,
                                 raw_archive_ref="data/raw/test_source/bbbb.bin")
    result.require_provenance()  # now complete


def replace_provenance(result: TransportResult, **overrides) -> TransportResult:
    from dataclasses import replace

    return replace(result, **overrides)
