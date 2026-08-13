"""Module 10, including the ModernGov search that used to be a "known
limitation".

The limitation was self-inflicted twice over, and both faults are pinned here
as regression tests because both produced the same symptom — a council that
looked like it published nothing about drug and alcohol services:

  1. The wrong endpoint. /mgSearchResults.aspx and /mgDocumentSearch.aspx 302
     to mgError.aspx on every ModernGov instance. The document search is
     /ieSearchResults2.aspx, and it answers a plain GET; the "needs a POST
     with ASP.NET viewstate" note was inferred from two failing requests
     rather than read off the form, which has no viewstate field at all.

  2. The wrong parser. ModernGov hits are links to agenda items and issue
     histories, not to .pdf files, so a document-extension filter discarded
     every genuine result.

Parsing is asserted against pages captured from three live councils rather
than hand-written HTML, because hand-written HTML is where the first version
of this went wrong: it tested the markup somebody expected instead of the
markup ModernGov serves.
"""
from __future__ import annotations

import re
from pathlib import Path

from pipeline.keywords import COMMITTEE_SEARCH_TERMS
from pipeline.modules import m10_committee_papers as cp

FIXTURES = Path(__file__).resolve().parent / "fixtures"
KENT = (FIXTURES / "moderngov_search_kent_substance_misuse.html").read_text(encoding="utf-8")
KIRKLEES = (FIXTURES / "moderngov_search_kirklees_drug_and_alcohol.html").read_text(encoding="utf-8")
NO_RESULTS = (FIXTURES / "moderngov_search_no_results.html").read_text(encoding="utf-8")
SEARCH_FORM = (FIXTURES / "moderngov_doc_search_form.html").read_text(encoding="utf-8")

KENT_URL = "https://democracy.kent.gov.uk/ieSearchResults2.aspx?SS=substance%20misuse&PG=1"
KIRKLEES_URL = "https://democracy.kirklees.gov.uk/ieSearchResults2.aspx?SS=drug%20and%20alcohol&PG=1"


# --- system detection ------------------------------------------------------------

def test_detects_moderngov_from_its_signature_path():
    system, signature = cp.detect_committee_system(lambda p: p == "/mgWhatsNew.aspx")
    assert system == "moderngov"
    assert signature == "/mgWhatsNew.aspx"


def test_detects_cmis_from_its_signature_path():
    system, _ = cp.detect_committee_system(lambda p: "CMIS5" in p)
    assert system == "cmis"


def test_unknown_system_is_a_recorded_answer_not_a_guess():
    """Nothing matching must yield 'unknown', which routes the authority to
    the null adapter — never a default like 'moderngov'.
    """
    system, signature = cp.detect_committee_system(lambda p: False)
    assert system == "unknown"
    assert signature is None


# --- search URL -----------------------------------------------------------------------

def test_search_url_targets_the_endpoint_that_actually_answers():
    url = cp.build_moderngov_search_url("https://democracy.kent.gov.uk", "drug and alcohol")
    assert url.startswith("https://democracy.kent.gov.uk/ieSearchResults2.aspx?")
    assert "SS=drug%20and%20alcohol" in url
    assert "PG=1" in url


def test_search_url_is_not_the_endpoint_that_redirects_to_an_error_page():
    """Regression guard. /mgSearchResults.aspx returns 302 -> mgError.aspx on
    every instance tested, which is what made this module look like it had
    searched and found nothing.
    """
    url = cp.build_moderngov_search_url("https://democracy.kent.gov.uk", "TUPE")
    assert "mgSearchResults.aspx" not in url
    assert "mgDocumentSearch.aspx" not in url


def test_the_search_form_carries_no_viewstate():
    """Pinned against the real form: the reason this module does not post one."""
    assert "__VIEWSTATE" not in SEARCH_FORM
    assert "__EVENTVALIDATION" not in SEARCH_FORM


def test_search_url_parameters_match_the_forms_own_defaults():
    url = cp.build_moderngov_search_url("https://x.gov.uk", "TUPE")
    for expected in ("DT=3", "ADV=0", "CA=false", "SB=true"):
        assert expected in url


