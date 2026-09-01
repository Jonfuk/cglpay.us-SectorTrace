"""Immutable analysis release manifests and model inheritance."""
from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from typing import Any

from pipeline.analysis.domains import domain_registry
from pipeline.analysis.signals import utcnow

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


def code_commit() -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                text=True, timeout=5)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def release_manifest(settings: Any, *, release_id: str | None = None,
                     domains: list[str] | None = None, config: dict | None = None) -> dict:
    selected = domains or sorted(domain_registry())
    unknown = sorted(set(selected) - set(domain_registry()))
    if unknown:
        raise ValueError(f"unknown analysis domains: {unknown}")
    models = resolved_models(settings)
    manifest = {
        "release_id": release_id or f"analysis-{uuid.uuid4()}",
        "status": "draft", "code_commit": code_commit(), "created_at": utcnow(),
        "domains": selected, "models": models, "config": config or {},
    }
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return manifest


def create_release(conn, settings: Any, *, domains: list[str] | None = None,
                   config: dict | None = None) -> dict:
    manifest = release_manifest(settings, domains=domains, config=config)
    conn.execute(
        "INSERT INTO analysis_releases (release_id, status, manifest_json, manifest_sha256, "
        "code_commit, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (manifest["release_id"], manifest["status"], json.dumps(manifest, sort_keys=True),
         manifest["manifest_sha256"], manifest["code_commit"], manifest["created_at"]))
    return manifest


def load_release(conn, release_id: str) -> dict | None:
    row = conn.execute("SELECT manifest_json FROM analysis_releases WHERE release_id = ?",
                       (release_id,)).fetchone()
    return json.loads(row[0]) if row else None
