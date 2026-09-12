"""The claims registry: writing, citing, deciding — and the refusals.

The rules themselves are the phase plan's own, and each is tested here as a
database fact rather than as behaviour of a particular route:

  * Nothing is computed — a claim is a statement linked to rows, and the
    linkage is a human judgement recorded like every other decision.
  * A claim without a recorded reviewer and decision history is not a claim:
    migration 0048's triggers refuse a decided claim without a
    claim_verifications row, on INSERT and on UPDATE.
  * A citation must resolve: a key that names nothing is refused at the
    door, the same refusal promotion makes for a dead link.
  * The lifecycle is draft → published/rejected, published → retracted, and
    anything back to draft by reset. A decided claim's text and citations
    are not editable underneath the decision.
"""
from __future__ import annotations

import pytest

from pipeline import census_verify, claims, db
from pipeline.claims import (
    CITABLE,
    ClaimError,
    build_key,
    citable_tables,
)


@pytest.fixture
def seed(conn):
    """A provider, a statutory pay rate and a verified census metric to cite."""
    conn.execute(
        "INSERT INTO providers (provider_key, canonical_name, is_target, notes) "
        "VALUES ('via', 'Via', 1, '')")
    conn.execute(
        "INSERT INTO statutory_pay_rates (period_label, band_label, band_role, "
        "amount, value_text, source_url, retrieved_at, http_status, source_system, "
        "payload_sha256) VALUES ('April 2026', '21 and over', "
        "'national_living_wage', 12.71, '12.71', 'https://gov.uk/rates', "
        "'2026-01-01T00:00:00Z', 200, 'm17', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')")
    conn.execute(
        "INSERT INTO workforce_census_reports (census_year, report_title, "
        "document_url, page_count, publisher, source_url, retrieved_at, "
        "http_status, source_system, payload_sha256) VALUES (2024, 'Census', "
        "'https://nhsbn.example/c.pdf', 60, 'NHSBN', "
        "'https://nhsbn.example/c.pdf', '2026-08-01T00:00:00Z', 200, "
        "'m06_workforce_census', 'cen123')")
    conn.execute(
        "INSERT INTO census_verifications (census_year, metric, "
        "workforce_segment, raw_text, decision, decided_by, decided_at) "
        "VALUES (2024, 'vacancy_rate', 'delivery', "
        "'8% vacancy rate in the delivery workforce', 'verified', 'Ruth', "
        "'2026-08-01T00:00:00Z')")
    conn.execute(
        "INSERT INTO workforce_census_metrics (census_year, metric, "
        "workforce_segment, value, unit, source_page, raw_text, verified, "
        "source_url, retrieved_at, http_status, source_system, "
        "payload_sha256) VALUES (2024, 'vacancy_rate', 'delivery', 8.0, "
        "'percent', 6, '8% vacancy rate in the delivery workforce', 1, "
        "'https://nhsbn.example/c.pdf', '2026-08-01T00:00:00Z', 200, "
        "'m06_workforce_census', 'cen123')")
    conn.commit()
    return conn


def rate_key():
    return build_key({"period_label": "April 2026", "band_label": "21 and over"},
                      ("period_label", "band_label"))


# --- writing -------------------------------------------------------------------


def test_a_claim_is_written_as_a_draft(conn):
    claim = claims.create(conn, "The sector's pay falls below the floor.",
                           "Jon", caveats="Not a pay scale.")

    assert claim["status"] == "draft"
    assert claim["created_by"] == "Jon"
    assert claim["caveats"] == "Not a pay scale."
    assert claim["citations"] == []
    assert claim["decisions"] == []


def test_a_claim_needs_text_and_an_author(conn):
    with pytest.raises(ClaimError, match="needs its text"):
        claims.create(conn, "  ", "Jon")
    with pytest.raises(ClaimError, match="attributed"):
        claims.create(conn, "A claim.", "")


