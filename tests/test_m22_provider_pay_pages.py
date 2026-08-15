"""Module 22: provider career and reward pages.

Attribution is exact by construction — every page is the provider's own
site, from the hand-verified registry or a same-host link on one — so the
tests are about the extraction discipline: figures keep their context, an
unreadable figure is NULL plus a parse failure, a page with no figures is
an answer about that page, and an unavailable page is a review item.
"""
from __future__ import annotations

from pipeline.modules import m22_provider_pay_pages as pp
from pipeline.registry import ModuleContext

CAREERS_PAGE = """
<html><head><title>Careers at Via</title></head><body>
<h1>Work at Via</h1>
<p>Join a national charity supporting people with alcohol dependence.</p>
<h2>Current vacancies</h2>
<p>Recovery Worker, £23,000 to £26,500 a year. Applications close soon.</p>
<p>Some roles pay £11.50 an hour.</p>
<p>Salaries depend on experience.</p>
<a href="/work-at-via/benefits">See our benefits</a>
<a href="https://other.example.com/jobs">Other site</a>
<a href="/work-at-via/benefits.pdf">Benefits PDF</a>
</body></html>
"""

BENEFITS_PAGE = """
<html><head><title>Benefits</title></head><body>
<h1>Benefits</h1>
<p>We offer 25 days holiday, a pension, and a competitive salary of £30,000.</p>
</body></html>
"""


def _allow_robots(httpx_mock, host="https://www.viaorg.uk"):
    httpx_mock.add_response(url=f"{host}/robots.txt", status_code=200, text="",
                            is_reusable=True)


def _run(conn, settings, httpx_mock):
    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    pp.run(ctx)


# --- extraction ----------------------------------------------------------------

def test_a_figure_keeps_its_section_and_its_sentence():
    mentions, failures = pp.extract_mentions(CAREERS_PAGE)
    assert failures == []
    by_text = {m["mention_text"]: m for m in mentions}

    range_mention = by_text["Recovery Worker, £23,000 to £26,500 a year."]
    assert range_mention["section"] == "Current vacancies"
    assert range_mention["salary_min"] == 23000.0
    assert range_mention["salary_max"] == 26500.0
    assert range_mention["salary_period"] == "year"
    assert range_mention["salary_basis"] == "range"

    hourly = by_text["Some roles pay £11.50 an hour."]
    assert hourly["salary_min"] == hourly["salary_max"] == 11.5
    assert hourly["salary_period"] == "hour"


def test_a_page_with_no_figures_yields_no_mentions():
    mentions, failures = pp.extract_mentions(
        "<html><body><h1>Careers</h1><p>We are a great place to work.</p></body></html>")
    assert mentions == []
    assert failures == []


def test_an_unreadable_figure_is_a_failure_and_still_a_mention():
    page = ("<html><body><h2>Pay</h2>"
            "<p>Salary is £TBC on appointment.</p></body></html>")
    mentions, failures = pp.extract_mentions(page)
    assert failures == [("Salary is £TBC on appointment.", "Salary is £TBC on appointment.")]
    assert len(mentions) == 1
    assert mentions[0]["salary_basis"] == "unparsed"
    assert mentions[0]["salary_min"] is None


def test_a_page_without_a_heading_before_a_figure_has_no_section():
    mentions, _failures = pp.extract_mentions("<p>We pay £20,000 a year.</p>")
    assert mentions[0]["section"] is None


def test_script_text_is_not_page_text():
    page = ("<script>var pay = '£99999';</script>"
            "<p>We pay £20,000 a year.</p>")
    mentions, _failures = pp.extract_mentions(page)
    assert len(mentions) == 1


# --- the crawl's link rules ----------------------------------------------------

def test_only_same_host_vocabulary_links_are_followed():
    links = pp._linked_pages("https://www.viaorg.uk/work-at-via/", _parse(CAREERS_PAGE))
    assert links == ["https://www.viaorg.uk/work-at-via/benefits"]
    assert "https://other.example.com/jobs" not in links
    assert "benefits.pdf" not in [url for url in links]


def _parse(html: str):
    parser = pp._PageParser()
    parser.feed(html)
    parser.close()
    return parser


def test_the_link_vocabulary_is_the_pages_own_words():
    assert pp._worth_following("/careers/", "Current vacancies")
    assert pp._worth_following("/rewards/", "Rewards package")
    assert not pp._worth_following("/news/", "Latest news")
    assert pp._worth_following("/jobs-at-via", "")


# --- a run ---------------------------------------------------------------------

def _only_via(monkeypatch):
    monkeypatch.setattr(pp, "PROVIDER_PAY_PAGES", {
        "via": [("https://www.viaorg.uk/work-at-via/", "test")]})


def test_a_run_stores_pages_and_mentions(conn, settings, httpx_mock, monkeypatch):
    _only_via(monkeypatch)
    _allow_robots(httpx_mock)
    httpx_mock.add_response(
        url="https://www.viaorg.uk/work-at-via/", text=CAREERS_PAGE, is_reusable=True)
    httpx_mock.add_response(
        url="https://www.viaorg.uk/work-at-via/benefits", text=BENEFITS_PAGE,
        is_reusable=True)

    _run(conn, settings, httpx_mock)

    pages = conn.execute(
        "SELECT * FROM provider_pay_pages ORDER BY page_url").fetchall()
    assert [p["page_url"] for p in pages] == [
        "https://www.viaorg.uk/work-at-via/",
        "https://www.viaorg.uk/work-at-via/benefits"]
    assert [p["page_role"] for p in pages] == ["registered", "followed"]
    assert pages[0]["pay_mentions"] == 2
    assert pages[1]["pay_mentions"] == 1
    assert pages[0]["page_title"] == "Careers at Via"

    mentions = conn.execute("SELECT * FROM provider_pay_mentions").fetchall()
    assert len(mentions) == 3
    assert {m["match_basis"] for m in mentions} == {"site_owned"}
    assert all(m["provider_key"] == "via" for m in mentions)
    benefit = next(m for m in mentions if m["page_url"].endswith("benefits"))
    assert benefit["salary_min"] == 30000.0
    assert benefit["salary_basis"] == "single"


