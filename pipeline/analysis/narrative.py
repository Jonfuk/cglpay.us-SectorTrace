"""Grounded narrative verification and lightweight open-set discovery."""
from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from pipeline.analysis.prefilter import RULES_VERSION
from pipeline.analysis.prefilter import matches as _prefilter_matches
from pipeline.analysis.signals import Signal, new_signal

_SENTENCE_RE = re.compile(r"[^.!?]+(?:[.!?]|$)", re.S)
_CONTRADICTION_RE = re.compile(r"\b(?:not|no|without|never|did not|isn't|wasn't)\b", re.I)
NARRATIVE_PREFILTER_VERSION = RULES_VERSION


def theme_key_for_text(text: str) -> str:
    words = [word.lower() for word in re.findall(r"[a-z][a-z-]{4,}", (text or "").strip())]
    return Counter(words).most_common(1)[0][0] if words else "outlier"


def narrative_candidate_prefilter(text: str, *, enabled: bool = False) -> bool:
    """Cheap deterministic candidate gate.

    It is shadow-only by default: the model path remains the correctness
    baseline until an adjudicated corpus proves recall for rare categories.
    """
    if not enabled:
        return True
    return _prefilter_matches(text)


@dataclass(frozen=True)
class NarrativeCandidate:
    namespace: str
    signal_type: str
    subtype: str | None
    assertion_status: str
    direction: str
    subject_type: str
    subject_id: str
    evidence_quote: str
    scope_quote: str
    evidence_ref: str
    period_start: str | None = None
    period_end: str | None = None
    planned_or_hypothetical: bool = False
    model_outputs: tuple[dict[str, Any], ...] = ()


def extraction_prompt(*, namespace: str, subject_type: str, subject_id: str, text: str) -> str:
    """Build the bounded extraction prompt used by both analysis models."""
    return (
        "Extract at most one grounded automated signal from this source passage. "
        "Return {\"signal\": null} when no qualifying signal is present. "
        "Otherwise return a JSON object under signal with exactly these fields: "
        "signal_type, subtype, assertion_status, direction, evidence_quote, scope_quote, "
        "period_start, period_end, planned_or_hypothetical. Quotes must be exact contiguous "
        "substrings from the passage. Do not infer names, identifiers, dates or numbers. "
        f"The canonical namespace is {namespace!r}; subject type is {subject_type!r}; "
        f"subject id is {subject_id!r}.\n\nPASSAGE:\n{text}"
    )


def candidate_from_payload(payload: dict[str, Any] | None, *, namespace: str,
                           subject_type: str, subject_id: str, evidence_ref: str,
                           model_output: dict[str, Any] | None = None) -> NarrativeCandidate | None:
    """Convert model JSON to a candidate while retaining canonical identity."""
    signal = payload.get("signal") if isinstance(payload, dict) else None
    if not isinstance(signal, dict):
        return None
    required = ("signal_type", "assertion_status", "direction", "evidence_quote", "scope_quote")
    if any(not str(signal.get(field) or "").strip() for field in required):
        return None
    assertion_status = str(signal["assertion_status"])
    direction = str(signal["direction"])
    if assertion_status not in ("affirmed", "negated", "historical", "planned", "hypothetical", "unknown"):
        return None
    if direction not in ("adverse", "improving", "neutral", "mixed", "unknown"):
        return None
    return NarrativeCandidate(
        namespace=namespace, signal_type=str(signal["signal_type"]),
        subtype=str(signal.get("subtype")) if signal.get("subtype") is not None else None,
        assertion_status=assertion_status, direction=direction,
        subject_type=subject_type, subject_id=subject_id,
        evidence_quote=str(signal["evidence_quote"]), scope_quote=str(signal["scope_quote"]),
        evidence_ref=evidence_ref,
        period_start=signal.get("period_start"), period_end=signal.get("period_end"),
        planned_or_hypothetical=bool(signal.get("planned_or_hypothetical", False)),
        model_outputs=(model_output,) if model_output else (),
    )


