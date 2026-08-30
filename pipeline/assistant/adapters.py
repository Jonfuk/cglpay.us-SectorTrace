"""Assistant adapters (BETA-107; retargeted to OpenRouter in BETA-114): two
OpenAI-chat-compatible HTTP backends.

  * `LFMOllamaAdapter` — the answerer leg. Historically a local Ollama; since
    BETA-114 it reaches OpenRouter (`assistant_ollama_url`, defaulting to
    `https://openrouter.ai/api/v1`) with the slug `resolved_lfm_model`.
  * `NeedleAdapter` — the router leg. Historically the Needle 2 endpoint; since
    BETA-114 it reaches OpenRouter (`assistant_needle_url`) with the slug
    `resolved_needle_model`. The two legs are configured independently so a
    cheap model can route and a stronger one can ground.

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
    resolved_lfm_model,
    resolved_needle_model,
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

    def __init__(self, *, base_url: str, model: str,
                 api_key: str = "") -> None:
        self.base_url = base_url
        self.model = model
        self._api_key = api_key or _PLACEHOLDER_KEY

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
        return OpenAI(base_url=self.base_url, api_key=self._api_key)

    def generate(self, prompt: str, *, system: str | None = None,
                 max_tokens: int = _DEFAULT_MAX_TOKENS,
                 temperature: float = 0.0, timeout: float | None = None) -> str:
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
        try:
            resp = client.chat.completions.create(
                model=self.model, messages=messages,
                max_tokens=max_tokens, temperature=temperature)
        except AssistantUnavailable:
            raise
        except Exception as exc:  # connection refused / model not pulled / timeout
            raise AssistantUnavailable(
                f"{self.model} at {self.base_url} did not respond: "
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
            model=resolved_lfm_model(settings),
            api_key=resolved_api_key(settings))


class NeedleAdapter(_OpenAICompatAdapter):
    name = "needle-2"

    def __init__(self, settings: Any) -> None:
        super().__init__(
            base_url=getattr(settings, "assistant_needle_url", ""),
            model=resolved_needle_model(settings),
            api_key=resolved_api_key(settings))


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
