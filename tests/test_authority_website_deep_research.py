from pipeline.authority_websites import AUTHORITY_WEBSITES


def test_deep_research_base_urls_are_recorded_with_their_check_date():
    expected = {
        "E09000007": "https://www.camden.gov.uk",
        "E09000010": "https://www.enfield.gov.uk",
        "E06000006": "https://www3.halton.gov.uk",
        "E06000046": "https://www.iow.gov.uk",
        "E08000012": "https://www.liverpool.gov.uk",
        "E06000002": "https://www.middlesbrough.gov.uk",
        "E10000020": "https://www.norfolk.gov.uk",
        "E06000057": "https://www.northumberland.gov.uk",
        "E08000023": "https://www.southtyneside.gov.uk",
        "E06000045": "https://www.southampton.gov.uk",
        "E06000004": "https://www.stockton.gov.uk",
        "E08000024": "https://www.sunderland.gov.uk",
    }

    for ons_code, base_url in expected.items():
        entry = AUTHORITY_WEBSITES[ons_code]
        assert entry.base_url == base_url
        assert entry.base_url_verified_on == "2026-08-17"


def test_deep_research_committee_roots_are_recorded_as_moderngov():
    expected = {
        "E06000022": "https://democracy.bathnes.gov.uk",
        "E08000002": "https://councildecisions.bury.gov.uk",
        "E08000026": "https://edemocracy.coventry.gov.uk",
        "E09000014": "https://www.minutes.haringey.gov.uk",
        "E06000004": "https://moderngov.stockton.gov.uk",
    }

    for ons_code, committee_url in expected.items():
        entry = AUTHORITY_WEBSITES[ons_code]
        assert entry.committee_url == committee_url
        assert entry.committee_system == "moderngov"
        assert entry.verified_on == "2026-08-17"
