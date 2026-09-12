"""Immutable analysis release manifests and model inheritance."""
from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from pathlib import Path
from typing import Any

from pipeline.analysis.domains import domain_registry
from pipeline.analysis.signals import utcnow
from pipeline.assistant.runtime import (
    resolved_claim_models,
    resolved_lfm_models,
    resolved_needle_models,
)

DEFAULT_SCOUT_MODEL = "openai/gpt-4o-mini"
DEFAULT_EXTRACTOR_MODEL = "openai/gpt-oss-120b"


def resolved_models(settings: Any) -> dict[str, str]:
    """Resolve analysis models once; later env changes cannot mutate a release."""
    scout = (getattr(settings, "claim_signal_scout_model", None)
             or getattr(settings, "assistant_needle_model", None) or DEFAULT_SCOUT_MODEL)
    extractor = (getattr(settings, "claim_signal_extractor_model", None)
                 or getattr(settings, "assistant_lfm_model", None) or DEFAULT_EXTRACTOR_MODEL)
    reflection = (getattr(settings, "claim_signal_reflection_model", None) or extractor)
    return {"scout": scout, "extractor": extractor, "reflection": reflection,
            "minicheck": "local:MiniCheck-Flan-T5-Large",
            "alignscore": "local:AlignScore-base"}


def resolved_model_fallbacks(settings: Any) -> dict[str, list[str]]:
    """Capture immutable fallback order alongside the release's model IDs."""
    assistant_needle = resolved_needle_models(settings)
    assistant_lfm = resolved_lfm_models(settings)

    def chain(role: str, primary: str, assistant_chain: tuple[str, ...]) -> list[str]:
        claim_chain = resolved_claim_models(settings, role)
        selected = claim_chain if claim_chain else assistant_chain
        return list(dict.fromkeys(model for model in selected if model and model != primary))

    models = resolved_models(settings)
    return {
        "scout": chain("scout", models["scout"], assistant_needle),
        "extractor": chain("extractor", models["extractor"], assistant_lfm),
        "reflection": chain("reflection", models["reflection"], assistant_lfm),
    }


def code_commit() -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                text=True, timeout=5)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _json_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _archive_manifest_sha(conn) -> str:
    digest = hashlib.sha256()
    cursor = conn.execute(
        "SELECT object_id, source_system, payload_sha256, size_bytes "
        "FROM archive_objects ORDER BY object_id")
    while True:
        rows = cursor.fetchmany(1000)
        if not rows:
            break
        for row in rows:
            digest.update(json.dumps(dict(row), sort_keys=True,
                                     separators=(",", ":"), default=str).encode() + b"\n")
    return digest.hexdigest()


