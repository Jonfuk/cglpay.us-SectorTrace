"""The `assistant` runtime boundary (BETA-107).

This module is importable with **none** of the optional runtime present: no
`[assistant]` extra, no `openai` client, no Ollama, no model weights, no
Needle endpoint. It reports what is missing rather than raising, so a
checkout without any of it runs the offline suite unchanged.

`AssistantUnavailable` is the one exception the whole package raises when
asked to do something it cannot — never a bare `ImportError` or a socket
error leaking out.
"""
from __future__ import annotations

import importlib.util
from typing import Any

# The pinned local model, kept here (not in `adapters.py`) so `runtime.py`
# has no import cycle with the adapters. Installed out of band on the
# analysis host via Ollama; never by pip. These are the defaults — a
# deployment overrides them through the `assistant_*_model` / `_quant`
# settings (see `resolved_*` below), e.g. to serve a larger LFM2.5 size or
# to name the weights by the `hf.co/...` string an Ollama pulled them under.
LFM_MODEL = "LiquidAI/LFM2.5-1.2B-Instruct"
LFM_QUANT = "Q4_K_M"
NEEDLE_MODEL = "needle-2"


def resolved_lfm_model(settings: Any) -> str:
    return getattr(settings, "assistant_lfm_model", "") or LFM_MODEL


def resolved_lfm_quant(settings: Any) -> str:
    return getattr(settings, "assistant_lfm_quant", "") or LFM_QUANT


def resolved_needle_model(settings: Any) -> str:
    return getattr(settings, "assistant_needle_model", "") or NEEDLE_MODEL


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
        "ready": enabled and installed,
        "model": {"id": resolved_lfm_model(settings),
                  "quant": resolved_lfm_quant(settings)},
        "adapters": {
            "lfm-ollama": {
                "endpoint": getattr(settings, "assistant_ollama_url", None),
                "model": resolved_lfm_model(settings),
            },
            "needle-2": {
                "endpoint": getattr(settings, "assistant_needle_url", None),
                "model": resolved_needle_model(settings),
            },
        },
        "note": "Off by default; local analysis host only; the Railway image "
                "installs neither the [assistant] extra nor the model. No "
                "endpoint was contacted to produce this status.",
    }


def require_enabled(settings: Any) -> None:
    if not is_enabled(settings):
        raise AssistantUnavailable(
            "the assistant layer is off (Settings.assistant_enabled is False)")
    if not openai_client_installed():
        raise AssistantUnavailable(
            "the `assistant` extra is not installed "
            "(`uv sync --extra assistant`)")
