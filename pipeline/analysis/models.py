"""Optional OpenAI-compatible model boundary for analysis runs.

The worker remains useful without the optional assistant dependency: model
calls are skipped and the deterministic discovery/structured stages continue.
When enabled, every request is cached and recorded with its immutable release,
prompt hash, latency and provider-reported cost.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from pipeline.analysis.operations import utcnow
from pipeline.assistant.runtime import resolved_api_key
from pipeline.assistant.transport import (
    TransportTelemetry,
    provider_preferences,
    run_with_resilience,
)


class AnalysisModelUnavailable(RuntimeError):
    """The optional model backend is not configured or did not answer."""


class AnalysisModelConfigurationError(AnalysisModelUnavailable):
    """A permanent configuration/authentication error that should fail fast."""


class AnalysisModelInvalidJSON(AnalysisModelUnavailable):
    """The model answered, but its response was not a complete JSON object."""


def request_identity(*, role: str, system_prompt: str, prompt: str,
                     model: str, fallback_models: list[str] | None = None,
                     generation: dict[str, Any] | None = None,
                     provider_policy: dict[str, Any] | None = None,
                     schema: dict[str, Any] | None = None,
                     cache_version: str = "1") -> str:
    """Content address the exact model request, independent of a release id."""
    payload = {
        "role": role,
        "system_sha256": hashlib.sha256(system_prompt.encode()).hexdigest(),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "model": model, "fallback_models": fallback_models or [],
        "generation": generation or {}, "provider_policy": provider_policy or {},
        "schema": schema or {}, "cache_version": cache_version,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


class AnalysisModelClient:
    def __init__(self, settings: Any, *, release_id: str, run_id: str,
                 models: dict[str, str], conn,
                 fallback_models: dict[str, list[str]] | None = None,
                 audit_sink=None, cache_lookup=None, cache_sink=None) -> None:
        self.settings = settings
        self.release_id = release_id
        self.run_id = run_id
        self.models = models
        self.fallback_models = fallback_models or {}
        self.conn = conn
        self.audit_sink = audit_sink
        self.cache_lookup = cache_lookup
        self.cache_sink = cache_sink
        self._http_client = None
        self.last_cost_micros = 0
        self.last_cached = False
        self.last_telemetry: dict[str, Any] = {}

    def request_sha(self, prompt: str, *, role: str) -> str | None:
        model_id = self.models.get(role)
        if not model_id:
            return None
        return request_identity(
            role=role, system_prompt="Return one valid JSON object and no markdown.",
            prompt=prompt, model=model_id,
            fallback_models=self.fallback_models.get(role, []),
            generation={"response_format": {"type": "json_object"},
                        "max_tokens": 1024, "temperature": 0},
            provider_policy=self._provider_policy(), schema={"type": "json_object"})

    def generate_json(self, prompt: str, *, role: str, domain_id: str,
                      window_id: str | None = None) -> dict[str, Any] | None:
        self.last_cost_micros = 0
        self.last_cached = False
        model_id = self.models.get(role)
        if not model_id:
            detail = f"no model configured for analysis role {role!r}"
            self._record(model_id="unconfigured", domain_id=domain_id, prompt_sha=hashlib.sha256(prompt.encode()).hexdigest(), request_sha=None,
                         window_id=window_id, response=None, cost_micros=None, latency_ms=0,
                         status="unavailable", cached=False, error_detail=detail)
            raise AnalysisModelConfigurationError(detail)
        prompt_sha = hashlib.sha256(prompt.encode()).hexdigest()
        request_sha = self.request_sha(prompt, role=role)
        assert request_sha is not None
        cached = self._cached(request_sha)
        if cached and cached["response_json"]:
            self.last_cost_micros = 0
            self.last_cached = True
            served_model_id = cached.get("actual_model") or model_id
            self.last_telemetry = {"actual_model": served_model_id, "provider": cached.get("provider_id"),
                                   "cached": True}
            self._record(model_id=served_model_id, domain_id=domain_id, prompt_sha=prompt_sha,
                         request_sha=request_sha, window_id=window_id,
                         response=None, cost_micros=0, latency_ms=0,
                         status="ok", cached=True, error_detail=None,
                         provider_id=cached.get("provider_id"), response_cache_key=request_sha)
            return json.loads(cached["response_json"])
        try:
            from openai import OpenAI
        except ImportError as exc:
            detail = "analysis model support requires the assistant extra"
            self._record(model_id=model_id, domain_id=domain_id, prompt_sha=prompt_sha, request_sha=request_sha, window_id=window_id,
                         response=None, cost_micros=None, latency_ms=0,
                         status="unavailable", cached=False, error_detail=detail)
            raise AnalysisModelConfigurationError(detail) from exc
        if not getattr(self.settings, "assistant_enabled", False):
            detail = "analysis model support is disabled"
            self._record(model_id=model_id, domain_id=domain_id, prompt_sha=prompt_sha, request_sha=request_sha, window_id=window_id,
                         response=None, cost_micros=None, latency_ms=0,
                         status="unavailable", cached=False, error_detail=detail)
            raise AnalysisModelConfigurationError(detail)
        base_url = getattr(self.settings, "assistant_ollama_url", "")
        if not base_url:
            detail = "no OpenAI-compatible analysis endpoint is configured"
            self._record(model_id=model_id, domain_id=domain_id, prompt_sha=prompt_sha, request_sha=request_sha, window_id=window_id,
                         response=None, cost_micros=None, latency_ms=0,
                         status="unavailable", cached=False, error_detail=detail)
            raise AnalysisModelConfigurationError(detail)
        started = time.monotonic()
        telemetry = TransportTelemetry()
        try:
            if self._http_client is None:
                self._http_client = OpenAI(
                    base_url=base_url,
                    api_key=resolved_api_key(self.settings) or "no-key-configured",
                    max_retries=0,
                    timeout=max(1.0, float(getattr(self.settings, "assistant_request_timeout_seconds", 60.0))),
                )
            extra_body: dict[str, Any] = {}
            if "openrouter.ai" in base_url.lower():
                fallback_models = self.fallback_models.get(role, [])
                if fallback_models:
                    extra_body["models"] = fallback_models
                provider = provider_preferences(self.settings, base_url=base_url)
                if provider:
                    extra_body["provider"] = provider
            kwargs: dict[str, Any] = {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": "Return one valid JSON object and no markdown."},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": 1024,
                "temperature": 0,
            }
            if extra_body:
                kwargs["extra_body"] = extra_body
            response = run_with_resilience(
                lambda: self._http_client.chat.completions.create(**kwargs),
                settings=self.settings, circuit_key=f"{base_url}|{model_id}",
                base_url=base_url, telemetry=telemetry,
                deadline_seconds=max(1.0, float(getattr(
                    self.settings, "assistant_request_timeout_seconds", 60.0))))
            self.last_telemetry = telemetry.as_dict()
            content = response.choices[0].message.content or "{}"
        except Exception as exc:
            self.last_telemetry = telemetry.as_dict()
            self._record(model_id=model_id, domain_id=domain_id, prompt_sha=prompt_sha, request_sha=request_sha, window_id=window_id,
                         response=None, cost_micros=None,
                         latency_ms=round((time.monotonic() - started) * 1000),
                         status="error", cached=False,
                         error_detail=f"{type(exc).__name__}: {exc}",
                         provider_id=self.last_telemetry.get("provider"),
                         retry_count=self.last_telemetry.get("retry_count", 0),
                         status_code=(self.last_telemetry.get("status_codes") or [None])[-1])
            detail = f"{model_id} did not respond: {type(exc).__name__}: {exc}"
            status_codes = self.last_telemetry.get("status_codes") or []
            if any(status in {400, 401, 403, 404, 422} for status in status_codes):
                raise AnalysisModelConfigurationError(detail) from exc
            raise AnalysisModelUnavailable(detail) from exc
        try:
            payload = json.loads(content)
        except (TypeError, ValueError) as exc:
            self._record(model_id=model_id, domain_id=domain_id, prompt_sha=prompt_sha, request_sha=request_sha, window_id=window_id,
                         response=content, cost_micros=None,
                         latency_ms=round((time.monotonic() - started) * 1000),
                         status="invalid_json", cached=False,
                         error_detail=f"invalid JSON response: {type(exc).__name__}: {exc}",
                         provider_id=self.last_telemetry.get("provider"),
                         retry_count=self.last_telemetry.get("retry_count", 0))
            raise AnalysisModelInvalidJSON("analysis model returned invalid JSON") from exc
        answered_model_id = getattr(response, "model", None) or model_id
        usage = getattr(response, "usage", None)
        raw_cost = getattr(usage, "cost", None) if usage is not None else None
        try:
            cost_micros = round(float(raw_cost) * 1_000_000) if raw_cost is not None else 0
        except (TypeError, ValueError):
            cost_micros = 0
        self.last_cost_micros = cost_micros
        self.last_cached = False
        response_json = json.dumps(payload, sort_keys=True)
        cache_row = {
            "request_sha256": request_sha,
            "response_sha256": hashlib.sha256(response_json.encode()).hexdigest(),
            "response_json": response_json, "requested_model": model_id,
            "actual_model": answered_model_id,
            "provider_id": self.last_telemetry.get("provider"), "created_at": utcnow(),
        }
        self._cache(cache_row)
        self._record(model_id=answered_model_id, domain_id=domain_id, prompt_sha=prompt_sha,
                     request_sha=request_sha, window_id=window_id,
                     response=None, cost_micros=cost_micros,
                     latency_ms=round((time.monotonic() - started) * 1000), status="ok", cached=False,
                     provider_id=self.last_telemetry.get("provider"),
                     retry_count=self.last_telemetry.get("retry_count", 0),
                     response_cache_key=request_sha)
        return payload

    def _provider_policy(self) -> dict[str, Any]:
        base_url = getattr(self.settings, "assistant_ollama_url", "")
        return {
            "base_url": base_url,
            "preferences": provider_preferences(self.settings, base_url=base_url) or {},
        }

    def close(self) -> None:
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def _cached(self, request_sha: str):
        if self.cache_lookup is not None:
            return self.cache_lookup(request_sha)
        if self.conn is None:
            return None
        row = self.conn.execute(
            "SELECT request_sha256, response_json, actual_model, provider_id "
            "FROM analysis_model_response_cache WHERE request_sha256 = %s",
            (request_sha,)).fetchone()
        return dict(row) if row else None

    def _cache(self, row: dict[str, Any]) -> None:
        if self.cache_sink is not None:
            self.cache_sink(row)
            return
        if self.conn is None:
            return
        self.conn.execute(
            "INSERT INTO analysis_model_response_cache (request_sha256, response_sha256, response_json, "
            "requested_model, actual_model, provider_id, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT DO NOTHING",
            (row["request_sha256"], row["response_sha256"], row["response_json"],
             row["requested_model"], row["actual_model"], row.get("provider_id"), row["created_at"]))
        stored = self.conn.execute(
            "SELECT response_sha256 FROM analysis_model_response_cache WHERE request_sha256 = %s",
            (row["request_sha256"],)).fetchone()
        if stored is None or stored["response_sha256"] != row["response_sha256"]:
            raise RuntimeError("content-addressed model response conflict")

    def _record(self, *, model_id: str, domain_id: str, prompt_sha: str,
                request_sha: str | None, window_id: str | None,
                response: str | None, cost_micros: int | None, latency_ms: int,
                status: str, cached: bool, error_detail: str | None = None,
                provider_id: str | None = None, retry_count: int = 0,
                status_code: int | None = None,
                response_cache_key: str | None = None) -> None:
        values = (
            f"model-call-{uuid.uuid4()}", self.release_id, self.run_id, domain_id, window_id,
            model_id, provider_id, prompt_sha, request_sha, response_cache_key, response,
            int(cached), cost_micros, latency_ms, max(0, int(retry_count or 0)), status_code,
            status, error_detail, utcnow())
        if self.audit_sink is not None:
            self.audit_sink(values)
            return
        if self.conn is None:
            raise RuntimeError("model audit has no database writer or audit sink")
        self.conn.execute(
            "INSERT INTO analysis_model_calls (model_call_id, release_id, run_id, domain_id, window_id, "
            "model_id, provider_id, prompt_sha256, request_sha256, response_cache_key, response_json, "
            "cached, cost_micros, latency_ms, retry_count, status_code, status, error_detail, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            values)
        self.conn.commit()


AUDIT_INSERT_SQL = (
    "INSERT INTO analysis_model_calls (model_call_id, release_id, run_id, domain_id, window_id, "
    "model_id, provider_id, prompt_sha256, request_sha256, response_cache_key, response_json, "
    "cached, cost_micros, latency_ms, retry_count, status_code, status, error_detail, created_at) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
