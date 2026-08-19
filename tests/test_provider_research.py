from __future__ import annotations

import json

import pytest

from pipeline import provider_research
from pipeline.keywords import SUPPLIER_NAME_VARIANTS
from pipeline.web import public_queries, review


def _seed_providers(conn):
    for key, variants in SUPPLIER_NAME_VARIANTS.items():
        conn.execute(
            "INSERT INTO providers (provider_key, canonical_name, is_target) VALUES (?, ?, ?)",
            (key, variants[0], 1 if key == "change_grow_live" else 0),
        )
    conn.commit()


def _manifest(run_id: str, content_sha: str | None = None):
    item = {
        "provider_key": "change_grow_live",
        "entity_type": "company",
        "entity_identifier": "06228752",
        "category": "pay_workforce",
        "fact_type": "benefits_statement",
        "question": "What benefits does the provider publish?",
        "raw_finding": "The provider publishes a stated benefits package.",
        "interpretation": "This is provider-published recruitment evidence, not proof of staff take-up.",
        "source_url": "https://provider.example/careers",
        "publisher": "Change Grow Live",
        "published_date": "2026-08-01",
        "accessed_at": "2026-08-19T12:00:00Z",
        "citation": "Benefits page, section 2",
        "licence": "provider_own",
        "identity_match_basis": "provider_identifier",
        "time_period": "2026",
        "confidence": 0.9,
        "evidence_status": "candidate",
        "destination": "provider_research_evidence",
        "source_file": "source.txt",
    }
    if content_sha:
        item["content_sha256"] = content_sha
    return {
        "research_run": {
            "run_id": run_id,
            "prompt_version": "provider-research-v1",
            "actor_type": "ai",
            "actor_id": "test-runner",
            "model_id": "test-model",
            "started_at": "2026-08-19T12:00:00Z",
        },
        "items": [item],
    }


def test_manifest_validation_rejects_unknown_provider_without_writing(tmp_path):
    payload = _manifest("bad-run")
    payload["items"][0]["provider_key"] = "not_a_provider"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "source.txt").write_text("source bytes", encoding="utf-8")

    with pytest.raises(provider_research.ResearchError, match="13 configured"):
        provider_research.validate_manifest_file(path, bundle_dir=tmp_path)


def test_ingest_creates_candidate_and_two_review_gates(conn, settings, tmp_path):
    _seed_providers(conn)
    source = tmp_path / "source.txt"
    source.write_text("source bytes", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(_manifest("run-1")), encoding="utf-8")

    result = provider_research.ingest_manifest(
        manifest, settings=settings, bundle_dir=tmp_path)
    assert result["items"] == 1
    item = conn.execute("SELECT * FROM provider_research_items").fetchone()
    assert item["state"] == "candidate"
    assert item["identity_review_item_id"]
    assert item["evidence_review_item_id"]
    assert conn.execute(
        "SELECT COUNT(*) FROM review_queue WHERE module = 'provider_research'"
    ).fetchone()[0] == 2
    assert item["source_archive_path"].startswith("data/raw/provider_research/")


def test_only_twice_reviewed_items_can_be_promoted(conn, settings, tmp_path):
    _seed_providers(conn)
    (tmp_path / "source.txt").write_text("source bytes", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(_manifest("run-2")), encoding="utf-8")
    provider_research.ingest_manifest(manifest, settings=settings, bundle_dir=tmp_path)
    item = conn.execute("SELECT * FROM provider_research_items").fetchone()

    with pytest.raises(provider_research.ResearchError, match="both be approved"):
        provider_research.promote(conn, item["id"], "Reviewer")

    for review_id in (item["identity_review_item_id"], item["evidence_review_item_id"]):
        review.decide(conn, [review_id], "approved", "Reviewer")

    promoted = provider_research.promote(conn, item["id"], "Reviewer")
    assert promoted["provider_key"] == "change_grow_live"
    assert conn.execute("SELECT COUNT(*) FROM provider_research_evidence").fetchone()[0] == 1
    assert conn.execute(
        "SELECT state FROM provider_research_items WHERE id = ?", (item["id"],)
    ).fetchone()[0] == "approved"

    timeline = public_queries.provider_timeline(conn, "change_grow_live")
    assert timeline["research_evidence"][0]["category"] == "pay_workforce"
    assert timeline["caveats"]["provider_research"]


def test_coverage_returns_all_thirteen_providers(conn):
    _seed_providers(conn)
    report = provider_research.coverage(conn)
    assert len(report["providers"]) == 13
    assert len(report["matrix"]) == 13
    assert "identity" in report["categories"]
    assert all(len(row["cells"]) == len(report["categories"]) for row in report["matrix"])


def test_changed_source_creates_version_and_supersedes_prior_candidate(conn, settings, tmp_path):
    _seed_providers(conn)
    source = tmp_path / "source.txt"
    manifest = tmp_path / "manifest.json"

    source.write_text("original source bytes", encoding="utf-8")
    manifest.write_text(json.dumps(_manifest("run-original")), encoding="utf-8")
    provider_research.ingest_manifest(manifest, settings=settings, bundle_dir=tmp_path)
    original = conn.execute("SELECT * FROM provider_research_items").fetchone()

    source.write_text("materially changed source bytes", encoding="utf-8")
    manifest.write_text(json.dumps(_manifest("run-changed")), encoding="utf-8")
    provider_research.ingest_manifest(manifest, settings=settings, bundle_dir=tmp_path)
    rows = conn.execute(
        "SELECT * FROM provider_research_items ORDER BY id"
    ).fetchall()

    assert len(rows) == 2
    assert rows[1]["stable_candidate_key"] == rows[0]["stable_candidate_key"]
    assert rows[1]["supersedes_item_id"] == original["id"]
    assert rows[0]["state"] == "superseded"
