from __future__ import annotations

import pytest

from pipeline import authority_websites
from pipeline.modules import m15_foi as foi

# --- GSS code extraction from mySociety's tags -----------------------------------

@pytest.mark.parametrize("tags,expected", [
    ("cassr england gss:E08000012 highways la_type:MD", "E08000012"),
    ("statistical_geography:E10000025 county", "E10000025"),
    ("lad23cd_code:E07000223 district", "E07000223"),
    ("england local_council", None),
    ("", None),
])
def test_extract_gss_code(tags, expected):
    assert foi.extract_gss_code(tags) == expected


def test_parse_authorities_csv_keeps_only_known_english_authorities():
    csv_text = (
        "Internal ID,Name,Short name,URL name,Tags,Home page,Publication scheme,Disclosure log\n"
        "3,Liverpool City Council,,liverpool_city_council,gss:E08000012 england,"
        "https://www.liverpool.gov.uk/,https://liverpool.gov.uk/ps,https://liverpool.gov.uk/dl\n"
        "9,Some Scottish Body,,scot_body,gss:S12000033 scotland,https://x.scot,,\n"
        "11,Not An Authority,,thing,no_code_here,https://y.uk,,\n")
    rows = foi.parse_authorities_csv(csv_text, {"E08000012"})
    assert len(rows) == 1
    row = rows[0]
    assert row["ons_code"] == "E08000012"
    assert row["wdtk_body_url"].endswith("/body/liverpool_city_council")
    assert row["home_page_url"] == "https://www.liverpool.gov.uk/"
    assert row["disclosure_log_url"] == "https://liverpool.gov.uk/dl"


def test_parse_authorities_csv_tolerates_missing_urls():
    csv_text = ("Internal ID,Name,Short name,URL name,Tags,Home page,Publication scheme,Disclosure log\n"
                "1,Oxfordshire County Council,,oxon,gss:E10000025,https://oxon.gov.uk,,\n")
    row = foi.parse_authorities_csv(csv_text, {"E10000025"})[0]
    assert row["disclosure_log_url"] is None
    assert row["publication_scheme_url"] is None


# --- the feed search URL ------------------------------------------------------------

def test_feed_search_url_quotes_the_phrase():
    """An unquoted multi-word query is OR-ish on Alaveteli and returns most of
    the site. The quotes must survive into the URL.
    """
    url = foi.feed_search_url("staffing levels")
    assert url.startswith("https://www.whatdotheyknow.com/feed/search/")
    assert url.endswith(".json")
    assert "%22staffing%20levels%22" in url


def test_feed_search_url_encodes_path_unsafe_characters():
    """The query sits in the path, not the query string, so a raw space or
    slash gives a 404 rather than a bad search.
    """
    url = foi.feed_search_url("drug/alcohol spend")
    assert " " not in url
    assert "%2F" in url


@pytest.mark.parametrize("term", [t for terms in foi.FOI_TOPICS.values() for t in terms])
def test_every_configured_term_builds_a_usable_url(term):
    url = foi.feed_search_url(term)
    assert url.count("/feed/search/") == 1
    assert not url.endswith("/.json")


# --- topic matching ---------------------------------------------------------------

@pytest.mark.parametrize("text,topic", [
    ("FOI response: substance misuse budget 2024", "budget_and_spend"),
    ("Drug and alcohol recommissioning timetable", "commissioning"),
    ("Request about staffing levels in treatment services", "workforce"),
    ("Waiting times for structured treatment", "service_delivery"),
    ("Naloxone distribution figures", "service_delivery"),
])
def test_match_foi_topic(text, topic):
    matched = foi.match_foi_topic(text)
    assert matched is not None
    assert matched[0] == topic


def test_match_foi_topic_returns_none_for_unrelated_text():
    assert foi.match_foi_topic("Bin collection calendar 2025") is None
    assert foi.match_foi_topic("") is None


def test_workforce_terms_cover_the_brief_list():
    workforce = " ".join(foi.FOI_TOPICS["workforce"]).lower()
    for term in ("vacanc", "turnover", "agency", "sickness", "caseload", "tupe", "pay scales"):
        assert term in workforce


