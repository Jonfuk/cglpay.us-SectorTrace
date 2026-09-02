from __future__ import annotations

import pytest

from pipeline.assistant.transport import (
    CircuitOpenError,
    TransportTelemetry,
    provider_preferences,
    run_with_resilience,
)


class _RateLimited(RuntimeError):
    status_code = 429

    class response:
        headers = {"Retry-After": "0"}


class _Unavailable(RuntimeError):
    status_code = 503


def test_transient_errors_are_retried_with_telemetry(settings, monkeypatch):
    monkeypatch.setattr(settings, "assistant_max_retries", 1, raising=False)
    monkeypatch.setattr(settings, "assistant_retry_base_seconds", 0, raising=False)
    monkeypatch.setattr(settings, "assistant_retry_max_seconds", 0, raising=False)
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise _RateLimited("busy")
        return type("Response", (), {"model": "x/backup"})()

    telemetry = TransportTelemetry()
    result = run_with_resilience(operation, settings=settings,
                                 circuit_key="test-retry", base_url="https://example.test",
                                 telemetry=telemetry)

    assert result.model == "x/backup"
    assert calls == 2
    assert telemetry.attempts == 2
    assert telemetry.retry_count == 1
    assert telemetry.status_codes == [429]


def test_circuit_breaker_prevents_immediate_rehammering(settings, monkeypatch):
    monkeypatch.setattr(settings, "assistant_max_retries", 0, raising=False)
    monkeypatch.setattr(settings, "assistant_circuit_breaker_failures", 1, raising=False)
    key = "test-circuit-unique"

    def operation():
        raise _Unavailable("down")

    with pytest.raises(_Unavailable):
        run_with_resilience(operation, settings=settings, circuit_key=key,
                            base_url="https://example.test")
    with pytest.raises(CircuitOpenError):
        run_with_resilience(operation, settings=settings, circuit_key=key,
                            base_url="https://example.test")


def test_provider_preferences_are_openrouter_only(settings, monkeypatch):
    monkeypatch.setattr(settings, "assistant_provider_sort", "latency", raising=False)
    monkeypatch.setattr(settings, "assistant_provider_ignore", "novitaai, novitaai", raising=False)

    assert provider_preferences(settings, base_url="https://openrouter.ai/api/v1") == {
        "sort": "latency",
        "ignore": ["novitaai"],
        "allow_fallbacks": True,
        "require_parameters": True,
    }
    assert provider_preferences(settings, base_url="http://ollama:11434/v1") == {}