def test_search_url_tolerates_a_trailing_slash():
    assert (cp.build_moderngov_search_url("https://x.gov.uk", "TUPE")
            == cp.build_moderngov_search_url("https://x.gov.uk/", "TUPE"))


def test_search_url_keeps_a_subdirectory_mount():
    """Some councils mount ModernGov under a path rather than a subdomain."""
    url = cp.build_moderngov_search_url("https://www.x.gov.uk/moderngov", "TUPE")
    assert url.startswith("https://www.x.gov.uk/moderngov/ieSearchResults2.aspx")


def test_paging_asks_for_the_requested_page():
    assert "PG=3" in cp.build_moderngov_search_url("https://x.gov.uk", "TUPE", page=3)


# --- results parsing, against real pages -------------------------------------------------

def test_finds_the_hits_a_document_extension_filter_threw_away():
    """The original parser kept only .pdf/.doc links and so returned nothing
    from this exact page.
    """
    rows = cp.parse_moderngov_results(KENT, KENT_URL, "substance misuse")
    assert len(rows) == 10
    assert not any(r["document_url"].endswith(".pdf") for r in rows)
    assert all("democracy.kent.gov.uk" in r["document_url"] for r in rows)


def test_reads_a_key_issue_hit():
    rows = cp.parse_moderngov_results(KENT, KENT_URL, "substance misuse")
    issues = [r for r in rows if r["result_type"] == "key_issue"]
    assert issues
    assert any("Substance Misuse" in (r["report_title"] or "") for r in issues)
    assert all("mgIssueHistoryHome.aspx" in r["document_url"] for r in issues)


def test_kent_and_kirklees_label_the_same_thing_differently():
    """Kent prints "Issue:" and Kirklees prints "Key issue:". Both normalise
    to key_issue, or the two councils' evidence would not be comparable.
    """
    assert cp._classify("Issue", "Some issue") == "key_issue"
    assert cp._classify("Key issue", "Some issue") == "key_issue"


def test_an_unfamiliar_label_is_kept_rather_than_flattened():
    """A record type this pipeline has not seen is worth noticing, not
    discarding into 'other'.
    """
    assert cp._classify("Petition", "A petition") == "petition"


def test_an_item_number_is_not_mistaken_for_a_record_type():
    assert cp._classify("183.", "20/01/2022 - Some Committee") == "meeting"
    assert cp._classify("Item5", "20/01/2022 - Some Committee") == "meeting"


def test_reads_an_agenda_item_with_its_meeting_context():
    rows = cp.parse_moderngov_results(KIRKLEES, KIRKLEES_URL, "drug and alcohol")
    item = next(r for r in rows
                 if r["agenda_item_title"] == "Re-Commissioning of Alcohol and Drug Services")
    assert item["result_type"] == "agenda_item"
    assert item["committee_name"] == \
        "Safer Stronger Communities Executive (Community Safety Partnership)"
    assert item["meeting_date"] == "2015-09-17"
    assert item["item_reference"] == "Item5"
    assert item["document_url"].endswith("ieListDocuments.aspx?CId=133&MID=377#AI1551")


def test_the_agenda_item_wins_over_the_meeting_that_contains_it():
    """The meeting URL is the item URL's prefix, so emitting both would give a
    reviewer two rows and make them find the item by hand in one of them.
    """
    rows = cp.parse_moderngov_results(KIRKLEES, KIRKLEES_URL, "drug and alcohol")
    urls = {r["document_url"] for r in rows}
    assert "https://democracy.kirklees.gov.uk/ieListDocuments.aspx?CId=133&MID=377#AI1551" in urls
    assert "https://democracy.kirklees.gov.uk/ieListDocuments.aspx?CId=133&MID=377" not in urls


def test_meeting_dates_are_reformatted_not_inferred():
    assert cp._iso_date("17/09/2015") == "2015-09-17"
    assert cp._iso_date("08/02/2011") == "2011-02-08"


def test_a_date_that_does_not_parse_is_none_rather_than_a_guess():
    for value in ("sometime in 2015", "2015-09-17x", "", None, "31/02/2020"):
        assert cp._iso_date(value) is None


def test_a_heading_with_a_time_still_yields_the_date():
    rows = cp.parse_moderngov_results(KIRKLEES, KIRKLEES_URL, "drug and alcohol")
    timed = [r for r in rows if r["committee_name"] == "Safer Stronger Communities Partnership Board"]
    assert timed
    assert timed[0]["meeting_date"] == "2011-02-08"


