"""Needle routing and the confidence gate (BETA-110).

One analyst question in, at most one allowlisted tool call out. Needle 2 is a
small local router with built-in tool retrieval and a calibrated confidence
head; it is a better bounded dispatcher than spending LFM context on the whole
catalogue. But its output is never trusted directly:

  * the returned tool name is checked against the closed catalogue
    (`pipeline.assistant.tools.TOOL_NAMES`);
  * the returned arguments are re-validated by `tools.validate_args`, the same
    function the executor uses — the router does not get to widen a bound;
  * the confidence must clear a threshold frozen on the BETA-113 development
    routing set before anything is executed.

Anything below the threshold, ambiguous, out of scope or invalid returns a
*clarification* and executes no tool. A router timeout or a dead endpoint
raises `AssistantUnavailable` (fail closed — no tool runs). Needle sees only
the question and the catalogue, never retrieved document text, so a prompt
injected into a document cannot change the selected action.

Needle telemetry is off: the adapter talks to a local endpoint only and no
usage is reported anywhere.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from pipeline.assistant.tools import TOOL_NAMES, ToolError, tool_schemas, validate_args

# Frozen on the development routing set (see docs/assistant.md and
# `pipeline nlp assistant-eval`). Not a runtime setting: changing it is a
# deliberate edit here, re-scored against the held-out BETA-113 suite.
FROZEN_ROUTING_THRESHOLD = 0.60

# A short ceiling for the router leg specifically (BETA-112 asks for one).
ROUTER_TIMEOUT_SECONDS = 8.0

_MAX_QUESTION_LEN = 600

ROUTER_SYSTEM_PROMPT = (
    "You are a routing function for a read-only evidence assistant. You never "
    "answer the question. You choose at most one tool from the fixed catalogue "
    "below and return ONLY a JSON object:\n"
    '  {"tool": <name or null>, "arguments": {<bounded args>}, '
    '"confidence": <0..1>}\n'
    "Rules: pick `null` for the tool when the question is ambiguous, needs "
    "clarification, or asks for something no tool covers. Never invent a tool "
    "name or an argument name. Never emit a table name, URL, file path or SQL. "
    "Confidence is your calibrated probability that this single call answers "
    "the question. Output the JSON and nothing else."
)


def router_prompt_sha256() -> str:
    """SHA-256 of the exact bytes of the frozen router contract — the system
    prompt plus the catalogue it is given. Recorded on every ledger row so a
    change of routing behaviour is visible."""
    payload = json.dumps(
        {"system": ROUTER_SYSTEM_PROMPT, "catalogue": tool_schemas()},
        sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class RoutingDecision:
    outcome: str                       # "route" | "clarify"
    reason: str
    tool: str | None = None
    arguments: dict | None = None
    confidence: float | None = None
    clarification: str | None = None
    raw: str | None = None             # the router's raw text, for the ledger/debug
    catalogue_sha256: str = field(default_factory=router_prompt_sha256)

    @property
    def should_execute(self) -> bool:
        return self.outcome == "route"


def _clarify(reason: str, message: str, *, confidence: float | None = None,
             raw: str | None = None) -> RoutingDecision:
    return RoutingDecision(outcome="clarify", reason=reason,
                           clarification=message, confidence=confidence, raw=raw)


def _build_prompt(question: str) -> str:
    catalogue = json.dumps(tool_schemas(), indent=2, sort_keys=True)
    return (f"Tool catalogue:\n{catalogue}\n\n"
            f"Analyst question:\n{question}\n\n"
            "Return the routing JSON now.")


_JSON_OBJ_RE = re.compile(r"\{.*\}", re.S)


def _parse(raw: str) -> dict | None:
    """Pull the first JSON object out of the router's reply. A small local
    model sometimes wraps it in prose or a code fence; anything we cannot
    parse into an object is treated as no decision (fail closed)."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    match = _JSON_OBJ_RE.search(text)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def route(question: str, *, settings: Any, adapter: Any = None,
          threshold: float = FROZEN_ROUTING_THRESHOLD,
          timeout: float | None = ROUTER_TIMEOUT_SECONDS) -> RoutingDecision:
    """Route `question` to one tool, or return a clarification.

    `adapter` is any object with a `generate(prompt, *, system, timeout)` ->
    str method (a `NeedleAdapter` in production, a fake in tests). When omitted
    a `NeedleAdapter` is built, which itself raises `AssistantUnavailable` if
    the layer is disabled or the extra is missing.
    """
    question = (question or "").strip()
    if not question:
        return _clarify("empty", "Ask a question first.")
    if len(question) > _MAX_QUESTION_LEN:
        return _clarify(
            "too_long",
            f"That question is over {_MAX_QUESTION_LEN} characters — please "
            "shorten it to one specific ask.")

    if adapter is None:
        from pipeline.assistant.adapters import NeedleAdapter
        adapter = NeedleAdapter(settings)

    # A dead endpoint or a timeout surfaces here as AssistantUnavailable and is
    # deliberately NOT caught — the orchestrator records outcome "unavailable"
    # and nothing is executed. That is the fail-closed behaviour BETA-110 asks
    # for; a router that cannot answer must not default to running a tool.
    raw = adapter.generate(_build_prompt(question),
                           system=ROUTER_SYSTEM_PROMPT, timeout=timeout)

    obj = _parse(raw)
    if obj is None:
        return _clarify("unparseable",
                        "The router did not return a usable decision. Try "
                        "rephrasing the question.", raw=raw)

    tool = obj.get("tool")
    if tool in (None, "", "null", "none", "clarify"):
        return _clarify("router_abstained",
                        "The router could not confidently match this to one of "
                        "its tools. Narrow the question — e.g. name the source "
                        "or the metric you mean.", raw=raw)
    if not isinstance(tool, str) or tool not in TOOL_NAMES:
        return _clarify("unknown_tool",
                        "The router picked something outside its catalogue, so "
                        "nothing was run.", raw=raw)

    confidence = obj.get("confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = None

    # Validate arguments with the executor's own function BEFORE the confidence
    # check — an above-threshold call with malformed args is still a clarify,
    # and we want the more specific reason.
    try:
        cleaned = validate_args(tool, obj.get("arguments") or {})
    except ToolError as exc:
        return _clarify("invalid_arguments",
                        f"The router's arguments did not fit {tool}: {exc}",
                        confidence=confidence, raw=raw)

    if confidence is None:
        return _clarify("no_confidence",
                        "The router returned no confidence score, so nothing "
                        "was run.", raw=raw)
    if confidence < threshold:
        return _clarify(
            "below_threshold",
            f"The router was not confident enough ({confidence:.2f} < "
            f"{threshold:.2f}) to run a tool. Rephrase or add detail.",
            confidence=confidence, raw=raw)

    return RoutingDecision(outcome="route", reason="routed", tool=tool,
                           arguments=cleaned, confidence=confidence, raw=raw)
