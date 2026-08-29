"""One orchestration service shared by the HTTP route and the CLI (BETA-112).

`ask()` runs one read-only turn: route the question to at most one tool
(BETA-110), execute that tool (BETA-109), ground an answer on its result
(BETA-111), record one immutable ledger row (BETA-108), and return a single
domain payload. Neither entry point — `POST /api/admin/assistant` or
`pipeline nlp assistant` — may bypass the schema, confidence, citation or
provenance checks, because both call exactly this function.

It is single-turn by design: no conversation storage, no public access, no
autonomous multi-tool loop. Exactly one tool call is permitted per turn. A
short router timeout and a 30-second overall ceiling both fail closed, and
every failure mode resolves to one of the explicit outcomes below rather than
to an exception escaping to the caller.
"""
from __future__ import annotations

import time
from typing import Any

import structlog

from pipeline.assistant import grounding, routing, tools
from pipeline.assistant.runtime import (
    LFM_MODEL,
    LFM_QUANT,
    NEEDLE_MODEL,
    AssistantUnavailable,
    require_enabled,
)

log = structlog.get_logger()

OVERALL_TIMEOUT_SECONDS = 30.0

CAVEAT = (
    "Experimental local finding aid. This answer is produced by a small local "
    "model summarising ONE read-only query of the warehouse; it is not "
    "evidence, not a review decision and not a published figure. Every "
    "citation links to stored provenance — open it before relying on anything."
)

# outcome vocabulary the payload and the ledger share.
OUTCOMES = ("ok", "abstained", "clarified", "timeout", "unavailable", "failed")


def _models(settings) -> dict:
    return {
        "router": {"id": NEEDLE_MODEL,
                   "endpoint": getattr(settings, "assistant_needle_url", None)},
        "answerer": {"id": LFM_MODEL, "quant": LFM_QUANT,
                     "endpoint": getattr(settings, "assistant_ollama_url", None)},
    }


def _payload(*, outcome: str, settings, filters: dict, timings: dict,
             run_id: str | None, tool: str | None = None,
             confidence: float | None = None, answer: str | None = None,
             citations: list | None = None, clarification: str | None = None,
             detail: str | None = None) -> dict:
    return {
        "outcome": outcome,
        "answer": answer,
        "citations": citations or [],
        "clarification": clarification,
        "detail": detail,
        "tool": tool,
        "routing_confidence": confidence,
        "models": _models(settings),
        "filters": filters,
        "timings_ms": timings,
        "run_id": run_id,
        "caveat": CAVEAT,
    }