def _processing_versions(conn, settings: Any, config: dict[str, Any]) -> dict[str, Any]:
    migration_names = [row["filename"] for row in conn.execute(
        "SELECT filename FROM schema_migrations ORDER BY filename")]
    root = Path(__file__).resolve().parents[1]
    ontology_files = sorted((root / "nlp" / "ontology").glob("*.yml"))
    ontology_digest = hashlib.sha256()
    for path in ontology_files:
        ontology_digest.update(path.name.encode() + b"\0" + path.read_bytes())
    embedding_rows = [dict(row) for row in conn.execute(
        "SELECT model_key, dimension, COUNT(*) AS rows FROM document_embeddings "
        "GROUP BY model_key, dimension ORDER BY model_key, dimension")]
    models = resolved_models(settings)
    fallbacks = resolved_model_fallbacks(settings)
    provider_policy = {
        "endpoint": getattr(settings, "assistant_ollama_url", ""),
        "sort": getattr(settings, "assistant_provider_sort", ""),
        "order": getattr(settings, "assistant_provider_order", ""),
        "ignore": getattr(settings, "assistant_provider_ignore", ""),
        "allow_fallbacks": getattr(settings, "assistant_provider_allow_fallbacks", True),
        "require_parameters": getattr(settings, "assistant_provider_require_parameters", True),
        "models": models, "fallbacks": fallbacks,
        "request_contract": {
            "system_prompt": "Return one valid JSON object and no markdown.",
            "response_format": {"type": "json_object"},
            "max_tokens": 1024, "temperature": 0,
            "schema": {"type": "json_object"}, "cache_version": "1",
        },
    }
    source_snapshot = config.get("source_snapshot") or {"tables": [], "sha256": _json_sha([])}
    schema_sha = _json_sha(migration_names)
    from pipeline.analysis.prefilter import RULES_VERSION, rules_sha256

    return {
        "schema_version": migration_names[-1] if migration_names else "unmigrated",
        "schema_sha256": schema_sha,
        "warehouse_data_version": source_snapshot.get("sha256") or _json_sha(source_snapshot),
        "source_snapshot_sha256": source_snapshot.get("sha256") or _json_sha(source_snapshot),
        "archive_manifest_sha256": _archive_manifest_sha(conn),
        "nlp_version": "document-nlp-stage-ledger-v1",
        "ontology_version": ontology_digest.hexdigest(),
        "rule_version": f"{RULES_VERSION}:{rules_sha256()}",
        "embedding_model": json.dumps(embedding_rows, sort_keys=True) if embedding_rows else None,
        "embedding_dimensions": (embedding_rows[0]["dimension"]
                                 if len({row["dimension"] for row in embedding_rows}) == 1 else None),
        "entity_resolution_version": "exact-normalised-identifier-v1",
        "graph_projection_version": "postgres-canonical-neo4j-derived-v1",
        "model_configuration_sha256": _json_sha(provider_policy),
    }


def release_manifest(settings: Any, *, release_id: str | None = None,
                     domains: list[str] | None = None, config: dict | None = None) -> dict:
    selected = domains or sorted(domain_registry())
    unknown = sorted(set(selected) - set(domain_registry()))
    if unknown:
        raise ValueError(f"unknown analysis domains: {unknown}")
    models = resolved_models(settings)
    model_fallbacks = resolved_model_fallbacks(settings)
    manifest = {
        "release_id": release_id or f"analysis-{uuid.uuid4()}",
        "status": "draft",
        "code_commit": getattr(settings, "git_revision", None) or code_commit(),
        "created_at": utcnow(),
        "domains": selected, "models": models, "config": config or {},
        "model_fallbacks": model_fallbacks,
    }
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return manifest


def create_release(conn, settings: Any, *, domains: list[str] | None = None,
                   config: dict | None = None) -> dict:
    manifest = release_manifest(settings, domains=domains, config=config)
    manifest["system"] = _processing_versions(conn, settings, config or {})
    manifest["manifest_sha256"] = _json_sha({
        key: value for key, value in manifest.items() if key != "manifest_sha256"})
    conn.execute(
        "INSERT INTO analysis_releases (release_id, status, manifest_json, manifest_sha256, "
        "code_commit, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
        (manifest["release_id"], manifest["status"], json.dumps(manifest, sort_keys=True),
         manifest["manifest_sha256"], manifest["code_commit"], manifest["created_at"]))
    return manifest


def load_release(conn, release_id: str) -> dict | None:
    row = conn.execute("SELECT manifest_json FROM analysis_releases WHERE release_id = %s",
                       (release_id,)).fetchone()
    return json.loads(row["manifest_json"]) if row else None


