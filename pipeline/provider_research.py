"""Ingest and promote provider research manifests.

Research is deliberately a candidate layer. A manifest may say that a source
was found, blocked, absent, or already represented elsewhere in the warehouse,
but it cannot make any of those statements public by itself. The identity and
evidence review queues are separate so a correct quotation attached to the
wrong legal entity cannot become publishable evidence.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from pipeline import archive, db
from pipeline.config import Settings, get_settings
from pipeline.keywords import SUPPLIER_NAME_VARIANTS

MODULE = "provider_research"
STATUSES = {
    "evidence_found", "candidate", "no_evidence", "source_inaccessible",
    "not_applicable", "existing_project_evidence",
}
IDENTITY_BASES = {
    "provider_identifier", "source_named_provider", "historical_name",
    "group_relationship", "exact_name", "unknown",
}
REVIEW_STAGES = {"identity", "evidence"}
DEFAULT_CATEGORIES = (
    "identity", "group_structure", "pay_workforce", "contracts",
    "service_footprint", "finance", "regulation", "legal_risk",
    "strategy_governance",
)


class ResearchError(ValueError):
    """A manifest or promotion that cannot be accepted safely."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _text(value, field: str, *, required: bool = False, limit: int | None = None) -> str | None:
    if value is None:
        if required:
            raise ResearchError(f"{field} is required")
        return None
    result = str(value).strip()
    if required and not result:
        raise ResearchError(f"{field} is required")
    if limit and len(result) > limit:
        raise ResearchError(f"{field} is longer than {limit} characters")
    return result or None


def _url(value: str | None, field: str, *, required: bool = False) -> str | None:
    value = _text(value, field, required=required, limit=2000)
    if value is None:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ResearchError(f"{field} must be an absolute http(s) URL")
    return value