def exact_substring(text: str, quote: str) -> bool:
    return bool(quote) and quote in text


def sentence_containing(text: str, quote: str) -> str | None:
    if not exact_substring(text, quote):
        return None
    start = text.rfind(".", 0, text.index(quote)) + 1
    end_match = re.search(r"[.!?]", text[text.index(quote):])
    end = text.index(quote) + (end_match.end() if end_match else len(text[text.index(quote):]))
    return text[start:end].strip()


def verify_candidate(candidate: NarrativeCandidate, source_text: str, *,
                     second_model: NarrativeCandidate | None = None,
                     minicheck_pass: bool = True, alignscore_pass: bool = True,
                     contradiction: bool | None = None) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if second_model is None:
        failures.append("dual_model_agreement_missing")
    else:
        fields = ("namespace", "signal_type", "subtype", "assertion_status", "subject_type",
                  "subject_id", "evidence_quote", "scope_quote")
        for field in fields:
            if getattr(candidate, field) != getattr(second_model, field):
                failures.append(f"model_disagreement:{field}")
    evidence_sentence = sentence_containing(source_text, candidate.evidence_quote)
    scope_sentence = sentence_containing(source_text, candidate.scope_quote)
    if evidence_sentence is None:
        failures.append("evidence_quote_not_exact_source_substring")
    if scope_sentence is None:
        failures.append("scope_quote_not_exact_source_substring")
    if evidence_sentence and scope_sentence and evidence_sentence != scope_sentence:
        failures.append("evidence_scope_sentence_mismatch")
    if not minicheck_pass:
        failures.append("minicheck_failed")
    if not alignscore_pass:
        failures.append("alignscore_failed")
    contradiction = bool(_CONTRADICTION_RE.search(evidence_sentence or "")) if contradiction is None else contradiction
    if contradiction and candidate.assertion_status == "affirmed":
        failures.append("explicit_contradiction")
    return not failures, failures


def candidate_to_signal(candidate: NarrativeCandidate, *, release_id: str,
                        source_text: str, second_model: NarrativeCandidate | None = None,
                        minicheck_pass: bool = True, alignscore_pass: bool = True) -> Signal | None:
    ok, failures = verify_candidate(candidate, source_text, second_model=second_model,
                                    minicheck_pass=minicheck_pass, alignscore_pass=alignscore_pass)
    if not ok:
        return None
    confidence = {"agreement": True, "minicheck": minicheck_pass, "alignscore": alignscore_pass,
                  "planned_or_hypothetical": candidate.planned_or_hypothetical, "failures": failures}
    return new_signal(release_id=release_id, domain_id=candidate.namespace,
                      taxonomy_namespace=candidate.namespace, signal_type=candidate.signal_type,
                      subject_type=candidate.subject_type, subject_id=candidate.subject_id,
                      direction=candidate.direction, assertion_status=candidate.assertion_status,
                      period_start=candidate.period_start, period_end=candidate.period_end,
                      evidence_refs=[candidate.evidence_ref], derivation_method="dual_model_narrative",
                      confidence_contract=confidence)


