"""Deterministic, operator-only role triage for Open Jobs observations.

The classifier is a finding aid, not a relevance score.  A match creates a
human review item and never promotes an advert, identifies an employer, or
claims that a vacancy belongs to the substance-misuse sector.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.modules.m16_nhs_jobs import ROLE_KEYWORDS

# Keep the shared NHS Jobs vocabulary as the first part of this list so the
# same role language is used across the two source-specific collectors.  The
# extra phrases are deliberately narrow; broad words such as "care" and
# "support" produce an unreviewable queue of unrelated jobs.
POSITIVE_TERMS: tuple[str, ...] = tuple(dict.fromkeys(
    (*ROLE_KEYWORDS,
     "substance use", "addiction worker", "addictions worker", "addiction",
     "opioid", "opiate", "detox", "needle exchange", "harm reduction",
     "drug treatment", "alcohol treatment", "treatment recovery"),
))

# These phrases are common false positives for the word "recovery".  They
# remain visible in the triage result so an operator can audit why a row was
# excluded from the candidate count.
NEGATIVE_TERMS: tuple[str, ...] = (
    "disaster recovery", "data recovery", "debt recovery", "vehicle recovery",
    "mortgage recovery", "recovery of", "recovery technician",
)


def _pattern(term: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE)


_POSITIVE = tuple((term, _pattern(term)) for term in POSITIVE_TERMS)
_NEGATIVE = tuple((term, _pattern(term)) for term in NEGATIVE_TERMS)


@dataclass(frozen=True)
class TriageResult:
    """The explainable result for one current advert observation."""

    decision: str
    matched_terms: tuple[str, ...]
    excluded_terms: tuple[str, ...]
    matched_fields: tuple[str, ...]

    @property
    def candidate(self) -> bool:
        return self.decision == "candidate"

    def payload(self) -> dict[str, object]:
        return {
            "triage_version": "role_v1",
            "decision": self.decision,
            "matched_terms": list(self.matched_terms),
            "excluded_terms": list(self.excluded_terms),
            "matched_fields": list(self.matched_fields),
        }


def classify(*, title: str | None, company: str | None, location: str | None) -> TriageResult:
    """Classify an advert as a review candidate or an excluded finding aid.

    Matching is case-insensitive and preserves the field in which a term was
    found.  Location is recorded for audit but does not decide England scope;
    that remains a human decision because aggregator geography can be partial
    or ambiguous.
    """
    fields = {
        "title": title or "",
        "company": company or "",
        "location": location or "",
    }
    matched_terms: list[str] = []
    matched_fields: list[str] = []
    for term, pattern in _POSITIVE:
        field_hits = [name for name, value in fields.items() if pattern.search(value)]
        if field_hits:
            matched_terms.append(term)
            matched_fields.extend(field_hits)
    excluded_terms = [term for term, pattern in _NEGATIVE
                      if any(pattern.search(value) for value in fields.values())]
    if not matched_terms and excluded_terms:
        decision = "excluded"
    elif not matched_terms:
        decision = "no_match"
    elif excluded_terms:
        decision = "excluded"
    else:
        decision = "candidate"
    return TriageResult(
        decision=decision,
        matched_terms=tuple(matched_terms),
        excluded_terms=tuple(excluded_terms),
        matched_fields=tuple(dict.fromkeys(matched_fields)),
    )
