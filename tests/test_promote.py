"""Candidates becoming evidence, and everything that must not.

This is the project's central refusal made operable, so most of these tests
are about what promotion will not do: promote without a person's name, without
confirming what the candidate only guessed, without the document answering, or
without leaving a record. The trigger tests matter most — they are what makes
"nothing reaches the evidence tables unpromoted" a property of the database
rather than a habit of the code above it.
"""
from __future__ import annotations

import json

import pytest

from pipeline import catalog, db, promote


@pytest.fixture
def seeded(conn):
    """One authority, and one candidate of each kind against it."""
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, "
        "first_seen_vintage, last_seen_vintage, source_url, retrieved_at, "
        "http_status, source_system, payload_sha256) VALUES "
        "('E10000016', 'Kent', 'CTY', '2013-04-01', '2024', '2024', "
        "'https://example.org/a', '2026-08-01T00:00:00Z', 200, 'ons', 'abc')")
    conn.execute(
        "INSERT INTO cdp_document_candidates (authority_ons_code, candidate_url, "
        "title, document_type_guess, confidence, discovered_at, discovery_method, "
        "verified, rejected, source_url, retrieved_at, http_status, source_system, "
        "payload_sha256) VALUES ('E10000016', 'https://kent.gov.uk/cdp.pdf', "
        "'Kent CDP strategy', 'strategy', 0.75, '2026-08-01T00:00:00Z', 'link', "
        "0, 0, 'https://kent.gov.uk/list', '2026-08-01T00:00:00Z', 200, 'm09', 'listing-hash')")
    conn.execute(
        "INSERT INTO committee_paper_candidates (authority_ons_code, document_url, "
        "committee_name, meeting_date, report_title, matched_terms, committee_system, "
        "verified, rejected, discovered_at, source_url, retrieved_at, http_status, "
        "source_system, payload_sha256) VALUES ('E10000016', "
        "'https://kent.gov.uk/paper.pdf', 'Health Committee', '2026-05-02', "
        "'Drug and alcohol treatment', 'drug and alcohol', 'moderngov', 0, 0, "
        "'2026-08-01T00:00:00Z', 'https://kent.gov.uk/search', '2026-08-01T00:00:00Z', "
        "200, 'm10', 'listing-hash')")
    conn.execute(
        "INSERT INTO foi_request_candidates (ons_code, candidate_url, title, "
        "matched_term, topic, discovered_at, discovery_source, verified, rejected, "
        "source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('E10000016', 'https://wdtk.com/request/1', 'Treatment budget', "
        "'drug treatment', 'budget', '2026-08-01T00:00:00Z', 'wdtk_feed_search', "
        "0, 0, 'https://wdtk.com/search', '2026-08-01T00:00:00Z', 200, 'm15', 'listing-hash')")
    conn.commit()
    return conn


@pytest.fixture
def document(httpx_mock):
    httpx_mock.add_response(url="https://kent.gov.uk/cdp.pdf",
                             content=b"%PDF-1.4 the actual strategy",
                             headers={"content-type": "application/pdf"})
    httpx_mock.add_response(url="https://kent.gov.uk/robots.txt", text="")
    return httpx_mock


# --- the guarantee -------------------------------------------------------------


def test_evidence_cannot_be_inserted_without_a_promotion(seeded):
    """The trigger. Not a convention the code above is trusted to follow."""
    with pytest.raises(db.IntegrityError, match="without a human"):
        seeded.execute(
            "INSERT INTO cdp_documents (authority_ons_code, document_url, "
            "document_type, source_url, retrieved_at, http_status, source_system, "
            "payload_sha256) VALUES ('E10000016', 'https://kent.gov.uk/sneaky.pdf', "
            "'strategy', 'https://kent.gov.uk/sneaky.pdf', '2026-08-01T00:00:00Z', "
            "200, 'manual', 'hash')")


@pytest.mark.parametrize("table, columns, values", [
    ("committee_papers",
     "authority_ons_code, document_url, source_url, retrieved_at, http_status, "
     "source_system, payload_sha256",
     "'E10000016', 'https://kent.gov.uk/x.pdf', 'u', '2026-08-01T00:00:00Z', 200, 'm', 'h'"),
    ("foi_requests",
     "ons_code, request_url, source_url, retrieved_at, http_status, "
     "source_system, payload_sha256",
     "'E10000016', 'https://wdtk.com/request/9', 'u', '2026-08-01T00:00:00Z', 200, 'm', 'h'"),
])
def test_every_evidence_table_is_guarded(seeded, table, columns, values):
    with pytest.raises(db.IntegrityError, match="without a human"):
        seeded.execute(f"INSERT INTO {table} ({columns}) VALUES ({values})")