def _stable_candidate_key(item: dict) -> str:
    identity = {
        "provider_key": item["provider_key"],
        "entity_type": item.get("entity_type"),
        "entity_identifier": item.get("entity_identifier"),
        "category": item["category"],
        "fact_type": item["fact_type"],
        "source_url": item.get("source_url"),
        "published_date": item.get("published_date"),
        "time_period": item.get("time_period"),
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return "research:" + _sha256(encoded)


def _candidate_key(item: dict, stable_key: str, content_sha256: str | None) -> str:
    if not content_sha256:
        return stable_key
    return stable_key + ":" + content_sha256


def _manifest_parts(payload: dict) -> tuple[dict, list[dict]]:
    if not isinstance(payload, dict):
        raise ResearchError("manifest must be a JSON object")
    metadata = payload.get("research_run") or payload.get("run")
    items = payload.get("items")
    if not isinstance(metadata, dict):
        raise ResearchError("manifest.research_run must be an object")
    if not isinstance(items, list) or not items:
        raise ResearchError("manifest.items must be a non-empty array")
    return metadata, items


def validate_manifest(payload: dict, *, bundle_dir: Path | None = None) -> dict:
    """Validate and normalize a manifest without writing anything."""
    metadata, raw_items = _manifest_parts(payload)
    prompt_version = _text(metadata.get("prompt_version"), "research_run.prompt_version", required=True, limit=200)
    run_id = _text(metadata.get("run_id"), "research_run.run_id", required=True, limit=200)
    actor_type = _text(metadata.get("actor_type", "human"), "research_run.actor_type", required=True)
    if actor_type not in {"human", "ai"}:
        raise ResearchError("research_run.actor_type must be human or ai")
    actor_id = _text(metadata.get("actor_id"), "research_run.actor_id", limit=200)
    model_id = _text(metadata.get("model_id"), "research_run.model_id", limit=200)
    if actor_type == "ai" and not actor_id:
        raise ResearchError("AI research runs require research_run.actor_id")

    providers = set(SUPPLIER_NAME_VARIANTS)
    normalized: list[dict] = []
    source_count = 0
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            raise ResearchError(f"items[{index}] must be an object")
        prefix = f"items[{index}]"
        provider_key = _text(raw.get("provider_key"), f"{prefix}.provider_key", required=True)
        if provider_key not in providers:
            raise ResearchError(f"{prefix}.provider_key is not one of the 13 configured providers")
        category = _text(raw.get("category"), f"{prefix}.category", required=True, limit=100)
        fact_type = _text(raw.get("fact_type"), f"{prefix}.fact_type", required=True, limit=100)
        question = _text(raw.get("question"), f"{prefix}.question", required=True, limit=4000)
        status = _text(raw.get("evidence_status"), f"{prefix}.evidence_status", required=True)
        if status not in STATUSES:
            raise ResearchError(f"{prefix}.evidence_status is not supported")
        identity_basis = _text(raw.get("identity_match_basis"), f"{prefix}.identity_match_basis", required=True)
        if identity_basis not in IDENTITY_BASES:
            raise ResearchError(f"{prefix}.identity_match_basis is not supported")
        destination = _text(raw.get("destination"), f"{prefix}.destination", required=True, limit=200)
        accessed_at = _text(raw.get("accessed_at"), f"{prefix}.accessed_at", required=True, limit=100)
        source_url = _url(raw.get("source_url"), f"{prefix}.source_url", required=status != "not_applicable")
        citation = _text(raw.get("citation"), f"{prefix}.citation", required=status != "not_applicable", limit=4000)
        publisher = _text(raw.get("publisher"), f"{prefix}.publisher", required=status != "not_applicable", limit=500)
        published_date = _text(raw.get("published_date"), f"{prefix}.published_date", required=status != "not_applicable", limit=100)
        licence = _text(raw.get("licence"), f"{prefix}.licence", required=status != "not_applicable", limit=1000)
        finding = _text(raw.get("raw_finding"), f"{prefix}.raw_finding", limit=20000)
        interpretation = _text(raw.get("interpretation"), f"{prefix}.interpretation", limit=20000)
        if status in {"evidence_found", "candidate", "existing_project_evidence"} and not finding:
            raise ResearchError(f"{prefix}.raw_finding is required for {status}")
        if status == "no_evidence" and not (finding or interpretation):
            raise ResearchError(f"{prefix} needs a search result or interpretation for no_evidence")
        confidence = raw.get("confidence")
        if confidence is not None:
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                raise ResearchError(f"{prefix}.confidence must be between 0 and 1") from None
            if not 0 <= confidence <= 1:
                raise ResearchError(f"{prefix}.confidence must be between 0 and 1")
        priority_score = raw.get("priority_score")
        if priority_score is not None:
            try:
                priority_score = float(priority_score)
            except (TypeError, ValueError):
                raise ResearchError(f"{prefix}.priority_score must be numeric") from None
        source_file = _text(raw.get("source_file"), f"{prefix}.source_file", limit=1000)
        content_sha256 = _text(raw.get("content_sha256"), f"{prefix}.content_sha256", limit=64)
        source_archive_path = None
        if source_file:
            if bundle_dir is None:
                raise ResearchError(f"{prefix}.source_file requires --bundle-dir")
            root = bundle_dir.resolve()
            path = (root / source_file).resolve()
            if root not in path.parents and path != root:
                raise ResearchError(f"{prefix}.source_file is outside the bundle directory")
            if not path.is_file():
                raise ResearchError(f"{prefix}.source_file does not exist: {source_file}")
            body = path.read_bytes()
            actual = _sha256(body)
            if content_sha256 and content_sha256 != actual:
                raise ResearchError(f"{prefix}.content_sha256 does not match source_file")
            content_sha256 = actual
            source_count += 1
        elif status in {"evidence_found", "candidate"}:
            raise ResearchError(f"{prefix}.source_file is required for source-backed evidence")
        if not content_sha256 and status in {"evidence_found", "candidate"}:
            raise ResearchError(f"{prefix}.content_sha256 is required for source-backed evidence")

        normalized.append({
            "provider_key": provider_key,
            "entity_type": _text(raw.get("entity_type"), f"{prefix}.entity_type", limit=100),
            "entity_identifier": _text(raw.get("entity_identifier"), f"{prefix}.entity_identifier", limit=300),
            "category": category,
            "fact_type": fact_type,
            "question": question,
            "raw_finding": finding,
            "interpretation": interpretation,
            "source_url": source_url,
            "publisher": publisher,
            "published_date": published_date,
            "accessed_at": accessed_at,
            "citation": citation,
            "licence": licence,
            "identity_match_basis": identity_basis,
            "time_period": _text(raw.get("time_period"), f"{prefix}.time_period", limit=200),
            "confidence": confidence,
            "evidence_status": status,
            "destination": destination,
            "content_sha256": content_sha256,
            "source_file": source_file,
            "source_archive_path": source_archive_path,
            "priority_score": priority_score,
            "priority_factors_json": json.dumps(raw.get("priority_factors") or {}, sort_keys=True),
            "stable_candidate_key": None,
        })

    return {
        "run_id": run_id,
        "prompt_version": prompt_version,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "model_id": model_id,
        "started_at": _text(metadata.get("started_at"), "research_run.started_at", limit=100) or _now(),
        "completed_at": _text(metadata.get("completed_at"), "research_run.completed_at", limit=100),
        "items": normalized,
        "source_count": source_count,
    }


def _review_id(conn, raw_value: str) -> int:
    row = conn.execute(
        "SELECT id FROM review_queue WHERE module = ? AND item_type = ? AND raw_value = ?",
        (MODULE, "provider_research", raw_value),
    ).fetchone()
    if not row:
        raise ResearchError(f"could not create review item for {raw_value}")
    return int(row["id"])


def ingest_manifest(
    manifest_path: Path,
    *,
    settings: Settings | None = None,
    bundle_dir: Path | None = None,
) -> dict:
    """Validate and atomically ingest a manifest and its source bundle."""
    settings = settings or get_settings()
    manifest_path = Path(manifest_path).resolve()
    if not manifest_path.is_file():
        raise ResearchError(f"manifest does not exist: {manifest_path}")
    manifest_bytes = manifest_path.read_bytes()
    try:
        payload = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchError(f"manifest is not valid UTF-8 JSON: {exc}") from None
    bundle = Path(bundle_dir).resolve() if bundle_dir else None
    normalized = validate_manifest(payload, bundle_dir=bundle)
    manifest_sha = _sha256(manifest_bytes)
    now = _now()
    raw = archive.get_archive(settings)
    manifest_archive = raw.put("provider_research", manifest_sha, "application/json", manifest_bytes)
    archived_sources: dict[str, str] = {}
    if bundle:
        for item in normalized["items"]:
            source_file = item["source_file"]
            if not source_file or item["content_sha256"] in archived_sources:
                continue
            path = (bundle / source_file).resolve()
            body = path.read_bytes()
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            archived_sources[item["content_sha256"]] = raw.put(
                "provider_research", item["content_sha256"], content_type, body)

    conn = db.get_connection(settings)
    try:
        db.apply_migrations(conn, db.migrations_dir_for(settings))
        existing = conn.execute(
            "SELECT run_id FROM provider_research_runs WHERE manifest_sha256 = ?",
            (manifest_sha,),
        ).fetchone()
        if existing:
            return {"run_id": existing["run_id"], "manifest_sha256": manifest_sha,
                    "items": 0, "duplicate": True}
        conn.execute(
            "INSERT INTO provider_research_runs "
            "(run_id, prompt_version, actor_type, actor_id, model_id, started_at, "
            "completed_at, manifest_sha256, manifest_archive_path, source_bundle_archive_prefix, "
            "status, item_count, source_count, validation_errors, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ingested', ?, ?, NULL, ?)",
            (normalized["run_id"], normalized["prompt_version"], normalized["actor_type"],
             normalized["actor_id"], normalized["model_id"], normalized["started_at"],
             normalized["completed_at"] or now, manifest_sha, manifest_archive,
             "data/raw/provider_research/", len(normalized["items"]),
             normalized["source_count"], now),
        )
        inserted = 0
        for item in normalized["items"]:
            stable_candidate_key = _stable_candidate_key(item)
            candidate_key = _candidate_key(item, stable_candidate_key, item["content_sha256"])
            item["candidate_key"] = candidate_key
            item["stable_candidate_key"] = stable_candidate_key
            archive_path = archived_sources.get(item["content_sha256"])
            existing_item = conn.execute(
                "SELECT id FROM provider_research_items WHERE candidate_key = ?", (candidate_key,)
            ).fetchone()
            conn.execute(
                "INSERT INTO provider_research_items "
                "(run_id, candidate_key, provider_key, entity_type, entity_identifier, category, "
                "fact_type, question, raw_finding, interpretation, source_url, publisher, "
                "published_date, accessed_at, citation, licence, identity_match_basis, time_period, "
                "confidence, evidence_status, destination, content_sha256, source_archive_path, "
                "priority_score, priority_factors_json, stable_candidate_key, supersedes_item_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (candidate_key) DO NOTHING",
                (normalized["run_id"], candidate_key, item["provider_key"], item["entity_type"],
                 item["entity_identifier"], item["category"], item["fact_type"], item["question"],
                 item["raw_finding"], item["interpretation"], item["source_url"], item["publisher"],
                 item["published_date"], item["accessed_at"], item["citation"], item["licence"],
                 item["identity_match_basis"], item["time_period"], item["confidence"],
                 item["evidence_status"], item["destination"], item["content_sha256"], archive_path,
                 item["priority_score"], item["priority_factors_json"], stable_candidate_key, None, now, now),
            )
            row = conn.execute(
                "SELECT id, identity_review_item_id, evidence_review_item_id, stable_candidate_key "
                "FROM provider_research_items WHERE candidate_key = ?", (candidate_key,)
            ).fetchone()
            if existing_item:
                continue
            prior = conn.execute(
                "SELECT id FROM provider_research_items "
                "WHERE stable_candidate_key = ? AND candidate_key <> ? "
                "AND state <> 'superseded' ORDER BY created_at DESC, id DESC LIMIT 1",
                (stable_candidate_key, candidate_key),
            ).fetchone()
            if prior:
                conn.execute(
                    "UPDATE provider_research_items SET state = 'superseded', updated_at = ? WHERE id = ?",
                    (now, prior["id"]),
                )
                conn.execute(
                    "UPDATE provider_research_evidence SET superseded_at = ? "
                    "WHERE source_item_id = ? AND superseded_at IS NULL",
                    (now, prior["id"]),
                )
                conn.execute(
                    "UPDATE provider_research_items SET supersedes_item_id = ? WHERE id = ?",
                    (prior["id"], row["id"]),
                )
            if row["identity_review_item_id"] is None and item["evidence_status"] != "not_applicable":
                context = json.dumps({"research_item_id": row["id"], "candidate_key": candidate_key,
                                      "stage": "identity", "provider_key": item["provider_key"]}, sort_keys=True)
                db.record_review_item(conn, MODULE, "provider_research", candidate_key + ":identity", context)
                identity_id = _review_id(conn, candidate_key + ":identity")
                conn.execute("UPDATE provider_research_items SET identity_review_item_id = ? WHERE id = ?",
                             (identity_id, row["id"]))
            if row["evidence_review_item_id"] is None and item["evidence_status"] != "not_applicable":
                context = json.dumps({"research_item_id": row["id"], "candidate_key": candidate_key,
                                      "stage": "evidence", "provider_key": item["provider_key"]}, sort_keys=True)
                db.record_review_item(conn, MODULE, "provider_research", candidate_key + ":evidence", context)
                evidence_id = _review_id(conn, candidate_key + ":evidence")
                conn.execute("UPDATE provider_research_items SET evidence_review_item_id = ? WHERE id = ?",
                             (evidence_id, row["id"]))
            inserted += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"run_id": normalized["run_id"], "manifest_sha256": manifest_sha,
            "items": inserted, "sources": normalized["source_count"], "duplicate": False}


