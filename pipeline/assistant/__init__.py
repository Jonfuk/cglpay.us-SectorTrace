"""Optional natural-language operator layer (BETA-107).

A DOWNSTREAM, non-collecting convenience for the **local analysis host**.
Everything about it is off by default:

  * `Settings.assistant_enabled` is `False`;
  * this package imports with none of its dependencies, model weights or
    runtimes present — `runtime_status()` reports what is missing rather
    than raising;
  * the Railway image installs neither the `[assistant]` extra nor the
    model (see `Dockerfile` — the `uv sync` there pins the base extras);
  * an adapter raises `AssistantUnavailable` (never a bare `ImportError` or
    a socket error) when asked to run without its backend.

Never imported by a collector, the web server's request path, or CI. The
offline test suite must pass unchanged whether or not `openai`, Ollama, the
LFM weights or a Needle endpoint are present.
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
    "runtime_status",
]