def test_a_claim_cannot_be_born_decided(conn):
    """Migration 0048's INSERT trigger: nothing arrives with a status. The
    write path goes through create() which always drafts, and a direct insert
    is refused."""
    with pytest.raises(db.IntegrityError):
        conn.execute(
            "INSERT INTO claims (claim_text, status, created_by, created_at) "
            "VALUES ('born decided', 'published', 'Jon', '2026-08-01T00:00:00Z')")


def test_a_status_cannot_move_without_a_decision(conn):
    claim = claims.create(conn, "A claim.", "Jon")
    with pytest.raises(db.IntegrityError):
        # The SQL-box route: an UPDATE that skips the decision table. The
        # trigger refuses it.
        conn.execute("UPDATE claims SET status = 'published' WHERE id = %s",
                      (claim["id"],))


# --- citations -----------------------------------------------------------------


def test_citing_links_a_claim_to_an_evidence_row(conn, seed):
    claim = claims.create(conn, "The floor is £12.71.", "Jon")
    claim = claims.cite(conn, claim["id"], "statutory_pay_rates", rate_key(),
                         "Jon")

    assert len(claim["citations"]) == 1
    citation = claim["citations"][0]
    assert citation["evidence_table"] == "statutory_pay_rates"
    assert citation["evidence_key"] == rate_key()
    assert citation["cited_by"] == "Jon"


def test_a_citation_must_resolve(conn, seed):
    claim = claims.create(conn, "A claim.", "Jon")
    with pytest.raises(ClaimError, match="No citable row"):
        claims.cite(conn, claim["id"], "statutory_pay_rates", "nope\x1fnope",
                     "Jon")


def test_an_unknown_table_cannot_be_cited(conn, seed):
    claim = claims.create(conn, "A claim.", "Jon")
    with pytest.raises(ClaimError, match="not a citable evidence table"):
        claims.cite(conn, claim["id"], "contracts", "x", "Jon")


def test_the_same_row_is_not_cited_twice(conn, seed):
    claim = claims.create(conn, "A claim.", "Jon")
    claims.cite(conn, claim["id"], "statutory_pay_rates", rate_key(), "Jon")
    with pytest.raises(ClaimError, match="already cited"):
        claims.cite(conn, claim["id"], "statutory_pay_rates", rate_key(), "Jon")


def test_a_census_metric_is_cited_by_its_metric_key(conn, seed):
    row = conn.execute("SELECT * FROM workforce_census_metrics").fetchone()
    key = census_verify.metric_key(dict(row))

    claim = claims.create(conn, "Turnover is a problem.", "Jon")
    claim = claims.cite(conn, claim["id"], "workforce_census_metrics", key, "Jon")

    resolved = claims.resolve_citation(conn, "workforce_census_metrics", key)
    assert resolved is not None
    assert "vacancy_rate/delivery" in resolved["label"]