def test_the_guard_is_satisfied_by_a_real_promotion(seeded, settings, document):
    promote.promote(seeded, "cdp_document", "https://kent.gov.uk/cdp.pdf",
                     promoted_by="Jon", fields={"document_type": "strategy"},
                     settings=settings)

    assert seeded.execute("SELECT COUNT(*) FROM cdp_documents").fetchone().values().__iter__().__next__() == 1


# --- what promotion refuses ----------------------------------------------------


def test_it_will_not_promote_anonymously(seeded, settings):
    with pytest.raises(promote.PromotionError, match="attributed"):
        promote.promote(seeded, "cdp_document", "https://kent.gov.uk/cdp.pdf",
                         promoted_by="   ", fields={"document_type": "strategy"},
                         settings=settings)


def test_it_will_not_guess_what_the_candidate_guessed(seeded, settings):
    """`document_type` is NOT NULL on the target and the schema says
    "confirmed, not guessed". The candidate's guess is not a confirmation."""
    with pytest.raises(promote.PromotionError, match="document_type"):
        promote.promote(seeded, "cdp_document", "https://kent.gov.uk/cdp.pdf",
                         promoted_by="Jon", fields={}, settings=settings)


def test_a_document_that_does_not_answer_is_not_promoted(seeded, settings, httpx_mock):
    httpx_mock.add_response(url="https://kent.gov.uk/robots.txt", text="")
    httpx_mock.add_response(url="https://kent.gov.uk/cdp.pdf", status_code=404)

    with pytest.raises(promote.PromotionError, match="404"):
        promote.promote(seeded, "cdp_document", "https://kent.gov.uk/cdp.pdf",
                         promoted_by="Jon", fields={"document_type": "strategy"},
                         settings=settings)

    assert seeded.execute("SELECT COUNT(*) FROM cdp_documents").fetchone().values().__iter__().__next__() == 0
    assert seeded.execute("SELECT COUNT(*) FROM evidence_promotions").fetchone().values().__iter__().__next__() == 0


def test_a_failed_fetch_leaves_nothing_behind(seeded, settings, httpx_mock):
    """403 rather than 500 deliberately: a 500 is retryable, and six attempts
    with backoff is a slow way to test a refusal that does not depend on it."""
    httpx_mock.add_response(url="https://kent.gov.uk/robots.txt", text="")
    httpx_mock.add_response(url="https://kent.gov.uk/cdp.pdf", status_code=403)

    with pytest.raises(promote.PromotionError):
        promote.promote(seeded, "cdp_document", "https://kent.gov.uk/cdp.pdf",
                         promoted_by="Jon", fields={"document_type": "strategy"},
                         settings=settings)

    assert seeded.execute(
        "SELECT verified FROM cdp_document_candidates").fetchone().values().__iter__().__next__() == 0


def test_an_unknown_candidate_is_refused(seeded, settings):
    with pytest.raises(promote.PromotionError, match="no cdp_document candidate"):
        promote.promote(seeded, "cdp_document", "https://kent.gov.uk/nope.pdf",
                         promoted_by="Jon", fields={"document_type": "strategy"},
                         settings=settings)


def test_an_unknown_kind_is_refused(seeded, settings):
    with pytest.raises(promote.PromotionError, match="unknown candidate kind"):
        promote.promote(seeded, "spreadsheets", "https://kent.gov.uk/cdp.pdf",
                         promoted_by="Jon", settings=settings)


def test_a_rejected_candidate_must_be_reset_first(seeded, settings):
    promote.reject(seeded, "cdp_document", ["https://kent.gov.uk/cdp.pdf"],
                    rejected_by="Jon")

    with pytest.raises(promote.PromotionError, match="was rejected"):
        promote.promote(seeded, "cdp_document", "https://kent.gov.uk/cdp.pdf",
                         promoted_by="Jon", fields={"document_type": "strategy"},
                         settings=settings)


# --- what a promotion records --------------------------------------------------