def test_the_match_count_suffix_is_not_part_of_the_title():
    rows = cp.parse_moderngov_results(KIRKLEES, KIRKLEES_URL, "drug and alcohol")
    assert not any(re.search(r"\(\d+\)$", r["report_title"] or "") for r in rows)


def test_records_the_sources_own_match_quality():
    """ModernGov ranks its own hits. Recording that is recording what the
    source says; scoring them ourselves would not be.
    """
    rows = cp.parse_moderngov_results(KENT, KENT_URL, "substance misuse")
    assert {r["match_quality"] for r in rows} <= {"excellent", "good", "average", None}
    assert any(r["match_quality"] == "excellent" for r in rows)


def test_carries_the_matched_text_for_the_reviewer():
    rows = cp.parse_moderngov_results(KENT, KENT_URL, "substance misuse")
    assert any(r["snippet"] for r in rows)


def test_records_which_term_found_the_hit():
    rows = cp.parse_moderngov_results(KENT, KENT_URL, "recommissioning")
    assert {r["matched_term"] for r in rows} == {"recommissioning"}


def test_no_duplicate_urls_within_a_page():
    rows = cp.parse_moderngov_results(KIRKLEES, KIRKLEES_URL, "drug and alcohol")
    urls = [r["document_url"] for r in rows]
    assert len(urls) == len(set(urls))


def test_parse_empty_html():
    assert cp.parse_moderngov_results("", "https://x.gov.uk/y", "t") == []


# --- knowing the difference between empty and broken -----------------------------------

def test_no_results_page_is_recognised_as_an_answer():
    """"Searched and found nothing" and "could not search" must not look the
    same, and ModernGov says which it is.
    """
    assert cp.has_no_results(NO_RESULTS) is True
    assert cp.parse_moderngov_results(NO_RESULTS, KENT_URL, "zzq") == []


def test_a_page_with_hits_is_not_a_no_results_page():
    assert cp.has_no_results(KENT) is False


def test_pagination_is_followed_from_the_pages_own_link():
    following = cp.next_result_page_url(KENT, KENT_URL)
    assert following is not None
    assert "PG=2" in following
    assert following.startswith("https://democracy.kent.gov.uk/")


def test_no_next_page_on_a_no_results_page():
    assert cp.next_result_page_url(NO_RESULTS, KENT_URL) is None


# --- one row per document, all the terms that found it -------------------------------------

def test_terms_accumulate_rather_than_overwriting_each_other(conn):
    """A Darlington scrutiny paper matches both 'drug and alcohol' and
    'treatment and recovery'. Keyed on the URL, the second term used to
    overwrite the first, discarding the agreement invisibly.
    """
    _seed_authority(conn)
    assert cp.merge_matched_terms(conn, "E10000016", "https://x/y", "drug and alcohol") \
        == "drug and alcohol"

    conn.execute(
        "INSERT INTO committee_paper_candidates (authority_ons_code, document_url, "
        "matched_terms, discovered_at, source_url, retrieved_at, http_status, source_system, "
        "payload_sha256) VALUES ('E10000016','https://x/y','drug and alcohol','2026-01-01',"
        "'u','t',200,'s','h')")

    assert cp.merge_matched_terms(conn, "E10000016", "https://x/y", "treatment and recovery") \
        == "drug and alcohol, treatment and recovery"


def test_reseeing_the_same_term_does_not_duplicate_it(conn):
    _seed_authority(conn)
    conn.execute(
        "INSERT INTO committee_paper_candidates (authority_ons_code, document_url, "
        "matched_terms, discovered_at, source_url, retrieved_at, http_status, source_system, "
        "payload_sha256) VALUES ('E10000016','https://x/y','TUPE, drug and alcohol',"
        "'2026-01-01','u','t',200,'s','h')")
    assert cp.merge_matched_terms(conn, "E10000016", "https://x/y", "TUPE") \
        == "TUPE, drug and alcohol"