def ask(conn, settings, question: str, *, source_system: str | None = None,
        date_from: str | None = None, date_to: str | None = None,
        limit: int | None = None, needle_adapter: Any = None,
        lfm_adapter: Any = None) -> dict:
    """Run one assistant turn. Always returns a payload; never raises for a
    runtime that is merely unavailable."""
    from pipeline.assistant import ledger

    filters = {"source_system": source_system or None,
               "date_from": date_from or None, "date_to": date_to or None,
               "limit": limit}
    timings: dict[str, int | None] = {"route_ms": None, "tool_ms": None,
                                       "answer_ms": None, "total_ms": None}
    started = time.perf_counter()

    def _elapsed_ms() -> int:
        return round((time.perf_counter() - started) * 1000)

    def _record(outcome: str, *, decision=None, envelope=None, grounded=None,
                error_class: str | None = None) -> str | None:
        return ledger.record(
            conn,
            question=question, filters=filters, outcome=outcome,
            needle_model=NEEDLE_MODEL,
            needle_endpoint=getattr(settings, "assistant_needle_url", None),
            lfm_model=LFM_MODEL, lfm_quant=LFM_QUANT,
            lfm_endpoint=getattr(settings, "assistant_ollama_url", None),
            router_prompt_sha256=routing.router_prompt_sha256(),
            answer_prompt_sha256=grounding.answer_prompt_sha256(),
            selected_tool=getattr(decision, "tool", None),
            routing_confidence=getattr(decision, "confidence", None),
            tool_args=getattr(decision, "arguments", None),
            retrieved_chunk_ids=(envelope or {}).get("result_ids")
            if envelope else None,
            answer=getattr(grounded, "answer", None),
            citation_ids=getattr(grounded, "cited_ids", None),
            timings=timings, error_class=error_class)

    try:
        require_enabled(settings)
    except AssistantUnavailable as exc:
        return _payload(outcome="unavailable", settings=settings, filters=filters,
                        timings=timings, run_id=None, detail=str(exc))

    # --- route ---------------------------------------------------------------
    try:
        decision = routing.route(question, settings=settings,
                                  adapter=needle_adapter)
    except AssistantUnavailable as exc:
        timings["route_ms"] = _elapsed_ms()
        timings["total_ms"] = _elapsed_ms()
        run_id = _record("unavailable", error_class=type(exc).__name__)
        return _payload(outcome="unavailable", settings=settings, filters=filters,
                        timings=timings, run_id=run_id, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 - a bug degrades, it does not 500
        timings["total_ms"] = _elapsed_ms()
        run_id = _record("failed", error_class=type(exc).__name__)
        log.warning("assistant.route_failed", error=f"{type(exc).__name__}: {exc}")
        return _payload(outcome="failed", settings=settings, filters=filters,
                        timings=timings, run_id=run_id, detail="router error")
    timings["route_ms"] = _elapsed_ms()

    if not decision.should_execute:
        timings["total_ms"] = _elapsed_ms()
        run_id = _record("clarified", decision=decision)
        return _payload(outcome="clarified", settings=settings, filters=filters,
                        timings=timings, run_id=run_id,
                        confidence=decision.confidence,
                        clarification=decision.clarification)

    # --- execute the single tool ------------------------------------------
    args = dict(decision.arguments or {})
    for field, value in (("source_system", source_system), ("date_from", date_from),
                         ("date_to", date_to), ("limit", limit)):
        if value and tools.tool_accepts(decision.tool, field):
            args.setdefault(field, value)

    tool_started = time.perf_counter()
    try:
        envelope = tools.run_tool(decision.tool, args, conn, settings)
    except tools.ToolError as exc:
        timings["tool_ms"] = round((time.perf_counter() - tool_started) * 1000)
        timings["total_ms"] = _elapsed_ms()
        run_id = _record("clarified", decision=decision)
        return _payload(outcome="clarified", settings=settings, filters=filters,
                        timings=timings, run_id=run_id,
                        confidence=decision.confidence,
                        clarification=f"The chosen tool could not run: {exc}")
    except Exception as exc:  # noqa: BLE001
        timings["tool_ms"] = round((time.perf_counter() - tool_started) * 1000)
        timings["total_ms"] = _elapsed_ms()
        run_id = _record("failed", decision=decision, error_class=type(exc).__name__)
        log.warning("assistant.tool_failed", tool=decision.tool,
                    error=f"{type(exc).__name__}: {exc}")
        return _payload(outcome="failed", settings=settings, filters=filters,
                        timings=timings, run_id=run_id, tool=decision.tool,
                        detail="tool error")
    timings["tool_ms"] = round((time.perf_counter() - tool_started) * 1000)

    # --- overall ceiling before the (slowest) answer leg -----------------
    remaining = OVERALL_TIMEOUT_SECONDS - (time.perf_counter() - started)
    if remaining <= 1.0:
        timings["total_ms"] = _elapsed_ms()
        run_id = _record("timeout", decision=decision, envelope=envelope)
        return _payload(outcome="timeout", settings=settings, filters=filters,
                        timings=timings, run_id=run_id, tool=decision.tool,
                        confidence=decision.confidence,
                        detail="the overall time budget was spent before the "
                               "answer step")

    # --- ground an answer ----------------------------------------------
    answer_started = time.perf_counter()
    try:
        grounded = grounding.answer(question, envelope, settings=settings,
                                    conn=conn, adapter=lfm_adapter)
    except AssistantUnavailable as exc:
        timings["answer_ms"] = round((time.perf_counter() - answer_started) * 1000)
        timings["total_ms"] = _elapsed_ms()
        run_id = _record("unavailable", decision=decision, envelope=envelope,
                         error_class=type(exc).__name__)
        return _payload(outcome="unavailable", settings=settings, filters=filters,
                        timings=timings, run_id=run_id, tool=decision.tool,
                        confidence=decision.confidence, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        timings["answer_ms"] = round((time.perf_counter() - answer_started) * 1000)
        timings["total_ms"] = _elapsed_ms()
        run_id = _record("failed", decision=decision, envelope=envelope,
                         error_class=type(exc).__name__)
        log.warning("assistant.answer_failed",
                    error=f"{type(exc).__name__}: {exc}")
        return _payload(outcome="failed", settings=settings, filters=filters,
                        timings=timings, run_id=run_id, tool=decision.tool,
                        detail="answer error")
    timings["answer_ms"] = round((time.perf_counter() - answer_started) * 1000)
    timings["total_ms"] = _elapsed_ms()

    outcome = "ok" if grounded.outcome == "answered" else "abstained"
    run_id = _record(outcome, decision=decision, envelope=envelope,
                     grounded=grounded)
    return _payload(
        outcome=outcome, settings=settings, filters=filters, timings=timings,
        run_id=run_id, tool=decision.tool, confidence=decision.confidence,
        answer=grounded.answer, citations=grounded.citations,
        clarification=None if outcome == "ok" else
        "The evidence returned was not enough to answer; nothing was asserted.",
        detail=None if outcome == "ok" else grounded.reason)