def test_council_jobs_pages_are_not_read_as_foi_evidence():
    """The first live run's only candidate was a council jobs page matching a
    bare "vacancies". Workforce terms are qualified for that reason.
    """
    assert foi.match_foi_topic("Jobs and careers - Council vacancies (3)") is None


def test_genuine_workforce_foi_wording_still_matches():
    assert foi.match_foi_topic("FOI: staff vacancies in drug and alcohol services")[0] == "workforce"
    assert foi.match_foi_topic("Response - staffing levels 2024")[0] == "workforce"


# --- candidate extraction ------------------------------------------------------------

def test_extract_candidates_matches_on_link_text():
    html = ('<a href="/foi/1234">FOI 1234 - substance misuse budget</a>'
            '<a href="/foi/9999">FOI 9999 - potholes</a>')
    found = foi.extract_foi_candidates(html, "https://council.gov.uk/disclosure-log")
    assert len(found) == 1
    assert found[0]["topic"] == "budget_and_spend"
    assert found[0]["matched_term"] == "substance misuse budget"


def test_extract_candidates_stays_on_the_same_host():
    html = ('<a href="https://other.example.com/x">staffing levels</a>'
            '<a href="/local/y">staffing levels</a>')
    found = foi.extract_foi_candidates(html, "https://council.gov.uk/dl")
    assert len(found) == 1
    assert "council.gov.uk" in found[0]["candidate_url"]


def test_extract_candidates_deduplicates():
    html = ('<a href="/foi/1#a">caseloads</a><a href="/foi/1#b">caseloads</a>')
    assert len(foi.extract_foi_candidates(html, "https://council.gov.uk/dl")) == 1


def test_extract_candidates_empty_html():
    assert foi.extract_foi_candidates("", "https://council.gov.uk/dl") == []


# --- verification discipline --------------------------------------------------------------

def test_candidates_default_to_unverified(conn):
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, first_seen_vintage, "
        "last_seen_vintage, source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('E08000012','Liverpool','metropolitan_district','2020-01-01','x','x','u','t',200,'s','h')")
    conn.execute(
        "INSERT INTO foi_request_candidates (ons_code, candidate_url, title, matched_term, topic, "
        "discovered_at, discovery_source, source_url, retrieved_at, http_status, source_system, "
        "payload_sha256) VALUES ('E08000012','https://x/1','T','vacancies','workforce',"
        "'2026-01-01','disclosure_log','u','t',200,'s','h')")
    row = conn.execute("SELECT * FROM foi_request_candidates").fetchone()
    assert row["verified"] == 0
    assert row["rejected"] == 0


def test_foi_requests_table_starts_empty(conn):
    assert conn.execute("SELECT COUNT(*) c FROM foi_requests").fetchone()["c"] == 0


# --- the website fallback that unblocks Modules 9 and 10 -------------------------------------

def _seed_profile(conn, ons_code="E08000012"):
    conn.execute(
        "INSERT OR IGNORE INTO authorities (ons_code, name, type, active_from, first_seen_vintage, "
        "last_seen_vintage, source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?,'Liverpool','metropolitan_district','2020-01-01','x','x','u','t',200,'s','h')",
        (ons_code,))
    conn.execute(
        "INSERT INTO authority_foi_profiles (ons_code, authority_name, home_page_url, "
        "source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?, 'Liverpool City Council', 'https://www.liverpool.gov.uk/', 'u','t',200,'s','h')",
        (ons_code,))


def test_website_fallback_uses_the_published_register(conn):
    """Lifts Modules 9 and 10 from a hand-verified handful to every authority
    mySociety publishes a URL for — a citable source, not a guess.
    """
    _seed_profile(conn)
    site = authority_websites.website_for("E08000012", conn)
    assert site is not None
    assert site.base_url == "https://www.liverpool.gov.uk"
    assert site.committee_url is None  # the register does not record one


