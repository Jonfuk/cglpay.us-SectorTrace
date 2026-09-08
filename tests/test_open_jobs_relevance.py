from pipeline.open_jobs.relevance import classify


def test_role_match_is_explainable_and_candidate():
    result = classify(
        title="Substance Misuse Recovery Worker",
        company=None,
        location="Leeds",
    )

    assert result.decision == "candidate"
    assert "substance misuse" in result.matched_terms
    assert "title" in result.matched_fields
    assert result.payload()["triage_version"] == "role_v1"


def test_generic_recovery_false_positive_is_excluded():
    result = classify(
        title="Data Recovery Technician",
        company=None,
        location="Bristol",
    )

    assert result.decision == "excluded"
    assert "data recovery" in result.excluded_terms
    assert not result.candidate


def test_location_does_not_make_an_advert_relevant():
    result = classify(title="Support Worker", company=None, location="England")

    assert result.decision == "no_match"


def test_archived_content_can_surface_a_role_without_title_hit():
    result = classify(
        title="Clinical Practitioner",
        company=None,
        location="Manchester",
        content="The post delivers opioid substitution treatment.",
    )

    assert result.decision == "candidate"
    assert result.matched_terms == ("opioid",)
    assert result.matched_fields == ("content",)
