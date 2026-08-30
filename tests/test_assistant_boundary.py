"""The optional assistant runtime boundary (BETA-107; OpenRouter since
BETA-114).

The `pipeline.assistant` package must import and report its status with none
of its optional runtime present — no `openai` client, no configured key or
model slug — and the offline suite must pass unchanged whether or not any of
that is installed. An adapter asked to run without a backend, a key or a model
slug raises `AssistantUnavailable`, never a bare import or socket error.
"""
from __future__ import annotations

import importlib.util
import threading
import types
from pathlib import Path

import httpx
import pytest

from pipeline.web.server import build_server

ROOT = Path(__file__).resolve().parent.parent
_HAS_OPENAI = importlib.util.find_spec("openai") is not None


class _RecordingClient:
    """Stands in for the `openai` client: records the kwargs of the one
    `chat.completions.create` call and returns a minimal valid response, so a
    test can assert what `generate()` sent without the extra or a network."""

    def __init__(self) -> None:
        self.create_kwargs: dict | None = None

    def with_options(self, **_kw):
        return self

    @property
    def chat(self):
        return types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.create_kwargs = kwargs
        msg = types.SimpleNamespace(content='{"tool": null, "confidence": 0.0}')
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


def test_the_package_imports_with_nothing_installed() -> None:
    import pipeline.assistant as assistant  # noqa: F401

    assert hasattr(assistant, "runtime_status")
    assert hasattr(assistant, "get_adapter")
    assert issubclass(assistant.AssistantUnavailable, RuntimeError)


def test_runtime_status_is_off_by_default_and_contacts_nothing(settings, monkeypatch) -> None:
    from pipeline.assistant import runtime_status

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    status = runtime_status(settings)
    assert status["enabled"] is False
    assert status["ready"] is False
    assert status["openai_client_installed"] == _HAS_OPENAI
    # No pinned model since BETA-114 — a deployment names the slugs.
    assert status["model"] == {"id": "", "quant": ""}
    assert status["api_key_configured"] is False
    assert set(status["adapters"]) == {"lfm-ollama", "needle-2"}
    assert "no endpoint was contacted" in status["note"].lower()


def test_model_identity_is_overridable_and_defaults_to_unset(settings, monkeypatch) -> None:
    from pipeline.assistant import runtime_status
    from pipeline.assistant.runtime import (
        resolved_lfm_model,
        resolved_lfm_quant,
        resolved_needle_model,
    )

    # Empty settings -> empty slugs (BETA-114: no pinned default; the adapter
    # fails closed rather than send a stale model to OpenRouter).
    assert resolved_lfm_model(settings) == ""
    assert resolved_lfm_quant(settings) == ""
    assert resolved_needle_model(settings) == ""

    # A deployment names router and answerer independently; status reflects it.
    monkeypatch.setattr(settings, "assistant_needle_model",
                        "openrouter/router-slug", raising=False)
    monkeypatch.setattr(settings, "assistant_lfm_model",
                        "openrouter/answerer-slug", raising=False)
    status = runtime_status(settings)
    assert status["model"]["id"] == "openrouter/answerer-slug"
    assert status["adapters"]["lfm-ollama"]["model"] == "openrouter/answerer-slug"
    assert status["adapters"]["needle-2"]["model"] == "openrouter/router-slug"


def test_api_key_comes_from_settings_or_the_openrouter_env_var(settings, monkeypatch) -> None:
    from pipeline.assistant.runtime import resolved_api_key

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert resolved_api_key(settings) == ""

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-from-env")
    assert resolved_api_key(settings) == "sk-or-from-env"

    # The dedicated setting wins over the shared env var.
    monkeypatch.setattr(settings, "assistant_api_key", "sk-or-from-settings",
                        raising=False)
    assert resolved_api_key(settings) == "sk-or-from-settings"


@pytest.mark.skipif(not _HAS_OPENAI, reason="needs the assistant extra")
def test_an_unconfigured_model_slug_is_assistant_unavailable(settings, monkeypatch) -> None:
    from pipeline.assistant import AssistantUnavailable
    from pipeline.assistant.adapters import NeedleAdapter

    # Endpoint set, key set, but no ASSISTANT_NEEDLE_MODEL — fail closed
    # before any network call rather than 404 against OpenRouter.
    monkeypatch.setattr(settings, "assistant_api_key", "sk-or-x", raising=False)
    with pytest.raises(AssistantUnavailable, match="no model configured"):
        NeedleAdapter(settings).generate("hello")


def test_only_the_router_leg_asks_for_json_object_mode(settings, monkeypatch) -> None:
    from pipeline.assistant.adapters import LFMOllamaAdapter, NeedleAdapter

    monkeypatch.setattr(settings, "assistant_needle_model", "x/router", raising=False)
    monkeypatch.setattr(settings, "assistant_lfm_model", "x/answerer", raising=False)

    router, rc = NeedleAdapter(settings), _RecordingClient()
    monkeypatch.setattr(router, "_client", lambda: rc)
    router.generate("q", system="s")
    assert rc.create_kwargs["response_format"] == {"type": "json_object"}

    answerer, ac = LFMOllamaAdapter(settings), _RecordingClient()
    monkeypatch.setattr(answerer, "_client", lambda: ac)
    answerer.generate("q", system="s")
    assert "response_format" not in ac.create_kwargs

    # A deployment whose router model 400s on response_format can turn it off.
    monkeypatch.setattr(settings, "assistant_router_json_mode", False, raising=False)
    off, oc = NeedleAdapter(settings), _RecordingClient()
    monkeypatch.setattr(off, "_client", lambda: oc)
    off.generate("q", system="s")
    assert "response_format" not in oc.create_kwargs


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
    monkeypatch.setattr(settings, "assistant_lfm_model", "x/y", raising=False)
    monkeypatch.setattr(settings, "assistant_api_key", "sk-or-x", raising=False)
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


def test_the_admin_route_reports_the_status(settings, monkeypatch) -> None:
    from pipeline import db

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
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
            assert out["model"] == {"id": "", "quant": ""}
            assert out["api_key_configured"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
