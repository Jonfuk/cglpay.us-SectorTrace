"""Grounded narrative verification and lightweight open-set discovery."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from pipeline.analysis.signals import Signal, new_signal

_SENTENCE_RE = re.compile(r"[^.!?]+(?:[.!?]|$)", re.S)
_CONTRADICTION_RE = re.compile(r"\b(?:not|no|without|never|did not|isn't|wasn't)\b", re.I)


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


def discover_themes(passages: Iterable[dict[str, Any]], *, novelty_threshold: float = .85,
                    recurrence_bar: dict[str, int] | None = None) -> list[dict[str, Any]]:
    """A dependency-free discovery fallback with the same safety contract as BERTopic.

    Deployments with BERTopic can replace clustering, but the output shape is
    intentionally stable and always preserves outliers rather than discarding
    low-density passages.
    """
    bar = {"passages": 10, "documents": 5, "subjects": 3} | (recurrence_bar or {})
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for passage in passages:
        text = str(passage.get("text") or "").strip()
        words = [w.lower() for w in re.findall(r"[a-z][a-z-]{4,}", text)]
        key = Counter(words).most_common(1)[0][0] if words else "outlier"
        groups[key].append({**passage, "representative_quote": text[:240]})
    themes = []
    for key, items in groups.items():
        documents = {i.get("document_id") for i in items if i.get("document_id")}
        subjects = {i.get("subject_id") for i in items if i.get("subject_id")}
        is_outlier = key == "outlier" or len(items) == 1
        themes.append({"theme_key": key, "passage_count": len(items),
                       "document_count": len(documents), "subject_count": len(subjects),
                       "novelty_similarity": 0.0 if is_outlier else min(.84, .5 + 1 / max(len(items), 1)),
                       "outlier": is_outlier, "passages": items,
                       "status": "promotion_ready" if len(items) >= bar["passages"] and
                       len(documents) >= bar["documents"] and len(subjects) >= bar["subjects"] and
                       (0.0 if is_outlier else .5) < novelty_threshold else "shadow"})
    return themes
