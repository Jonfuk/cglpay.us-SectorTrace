"""Offline contract tests for the operator-only OpenTender mirror."""
from __future__ import annotations

import gzip
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

from pipeline.modules import m40_opentender_registry as opentender
from pipeline.opentender import ParseSummary, iter_observations, reconcile
from pipeline.registry import ModuleContext
from pipeline.web.datasets import PUBLIC_DATASETS

FIXTURE = Path(__file__).parent / "fixtures" / "opentender_compiled.jsonl"


def test_mirror_is_not_in_public_dataset_projection():
    assert all(dataset.module != opentender.MODULE for dataset in PUBLIC_DATASETS)


def test_disabled_collector_is_inert():
    class NoUse:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("disabled collector touched the database")

    ctx = SimpleNamespace(
        settings=SimpleNamespace(opentender_enabled=False),
        conn=NoUse(), since=None, source="all", dry_run=False, limit=None,
    )
    assert opentender.collect(ctx) == {
        "packages": 0, "observations": 0, "failures": 0, "reviews": 0,
    }


def test_parser_keeps_valid_rows_and_quarantines_bad_siblings():
    summary = ParseSummary()
    rows = list(iter_observations(FIXTURE, summary=summary))
    assert [row.ocid for row in rows] == ["ocds-70d2nz-1", "ocds-70d2nz-2"]
    assert rows[0].cpv_codes == ("85000000",)
    assert summary.objects == 4
    assert [failure.reason for failure in summary.failures] == [
        "ocid does not use expected OpenTender prefix 'ocds-70d2nz'", "invalid JSON"
    ]


def test_parser_accepts_gzip_and_single_member_zip(tmp_path):
    source = FIXTURE.read_bytes()
    compressed = tmp_path / "opentender.jsonl.gz"
    compressed.write_bytes(gzip.compress(source))
    packed = tmp_path / "opentender.zip"
    with zipfile.ZipFile(packed, "w") as archive:
        archive.writestr("compiled.jsonl", source)

    assert len(list(iter_observations(compressed))) == 2
    assert len(list(iter_observations(packed))) == 2


def test_reconciliation_only_exact_ocid_is_not_a_review_candidate():
    observation = next(iter(iter_observations(FIXTURE)))
    result = reconcile(observation, [{
        "ocid": observation.ocid, "buyer_name": "Northshire Council",
        "title": "Community treatment services",
    }])
    assert result == {
        "status": "exact_ocid", "matched_ocid": observation.ocid,
        "candidate_count": 1, "basis": "ocid",
    }


def test_reconciliation_marks_different_ocid_as_candidate():
    rows = list(iter_observations(FIXTURE))
    result = reconcile(rows[1], [{
        "ocid": "ocds-b5fd17-primary",
        "buyer_name": rows[1].buyer_name,
        "title": rows[1].title,
        "date_published": rows[1].date_published,
        "value_core": rows[1].value_amount,
        "currency": rows[1].value_currency,
        "cpv_codes": ",".join(rows[1].cpv_codes),
    }])
    assert result["status"] == "candidate_match"
    assert result["matched_ocid"] == "ocds-b5fd17-primary"


def test_collect_stores_mirror_rows_and_does_not_write_contracts(conn, settings):
    conn.execute(
        "INSERT INTO contracts (notice_id, supplier_id, ocid, buyer_name, title, cpv_codes, "
        "value_core, currency, date_published, source_url, retrieved_at, http_status, "
        "source_system, payload_sha256) VALUES (%s, '', %s, %s, %s, %s, %s, %s, %s, "
        "%s, %s, 200, 'find_a_tender', 'primary-1')",
        ("primary-1", "ocds-70d2nz-1", "Northshire Council",
         "Community treatment services", "85000000", 1000, "GBP", "2024-01-15",
         "https://find.example/primary-1", "2026-09-13T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO contracts (notice_id, supplier_id, ocid, buyer_name, title, cpv_codes, "
        "value_core, currency, date_published, source_url, retrieved_at, http_status, "
        "source_system, payload_sha256) VALUES (%s, '', %s, %s, %s, %s, %s, %s, %s, "
        "%s, %s, 200, 'find_a_tender', 'primary-2')",
        ("primary-2", "ocds-b5fd17-primary", "Southshire Council",
         "Recovery support", "85100000", 2000, "GBP", "2024-02-15",
         "https://find.example/primary-2", "2026-09-13T00:00:00Z"),
    )
    conn.commit()
    settings.opentender_enabled = True
    settings.opentender_package_path = FIXTURE
    result = opentender.collect(ModuleContext(
        conn=conn, settings=settings, since=None, dry_run=False, limit=None,
    ))
    assert result == {"packages": 1, "observations": 2, "failures": 2, "reviews": 1}
    assert conn.execute("SELECT COUNT(*) AS n FROM contracts").fetchone()["n"] == 2
    mirror = conn.execute(
        "SELECT ocid, match_status, matched_ocid FROM procurement_mirror_observations "
        "ORDER BY ocid").fetchall()
    assert [dict(row) for row in mirror] == [
        {"ocid": "ocds-70d2nz-1", "match_status": "exact_ocid", "matched_ocid": "ocds-70d2nz-1"},
        {"ocid": "ocds-70d2nz-2", "match_status": "candidate_match", "matched_ocid": "ocds-b5fd17-primary"},
    ]
    review = conn.execute(
        "SELECT item_type, raw_value, context_json FROM review_queue "
        "WHERE module = 'm40_opentender_registry'").fetchall()
    assert len(review) == 1
    assert review[0]["item_type"] == "opentender_candidate_match"
    assert json.loads(review[0]["context_json"])["source_record_id"] == "release-2"
    attempt = conn.execute(
        "SELECT status, result_count, coverage_state FROM collection_attempts "
        "WHERE module = 'm40_opentender_registry'").fetchone()
    assert dict(attempt) == {"status": "ok", "result_count": 2, "coverage_state": "covered"}