def test_a_page_that_answered_with_no_figures_is_recorded_as_zero_mentions(
        conn, settings, httpx_mock, monkeypatch):
    """A page the provider published with no pay figures is an answer about
    that page; the count lives on the page row so a zero is visible, not an
    absence."""
    _only_via(monkeypatch)
    _allow_robots(httpx_mock)
    httpx_mock.add_response(
        url="https://www.viaorg.uk/work-at-via/",
        text="<html><body><h1>Work at Via</h1><p>Great people, great values.</p></body></html>",
        is_reusable=True)

    _run(conn, settings, httpx_mock)

    page = conn.execute("SELECT * FROM provider_pay_pages").fetchone()
    assert page["pay_mentions"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM provider_pay_mentions").fetchone()["c"] == 0


def test_a_rerun_replaces_the_mentions_of_a_changed_page(
        conn, settings, httpx_mock, monkeypatch):
    """The mentions table is a rendering of the page as fetched, not a
    history: a page that now carries fewer figures must not keep the old
    rows under indexes that no longer mean anything.
    """
    _only_via(monkeypatch)
    _allow_robots(httpx_mock)
    first = ("<html><body><h1>Work at Via</h1>"
             "<p>Recovery Worker, £23,000 a year.</p>"
             "<p>Some roles pay £11.50 an hour.</p></body></html>")
    httpx_mock.add_response(
        url="https://www.viaorg.uk/work-at-via/", text=first, is_reusable=True)

    _run(conn, settings, httpx_mock)
    assert conn.execute("SELECT COUNT(*) c FROM provider_pay_mentions").fetchone()["c"] == 2

    second = ("<html><body><h1>Work at Via</h1>"
              "<p>Now only £20,000 a year.</p></body></html>")
    httpx_mock.add_response(
        url="https://www.viaorg.uk/work-at-via/", text=second, is_reusable=True)
    _run(conn, settings, httpx_mock)

    page = conn.execute("SELECT * FROM provider_pay_pages").fetchone()
    assert page["pay_mentions"] == 1
    mentions = conn.execute("SELECT * FROM provider_pay_mentions").fetchall()
    assert len(mentions) == 1
    assert mentions[0]["mention_index"] == 0
    assert mentions[0]["salary_min"] == 20000.0


def test_an_unavailable_page_is_a_review_item_never_a_zero_row(
        conn, settings, httpx_mock, monkeypatch):
    """A 404 is not a page with no figures — the module never read it, so it
    must not look as though the provider published nothing there."""
    _only_via(monkeypatch)
    _allow_robots(httpx_mock)
    httpx_mock.add_response(url="https://www.viaorg.uk/work-at-via/",
                            status_code=404, text="")

    _run(conn, settings, httpx_mock)

    assert conn.execute("SELECT COUNT(*) c FROM provider_pay_pages").fetchone()["c"] == 0
    item = conn.execute(
        "SELECT * FROM review_queue WHERE item_type = 'pay_page_unavailable'").fetchone()
    assert item is not None
    assert "via" in item["raw_value"]


def test_a_robots_disallowed_page_is_recorded(conn, settings, httpx_mock, monkeypatch):
    _only_via(monkeypatch)
    httpx_mock.add_response(
        url="https://www.viaorg.uk/robots.txt",
        text="User-agent: *\nDisallow: /work-at-via/", is_reusable=True)

    _run(conn, settings, httpx_mock)

    assert conn.execute("SELECT COUNT(*) c FROM provider_pay_pages").fetchone()["c"] == 0
    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue "
        "WHERE item_type = 'pay_page_robots_disallowed'").fetchone()["c"] == 1


def test_the_followed_pages_budget_is_bounded(conn, settings, httpx_mock, monkeypatch):
    """A site that links itself everywhere costs bounded requests: only the
    first MAX_FOLLOWED_PAGES followed pages per provider are fetched."""
    monkeypatch.setattr(pp, "PROVIDER_PAY_PAGES", {
        "via": [("https://www.viaorg.uk/a", "test")]})
    monkeypatch.setattr(pp, "MAX_FOLLOWED_PAGES", 2)
    _allow_robots(httpx_mock)
    # every page links to two more pay pages, so the crawl could run forever
    for path in ("a", "b", "c"):
        httpx_mock.add_response(
            url=f"https://www.viaorg.uk/{path}",
            text=f'<html><body><p>Salary £{10000 + len(path) * 100} a year.</p>'
                 f'<a href="/b">Jobs</a><a href="/c">Careers</a></body></html>',
            is_reusable=True)

    _run(conn, settings, httpx_mock)

    fetched = {str(r.url) for r in httpx_mock.get_requests()
               if r.url.host == "www.viaorg.uk" and "/robots" not in str(r.url)}
    assert fetched == {"https://www.viaorg.uk/a", "https://www.viaorg.uk/b",
                       "https://www.viaorg.uk/c"}