def test_every_document_table_resolves_its_own_columns(conn):
    """The three promoted-document tables carry different title columns
    (title, report_title, subject). Each resolver must read its own — a
    resolver written against another table's columns raises KeyError, which
    is how this test fails."""
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, region, active_from, "
        "first_seen_vintage, last_seen_vintage, source_url, retrieved_at, "
        "http_status, source_system, payload_sha256) "
        "VALUES ('E06000001', 'Hartlepool', 'UA', 'North East', '2023-04-01', "
        "'2023', '2024', 'u', 'now', 200, 'm00_geography', '0000000000000000000000000000000000000000000000000000000000000000')")
    conn.execute(
        "INSERT INTO evidence_promotions (candidate_table, candidate_url, "
        "target_table, target_key, promoted_by, promoted_at, "
        "candidate_context_json) VALUES ('cdp_document_candidates', 'u1', "
        "'cdp_documents', 'E06000001|https://d.example/1', 'Ruth', 'now', '{}')")
    conn.execute(
        "INSERT INTO cdp_documents (authority_ons_code, document_url, title, "
        "document_type, source_url, retrieved_at, http_status, source_system, "
        "payload_sha256) VALUES ('E06000001', 'https://d.example/1', "
        "'A strategy', 'strategy', 'https://d.example/1', '2026-01-01T00:00:00Z', "
        "200, 'cdp_document_promotion', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')")
    conn.execute(
        "INSERT INTO evidence_promotions (candidate_table, candidate_url, "
        "target_table, target_key, promoted_by, promoted_at, "
        "candidate_context_json) VALUES ('committee_paper_candidates', 'u2', "
        "'committee_papers', 'E06000001|https://p.example/1', 'Ruth', 'now', '{}')")
    conn.execute(
        "INSERT INTO committee_papers (authority_ons_code, document_url, "
        "committee_name, report_title, source_url, retrieved_at, http_status, "
        "source_system, payload_sha256) VALUES ('E06000001', "
        "'https://p.example/1', 'Cttee', 'A paper', 'https://p.example/1', "
        "'2026-01-01T00:00:00Z', 200, 'committee_paper_promotion', 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb')")
    conn.execute(
        "INSERT INTO evidence_promotions (candidate_table, candidate_url, "
        "target_table, target_key, promoted_by, promoted_at, "
        "candidate_context_json) VALUES ('foi_request_candidates', 'u3', "
        "'foi_requests', 'E06000001|https://w.example/1', 'Ruth', 'now', '{}')")
    conn.execute(
        "INSERT INTO foi_requests (ons_code, request_url, subject, status, "
        "source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('E06000001', 'https://w.example/1', 'A request', 'successful', "
        "'https://w.example/1', '2026-01-01T00:00:00Z', 200, "
        "'foi_request_promotion', 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc')")
    conn.commit()

    cases = [
        ("cdp_documents", "E06000001\x1fhttps://d.example/1", "A strategy"),
        ("committee_papers", "E06000001\x1fhttps://p.example/1", "A paper"),
        ("foi_requests", "E06000001\x1fhttps://w.example/1", "A request"),
    ]
    for table, key, expected in cases:
        resolved = claims.resolve_citation(conn, table, key)
        assert resolved is not None, table
        assert resolved["label"] == expected, table
        assert resolved["url"] == key.split("\x1f")[1], table


def test_unverified_census_metrics_are_not_citable(conn, seed):
    conn.execute(
        "INSERT INTO workforce_census_metrics (census_year, metric, "
        "workforce_segment, value, unit, source_page, raw_text, verified, "
        "source_url, retrieved_at, http_status, source_system, "
        "payload_sha256) VALUES (2024, 'turnover_rate', 'all', 19.0, "
        "'percent', 6, '19% turnover', 0, 'https://nhsbn.example/c.pdf', "
        "'2026-08-01T00:00:00Z', 200, 'm06', 'cen123')")
    conn.commit()

    hits = claims.search_citable(conn, "workforce_census_metrics", "turnover")
    assert hits == []


def test_a_citation_that_stops_resolving_is_reported_not_guessed(conn, seed):
    claim = claims.create(conn, "The floor.", "Jon")
    claims.cite(conn, claim["id"], "statutory_pay_rates", rate_key(), "Jon")
    # A module re-run replaces the row: same key, nothing behind it now.
    conn.execute("DELETE FROM statutory_pay_rates")
    conn.commit()

    assert claims.resolve_citation(conn, "statutory_pay_rates", rate_key()) is None


def test_the_citable_set_is_pinned(conn):
    """The registry a claim may cite. Adding a table is a deliberate act, and
    the portal must be able to resolve every table in it."""
    assert set(citable_tables()) == set(CITABLE)
    assert "contracts" not in CITABLE, (
        "contracts rows are not citable: a claim rests on verified rows, and "
        "the notice corpus has no human verification step")
    for table, spec in CITABLE.items():
        assert spec["key_columns"]
        assert spec["search_columns"]
        assert callable(spec["resolve"])


# --- deciding ------------------------------------------------------------------


def test_publishing_records_the_reviewer_first(conn, seed):
    claim = claims.create(conn, "A claim.", "Jon")
    claim = claims.cite(conn, claim["id"], "statutory_pay_rates", rate_key(),
                         "Jon")

    claim = claims.decide(conn, claim["id"], "published", "Ruth",
                           note="checked the rates page")

    assert claim["status"] == "published"
    decision = claim["decisions"][-1]
    assert decision["decision"] == "published"
    assert decision["decided_by"] == "Ruth"
    assert decision["note"] == "checked the rates page"