def test_the_evidence_carries_the_documents_own_provenance(seeded, settings, document):
    """Not the listing page's. This is the whole reason promotion fetches."""
    promote.promote(seeded, "cdp_document", "https://kent.gov.uk/cdp.pdf",
                     promoted_by="Jon", fields={"document_type": "strategy"},
                     settings=settings)

    row = seeded.execute(
        "SELECT source_url, payload_sha256, http_status, archived_path "
        "FROM cdp_documents").fetchone()

    assert row["source_url"] == "https://kent.gov.uk/cdp.pdf"
    assert row["payload_sha256"] != "listing-hash", (
        "the candidate's hash is of the page the link was found on")
    assert row["http_status"] == 200
    assert row["archived_path"], "the bytes are archived, which is what makes it citable"


def test_the_promotion_names_who_and_when(seeded, settings, document):
    result = promote.promote(
        seeded, "cdp_document", "https://kent.gov.uk/cdp.pdf",
        promoted_by="Jon", fields={"document_type": "strategy"},
        note="opened it, it is the 2024 strategy", settings=settings)

    row = seeded.execute("SELECT * FROM evidence_promotions").fetchone()

    assert row["promoted_by"] == "Jon"
    assert row["note"] == "opened it, it is the 2024 strategy"
    assert row["promoted_at"] == result["promoted_at"]
    assert row["target_key"] == "E10000016|https://kent.gov.uk/cdp.pdf"


def test_it_keeps_the_candidate_as_it_read_at_the_time(seeded, settings, document):
    """A later module run can refresh a candidate underneath a decision."""
    promote.promote(seeded, "cdp_document", "https://kent.gov.uk/cdp.pdf",
                     promoted_by="Jon", fields={"document_type": "strategy"},
                     settings=settings)

    context = json.loads(seeded.execute(
        "SELECT candidate_context_json FROM evidence_promotions").fetchone().values().__iter__().__next__())

    assert context["title"] == "Kent CDP strategy"
    assert context["confidence"] == 0.75


def test_the_confirmed_type_beats_the_guess(seeded, settings, document):
    promote.promote(seeded, "cdp_document", "https://kent.gov.uk/cdp.pdf",
                     promoted_by="Jon",
                     fields={"document_type": "needs_assessment"},
                     settings=settings)

    assert seeded.execute(
        "SELECT document_type FROM cdp_documents").fetchone().values().__iter__().__next__() == "needs_assessment"


def test_the_candidate_is_marked_verified(seeded, settings, document):
    promote.promote(seeded, "cdp_document", "https://kent.gov.uk/cdp.pdf",
                     promoted_by="Jon", fields={"document_type": "strategy"},
                     settings=settings)

    row = seeded.execute(
        "SELECT verified, verified_at FROM cdp_document_candidates").fetchone()
    assert row["verified"] == 1
    assert row["verified_at"]


def test_search_properties_do_not_travel_to_the_evidence(seeded, settings, httpx_mock):
    """`matched_terms` and `match_quality` describe the search that found a
    document, not the document. The evidence table has nowhere to put them and
    that is deliberate."""
    httpx_mock.add_response(url="https://kent.gov.uk/robots.txt", text="")
    httpx_mock.add_response(url="https://kent.gov.uk/paper.pdf", content=b"%PDF paper")

    promote.promote(seeded, "committee_paper", "https://kent.gov.uk/paper.pdf",
                     promoted_by="Jon", settings=settings)

    columns = {d["name"] for d in catalog.columns_of(seeded, "committee_papers")}
    assert "matched_terms" not in columns
    row = seeded.execute("SELECT committee_name, report_title FROM committee_papers").fetchone()
    assert row["committee_name"] == "Health Committee"


def test_an_foi_candidate_promotes_without_its_snippet(seeded, settings, httpx_mock):
    """A snippet is a search-engine extract, never a response. It must not
    become response_text."""
    httpx_mock.add_response(url="https://wdtk.com/robots.txt", text="")
    httpx_mock.add_response(url="https://wdtk.com/request/1", text="<html>request</html>")

    promote.promote(seeded, "foi_request", "https://wdtk.com/request/1",
                     promoted_by="Jon", settings=settings)

    row = seeded.execute("SELECT subject, response_text FROM foi_requests").fetchone()
    assert row["subject"] == "Treatment budget"
    assert row["response_text"] is None


# --- rejection and reset -------------------------------------------------------