def test_accumulated_terms_are_sorted_so_reruns_are_stable(conn):
    _seed_authority(conn)
    conn.execute(
        "INSERT INTO committee_paper_candidates (authority_ons_code, document_url, "
        "matched_terms, discovered_at, source_url, retrieved_at, http_status, source_system, "
        "payload_sha256) VALUES ('E10000016','https://x/y','TUPE','2026-01-01','u','t',"
        "200,'s','h')")
    assert cp.merge_matched_terms(conn, "E10000016", "https://x/y", "recommissioning") \
        == "TUPE, recommissioning"


def test_a_document_found_by_two_terms_is_one_candidate_row(
        conn, settings, httpx_mock, monkeypatch):
    _seed_authority(conn)
    _register_kent(monkeypatch)
    # The same results page for every term, so every term finds every document.
    _mock_moderngov(httpx_mock, KIRKLEES)

    _run(conn, settings)

    urls = [r["document_url"] for r in conn.execute(
        "SELECT document_url FROM committee_paper_candidates")]
    assert len(urls) == len(set(urls))
    terms = conn.execute(
        "SELECT matched_terms FROM committee_paper_candidates LIMIT 1").fetchone()["matched_terms"]
    assert ", " in terms, "a document found by every term should list every term"


# --- committee URL discovery ---------------------------------------------------------------

def test_finds_a_committee_link_a_council_publishes():
    html = ('<a href="/services">Services</a>'
            '<a href="https://democracy.example.gov.uk/ieDocHome.aspx?bcr=1">Committee papers</a>')
    assert cp.committee_links_on_page(html, "https://www.example.gov.uk/") == \
        ["https://democracy.example.gov.uk"]


def test_keeps_a_subdirectory_mount_when_discovering():
    html = '<a href="https://www.x.gov.uk/moderngov/mgWhatsNew.aspx">Meetings</a>'
    assert cp.committee_links_on_page(html, "https://www.x.gov.uk/") == \
        ["https://www.x.gov.uk/moderngov"]


def test_discovery_ignores_ordinary_council_links():
    html = '<a href="/bins">Bins</a><a href="/council-tax">Council tax</a>'
    assert cp.committee_links_on_page(html, "https://www.x.gov.uk/") == []


def test_discovery_deduplicates_a_repeated_system():
    html = ('<a href="https://d.x.gov.uk/mgWhatsNew.aspx">A</a>'
            '<a href="https://d.x.gov.uk/ieDocHome.aspx">B</a>')
    assert cp.committee_links_on_page(html, "https://www.x.gov.uk/") == ["https://d.x.gov.uk"]


def test_discovery_rejects_a_non_http_scheme():
    html = '<a href="javascript:void(mgWhatsNew.aspx)">x</a>'
    assert cp.committee_links_on_page(html, "https://www.x.gov.uk/") == []


# --- search terms -------------------------------------------------------------------------

def test_search_terms_come_from_config():
    for term in ("drug and alcohol", "substance misuse", "TUPE", "public health grant"):
        assert term in COMMITTEE_SEARCH_TERMS


# --- verification discipline ------------------------------------------------------------------

def _seed_authority(conn):
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, first_seen_vintage, "
        "last_seen_vintage, source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('E10000016','Kent','county','2020-01-01','x','x','u','t',200,'s','h')")


def _register_kent(monkeypatch, committee_url="https://democracy.example.gov.uk"):
    from pipeline import authority_websites

    monkeypatch.setitem(
        authority_websites.AUTHORITY_WEBSITES, "E10000016",
        authority_websites.AuthorityWebsite(
            ons_code="E10000016", name="Kent", base_url="https://x.gov.uk",
            committee_url=committee_url, committee_system="moderngov",
            verified_on="2026-01-01"))


def _mock_moderngov(httpx_mock, search_body: str, status_code: int = 200):
    httpx_mock.add_response(url="https://democracy.example.gov.uk/robots.txt",
                             status_code=404, text="", is_reusable=True)
    httpx_mock.add_response(url="https://democracy.example.gov.uk/mgWhatsNew.aspx",
                             text="<html>ok</html>", is_reusable=True)
    httpx_mock.add_response(url=re.compile(r".*ieSearchResults2\.aspx.*"),
                             status_code=status_code, text=search_body, is_reusable=True)


