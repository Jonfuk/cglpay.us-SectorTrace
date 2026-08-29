"""The optional assistant runtime boundary (BETA-107).

The `pipeline.assistant` package must import and report its status with none
of its optional runtime present — no `openai` client, no Ollama, no model
weights, no Needle endpoint — and the offline suite must pass unchanged
whether or not any of that is installed. An adapter asked to run without a
backend raises `AssistantUnavailable`, never a bare import or socket error.
"""
from __future__ import annotations

import importlib.util
import threading
from pathlib import Path

import httpx
import pytest

from pipeline.web.server import build_server

ROOT = Path(__file__).resolve().parent.parent
_HAS_OPENAI = importlib.util.find_spec("openai") is not None


def test_the_package_imports_with_nothing_installed() -> None:
    import pipeline.assistant as assistant  # noqa: F401

    assert hasattr(assistant, "runtime_status")
    assert hasattr(assistant, "get_adapter")
    assert issubclass(assistant.AssistantUnavailable, RuntimeError)


def test_runtime_status_is_off_by_default_and_contacts_nothing(settings) -> None:
    from pipeline.assistant import runtime_status

    status = runtime_status(settings)
    assert status["enabled"] is False
    assert status["ready"] is False
    assert status["openai_client_installed"] == _HAS_OPENAI
    assert status["model"] == {"id": "LiquidAI/LFM2.5-1.2B-Instruct",
                                "quant": "Q4_K_M"}
    assert set(status["adapters"]) == {"lfm-ollama", "needle-2"}
    assert "no endpoint was contacted" in status["note"].lower()


def test_model_identity_is_overridable_and_defaults_to_the_pin(settings, monkeypatch) -> None:
    from pipeline.assistant import runtime_status
    from pipeline.assistant.runtime import (
        resolved_lfm_model,
        resolved_lfm_quant,
        resolved_needle_model,
    )

    # Empty settings -> the pinned constants, unchanged.
    assert resolved_lfm_model(settings) == "LiquidAI/LFM2.5-1.2B-Instruct"
    assert resolved_lfm_quant(settings) == "Q4_K_M"
    assert resolved_needle_model(settings) == "needle-2"

    # A deployment serving a different size sets them; status reflects it.
    monkeypatch.setattr(settings, "assistant_lfm_model",
                        "hf.co/LiquidAI/LFM2.5-2.6B-GGUF:Q4_K_M", raising=False)
    monkeypatch.setattr(settings, "assistant_needle_model",
                        "hf.co/LiquidAI/LFM2.5-2.6B-GGUF:Q4_K_M", raising=False)
    status = runtime_status(settings)
    assert status["model"]["id"] == "hf.co/LiquidAI/LFM2.5-2.6B-GGUF:Q4_K_M"
    assert status["adapters"]["lfm-ollama"]["model"] == "hf.co/LiquidAI/LFM2.5-2.6B-GGUF:Q4_K_M"
    assert status["adapters"]["needle-2"]["model"] == "hf.co/LiquidAI/LFM2.5-2.6B-GGUF:Q4_K_M"


def test_get_adapter_refuses_while_the_layer_is_disabled(settings) -> None:
    from pipeline.assistant import AssistantUnavailable, get_adapter

    with pytest.raises(AssistantUnavailable):
        get_adapter("lfm-ollama", settings)
    with pytest.raises(AssistantUnavailable):
        get_adapter("needle-2", settings)


def test_enabling_without_the_extra_still_raises_assistant_unavailable(
        settings, monkeypatch) -> None:
    from pipeline.assistant import AssistantUnavailable, get_adapter, runtime

    monkeypatch.setattr(settings, "assistant_enabled", True, raising=False)
    monkeypatch.setattr(runtime, "openai_client_installed", lambda: False)
    with pytest.raises(AssistantUnavailable):
        get_adapter("lfm-ollama", settings)


@pytest.mark.skipif(not _HAS_OPENAI, reason="needs the assistant extra")
def test_a_dead_endpoint_surfaces_as_assistant_unavailable(settings, monkeypatch) -> None:
    from pipeline.assistant import AssistantUnavailable
    from pipeline.assistant.adapters import LFMOllamaAdapter

    monkeypatch.setattr(settings, "assistant_ollama_url",
                        "http://127.0.0.1:9/v1", raising=False)  # nothing listens on :9
    with pytest.raises(AssistantUnavailable):
        LFMOllamaAdapter(settings).generate("hello")


def test_an_unknown_adapter_name_is_rejected(settings, monkeypatch) -> None:
    from pipeline.assistant import AssistantUnavailable, get_adapter, runtime

    monkeypatch.setattr(settings, "assistant_enabled", True, raising=False)
    monkeypatch.setattr(runtime, "openai_client_installed", lambda: True)
    with pytest.raises(AssistantUnavailable):
        get_adapter("gpt-4", settings)


def test_the_extra_is_declared_and_kept_out_of_the_default_docker_image() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "\nassistant = [" in pyproject
    assert '"openai' in pyproject.split("\nassistant = [", 1)[1].split("]", 1)[0]

    # Both deploy images can be built with the extra (a self-hosted box that
    # provisions the assistant runtime does), but only on an explicit
    # opt-in: ARG INSTALL_ASSISTANT defaults to false, and every
    # `--extra assistant` line is guarded by a test on it. Railway builds
    # `Dockerfile` with no build args (railway.toml below) and does not
    # build `Dockerfile.documents` at all, so its image never gets `openai`.
    for name in ("Dockerfile", "deploy/Dockerfile.documents"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "ARG INSTALL_ASSISTANT=false" in text, name
        for line in text.splitlines():
            if "--extra assistant" in line:
                assert '"$INSTALL_ASSISTANT" = "true"' in line, (name, line)

    railway = (ROOT / "railway.toml").read_text(encoding="utf-8")
    assert "INSTALL_ASSISTANT" not in railway


def test_the_admin_route_reports_the_status(settings) -> None:
    from pipeline import db

    conn = db.get_connection(settings)
    db.apply_migrations(conn, settings.migrations_dir)
    server = build_server(settings, host="127.0.0.1", port=0)
    conn.close()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=10.0) as http:
            out = http.get("/api/admin/assistant").json()
            assert out["enabled"] is False
            assert out["model"]["quant"] == "Q4_K_M"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
