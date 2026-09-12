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


def _model_list(value: Any) -> tuple[str, ...]:
    """Parse a comma/newline separated fallback setting safely."""
    if not value:
        return ()
    if isinstance(value, str):
        values = value.replace("\n", ",").split(",")
    else:
        values = value
    return tuple(str(item).strip() for item in values if str(item).strip())


def _model_chain(primary: str, fallbacks: Any) -> tuple[str, ...]:
    """Return a de-duplicated primary-plus-fallback model chain."""
    chain = (primary,) + _model_list(fallbacks)
    return tuple(dict.fromkeys(model for model in chain if model))


def resolved_lfm_models(settings: Any) -> tuple[str, ...]:
    return _model_chain(
        resolved_lfm_model(settings),
        getattr(settings, "assistant_lfm_fallback_models", ""),
    )


def resolved_lfm_quant(settings: Any) -> str:
    return getattr(settings, "assistant_lfm_quant", "") or LFM_QUANT


def resolved_needle_model(settings: Any) -> str:
    return getattr(settings, "assistant_needle_model", "") or NEEDLE_MODEL


def resolved_needle_models(settings: Any) -> tuple[str, ...]:
    return _model_chain(
        resolved_needle_model(settings),
        getattr(settings, "assistant_needle_fallback_models", ""),
    )


def resolved_claim_models(settings: Any, role: str) -> tuple[str, ...]:
    """Resolve role-specific analysis models without changing assistant roles."""
    primary_name = {
        "scout": "claim_signal_scout_model",
        "extractor": "claim_signal_extractor_model",
        "reflection": "claim_signal_reflection_model",
    }.get(role)
    fallback_name = {
        "scout": "claim_signal_scout_fallback_models",
        "extractor": "claim_signal_extractor_fallback_models",
        "reflection": "claim_signal_reflection_fallback_models",
    }.get(role)
    if not primary_name or not fallback_name:
        return ()
    primary = getattr(settings, primary_name, "") or ""
    return _model_chain(primary, getattr(settings, fallback_name, ""))


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