def test_rejection_is_bulk_and_promotion_is_not(seeded, settings):
    """Rejecting says a link is not what it looked like, which is reachable
    from the listing. Promoting says it is, which needs the document open."""
    count = promote.reject(
        seeded, "committee_paper", ["https://kent.gov.uk/paper.pdf"],
        rejected_by="Jon", note="a COVID grant report")

    assert count == 1
    assert seeded.execute(
        "SELECT rejected FROM committee_paper_candidates").fetchone().values().__iter__().__next__() == 1
    assert not hasattr(promote, "promote_many")


def test_rejection_is_attributed_too(seeded):
    with pytest.raises(promote.PromotionError, match="attributed"):
        promote.reject(seeded, "cdp_document", ["https://kent.gov.uk/cdp.pdf"],
                        rejected_by="")


def test_rejecting_nothing_is_not_an_error(seeded):
    assert promote.reject(seeded, "cdp_document", [], rejected_by="Jon") == 0


def test_rejection_is_quarantined_with_its_reason(seeded):
    """A rejected candidate becomes listable/retryable the same way parse
    failures and archive mismatches are (migration 0103), not just a flag on
    the candidate row that carries no reason."""
    promote.reject(
        seeded, "committee_paper", ["https://kent.gov.uk/paper.pdf"],
        rejected_by="Jon", note="a COVID grant report")

    row = seeded.execute(
        "SELECT kind, module, item_identity, reason, payload_json, retry_state "
        "FROM quarantine_items WHERE item_identity = %s",
        ("https://kent.gov.uk/paper.pdf",)).fetchone()
    assert row["kind"] == "rejected_candidate"
    assert row["module"] == "committee_paper_promotion"
    assert row["reason"] == "a COVID grant report"
    assert row["payload_json"]["rejected_by"] == "Jon"
    assert row["retry_state"] == "pending"


def test_reset_does_not_delete_evidence(seeded, settings, document):
    """Evidence has its own provenance and its own promotion record. Undoing a
    judgement about a candidate is not the same act as deleting a document."""
    promote.promote(seeded, "cdp_document", "https://kent.gov.uk/cdp.pdf",
                     promoted_by="Jon", fields={"document_type": "strategy"},
                     settings=settings)
    promote.reset(seeded, "cdp_document", "https://kent.gov.uk/cdp.pdf")

    assert seeded.execute("SELECT COUNT(*) FROM cdp_documents").fetchone().values().__iter__().__next__() == 1
    assert seeded.execute(
        "SELECT verified FROM cdp_document_candidates").fetchone().values().__iter__().__next__() == 0


def test_history_is_newest_first(seeded, settings, httpx_mock):
    # Reusable: a client is built per promotion, each with its own robots
    # cache, so two promotions against one host ask for robots.txt twice.
    # Redundant rather than impolite — the rate limit is process-wide.
    httpx_mock.add_response(url="https://kent.gov.uk/robots.txt", text="",
                             is_reusable=True)
    httpx_mock.add_response(url="https://kent.gov.uk/cdp.pdf", content=b"%PDF a")
    httpx_mock.add_response(url="https://kent.gov.uk/paper.pdf", content=b"%PDF b")

    promote.promote(seeded, "cdp_document", "https://kent.gov.uk/cdp.pdf",
                     promoted_by="Jon", fields={"document_type": "strategy"},
                     settings=settings)
    promote.promote(seeded, "committee_paper", "https://kent.gov.uk/paper.pdf",
                     promoted_by="Sam", settings=settings)

    entries = promote.history(seeded)
    assert [e["promoted_by"] for e in entries] == ["Sam", "Jon"]


def test_promoted_urls_lets_a_list_say_so(seeded, settings, document):
    assert promote.promoted_urls(seeded, "cdp_document") == set()

    promote.promote(seeded, "cdp_document", "https://kent.gov.uk/cdp.pdf",
                     promoted_by="Jon", fields={"document_type": "strategy"},
                     settings=settings)

    assert promote.promoted_urls(seeded, "cdp_document") == {
        "https://kent.gov.uk/cdp.pdf"}


# --- putting back what a re-run took (issue #2) ---------------------------------