def test_hand_verified_config_wins_over_the_fallback(conn):
    """Kent is verified against the specific paths those modules use, so it
    must not be replaced by a generic home page.
    """
    conn.execute(
        "INSERT OR IGNORE INTO authorities (ons_code, name, type, active_from, first_seen_vintage, "
        "last_seen_vintage, source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('E10000016','Kent','county','2020-01-01','x','x','u','t',200,'s','h')")
    conn.execute(
        "INSERT INTO authority_foi_profiles (ons_code, authority_name, home_page_url, "
        "source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('E10000016','Kent County Council','https://generic.example.gov.uk','u','t',200,'s','h')")
    site = authority_websites.website_for("E10000016", conn)
    assert site.committee_url == "https://democracy.kent.gov.uk"
    assert site.verified_on == "2026-08-11"


def test_website_for_returns_none_when_neither_source_has_it(conn):
    assert authority_websites.website_for("E99999999", conn) is None


def test_website_for_without_a_connection_still_works():
    assert authority_websites.website_for("E10000016") is not None
    assert authority_websites.website_for("E08000012") is not None


# --- disclosure log crawling (runs on the fetch pool) -------------------------------

class _StubResult:
    def __init__(self, body: bytes, url: str, status_code: int = 200):
        self.body, self.url, self.status_code = body, url, status_code
        self.payload_sha256 = "sha"
        from datetime import datetime, timezone
        self.retrieved_at = datetime(2026, 8, 11, tzinfo=timezone.utc)

    @property
    def ok(self):
        return bool(self.body) and self.status_code < 400


class _StubClient:
    """Stands in for a pool worker's client. The point of the fetch/write
    split is that a worker needs nothing but this.
    """

    def __init__(self, result=None, raises=None):
        self._result, self._raises = result, raises
        self.requested: list[str] = []

    def get(self, url, **_kwargs):
        self.requested.append(url)
        if self._raises is not None:
            raise self._raises
        return self._result


_PROFILE = {"ons_code": "E08000012", "disclosure_log_url": "https://liverpool.gov.uk/dl",
            "wdtk_body_url": "https://www.whatdotheyknow.com/body/liverpool"}

_LOG_HTML = (
    '<a href="/foi/2024-001-drug-and-alcohol-service-staffing">'
    'FOI 2024/001 drug and alcohol service staffing levels</a>'
    '<a href="/bins">Bin collections</a>'
)


def test_a_worker_returns_candidates_without_touching_the_database():
    client = _StubClient(_StubResult(_LOG_HTML.encode(), "https://liverpool.gov.uk/dl"))
    candidates, review_items = foi.crawl_disclosure_log(_PROFILE, client)

    assert review_items == []
    assert candidates, "the disclosure log yielded nothing"
    assert all(c["source_url"] and c["retrieved_at"] and c["payload_sha256"]
               for c in candidates), "candidates lost their provenance"
    assert not any("/bins" in c["candidate_url"] for c in candidates)


def test_an_unavailable_log_is_reported_not_counted_as_crawled():
    """A council whose log 404s must not look like a council with no FOI
    requests about drug and alcohol services.
    """
    client = _StubClient(_StubResult(b"", "https://liverpool.gov.uk/dl", status_code=404))
    candidates, review_items = foi.crawl_disclosure_log(_PROFILE, client)

    assert candidates == []
    assert [item[0] for item in review_items] == ["foi_log_unavailable"]
    assert review_items[0][2]["status"] == 404


def test_a_robots_disallowed_log_is_reported():
    from pipeline.http import RobotsDisallowed

    client = _StubClient(raises=RobotsDisallowed("no"))
    candidates, review_items = foi.crawl_disclosure_log(_PROFILE, client)

    assert candidates == []
    assert [item[0] for item in review_items] == ["foi_log_robots_disallowed"]


def test_an_unexpected_error_propagates_to_the_pool():
    """Anything other than robots or a bad status is the pool's to catch, so
    it lands on the Outcome and is recorded as foi_log_unreachable rather
    than being swallowed here.
    """
    import httpx

    client = _StubClient(raises=httpx.ConnectError("dns"))
    with pytest.raises(httpx.ConnectError):
        foi.crawl_disclosure_log(_PROFILE, client)