def _run(conn, settings):
    from pipeline.registry import ModuleContext

    cp.run(ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None))


def test_candidates_default_to_unverified(conn):
    _seed_authority(conn)
    conn.execute(
        "INSERT INTO committee_paper_candidates (authority_ons_code, document_url, report_title, "
        "matched_terms, discovered_at, source_url, retrieved_at, http_status, source_system, "
        "payload_sha256) VALUES ('E10000016','https://x/y.pdf','T','TUPE','2026-01-01','u','t',"
        "200,'s','h')")
    row = conn.execute("SELECT * FROM committee_paper_candidates").fetchone()
    assert row["verified"] == 0
    assert row["rejected"] == 0


def test_committee_papers_starts_empty(conn):
    """A search hit means a title or a paragraph matched a phrase — "TUPE" and
    "public health grant" appear in plenty of unrelated papers — so nothing is
    promoted without confirmation.
    """
    assert conn.execute("SELECT COUNT(*) c FROM committee_papers").fetchone()["c"] == 0


def test_a_live_search_writes_unverified_candidates(conn, settings, httpx_mock, monkeypatch):
    _seed_authority(conn)
    _register_kent(monkeypatch)
    _mock_moderngov(httpx_mock, KIRKLEES)

    _run(conn, settings)

    assert conn.execute(
        "SELECT committee_system FROM authority_committee_systems"
    ).fetchone()["committee_system"] == "moderngov"
    rows = conn.execute("SELECT * FROM committee_paper_candidates").fetchall()
    assert rows
    assert all(r["verified"] == 0 and r["rejected"] == 0 for r in rows)
    assert all(r["source_url"] and r["retrieved_at"] and r["payload_sha256"] for r in rows)
    assert conn.execute("SELECT COUNT(*) c FROM committee_papers").fetchone()["c"] == 0


def test_the_matched_text_goes_only_to_the_restricted_table(conn, settings, httpx_mock, monkeypatch):
    """ModernGov's snippets name officers in post ("Presented by <name>, Head
    of Health Improvement"). The candidates table is exportable; this is not.
    """
    _seed_authority(conn)
    _register_kent(monkeypatch)
    _mock_moderngov(httpx_mock, KIRKLEES)

    _run(conn, settings)

    snippets = conn.execute(
        "SELECT snippet_text FROM restricted_committee_result_snippets").fetchall()
    assert snippets
    assert any("Presented by" in (s["snippet_text"] or "") for s in snippets)

    columns = {r["name"] for r in conn.execute("PRAGMA table_info(committee_paper_candidates)")}
    assert "snippet" not in columns and "snippet_text" not in columns


def test_a_blocked_search_is_recorded_not_read_as_an_empty_council(
        conn, settings, httpx_mock, monkeypatch):
    """Several councils sit behind bot protection that answers 403. A blocked
    council must not be indistinguishable from one with nothing to find.
    """
    _seed_authority(conn)
    _register_kent(monkeypatch)
    _mock_moderngov(httpx_mock, "", status_code=403)

    _run(conn, settings)

    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue WHERE item_type='committee_search_blocked'"
    ).fetchone()["c"] >= 1
    assert conn.execute(
        "SELECT COUNT(*) c FROM committee_paper_candidates").fetchone()["c"] == 0


def test_a_genuinely_empty_search_is_recorded_as_such(conn, settings, httpx_mock, monkeypatch):
    _seed_authority(conn)
    _register_kent(monkeypatch)
    _mock_moderngov(httpx_mock, NO_RESULTS)

    _run(conn, settings)

    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue WHERE item_type='committee_search_no_matches'"
    ).fetchone()["c"] == 1
    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue WHERE item_type='committee_search_blocked'"
    ).fetchone()["c"] == 0


def test_an_unrecognised_results_page_is_flagged(conn, settings, httpx_mock, monkeypatch):
    """The failure this module is most exposed to is ModernGov changing its
    markup. Neither hits nor a "no results" message means the adapter no
    longer understands the page — which must not read as an empty council.
    """
    _seed_authority(conn)
    _register_kent(monkeypatch)
    _mock_moderngov(httpx_mock, "<html><body><p>Something else entirely</p></body></html>")

    _run(conn, settings)

    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue WHERE item_type='moderngov_results_unrecognised'"
    ).fetchone()["c"] >= 1
    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue WHERE item_type='committee_search_no_matches'"
    ).fetchone()["c"] == 0