def test_a_claim_cannot_be_decided_anonymously(conn):
    claim = claims.create(conn, "A claim.", "Jon")
    with pytest.raises(ClaimError, match="attributed"):
        claims.decide(conn, claim["id"], "published", "")


def test_only_a_draft_can_be_published_or_rejected(conn):
    claim = claims.create(conn, "A claim.", "Jon")
    claims.decide(conn, claim["id"], "rejected", "Ruth")
    with pytest.raises(ClaimError, match="cannot be published"):
        claims.decide(conn, claim["id"], "published", "Ruth")


def test_only_a_published_claim_can_be_retracted(conn):
    claim = claims.create(conn, "A claim.", "Jon")
    with pytest.raises(ClaimError, match="cannot be retracted"):
        claims.decide(conn, claim["id"], "retracted", "Ruth")


def test_a_published_claim_can_be_retracted(conn):
    claim = claims.create(conn, "A claim.", "Jon")
    claim = claims.decide(conn, claim["id"], "published", "Ruth")
    claim = claims.decide(conn, claim["id"], "retracted", "Ruth",
                           note="evidence changed")

    assert claim["status"] == "retracted"
    assert [d["decision"] for d in claim["decisions"]] == ["published", "retracted"]


def test_decided_text_is_not_editable_underneath_the_decision(conn):
    claim = claims.create(conn, "Original text.", "Jon")
    claims.decide(conn, claim["id"], "published", "Ruth")

    with pytest.raises(ClaimError, match="Reset it before editing"):
        claims.update_text(conn, claim["id"], "Rewritten text.")


def test_reset_returns_a_claim_to_draft_and_keeps_decisions(conn):
    claim = claims.create(conn, "A claim.", "Jon")
    claim = claims.decide(conn, claim["id"], "published", "Ruth")

    claim = claims.reset(conn, claim["id"])

    assert claim["status"] == "draft"
    assert len(claim["decisions"]) == 1, "the judgement was still taken"


def test_reset_cannot_be_called_on_a_draft(conn):
    claim = claims.create(conn, "A claim.", "Jon")
    with pytest.raises(ClaimError, match="already a draft"):
        claims.reset(conn, claim["id"])


def test_decided_citations_are_not_editable_underneath_the_decision(conn, seed):
    claim = claims.create(conn, "A claim.", "Jon")
    claims.cite(conn, claim["id"], "statutory_pay_rates", rate_key(), "Jon")
    claims.decide(conn, claim["id"], "published", "Ruth")

    with pytest.raises(ClaimError, match="Reset it before changing"):
        claims.uncite(conn, claim["id"], "statutory_pay_rates", rate_key())


# --- the worklist --------------------------------------------------------------


def test_listing_is_newest_first_and_filters_by_status(conn):
    first = claims.create(conn, "First.", "Jon")
    claims.create(conn, "Second.", "Jon")
    claims.decide(conn, first["id"], "published", "Ruth")

    page = claims.listing(conn)
    assert page["total"] == 2
    assert [item["id"] for item in page["items"]] == [2, 1]

    published = claims.listing(conn, status="published")
    assert [item["id"] for item in published["items"]] == [1]


def test_an_unknown_status_is_refused(conn):
    with pytest.raises(ClaimError, match="unknown status"):
        claims.listing(conn, status="promoted")


def test_counts_and_history(conn):
    claim = claims.create(conn, "A claim.", "Jon")
    claims.decide(conn, claim["id"], "published", "Ruth")

    counts = claims.counts(conn)
    assert counts["draft"] == 0 and counts["published"] == 1
    assert counts["rejected"] == 0 and counts["retracted"] == 0
    assert counts["total"] == 1
    assert counts["decisions"][0]["decided_by"] == "Ruth"
    assert counts["decisions"][0]["claim_text"] == "A claim."
