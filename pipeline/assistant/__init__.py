"""Optional natural-language operator layer (BETA-107; inference on OpenRouter
since BETA-114).

A DOWNSTREAM, non-collecting operator convenience. Everything about it is off
by default:

  * `Settings.assistant_enabled` is `False`;
  * this package imports with none of its dependencies or configuration
    present — `runtime_status()` reports what is missing rather than raising;
  * the Railway image installs neither the `[assistant]` extra nor a key
    (see `Dockerfile` — the `uv sync` there pins the base extras);
  * an adapter raises `AssistantUnavailable` (never a bare `ImportError` or
    a socket error) when asked to run without its backend or a model slug.

Never imported by a collector, the web server's request path, or CI. The
offline test suite must pass unchanged whether or not `openai` or an
OpenRouter key is present.
"""
from pipeline.assistant.adapters import (
    LFMOllamaAdapter,
    NeedleAdapter,
    get_adapter,
)
from pipeline.assistant.runtime import (
    LFM_MODEL,
    LFM_QUANT,
    NEEDLE_MODEL,
    AssistantUnavailable,
    is_enabled,
    openai_client_installed,
    require_enabled,
    resolved_api_key,
    resolved_lfm_model,
    resolved_lfm_quant,
    resolved_needle_model,
    runtime_status,
)

__all__ = [
    "AssistantUnavailable",
    "LFM_MODEL",
    "LFM_QUANT",
    "NEEDLE_MODEL",
    "LFMOllamaAdapter",
    "NeedleAdapter",
    "get_adapter",
    "is_enabled",
    "openai_client_installed",
    "require_enabled",
    "resolved_api_key",
    "resolved_lfm_model",
    "resolved_lfm_quant",
    "resolved_needle_model",
    "runtime_status",
]
