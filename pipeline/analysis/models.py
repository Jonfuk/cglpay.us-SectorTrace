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


class AnalysisModelUnavailable(RuntimeError):
    """The optional model backend is not configured or did not answer."""


class AnalysisModelInvalidJSON(AnalysisModelUnavailable):
    """The model answered, but its response was not a complete JSON object."""


class AnalysisModelClient:
    def __init__(self, settings: Any, *, release_id: str, run_id: str,
                 models: dict[str, str], conn) -> None:
        self.settings = settings
        self.release_id = release_id
        self.run_id = run_id
        self.models = models
        self.conn = conn
        self.last_cost_micros = 0
        self.last_cached = False

    def generate_json(self, prompt: str, *, role: str, domain_id: str,
                      window_id: str | None = None) -> dict[str, Any] | None:
        self.last_cost_micros = 0
        self.last_cached = False
        model_id = self.models.get(role)
        if not model_id:
            detail = f"no model configured for analysis role {role!r}"
            self._record(model_id="unconfigured", domain_id=domain_id, prompt_sha=hashlib.sha256(prompt.encode()).hexdigest(),
                         window_id=window_id, response=None, cost_micros=None, latency_ms=0,
                         status="unavailable", cached=False, error_detail=detail)
            raise AnalysisModelUnavailable(detail)
        prompt_sha = hashlib.sha256(prompt.encode()).hexdigest()
        cached = self.conn.execute(
            "SELECT response_json, cost_micros FROM analysis_model_calls "
            "WHERE release_id = ? AND model_id = ? AND prompt_sha256 = ? "
            "AND status = 'ok' ORDER BY created_at DESC LIMIT 1",
            (self.release_id, model_id, prompt_sha)).fetchone()
        if cached and cached["response_json"]:
            self.last_cost_micros = 0
            self.last_cached = True
            self._record(model_id=model_id, domain_id=domain_id, prompt_sha=prompt_sha, window_id=window_id,
                         response=cached["response_json"], cost_micros=0, latency_ms=0,
                         status="ok", cached=True, error_detail=None)
            return json.loads(cached["response_json"])
        try:
            from openai import OpenAI
        except ImportError as exc:
            detail = "analysis model support requires the assistant extra"
            self._record(model_id=model_id, domain_id=domain_id, prompt_sha=prompt_sha, window_id=window_id,
                         response=None, cost_micros=None, latency_ms=0,
                         status="unavailable", cached=False, error_detail=detail)
            raise AnalysisModelUnavailable(detail) from exc
        if not getattr(self.settings, "assistant_enabled", False):
            detail = "analysis model support is disabled"
            self._record(model_id=model_id, domain_id=domain_id, prompt_sha=prompt_sha, window_id=window_id,
                         response=None, cost_micros=None, latency_ms=0,
                         status="unavailable", cached=False, error_detail=detail)
            raise AnalysisModelUnavailable(detail)
        base_url = getattr(self.settings, "assistant_ollama_url", "")
        if not base_url:
            detail = "no OpenAI-compatible analysis endpoint is configured"
            self._record(model_id=model_id, domain_id=domain_id, prompt_sha=prompt_sha, window_id=window_id,
                         response=None, cost_micros=None, latency_ms=0,
                         status="unavailable", cached=False, error_detail=detail)
            raise AnalysisModelUnavailable(detail)
        started = time.monotonic()
        try:
            client = OpenAI(base_url=base_url, api_key=resolved_api_key(self.settings) or "no-key-configured")
            response = client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": "Return one valid JSON object and no markdown."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"}, max_tokens=1024, temperature=0,
            )
            content = response.choices[0].message.content or "{}"
        except Exception as exc:
            self._record(model_id=model_id, domain_id=domain_id, prompt_sha=prompt_sha, window_id=window_id,
                         response=None, cost_micros=None,
                         latency_ms=round((time.monotonic() - started) * 1000),
                         status="error", cached=False,
                         error_detail=f"{type(exc).__name__}: {exc}")
            detail = f"{model_id} did not respond: {type(exc).__name__}: {exc}"
            raise AnalysisModelUnavailable(detail) from exc
        try:
            payload = json.loads(content)
        except (TypeError, ValueError) as exc:
            self._record(model_id=model_id, domain_id=domain_id, prompt_sha=prompt_sha, window_id=window_id,
                         response=content, cost_micros=None,
                         latency_ms=round((time.monotonic() - started) * 1000),
                         status="invalid_json", cached=False,
                         error_detail=f"invalid JSON response: {type(exc).__name__}: {exc}")
            raise AnalysisModelInvalidJSON("analysis model returned invalid JSON") from exc
        usage = getattr(response, "usage", None)
        raw_cost = getattr(usage, "cost", None) if usage is not None else None
        try:
            cost_micros = round(float(raw_cost) * 1_000_000) if raw_cost is not None else 0
        except (TypeError, ValueError):
            cost_micros = 0
        self.last_cost_micros = cost_micros
        self.last_cached = False
        self._record(model_id=model_id, domain_id=domain_id, prompt_sha=prompt_sha, window_id=window_id,
                     response=json.dumps(payload, sort_keys=True), cost_micros=cost_micros,
                     latency_ms=round((time.monotonic() - started) * 1000), status="ok", cached=False)
        return payload

    def _record(self, *, model_id: str, domain_id: str, prompt_sha: str, window_id: str | None,
                response: str | None, cost_micros: int | None, latency_ms: int,
                status: str, cached: bool, error_detail: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO analysis_model_calls (model_call_id, release_id, run_id, domain_id, window_id, "
            "model_id, prompt_sha256, response_json, cached, cost_micros, latency_ms, status, error_detail, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"model-call-{uuid.uuid4()}", self.release_id, self.run_id, domain_id, window_id,
             model_id, prompt_sha, response, int(cached), cost_micros, latency_ms, status, error_detail, utcnow()))
        self.conn.commit()
