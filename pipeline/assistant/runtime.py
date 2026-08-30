"""The `assistant` runtime boundary (BETA-107; retargeted to OpenRouter in
BETA-114).

This module is importable with **none** of the optional runtime present: no
`[assistant]` extra, no `openai` client, no configured endpoint or key. It
reports what is missing rather than raising, so a checkout without any of it
runs the offline suite unchanged.

`AssistantUnavailable` is the one exception the whole package raises when
asked to do something it cannot — never a bare `ImportError` or a socket
error leaking out.

BETA-114 moved both inference legs off the local Ollama/Needle runtime and
onto OpenRouter (a CPU-only VPS could not meet the routing bars — see
`docs/assistant.md`). There is therefore no pinned model: a deployment must
name the router and answerer model slugs itself (`ASSISTANT_NEEDLE_MODEL` /
`ASSISTANT_LFM_MODEL`), and an unset slug fails closed in the adapter rather
than sending a stale default to OpenRouter. `LFM_MODEL` / `LFM_QUANT` /
`NEEDLE_MODEL` remain as empty constants only so importers and the ledger's
default-factory still resolve.
"""
from __future__ import annotations

import importlib.util
import os
from typing import Any

# No pinned model any more (BETA-114): OpenRouter has no single right default
# and a stale one would 404 on the wire. Kept as empty constants so the
# `resolved_*` fallbacks and grounding's dataclass default still have a name
# to reference; a real slug comes from the `assistant_*_model` settings.
LFM_MODEL = ""
LFM_QUANT = ""
NEEDLE_MODEL = ""


def resolved_lfm_model(settings: Any) -> str:
    return getattr(settings, "assistant_lfm_model", "") or LFM_MODEL


def resolved_lfm_quant(settings: Any) -> str:
    return getattr(settings, "assistant_lfm_quant", "") or LFM_QUANT


def resolved_needle_model(settings: Any) -> str:
    return getattr(settings, "assistant_needle_model", "") or NEEDLE_MODEL


def resolved_api_key(settings: Any) -> str:
    """The bearer token the adapters send. `ASSISTANT_API_KEY` first, then
    `OPENROUTER_API_KEY` (the same variable `nlp suggest-decisions` reads), so
    a host that already has one set for the review-triage path needs no second
    entry. Empty is allowed — a self-hosted OpenAI-compatible endpoint that
    ignores the key still works — and the adapter passes a placeholder in that
    case so the `openai` client's required-parameter check is satisfied."""
    return (getattr(settings, "assistant_api_key", None)
            or os.environ.get("OPENROUTER_API_KEY", "")
            or "")


class AssistantUnavailable(RuntimeError):
    """Raised when an assistant feature is asked for without its backend —
    the extra not installed, the runtime disabled, or the endpoint down."""


def openai_client_installed() -> bool:
    """True if the `openai` client (the `[assistant]` extra) can be imported.
    Uses `find_spec` so this check itself never imports it."""
    try:
        return importlib.util.find_spec("openai") is not None
    except (ImportError, ValueError):
        return False


def is_enabled(settings: Any) -> bool:
    return bool(getattr(settings, "assistant_enabled", False))


def runtime_status(settings: Any) -> dict:
    """What is enabled, installed and configured — **without contacting any
    endpoint**. Safe to call anywhere, including when the extra is absent."""
    installed = openai_client_installed()
    enabled = is_enabled(settings)
    return {
        "enabled": enabled,
        "openai_client_installed": installed,
        "api_key_configured": bool(resolved_api_key(settings)),
        "ready": enabled and installed,
        "model": {"id": resolved_lfm_model(settings),
                  "quant": resolved_lfm_quant(settings)},
        "adapters": {
            # Names are historical role labels: "lfm-ollama" is the answerer
            # leg, "needle-2" the router leg. Both now reach OpenRouter (or any
            # OpenAI-compatible endpoint) at the URL below; the model slug is
            # whatever the deployment set, empty until it does.
            "lfm-ollama": {
                "endpoint": getattr(settings, "assistant_ollama_url", None),
                "model": resolved_lfm_model(settings),
            },
            "needle-2": {
                "endpoint": getattr(settings, "assistant_needle_url", None),
                "model": resolved_needle_model(settings),
            },
        },
        "note": "Off by default; the Railway image installs neither the "
                "[assistant] extra nor a key. Inference runs on OpenRouter "
                "(BETA-114). No endpoint was contacted to produce this status.",
    }


def require_enabled(settings: Any) -> None:
    if not is_enabled(settings):
        raise AssistantUnavailable(
            "the assistant layer is off (Settings.assistant_enabled is False)")
    if not openai_client_installed():
        raise AssistantUnavailable(
            "the `assistant` extra is not installed "
            "(`uv sync --extra assistant`)")
