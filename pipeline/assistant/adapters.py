"""Assistant adapters (BETA-107): two OpenAI-chat-compatible HTTP backends.

  * `LFMOllamaAdapter` — a local Ollama serving
    `LiquidAI/LFM2.5-1.2B-Instruct` (Q4_K_M) at its `/v1` endpoint, for
    32K-context synthesis over what the warehouse already holds.
  * `NeedleAdapter` — the Needle 2 bounded retrieval router at its own local
    `/v1` endpoint.

Both talk HTTP through the `openai` client (the only `[assistant]` pin), so
neither needs a native model runtime *in this process*. Every path that
could touch the network is lazy: the client is built, and the extra is
imported, only inside `generate()`. A missing extra, a disabled layer, a
refused connection or an un-pulled model all surface as
`AssistantUnavailable` — never a raw import or socket error.
"""
from __future__ import annotations

from typing import Any

from pipeline.assistant.runtime import (
    LFM_MODEL,
    NEEDLE_MODEL,
    AssistantUnavailable,
    require_enabled,
)

_DEFAULT_MAX_TOKENS = 1024


class _OpenAICompatAdapter:
    """Shared chat-completions call over an OpenAI-compatible `/v1` base URL.

    `api_key` is a placeholder: a local Ollama and a local Needle both ignore
    it, but the `openai` client requires the parameter to be set.
    """

    name = "openai-compat"

    def __init__(self, *, base_url: str, model: str,
                 api_key: str = "local-no-key") -> None:
        self.base_url = base_url
        self.model = model
        self._api_key = api_key

    def _client(self):
        try:
            from openai import OpenAI  # lazy: the only place the extra is needed
        except ImportError as exc:  # pragma: no cover - depends on the extra
            raise AssistantUnavailable(
                "the `assistant` extra is not installed "
                "(`uv sync --extra assistant`)") from exc
        if not self.base_url:
            raise AssistantUnavailable(f"no endpoint configured for {self.name}")
        return OpenAI(base_url=self.base_url, api_key=self._api_key)

    def generate(self, prompt: str, *, system: str | None = None,
                 max_tokens: int = _DEFAULT_MAX_TOKENS,
                 temperature: float = 0.0) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        client = self._client()
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
            model=LFM_MODEL)


class NeedleAdapter(_OpenAICompatAdapter):
    name = "needle-2"

    def __init__(self, settings: Any) -> None:
        super().__init__(
            base_url=getattr(settings, "assistant_needle_url", ""),
            model=NEEDLE_MODEL)


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
