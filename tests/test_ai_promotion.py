from pipeline.ai_promotion import (
    AIPromotionPolicyError,
    Recommendation,
    validate,
)


def _recommendation(**overrides):
    values = dict(
        kind="committee_paper",
        url="https://council.example/paper.pdf",
        actor_id="research-batch-1",
        model_id="gpt-5.6-sol",
        policy_version="ai-promotion-v1",
        evidence_manifest_sha256="a" * 64,
        independent_review_count=2,
        confidence=0.98,
        official_source=True,
        exact_identity=True,
        explicit_document_type=True,
        dated=True,
        archived=True,
        no_conflicts=True,
    )
    values.update(overrides)
    return Recommendation(**values)


def test_autonomous_policy_accepts_fully_supported_recommendation():
    validate(_recommendation())


def test_autonomous_policy_rejects_ambiguous_identity():
    try:
        validate(_recommendation(exact_identity=False))
    except AIPromotionPolicyError as exc:
        assert "identity" in str(exc)
    else:
        raise AssertionError("ambiguous identity must remain human-routed")


def test_autonomous_policy_requires_two_independent_reviews():
    try:
        validate(_recommendation(independent_review_count=1))
    except AIPromotionPolicyError as exc:
        assert "two independent" in str(exc)
    else:
        raise AssertionError("single-review recommendations must be refused")