def test_a_rerun_no_longer_un_promotes_a_candidate(seeded, settings, document):
    """The bug itself, at the level the module writes: re-upserting a promoted
    candidate with the collection defaults must leave the decision standing.
    """
    from pipeline import db

    promote.promote(seeded, "cdp_document", "https://kent.gov.uk/cdp.pdf",
                     promoted_by="Jon", fields={"document_type": "strategy"},
                     settings=settings)

    db.upsert(seeded, "cdp_document_candidates", {
        "authority_ons_code": "E10000016",
        "candidate_url": "https://kent.gov.uk/cdp.pdf",
        "title": "Kent CDP strategy",
        "discovered_at": "2026-09-01T00:00:00Z",
        "verified": 0, "verified_at": None, "rejected": 0,
        "source_url": "https://kent.gov.uk/list",
        "retrieved_at": "2026-09-01T00:00:00Z",
        "http_status": 200, "source_system": "m09", "payload_sha256": "second-run",
    }, natural_key=["authority_ons_code", "candidate_url"],
        preserve=db.DECISION_COLUMNS)

    row = seeded.execute("SELECT * FROM cdp_document_candidates").fetchone()
    assert row["verified"] == 1
    assert row["verified_at"] is not None
    # The re-observation is still recorded — only the decision is protected.
    assert row["payload_sha256"] == "second-run"
    assert promote.promotions_without_flag(seeded) == []


def test_a_flag_a_rerun_already_cleared_is_reported(seeded, settings, document):
    promote.promote(seeded, "cdp_document", "https://kent.gov.uk/cdp.pdf",
                     promoted_by="Jon", fields={"document_type": "strategy"},
                     settings=settings)
    seeded.execute("UPDATE cdp_document_candidates SET verified = 0, verified_at = NULL")

    found = promote.promotions_without_flag(seeded)
    assert [row["kind"] for row in found] == ["cdp_document"]
    assert found[0]["url"] == "https://kent.gov.uk/cdp.pdf"
    assert found[0]["promotions"] == 1


def test_restore_flags_reports_before_it_writes(seeded, settings, document):
    promote.promote(seeded, "cdp_document", "https://kent.gov.uk/cdp.pdf",
                     promoted_by="Jon", fields={"document_type": "strategy"},
                     settings=settings)
    seeded.execute("UPDATE cdp_document_candidates SET verified = 0, verified_at = NULL")

    assert len(promote.restore_flags(seeded, dry_run=True)) == 1
    assert seeded.execute(
        "SELECT verified FROM cdp_document_candidates").fetchone().values().__iter__().__next__() == 0

    restored = promote.restore_flags(seeded)
    row = seeded.execute("SELECT * FROM cdp_document_candidates").fetchone()
    assert row["verified"] == 1
    # Restored to what the flag said, not re-decided today.
    assert row["verified_at"] == restored[0]["promoted_at"]
    assert promote.restore_flags(seeded) == []


def test_restore_flags_leaves_a_rejection_alone(seeded, settings, document):
    """A rejection is a later statement than the promotion it contradicts.
    Worth a look; not worth overwriting from a repair command.
    """
    promote.promote(seeded, "cdp_document", "https://kent.gov.uk/cdp.pdf",
                     promoted_by="Jon", fields={"document_type": "strategy"},
                     settings=settings)
    promote.reject(seeded, "cdp_document", ["https://kent.gov.uk/cdp.pdf"],
                    rejected_by="Sam")

    assert promote.restore_flags(seeded) == []
    row = seeded.execute("SELECT * FROM cdp_document_candidates").fetchone()
    assert (row["verified"], row["rejected"]) == (0, 1)


# --- companies_house_accounts (JON-36) ------------------------------------------
#
# The fourth kind: a filing m04_companies's filing-history stream tagged
# 'accounts' is a pointer nobody has opened, promoted the same way as the
# three kinds above -- except the fetch itself is a two-step Document API
# negotiation (metadata, then content) rather than a single client.get(url).

METADATA_URL = "https://document-api.company-information.service.gov.uk/document/abc"
CONTENT_URL = "https://document-api.company-information.service.gov.uk/document/abc/content"