def test_a_discovered_committee_url_is_marked_as_discovered(
        conn, settings, httpx_mock, monkeypatch):
    """A URL found on the council's home page is weaker evidence than a
    hand-verified entry, and the row says which it was.
    """
    from pipeline import authority_websites

    _seed_authority(conn)
    monkeypatch.setitem(
        authority_websites.AUTHORITY_WEBSITES, "E10000016",
        authority_websites.AuthorityWebsite(
            ons_code="E10000016", name="Kent", base_url="https://www.kent.example.gov.uk",
            committee_url=None, committee_system=None, verified_on=None))

    httpx_mock.add_response(url="https://www.kent.example.gov.uk/robots.txt",
                             status_code=404, text="", is_reusable=True)
    httpx_mock.add_response(
        url="https://www.kent.example.gov.uk",
        text='<a href="https://democracy.example.gov.uk/ieDocHome.aspx">Committee papers</a>',
        is_reusable=True)
    _mock_moderngov(httpx_mock, NO_RESULTS)

    _run(conn, settings)

    row = conn.execute("SELECT * FROM authority_committee_systems").fetchone()
    assert row["committee_url"] == "https://democracy.example.gov.uk"
    assert row["url_source"] == "homepage_link"
    assert row["committee_system"] == "moderngov"


def test_no_committee_link_anywhere_is_a_recorded_gap(conn, settings, httpx_mock, monkeypatch):
    from pipeline import authority_websites

    _seed_authority(conn)
    monkeypatch.setitem(
        authority_websites.AUTHORITY_WEBSITES, "E10000016",
        authority_websites.AuthorityWebsite(
            ons_code="E10000016", name="Kent", base_url="https://www.kent.example.gov.uk",
            committee_url=None, committee_system=None, verified_on=None))

    httpx_mock.add_response(url="https://www.kent.example.gov.uk/robots.txt",
                             status_code=404, text="", is_reusable=True)
    httpx_mock.add_response(url="https://www.kent.example.gov.uk",
                             text="<a href='/bins'>Bins</a>", is_reusable=True)

    _run(conn, settings)

    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue WHERE item_type='committee_url_unknown'"
    ).fetchone()["c"] == 1
    assert conn.execute(
        "SELECT COUNT(*) c FROM authority_committee_systems").fetchone()["c"] == 0


def test_system_detection_is_persisted_including_unknown(conn):
    _seed_authority(conn)
    conn.execute(
        "INSERT INTO authority_committee_systems (ons_code, committee_system, committee_url, "
        "detected_at) VALUES ('E10000016','unknown','https://x','2026-01-01')")
    row = conn.execute("SELECT * FROM authority_committee_systems").fetchone()
    assert row["committee_system"] == "unknown"


# --- politeness ------------------------------------------------------------------------------

def test_result_pages_per_term_are_capped():
    """The only thing standing between six search terms across 300 councils
    and a very long crawl.
    """
    assert 1 <= cp.MAX_RESULT_PAGES <= 5


def test_every_registry_entry_is_well_formed():
    """105 entries were added by hand from a verification document, and a
    hand-edited table of that size is where a typo hides.

    Each was fetched once through the pipeline's own client before it was
    recorded — see docs/verification/issue1_committee_urls.md — so what is
    checked here is shape, not reachability: no test may make a request.
    """
    from pipeline.authority_websites import AUTHORITY_WEBSITES

    for code, entry in AUTHORITY_WEBSITES.items():
        assert code == entry.ons_code, f"{code} is filed under the wrong key"
        assert re.fullmatch(r"E\d{8}", code), f"{code} is not an ONS code"
        assert entry.name, f"{code} has no name"
        for url in (entry.base_url, entry.committee_url):
            if url is not None:
                assert url.startswith("https://") or url.startswith("http://"), url
                assert not url.endswith("/"), f"{url} has a trailing slash"
        assert entry.committee_system in (None, "moderngov", "cmis", "democracy"), (
            f"{code} claims an unknown committee system")
        assert entry.verified_on, f"{code} does not say when it was verified"
