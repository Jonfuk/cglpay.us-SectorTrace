from __future__ import annotations

import pytest

from pipeline import authority_websites
from pipeline.modules import m09_cdp_documents as cdp

# --- classification --------------------------------------------------------------

@pytest.mark.parametrize("url,text,expected_type", [
    ("/docs/combating-drugs-partnership-strategy.pdf", "Combating Drugs Partnership Strategy",
     "cdp_strategy"),
    ("/docs/substance-misuse-needs-assessment.pdf", "Substance Misuse Needs Assessment",
     "needs_assessment"),
    ("/docs/drug-alcohol-outcomes-framework.pdf", "Drug and alcohol outcomes framework",
     "outcomes_framework"),
])
def test_classify_document_recognises_target_types(url, text, expected_type):
    document_type, confidence = cdp.classify_document(url, text)
    assert document_type == expected_type
    assert confidence > 0


@pytest.mark.parametrize("url,text", [
    ("/docs/housing-strategy.pdf", "Housing Strategy 2025"),
    ("/news/bin-collections", "Bin collection changes"),
    ("/docs/climate-needs-assessment.pdf", "Climate needs assessment"),
])
def test_classify_document_rejects_unrelated_documents(url, text):
    """A strategy or needs assessment about something else is not a CDP
    document; requiring a substance-related hint keeps them out.
    """
    assert cdp.classify_document(url, text) == (None, 0.0)


def test_confidence_rises_with_independent_signals():
    weak = cdp.classify_document("/x/drug-strategy", "drug strategy")[1]
    strong = cdp.classify_document(
        "/x/combating-drugs-partnership-strategy.pdf",
        "Combating Drugs Partnership Strategy and needs assessment")[1]
    assert strong > weak
    assert 0 < strong <= 1.0


# --- link extraction ----------------------------------------------------------------

def test_extract_candidates_finds_matching_links():
    html = '''
      <a href="/docs/combating-drugs-strategy.pdf">Combating Drugs Partnership Strategy</a>
      <a href="/docs/bins.pdf">Bin collections</a>
    '''
    found = cdp.extract_candidates(html, "https://www.example.gov.uk/public-health")
    assert len(found) == 1
    assert found[0]["candidate_url"].endswith("/docs/combating-drugs-strategy.pdf")
    assert found[0]["document_type_guess"] == "cdp_strategy"


def test_extract_candidates_stays_on_the_same_host():
    """A crawl must not wander onto unrelated domains."""
    html = ('<a href="https://other.example.com/drug-strategy.pdf">Drug Strategy</a>'
            '<a href="/local/drug-strategy.pdf">Drug Strategy</a>')
    found = cdp.extract_candidates(html, "https://www.example.gov.uk/")
    assert len(found) == 1
    assert "www.example.gov.uk" in found[0]["candidate_url"]


def test_extract_candidates_deduplicates_and_strips_fragments():
    html = ('<a href="/d/drug-strategy.pdf#p1">Drug Strategy</a>'
            '<a href="/d/drug-strategy.pdf#p2">Drug Strategy</a>')
    found = cdp.extract_candidates(html, "https://www.example.gov.uk/")
    assert len(found) == 1
    assert "#" not in found[0]["candidate_url"]


def test_extract_candidates_empty_html():
    assert cdp.extract_candidates("", "https://www.example.gov.uk/") == []


# --- verification discipline ------------------------------------------------------------

def test_candidates_default_to_unverified(conn):
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, first_seen_vintage, "
        "last_seen_vintage, source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('E10000016','Kent','county','2020-01-01','x','x','u','t',200,'s','h')")
    conn.execute(
        "INSERT INTO cdp_document_candidates (authority_ons_code, candidate_url, title, "
        "document_type_guess, confidence, discovered_at, source_url, retrieved_at, http_status, "
        "source_system, payload_sha256) VALUES ('E10000016','https://x/y.pdf','T','cdp_strategy',"
        "0.75,'2026-01-01','u','t',200,'s','h')")
    row = conn.execute("SELECT * FROM cdp_document_candidates").fetchone()
    assert row["verified"] == 0
    assert row["rejected"] == 0


def test_cdp_documents_requires_a_confirmed_type(conn):
    """cdp_documents.document_type is NOT NULL — a promoted document has a
    confirmed type, never a guess.
    """
    info = {c[1]: c for c in conn.execute("PRAGMA table_info(cdp_documents)")}
    assert info["document_type"][3] == 1  # notnull


# --- review worklist ------------------------------------------------------------------------

def test_markdown_groups_by_region_and_warns_nothing_is_ingested():
    rows = [
        {"authority_name": "Kent", "region": "South East", "candidate_url": "https://x/a.pdf",
         "title": "CDP Strategy", "document_type_guess": "cdp_strategy", "confidence": 0.75},
        {"authority_name": "Barnsley", "region": "Yorkshire", "candidate_url": "https://y/b.pdf",
         "title": "Needs Assessment", "document_type_guess": "needs_assessment", "confidence": 0.5},
    ]
    md = cdp.render_candidates_markdown(rows)
    assert "## South East" in md
    assert "## Yorkshire" in md
    assert "None of it is in the evidence base yet" in md
    assert "triage aid, not a probability" in md


def test_markdown_handles_no_candidates():
    md = cdp.render_candidates_markdown([])
    assert "No candidates discovered" in md


# --- website registry -----------------------------------------------------------------------

def test_registry_contains_only_verified_entries():
    """Every entry must carry the date its URLs were confirmed to load, so an
    unverified guess cannot quietly sit in the registry.
    """
    for site in authority_websites.AUTHORITY_WEBSITES.values():
        assert site.base_url.startswith("https://")
        assert site.verified_on, f"{site.ons_code} has no verified_on date"


def test_website_for_returns_none_when_unconfigured():
    assert authority_websites.website_for("E99999999") is None
