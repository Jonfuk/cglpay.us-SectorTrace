"""Record revision comparison (BETA-092).

Two revisions of one record, diffed field-aware (procurement notices sharing
an OCID) and text-aware (two parsed versions of one document). A publisher
amendment (`source` field) is labelled apart from a normalisation this
pipeline recomputed (`derived` field / parser change); the two change counts
are never added.
"""
from __future__ import annotations

import sqlite3

import pytest

from pipeline.web import record_diff
from pipeline.web.queries import QueryError


def _notice(conn, notice_id, *, ocid="ocds-x-1", title="Service tender",
            value="100000", ons="E09000007", published="2026-01-01"):
    conn.execute(
        "INSERT INTO contracts (notice_id, supplier_id, ocid, notice_type, "
        " buyer_name, buyer_ons_code, title, value_core, date_published, "
        " source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?, '', ?, 'tender', 'Camden', ?, ?, ?, ?, "
        " 'https://find-tender/x', ?, 200, 'find_tender', 'h')",
        (notice_id, ocid, ons, title, value, published, published + "T00:00:00Z"))
    conn.commit()


def test_ocds_diff_labels_source_and_derived_changes(conn: sqlite3.Connection) -> None:
    _notice(conn, "n1", title="Drug service", value="100000", ons="E09000007")
    _notice(conn, "n2", title="Drug & alcohol service", value="120000",
            ons="E09000007X", published="2026-03-01")
    out = record_diff.record_diff(conn, kind="ocds", a="n1", b="n2")
    assert out["same_ocid"] is True
    # title, value_core, date_published all verbatim from the release
    assert out["counts"]["changed_source"] == 3
    assert out["counts"]["changed_derived"] == 1  # buyer_ons_code
    changed = {f["field"]: f["class"] for f in out["fields"] if f["changed"]}
    assert changed == {"title": "source", "value_core": "source",
                       "date_published": "source", "buyer_ons_code": "derived"}
    assert "never added" in out["note"].lower()
    assert "total" not in out["counts"]


def test_ocds_diff_by_ocid_takes_the_two_most_recent(conn: sqlite3.Connection) -> None:
    _notice(conn, "old", published="2026-01-01")
    _notice(conn, "mid", published="2026-02-01")
    _notice(conn, "new", published="2026-03-01")
    out = record_diff.record_diff(conn, kind="ocds", ocid="ocds-x-1")
    assert out["a"]["notice_id"] == "mid" and out["b"]["notice_id"] == "new"


def test_ocds_diff_rejects_a_missing_notice(conn: sqlite3.Connection) -> None:
    _notice(conn, "n1")
    with pytest.raises(QueryError):
        record_diff.record_diff(conn, kind="ocds", a="n1", b="nope")


def _document(conn, *, source_system="committee_paper_promotion"):
    n = "2026-08-01T00:00:00Z"
    conn.execute(
        "INSERT INTO evidence_records (evidence_id, source_system, source_url, "
        " retrieved_at, http_status, payload_sha256, raw_object_path, mime_type, "
        " content_length, source_table, source_key, created_at) VALUES "
        "('ev1', ?, 'https://x/1', ?, 200, 's1', 'r/x.pdf', 'application/pdf', "
        " 10, 'committee_papers', 'k1', ?)", (source_system, n, n))
    conn.execute(
        "INSERT INTO document_records (document_id, evidence_id, source_table, "
        " source_key, document_type, mime_type, title, created_at, updated_at) "
        "VALUES ('d1', 'ev1', 'committee_papers', 'k1', 'committee_paper', "
        " 'application/pdf', 'Minutes', ?, ?)", (n, n))
    for vid, ver, active, at in [("v1", "1.0.0", 0, "2026-06-01T00:00:00Z"),
                                  ("v2", "2.0.0", 1, "2026-08-01T00:00:00Z")]:
        conn.execute(
            "INSERT INTO document_versions (document_version_id, document_id, "
            " parser_name, parser_version, parse_schema_version, config_hash, "
            " text_sha256, status, is_active, created_at) VALUES "
            "(?, 'd1', 'docling', ?, '1', ?, ?, 'parsed', ?, ?)",
            (vid, ver, f"cfg-{ver}", f"txt-{ver}", active, at))
    # v1: elements at seq 0,1  v2: seq 0 changed, seq 1 same, seq 2 added
    rows = [
        ("e10", "v1", 0, "para", "the old wording", "h-old"),
        ("e11", "v1", 1, "para", "unchanged line", "h-same"),
        ("e20", "v2", 0, "para", "the new wording", "h-new"),
        ("e21", "v2", 1, "para", "unchanged line", "h-same"),
        ("e22", "v2", 2, "para", "a brand new paragraph", "h-added"),
    ]
    for eid, vid, seq, etype, text, sha in rows:
        conn.execute(
            "INSERT INTO document_elements (document_element_id, "
            " document_version_id, element_type, sequence, text, text_sha256, "
            " metadata_json) VALUES (?, ?, ?, ?, ?, ?, '{}')",
            (eid, vid, etype, seq, text, sha))
    conn.commit()


def test_document_version_diff_is_element_aligned(conn: sqlite3.Connection) -> None:
    _document(conn)
    out = record_diff.record_diff(conn, kind="document", document_id="d1")
    assert out["a"]["document_version_id"] == "v1"
    assert out["b"]["document_version_id"] == "v2"
    assert out["counts"] == {"added": 1, "removed": 0, "changed": 1}
    kinds = {t["sequence"]: t["kind"] for t in out["text_changes"]}
    assert kinds == {0: "changed", 2: "added"}          # seq 1 omitted (identical)
    changed_meta = {m["field"] for m in out["meta"] if m["changed"]}
    assert {"parser_version", "config_hash", "text_sha256", "is_active"} <= changed_meta


def test_document_diff_refuses_a_non_allowlisted_source(conn: sqlite3.Connection) -> None:
    _document(conn, source_system="pfd_report")   # not in DOCUMENT_SEARCH_SOURCES
    with pytest.raises(QueryError):
        record_diff.record_diff(conn, kind="document", a="v1", b="v2")


def test_the_route_is_in_the_openapi_document() -> None:
    from pipeline.web import openapi
    assert "/api/v1/record_diff" in openapi.document()["paths"]