class ThemeAccumulator:
    """Incremental theme counts with bounded, stable evidence sampling."""

    def __init__(self, *, novelty_threshold: float = .85,
                 recurrence_bar: dict[str, int] | None = None,
                 max_evidence_per_theme: int | None = None,
                 max_evidence_total: int | None = None,
                 state: dict[str, Any] | None = None) -> None:
        self.novelty_threshold = novelty_threshold
        self.bar = {"passages": 10, "documents": 5, "subjects": 3} | (recurrence_bar or {})
        self.max_evidence_per_theme = (None if max_evidence_per_theme is None else
                                       max(0, int(max_evidence_per_theme)))
        self.max_evidence_total = (None if max_evidence_total is None else
                                   max(0, int(max_evidence_total)))
        self.groups: dict[str, dict[str, Any]] = {}
        self.retained_evidence = 0
        if state:
            self.retained_evidence = int(state.get("retained_evidence", 0))
            for key, raw in (state.get("groups") or {}).items():
                self.groups[key] = {
                    "items": list(raw.get("items") or []),
                    "passage_count": int(raw.get("passage_count", 0)),
                    "documents": set(raw.get("documents") or []),
                    "subjects": set(raw.get("subjects") or []),
                }

    def add(self, passage: dict[str, Any]) -> None:
        text_value = str(passage.get("text") or "").strip()
        key = theme_key_for_text(text_value)
        group = self.groups.setdefault(
            key, {"items": [], "passage_count": 0, "documents": set(), "subjects": set()})
        group["passage_count"] += 1
        if passage.get("document_id"):
            group["documents"].add(passage["document_id"])
        if passage.get("subject_id"):
            group["subjects"].add(passage["subject_id"])
        if ((self.max_evidence_per_theme is None or
             len(group["items"]) < self.max_evidence_per_theme) and
                (self.max_evidence_total is None or
                 self.retained_evidence < self.max_evidence_total)):
            group["items"].append({**passage, "representative_quote": text_value[:240]})
            self.retained_evidence += 1

    def state(self) -> dict[str, Any]:
        return {
            "retained_evidence": self.retained_evidence,
            "groups": {
                key: {**group, "documents": sorted(group["documents"]),
                      "subjects": sorted(group["subjects"])}
                for key, group in self.groups.items()
            },
        }

    def themes(self) -> list[dict[str, Any]]:
        result = []
        for key, group in self.groups.items():
            passage_count = group["passage_count"]
            documents = group["documents"]
            subjects = group["subjects"]
            is_outlier = key == "outlier" or passage_count == 1
            similarity = 0.0 if is_outlier else min(.84, .5 + 1 / max(passage_count, 1))
            result.append({
                "theme_key": key, "passage_count": passage_count,
                "document_count": len(documents), "subject_count": len(subjects),
                "novelty_similarity": similarity, "outlier": is_outlier,
                "passages": group["items"],
                "status": "promotion_ready" if
                passage_count >= self.bar["passages"] and
                len(documents) >= self.bar["documents"] and
                len(subjects) >= self.bar["subjects"] and
                (0.0 if is_outlier else .5) < self.novelty_threshold else "shadow",
            })
        return result


def discover_themes(passages: Iterable[dict[str, Any]], *, novelty_threshold: float = .85,
                    recurrence_bar: dict[str, int] | None = None,
                    max_evidence_per_theme: int | None = None,
                    max_evidence_total: int | None = None,
                    progress_callback: Callable[[int], None] | None = None,
                    progress_interval_seconds: float = 5.0) -> list[dict[str, Any]]:
    """A dependency-free discovery fallback with the same safety contract as BERTopic.

    Deployments with BERTopic can replace clustering, but the output shape is
    intentionally stable and always preserves outliers rather than discarding
    low-density passages.

    When evidence limits are supplied, counts and distinct document/subject
    totals still cover every passage, while only a bounded sample is retained
    in each theme's evidence payload. A progress callback can keep a worker's
    liveness visible during large scans.
    """
    accumulator = ThemeAccumulator(
        novelty_threshold=novelty_threshold, recurrence_bar=recurrence_bar,
        max_evidence_per_theme=max_evidence_per_theme,
        max_evidence_total=max_evidence_total)
    started = time.monotonic()
    last_progress = started
    processed = 0
    reported = 0
    for passage in passages:
        processed += 1
        accumulator.add(passage)
        now = time.monotonic()
        if progress_callback and now - last_progress >= max(0.1, progress_interval_seconds):
            progress_callback(processed)
            reported = processed
            last_progress = now
    if progress_callback and processed and reported != processed:
        progress_callback(processed)
    return accumulator.themes()
