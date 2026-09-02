"""Small, dependency-free resilience layer for OpenAI-compatible requests."""
from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable


@dataclass
class TransportTelemetry:
    """Safe-to-persist facts about one logical request."""

    attempts: int = 0
    retry_count: int = 0
    status_codes: list[int] = field(default_factory=list)
    retry_after_seconds: float | None = None
    actual_model: str | None = None
    provider: str | None = None
    circuit_open: bool = False
    error_type: str | None = None
    started_at: float = field(default_factory=time.monotonic)
    latency_ms: int = 0

    def finish(self) -> None:
        self.latency_ms = round((time.monotonic() - self.started_at) * 1000)

    def as_dict(self) -> dict[str, Any]:
        self.finish()
        return {
            "attempts": self.attempts,
            "retry_count": self.retry_count,
            "status_codes": list(self.status_codes),
            "retry_after_seconds": self.retry_after_seconds,
            "actual_model": self.actual_model,
            "provider": self.provider,
            "circuit_open": self.circuit_open,
            "error_type": self.error_type,
            "latency_ms": self.latency_ms,
        }


class CircuitOpenError(RuntimeError):
    """The shared endpoint circuit is cooling down after repeated failures."""


class TransportDeadlineExceeded(TimeoutError):
    """The logical request deadline expired before another attempt."""


@dataclass
class _Circuit:
    failures: int = 0
    open_until: float = 0.0


_LOCK = threading.RLock()
_SEMAPHORES: dict[tuple[str, int], threading.BoundedSemaphore] = {}
_CIRCUITS: dict[str, _Circuit] = {}


def _setting(settings: Any, name: str, default: Any) -> Any:
    return getattr(settings, name, default)


def _status_code(exc: BaseException) -> int | None:
    raw = getattr(exc, "status_code", None)
    if raw is None:
        response = getattr(exc, "response", None)
        raw = getattr(response, "status_code", None)
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _retry_after(exc: BaseException) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or {}
    value = headers.get("Retry-After") or headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            when = parsedate_to_datetime(str(value))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def _retryable(exc: BaseException) -> bool:
    status = _status_code(exc)
    if status in {408, 409, 425, 429} or (status is not None and status >= 500):
        return True
    name = type(exc).__name__.lower()
    return any(token in name for token in ("timeout", "connection", "connecterror"))


def _semaphore(base_url: str, limit: int) -> threading.BoundedSemaphore:
    key = (base_url, limit)
    with _LOCK:
        return _SEMAPHORES.setdefault(key, threading.BoundedSemaphore(limit))


def _circuit_is_open(key: str, now: float) -> bool:
    with _LOCK:
        state = _CIRCUITS.get(key)
        return bool(state and state.open_until > now)


def _record_failure(key: str, *, threshold: int, cooldown: float) -> None:
    with _LOCK:
        state = _CIRCUITS.setdefault(key, _Circuit())
        state.failures += 1
        if state.failures >= threshold:
            state.open_until = time.monotonic() + cooldown


def _record_success(key: str) -> None:
    with _LOCK:
        _CIRCUITS.pop(key, None)


def run_with_resilience(operation: Callable[[], Any], *, settings: Any,
                        circuit_key: str, base_url: str,
                        telemetry: TransportTelemetry | None = None,
                        deadline_seconds: float | None = None) -> Any:
    """Run one request with bounded concurrency, retries and a circuit breaker.

    OpenRouter's own model/provider fallback remains responsible for selecting
    the next model. This layer only retries the complete logical request after
    transient failures and prevents a failing endpoint from being hammered.
    """
    telemetry = telemetry or TransportTelemetry()
    max_retries = max(0, min(5, int(_setting(settings, "assistant_max_retries", 2))))
    base_delay = max(0.0, float(_setting(settings, "assistant_retry_base_seconds", 0.5)))
    max_delay = max(base_delay, float(_setting(settings, "assistant_retry_max_seconds", 8.0)))
    threshold = max(1, int(_setting(settings, "assistant_circuit_breaker_failures", 3)))
    cooldown = max(0.0, float(_setting(settings, "assistant_circuit_breaker_cooldown_seconds", 60.0)))
    concurrency = max(1, int(_setting(settings, "assistant_max_concurrency", 8)))
    gate = _semaphore(base_url, concurrency)

    with gate:
        for attempt in range(max_retries + 1):
            if (deadline_seconds is not None and
                    time.monotonic() - telemetry.started_at >= deadline_seconds):
                telemetry.error_type = "TransportDeadlineExceeded"
                telemetry.finish()
                raise TransportDeadlineExceeded(
                    f"request deadline exceeded for {circuit_key}")
            if _circuit_is_open(circuit_key, time.monotonic()):
                telemetry.circuit_open = True
                telemetry.error_type = "CircuitOpenError"
                telemetry.finish()
                raise CircuitOpenError(f"circuit open for {circuit_key}")
            telemetry.attempts += 1
            try:
                result = operation()
                _record_success(circuit_key)
                telemetry.actual_model = getattr(result, "model", None)
                telemetry.provider = (
                    getattr(result, "provider", None)
                    or getattr(result, "provider_name", None))
                telemetry.finish()
                return result
            except Exception as exc:
                telemetry.error_type = type(exc).__name__
                status = _status_code(exc)
                if status is not None:
                    telemetry.status_codes.append(status)
                retry_after = _retry_after(exc)
                if retry_after is not None:
                    telemetry.retry_after_seconds = retry_after
                should_retry = _retryable(exc) and attempt < max_retries
                _record_failure(circuit_key, threshold=threshold, cooldown=cooldown)
                if not should_retry:
                    telemetry.finish()
                    raise
                telemetry.retry_count += 1
                delay = min(max_delay, base_delay * (2 ** attempt))
                if retry_after is not None:
                    delay = max(delay, min(max_delay, retry_after))
                if deadline_seconds is not None:
                    remaining = deadline_seconds - (time.monotonic() - telemetry.started_at)
                    if remaining <= 0:
                        telemetry.finish()
                        raise
                    delay = min(delay, remaining)
                if delay > 0:
                    time.sleep(delay + random.uniform(0.0, min(0.25, delay / 4)))
    raise RuntimeError("resilience loop exited unexpectedly")  # pragma: no cover


def parse_csv_setting(value: Any) -> list[str]:
    """Parse comma/newline-separated provider settings."""
    if not value:
        return []
    values = value.replace("\n", ",").split(",") if isinstance(value, str) else value
    return list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))


def provider_preferences(settings: Any, *, base_url: str) -> dict[str, Any]:
    """Build OpenRouter-only provider preferences; leave self-hosted calls alone."""
    if "openrouter.ai" not in (base_url or "").lower():
        return {}
    provider: dict[str, Any] = {}
    sort = str(_setting(settings, "assistant_provider_sort", "") or "").strip()
    order = parse_csv_setting(_setting(settings, "assistant_provider_order", ""))
    ignore = parse_csv_setting(_setting(settings, "assistant_provider_ignore", ""))
    if sort:
        provider["sort"] = sort
    if order:
        provider["order"] = order
    if ignore:
        provider["ignore"] = ignore
    provider["allow_fallbacks"] = bool(_setting(settings, "assistant_provider_allow_fallbacks", True))
    provider["require_parameters"] = bool(_setting(settings, "assistant_provider_require_parameters", True))
    return provider
