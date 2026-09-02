"""Assistant adapters (BETA-107; retargeted to OpenRouter in BETA-114): two
OpenAI-chat-compatible HTTP backends.

  * `LFMOllamaAdapter` — the answerer leg. Historically a local Ollama; since
    BETA-114 it reaches OpenRouter (`assistant_ollama_url`, defaulting to
    `https://openrouter.ai/api/v1`) with the slug `resolved_lfm_model`.
  * `NeedleAdapter` — the router leg. Historically the Needle 2 endpoint; since
    BETA-114 it reaches OpenRouter (`assistant_needle_url`) with the slug
    `resolved_needle_model`. The two legs are configured independently so a
    cheap model can route and a stronger one can ground. The router leg also
    sets `response_format=json_object` (`assistant_router_json_mode`, on by
    default) — its prompt demands a bare JSON object and a small model drops
    fields without the constraint.

The class and adapter-registry names are kept as role labels rather than
renamed, to avoid a migration of the `assistant_runs` columns that record
them; see `docs/assistant.md`.

Both talk HTTP through the `openai` client (the only `[assistant]` pin), so
neither needs a native model runtime *in this process*. Every path that
could touch the network is lazy: the client is built, and the extra is
imported, only inside `generate()`. A missing extra, a disabled layer, an
unconfigured model slug, a refused connection or an unknown model all
surface as `AssistantUnavailable` — never a raw import or socket error.
"""
from __future__ import annotations

from typing import Any

from pipeline.assistant.runtime import (
    AssistantUnavailable,
    require_enabled,
    resolved_api_key,
    resolved_lfm_models,
    resolved_needle_models,
)
from pipeline.assistant.transport import (
    TransportTelemetry,
    provider_preferences,
    run_with_resilience,
)

_DEFAULT_MAX_TOKENS = 1024

# What the `openai` client is handed when no key is configured. A self-hosted
# OpenAI-compatible endpoint ignores it; OpenRouter rejects the call, which
# `generate()` maps to `AssistantUnavailable` like any other refusal.
_PLACEHOLDER_KEY = "no-key-configured"


class _OpenAICompatAdapter:
    """Shared chat-completions call over an OpenAI-compatible `/v1` base URL.

    `api_key` is the OpenRouter bearer token (`resolved_api_key`). It may be
    empty for a self-hosted endpoint that ignores it; a placeholder is sent in
    that case because the `openai` client requires the parameter to be set.
    """

    name = "openai-compat"

    def __init__(self, *, base_url: str, models: tuple[str, ...],
                 api_key: str = "", json_response: bool = False,
                 settings: Any = None) -> None:
        self.base_url = base_url
        self.models = models
        self.model = models[0] if models else ""
        self.settings = settings
        self.last_telemetry: dict[str, Any] = {}
        self._api_key = api_key or _PLACEHOLDER_KEY
        # Ask the API to constrain the reply to a JSON object. Only the router
        # leg sets this (BETA-114 follow-up): its prompt demands bare JSON and
        # a small model still drops the `confidence` field without the
        # constraint. The answerer writes prose and must never get it.
        self._json_response = json_response

    def _client(self):
        try:
            from openai import OpenAI  # lazy: the only place the extra is needed
        except ImportError as exc:  # pragma: no cover - depends on the extra
            raise AssistantUnavailable(
                "the `assistant` extra is not installed "
                "(`uv sync --extra assistant`)") from exc
        if not self.base_url:
            raise AssistantUnavailable(f"no endpoint configured for {self.name}")
        if not self.model:
            raise AssistantUnavailable(
                f"no model configured for {self.name} — set "
                "ASSISTANT_NEEDLE_MODEL (router) / ASSISTANT_LFM_MODEL "
                "(answerer) to OpenRouter slugs")
        return OpenAI(
            base_url=self.base_url,
            api_key=self._api_key,
            max_retries=0,
            timeout=max(1.0, float(getattr(self.settings, "assistant_request_timeout_seconds", 60.0))),
        )

    def generate(self, prompt: str, *, system: str | None = None,
                 max_tokens: int = _DEFAULT_MAX_TOKENS,
                 temperature: float = 0.0, timeout: float | None = None) -> str:
        self.last_telemetry = {}
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        client = self._client()
        if timeout is not None:
            # A per-call ceiling. The router gets a short one (BETA-112); the
            # OpenAI client raises on expiry, which `generate` maps to
            # `AssistantUnavailable` below — i.e. the caller fails closed.
            client = client.with_options(timeout=timeout)
        kwargs: dict[str, Any] = {
            "model": self.model, "messages": messages,
            "max_tokens": max_tokens, "temperature": temperature}
        # OpenRouter's OpenAI-compatible API accepts fallback model IDs in
        # `extra_body`; `model` remains the primary model for the SDK.
        extra_body: dict[str, Any] = {}
        if "openrouter.ai" in (self.base_url or "").lower():
            if len(self.models) > 1:
                extra_body["models"] = list(self.models[1:])
            provider = provider_preferences(self.settings, base_url=self.base_url)
            if provider:
                extra_body["provider"] = provider
        if extra_body:
            kwargs["extra_body"] = extra_body
        if self._json_response:
            kwargs["response_format"] = {"type": "json_object"}
        telemetry = TransportTelemetry()
        try:
            resp = run_with_resilience(
                lambda: client.chat.completions.create(**kwargs),
                settings=self.settings, circuit_key=f"{self.base_url}|{self.model}",
                base_url=self.base_url, telemetry=telemetry,
                deadline_seconds=timeout)
            self.last_telemetry = telemetry.as_dict()
        except AssistantUnavailable:
            raise
        except Exception as exc:  # connection refused / model not pulled / timeout
            self.last_telemetry = telemetry.as_dict()
            raise AssistantUnavailable(
                f"{self.model} at {self.base_url} did not respond "
                f"after {telemetry.attempts} attempt(s): "
                f"{type(exc).__name__}: {exc}") from exc
        try:
            return resp.choices[0].message.content or ""
        except (AttributeError, IndexError, KeyError) as exc:
            raise AssistantUnavailable(
                f"{self.model} returned an unexpected response shape") from exc


class LFMOllamaAdapter(_OpenAICompatAdapter):
    name = "lfm-ollama"

    def __init__(self, settings: Any) -> None:
        super().__init__(
            base_url=getattr(settings, "assistant_ollama_url", ""),
            models=resolved_lfm_models(settings),
            api_key=resolved_api_key(settings), settings=settings)


class NeedleAdapter(_OpenAICompatAdapter):
    name = "needle-2"

    def __init__(self, settings: Any) -> None:
        super().__init__(
            base_url=getattr(settings, "assistant_needle_url", ""),
            models=resolved_needle_models(settings),
            api_key=resolved_api_key(settings),
            settings=settings,
            json_response=getattr(settings, "assistant_router_json_mode", True))


_ADAPTERS = {
    "lfm": LFMOllamaAdapter, "lfm-ollama": LFMOllamaAdapter,
    "ollama": LFMOllamaAdapter,
    "needle": NeedleAdapter, "needle-2": NeedleAdapter,
}


def get_adapter(name: str, settings: Any) -> _OpenAICompatAdapter:
    """One adapter by name. Raises `AssistantUnavailable` if the layer is off
    or the extra is missing, so a caller never gets a half-built object."""
    require_enabled(settings)
    cls = _ADAPTERS.get(name)
    if cls is None:
        raise AssistantUnavailable(
            f"unknown adapter {name!r}; try {sorted(set(_ADAPTERS))}")
    return cls(settings)