@pytest.fixture
def ch_accounts_seeded(conn):
    """A tracked company and one companies_house_accounts candidate against it."""
    conn.execute(
        "INSERT INTO companies (company_number, company_name, match_basis, "
        "source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('03861209', 'CHANGE, GROW, LIVE', 'seed', 'https://x', "
        "'2026-08-01T00:00:00Z', 200, 'companies_house', 'x')")
    conn.execute(
        "INSERT INTO companies_house_accounts_candidates (company_number, candidate_url, "
        "transaction_id, filing_date, description, accounts_type, discovered_at, "
        "discovery_method, verified, rejected, source_url, retrieved_at, http_status, "
        "source_system, payload_sha256) VALUES ('03861209', %s, "
        "'t1', '2025-06-01', 'Accounts', 'accounts-with-accounts-type-group', "
        "'2026-08-01T00:00:00Z', 'filing_history_stream', 0, 0, "
        "'https://api.company-information.service.gov.uk/company/03861209/filing-history/t1', "
        "'2026-08-01T00:00:00Z', 200, 'companies_house_filed_accounts', 'identity-hash')",
        (METADATA_URL,))
    conn.commit()
    return conn


def _allow_document_api_robots(httpx_mock) -> None:
    httpx_mock.add_response(
        url="https://document-api.company-information.service.gov.uk/robots.txt",
        text="", is_reusable=True)


def test_promote_companies_house_accounts_fetches_metadata_then_negotiates_content(
        ch_accounts_seeded, settings, httpx_mock):
    _allow_document_api_robots(httpx_mock)
    httpx_mock.add_response(
        url=METADATA_URL,
        json={"links": {"document": CONTENT_URL},
              "resources": {"application/pdf": {"content_length": 1234}}})
    httpx_mock.add_response(
        url=CONTENT_URL, content=b"%PDF-1.4 accounts",
        headers={"content-type": "application/pdf"})

    promote.promote(ch_accounts_seeded, "companies_house_accounts", METADATA_URL,
                     promoted_by="Jon", settings=settings)

    row = ch_accounts_seeded.execute("SELECT * FROM companies_house_accounts_documents").fetchone()
    # document_url is the stable metadata URL a human reviewed; source_url is
    # the actual content fetched, after content negotiation.
    assert row["document_url"] == METADATA_URL
    assert row["source_url"] == CONTENT_URL
    assert row["content_type"] == "application/pdf"
    assert row["archived_path"]
    assert row["description"] == "Accounts"
    assert row["accounts_type"] == "accounts-with-accounts-type-group"


def test_promote_companies_house_accounts_falls_back_to_ixbrl_when_pdf_is_not_offered(
        ch_accounts_seeded, settings, httpx_mock):
    _allow_document_api_robots(httpx_mock)
    httpx_mock.add_response(
        url=METADATA_URL,
        json={"links": {"document": CONTENT_URL},
              "resources": {"application/xhtml+xml": {"content_length": 999}}})
    httpx_mock.add_response(
        url=CONTENT_URL, content=b"<html>ixbrl accounts</html>",
        headers={"content-type": "application/xhtml+xml"},
        match_headers={"Accept": "application/xhtml+xml"})

    promote.promote(ch_accounts_seeded, "companies_house_accounts", METADATA_URL,
                     promoted_by="Jon", settings=settings)

    row = ch_accounts_seeded.execute(
        "SELECT content_type FROM companies_house_accounts_documents").fetchone()
    assert row["content_type"] == "application/xhtml+xml"


def test_promote_companies_house_accounts_refuses_without_links_document(
        ch_accounts_seeded, settings, httpx_mock):
    _allow_document_api_robots(httpx_mock)
    httpx_mock.add_response(url=METADATA_URL, json={"resources": {}})

    with pytest.raises(promote.PromotionError, match="links.document"):
        promote.promote(ch_accounts_seeded, "companies_house_accounts", METADATA_URL,
                         promoted_by="Jon", settings=settings)

    assert ch_accounts_seeded.execute(
        "SELECT COUNT(*) FROM companies_house_accounts_documents"
    ).fetchone().values().__iter__().__next__() == 0


def test_companies_house_accounts_evidence_table_is_guarded(ch_accounts_seeded):
    """The fourth trigger, alongside the three in test_evidence_cannot_be_inserted_
    without_a_promotion / test_every_evidence_table_is_guarded above."""
    with pytest.raises(db.IntegrityError, match="without a human"):
        ch_accounts_seeded.execute(
            "INSERT INTO companies_house_accounts_documents (company_number, document_url, "
            "source_url, retrieved_at, http_status, source_system, payload_sha256) VALUES "
            "('03861209', "
            "'https://document-api.company-information.service.gov.uk/document/sneaky', "
            "'u', '2026-08-01T00:00:00Z', 200, 'manual', 'hash')")
