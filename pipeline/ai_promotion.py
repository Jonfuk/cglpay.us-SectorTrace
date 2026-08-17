"""Policy gate for autonomous evidence promotions.

The normal promotion path remains available to named human reviewers. This
module is the narrower autonomous path: a structured research manifest must
prove the policy predicates before it can call :func:`pipeline.promote.promote`.
It records the model and policy separately from ``promoted_by`` so an AI actor
can never impersonate a person in the existing audit column.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pipeline import promote


class AIPromotionPolicyError(ValueError):
    """A recommendation does not satisfy the autonomous promotion policy."""


@dataclass(frozen=True)
class Recommendation:
    kind: str
    url: str
    actor_id: str
    model_id: str
    policy_version: str
    evidence_manifest_sha256: str
    independent_review_count: int
    confidence: float
    official_source: bool
    exact_identity: bool
    explicit_document_type: bool
    dated: bool
    archived: bool
    no_conflicts: bool
    note: str | None = None


def validate(recommendation: Recommendation) -> None:
    """Validate all objective predicates before any network or DB write."""
    checks = {
        "official source": recommendation.official_source,
        "exact non-conflicting identity": recommendation.exact_identity,
        "explicit document type": recommendation.explicit_document_type,
        "identifiable date": recommendation.dated,
        "archived payload": recommendation.archived,
        "no conflicts": recommendation.no_conflicts,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AIPromotionPolicyError(
            "autonomous promotion refused; failed predicates: "
            + ", ".join(failed))
    if recommendation.independent_review_count < 2:
        raise AIPromotionPolicyError(
            "autonomous promotion requires two independent reviews")
    if not 0 <= recommendation.confidence <= 1:
        raise AIPromotionPolicyError("confidence must be between 0 and 1")
    for field in ("actor_id", "model_id", "policy_version",
                  "evidence_manifest_sha256"):
        if not getattr(recommendation, field).strip():
            raise AIPromotionPolicyError(f"{field} is required")


def apply(conn, recommendation: Recommendation, *, settings=None,
          resolver=None, fields: dict[str, Any] | None = None) -> dict:
    """Apply one policy-approved recommendation through the normal fetch path."""
    validate(recommendation)
    result = promote.promote(
        conn, recommendation.kind, recommendation.url,
        promoted_by="autonomous-policy", fields=fields,
        note=recommendation.note, settings=settings, resolver=resolver,
        actor_type="ai", actor_id=recommendation.actor_id,
        model_id=recommendation.model_id,
        policy_version=recommendation.policy_version,
        evidence_manifest_sha256=recommendation.evidence_manifest_sha256,
        independent_review_count=recommendation.independent_review_count,
        confidence=recommendation.confidence, qa_status="sampled_pending",
    )
    return result