def finalise_manifest(conn, release_id: str, *, output_sha256: str,
                      release_kind: str = "analytical", output_name: str = "analysis") -> dict:
    """Create the immutable whole-system manifest after output validation."""
    if release_kind not in {"analytical", "published"}:
        raise ValueError("release_kind must be analytical or published")
    existing = conn.execute(
        "SELECT manifest_json, output_sha256 FROM release_manifests WHERE release_id = %s "
        "AND release_kind = %s AND output_name = %s",
        (release_id, release_kind, output_name)).fetchone()
    if existing:
        if existing["output_sha256"] != output_sha256:
            raise ValueError("immutable release output digest conflicts with the sealed manifest")
        return json.loads(existing["manifest_json"])
    plan = load_release(conn, release_id)
    if plan is None:
        raise KeyError(release_id)
    if not plan.get("code_commit"):
        raise ValueError("an immutable release manifest requires an exact Git commit")
    system = dict(plan.get("system") or {})
    input_manifests = [dict(row) for row in conn.execute(
        "SELECT domain_id, source_tables_json, input_count, ordered_input_sha256, "
        "configuration_sha256, prefilter_version, prefilter_result_sha256, suppression_enabled "
        "FROM analysis_input_manifests "
        "WHERE release_id = %s ORDER BY domain_id", (release_id,))]
    if input_manifests:
        exact_input_digest = _json_sha({
            "planned_source_snapshot": system.get("source_snapshot_sha256"),
            "ordered_inputs": input_manifests,
        })
        system["source_snapshot_sha256"] = exact_input_digest
        system["warehouse_data_version"] = exact_input_digest
    required = {
        "schema_version", "schema_sha256", "warehouse_data_version",
        "source_snapshot_sha256", "archive_manifest_sha256", "nlp_version",
        "ontology_version", "rule_version", "entity_resolution_version",
        "graph_projection_version", "model_configuration_sha256",
    }
    missing = sorted(name for name in required if not system.get(name))
    if missing:
        raise ValueError(f"release system manifest is incomplete: {missing}")
    manifest = {
        "release_id": release_id, "release_kind": release_kind,
        "output_name": output_name, "git_commit": plan.get("code_commit"),
        **system, "created_at": utcnow(), "output_sha256": output_sha256,
    }
    manifest_sha = _json_sha(manifest)
    manifest["manifest_sha256"] = manifest_sha
    manifest_id = f"release-manifest-{manifest_sha}"
    conn.execute(
        "INSERT INTO release_manifests (release_manifest_id, release_id, release_kind, output_name, "
        "git_commit, schema_version, schema_sha256, warehouse_data_version, source_snapshot_sha256, "
        "archive_manifest_sha256, nlp_version, ontology_version, rule_version, embedding_model, "
        "embedding_dimensions, entity_resolution_version, graph_projection_version, "
        "model_configuration_sha256, created_at, output_sha256, manifest_json, manifest_sha256) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (manifest_id, release_id, release_kind, output_name, manifest.get("git_commit"),
         system["schema_version"], system["schema_sha256"], system["warehouse_data_version"],
         system["source_snapshot_sha256"], system["archive_manifest_sha256"], system["nlp_version"],
         system["ontology_version"], system["rule_version"], system.get("embedding_model"),
         system.get("embedding_dimensions"), system["entity_resolution_version"],
         system["graph_projection_version"], system["model_configuration_sha256"],
         manifest["created_at"], output_sha256, json.dumps(manifest, sort_keys=True), manifest_sha))
    from pipeline.analysis.lineage import add_edge, add_object

    output_node = add_object(
        conn, kind="published_output" if release_kind == "published" else "analysis",
        canonical_id=f"{release_id}:{output_name}", payload_sha256=output_sha256,
        processor_version=system["rule_version"],
        metadata={"release_manifest_id": manifest_id, "manifest_sha256": manifest_sha})
    for row in conn.execute(
            "SELECT signal_id, domain_id FROM automated_signals "
            "WHERE release_id = %s ORDER BY signal_id", (release_id,)):
        existing_node = conn.execute(
            "SELECT lineage_id FROM lineage_objects WHERE object_kind = 'analysis' "
            "AND canonical_id = %s", (row["signal_id"],)).fetchone()
        signal_node = (existing_node["lineage_id"] if existing_node else add_object(
            conn, kind="analysis", canonical_id=row["signal_id"],
            processor_version=system["rule_version"],
            metadata={"release_id": release_id, "domain_id": row["domain_id"]}))
        add_edge(conn, generated_id=output_node, used_id=signal_node,
                 activity="release_assembly", activity_version=system["rule_version"])
    return manifest