def validate_manifest_file(manifest_path: Path, *, bundle_dir: Path | None = None) -> dict:
    """Read and validate a manifest for the CLI's no-write preflight."""
    path = Path(manifest_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ResearchError(f"manifest does not exist: {path}") from None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchError(f"manifest is not valid UTF-8 JSON: {exc}") from None
    return validate_manifest(payload, bundle_dir=bundle_dir)


def apply_review_decision(conn, review_item_id: int, decision: str) -> None:
    """Reflect a generic review-queue decision onto a research candidate."""
    row = conn.execute(
        "SELECT id, context_json FROM review_queue WHERE id = ? AND module = ?",
        (review_item_id, MODULE),
    ).fetchone()
    if not row or not row["context_json"]:
        return
    try:
        context = json.loads(row["context_json"])
    except (TypeError, json.JSONDecodeError):
        return
    item_id, stage = context.get("research_item_id"), context.get("stage")
    if not isinstance(item_id, int) or stage not in REVIEW_STAGES:
        return
    column = "identity_review_state" if stage == "identity" else "evidence_review_state"
    state = "approved" if decision == "approved" else "rejected" if decision == "rejected" else "pending"
    now = _now()
    conn.execute(f"UPDATE provider_research_items SET {column} = ?, updated_at = ? WHERE id = ?",
                 (state, now, item_id))
    item = conn.execute(
        "SELECT identity_review_state, evidence_review_state FROM provider_research_items WHERE id = ?",
        (item_id,),
    ).fetchone()
    if not item:
        return
    overall = "rejected" if "rejected" in (item["identity_review_state"], item["evidence_review_state"]) else (
        "approved" if item["identity_review_state"] == "approved" and item["evidence_review_state"] == "approved" else "candidate")
    conn.execute("UPDATE provider_research_items SET state = ?, updated_at = ? WHERE id = ?",
                 (overall, now, item_id))


def promote(conn, item_id: int, promoted_by: str) -> dict:
    """Copy one fully reviewed source-backed candidate into public evidence."""
    promoted_by = (promoted_by or "").strip()
    if not promoted_by:
        raise ResearchError("promoted_by is required")
    item = conn.execute("SELECT * FROM provider_research_items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        raise ResearchError(f"no provider research item {item_id}")
    if item["identity_review_state"] != "approved" or item["evidence_review_state"] != "approved":
        raise ResearchError("identity and evidence review must both be approved before promotion")
    if item["evidence_status"] not in {"evidence_found", "candidate", "existing_project_evidence"}:
        raise ResearchError(f"{item['evidence_status']} items cannot be promoted as evidence")
    required = (item["source_url"], item["citation"], item["content_sha256"], item["source_archive_path"])
    if any(not str(value or "").strip() for value in required):
        raise ResearchError("promoted evidence needs a URL, citation, content hash, and archive path")
    now = _now()
    with conn:
        conn.execute(
            "INSERT INTO provider_research_evidence "
            "(source_item_id, provider_key, entity_type, entity_identifier, category, fact_type, "
            "question, raw_finding, interpretation, source_url, publisher, published_date, accessed_at, "
            "citation, licence, identity_match_basis, time_period, confidence, destination, "
            "content_sha256, source_archive_path, promoted_by, promoted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (source_item_id) DO NOTHING",
            tuple(item[key] for key in (
                "id", "provider_key", "entity_type", "entity_identifier", "category", "fact_type",
                "question", "raw_finding", "interpretation", "source_url", "publisher", "published_date",
                "accessed_at", "citation", "licence", "identity_match_basis", "time_period", "confidence",
                "destination", "content_sha256", "source_archive_path")) + (promoted_by, now),
        )
        conn.execute("UPDATE provider_research_items SET state = 'approved', updated_at = ? WHERE id = ?",
                     (now, item_id))
    evidence = conn.execute("SELECT * FROM provider_research_evidence WHERE source_item_id = ?", (item_id,)).fetchone()
    return dict(evidence)


def coverage(conn, *, provider_key: str | None = None) -> dict:
    """Return a comparable provider/category matrix and ranked worklist."""
    providers = conn.execute(
        "SELECT provider_key, canonical_name, is_target FROM providers "
        + ("WHERE provider_key = ? " if provider_key else "")
        + "ORDER BY is_target DESC, canonical_name", ((provider_key,) if provider_key else ()),
    ).fetchall()
    rows = conn.execute(
        "SELECT provider_key, category, evidence_status, state, COUNT(*) AS n, "
        "MAX(updated_at) AS latest FROM provider_research_items "
        + ("WHERE provider_key = ? " if provider_key else "")
        + "GROUP BY provider_key, category, evidence_status, state",
        ((provider_key,) if provider_key else ()),
    ).fetchall()
    grouped: dict[tuple[str, str], dict] = {}
    for row in rows:
        cell = grouped.setdefault((row["provider_key"], row["category"]), {"items": 0, "approved": 0, "candidate": 0, "latest": None, "statuses": {}})
        cell["items"] += row["n"]
        cell["approved"] += row["n"] if row["state"] == "approved" else 0
        cell["candidate"] += row["n"] if row["state"] == "candidate" else 0
        cell["latest"] = max(cell["latest"] or "", row["latest"] or "") or None
        cell["statuses"][row["evidence_status"]] = cell["statuses"].get(row["evidence_status"], 0) + row["n"]
    categories = sorted(set(DEFAULT_CATEGORIES) | {row["category"] for row in rows})
    matrix = []
    for provider in providers:
        cells = []
        for category in categories:
            cell = grouped.get((provider["provider_key"], category))
            cells.append({"category": category, "status": "not_researched" if not cell else (
                "verified" if cell["approved"] else "candidate"), **(cell or {"items": 0, "approved": 0, "candidate": 0, "latest": None, "statuses": {}})})
        matrix.append({"provider_key": provider["provider_key"], "canonical_name": provider["canonical_name"],
                       "is_target": provider["is_target"], "cells": cells})
    worklist = [dict(row) for row in conn.execute(
        "SELECT id, provider_key, category, question, evidence_status, state, priority_score, "
        "destination, updated_at FROM provider_research_items "
        "WHERE state IN ('candidate', 'approved') "
        + ("AND provider_key = ? " if provider_key else "")
        + "ORDER BY priority_score DESC NULLS LAST, updated_at DESC, id",
        ((provider_key,) if provider_key else ()),
    ).fetchall()]
    return {"providers": [dict(row) for row in providers], "categories": categories,
            "matrix": matrix, "worklist": worklist}


def runs(conn, *, limit: int = 50) -> list[dict]:
    return [dict(row) for row in conn.execute(
        "SELECT * FROM provider_research_runs ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 200)),)
    )]


def items(conn, *, provider_key: str | None = None, state: str | None = None,
          category: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
    where, params = [], []
    if provider_key:
        where.append("provider_key = ?")
        params.append(provider_key)
    if state:
        where.append("state = ?")
        params.append(state)
    if category:
        where.append("category = ?")
        params.append(category)
    clause = " WHERE " + " AND ".join(where) if where else ""
    params.extend([max(1, min(limit, 500)), max(0, offset)])
    return [dict(row) for row in conn.execute(
        "SELECT * FROM provider_research_items" + clause + " ORDER BY priority_score DESC NULLS LAST, id LIMIT ? OFFSET ?", params
    )]
