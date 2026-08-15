"""Module 22 — provider career and reward pages.

The provider's own half of the direct pay evidence (B3): pay figures
published on the tracked providers' own websites — advertised bands,
"rewards package" pages, listed rates. Attribution is exact by
construction: every page fetched is on a provider's own site, from the
hand-verified registry in `pipeline/provider_websites.py` (the D-05 lesson:
answers belong in a committed file) or from a same-host link on one. There
is no free-text matching anywhere, and `match_basis = 'site_owned'` on
every mention says so.

WHAT A PAGE YIELDS:

  * `provider_pay_pages` — one row per fetched page: whether it answered,
    and how many pay figures it carried. A page that answered with no
    figures is recorded with pay_mentions = 0, which is an answer about
    that page (the provider published no figures there), not a gap. A page
    that did not answer is a review item, never a zero row.
  * `provider_pay_mentions` — one row per figure: the sentence containing
    it, verbatim, the nearest preceding heading as its section, and the
    figure parsed with the same rules m16 applies to adverts (reused, not
    re-derived: an hourly rate is hourly, never annualised). A figure that
    is present but unreadable is a `parse_failures` row and is stored with
    NULLs — the text survives either way.

THE CRAWL IS BOUNDED AND ONE HOP DEEP:

  * From each registered page, same-host links whose anchor text or URL
    carries the pay or careers vocabulary are followed — the vocabulary is
    the page's own words, not a relevance score.
  * At most MAX_FOLLOWED_PAGES per provider, and links that are files
    (pdf, docx, ...) are not fetched — a linked pay-scale PDF is a real
    find, but reading PDFs is m03/m06's machinery, not this module's, and
    the page that links it is recorded either way.

WHAT THIS MODULE DELIBERATELY IS NOT: it does not read job boards (NHS
Jobs is m16's job, and provider job boards are usually separate hosts with
their own bot protection), and it does not claim that a page with no
figures means the provider pays nothing. The coverage caveat is the same
floor as m16's, written for websites.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import structlog

from pipeline import db
from pipeline.http import PipelineHTTPClient, RobotsDisallowed
from pipeline.modules.m16_nhs_jobs import parse_salary
from pipeline.provider_websites import PROVIDER_PAY_PAGES
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "provider_pay_pages"

# How many same-host pages the crawl may follow per provider, on top of the
# registered entry points. The budget exists so a site that links the whole
# of its careers section costs bounded requests rather than all of them.
MAX_FOLLOWED_PAGES = 10

# The vocabulary that makes a link worth following. Matched against the
# anchor text and the URL path, lower-cased. It is deliberately the words a
# provider would use on its own site rather than a claim about what the
# link contains.
_FOLLOW_WORDS = ("salary", "pay", "reward", "benefit", "band", "rate",
                 "career", "job", "vacanc", "recruit", "work-for",
                 "work for", "join-us", "join us", "opportunit")

_FILE_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv",
                    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".zip"}

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WHITESPACE_RE = re.compile(r"\s+")
_MONEY_PRESENT_RE = re.compile(r"£")

# Block elements that end a stretch of text. Inline elements (a, em, strong,
# span, ...) deliberately do not: a sentence that crosses an inline boundary
# must stay one sentence, and a sentence that crosses a paragraph must not.
_BLOCK_TAGS = {"p", "div", "li", "ul", "ol", "section", "article", "header",
               "footer", "main", "nav", "tr", "td", "th", "h5", "h6", "hr",
               "br", "blockquote", "table", "form"}


class _PageParser(HTMLParser):
    """A page as a stream of text and headings, plus its links and title.

    Text and headings interleave; the mention extractor walks the stream
    with the last heading seen as the current section.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[tuple[str, str]] = []  # ('heading' | 'text', content)
        self.links: list[tuple[str, str]] = []  # (href, anchor text)
        self.title: str | None = None
        self._buffer: list[str] = []
        self._mode: str | None = None  # None | 'text' | 'heading' | 'title'
        self._heading_tag: str | None = None
        self._link_href: str | None = None
        self._link_text: list[str] = []
        self._suppress = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("h1", "h2", "h3", "h4"):
            self._flush()
            self._mode = "heading"
            self._heading_tag = tag
        elif tag == "title":
            self._flush()
            self._mode = "title"
        elif tag == "a":
            self._link_href = dict(attrs).get("href")
            self._link_text = []
        elif tag in ("script", "style", "noscript"):
            self._flush()
            self._suppress = True  # script text is not page text

    def handle_data(self, data: str) -> None:
        if self._suppress:
            return
        if self._mode in ("heading", "title"):
            self._buffer.append(data)
            return
        if self._link_href is not None:
            self._link_text.append(data)
        if self._mode is None:
            self._mode = "text"
        if self._mode == "text":
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("h1", "h2", "h3", "h4", "title"):
            self._flush()
        elif tag in _BLOCK_TAGS:
            # A paragraph end closes the text stretch but not the current
            # section — the next paragraph belongs to the same heading.
            self._flush()
        elif tag == "a":
            if self._link_href:
                self.links.append((self._link_href, _clean(" ".join(self._link_text))))
            self._link_href = None
            self._link_text = []
        elif tag in ("script", "style", "noscript"):
            self._suppress = False

    def close(self) -> None:
        self._flush()
        super().close()

    def _flush(self) -> None:
        if self._buffer:
            text = _clean(" ".join(self._buffer))
            if text:
                if self._mode == "title":
                    self.title = text
                else:
                    self.parts.append((self._mode or "text", text))
        self._buffer = []
        self._mode = None


def _clean(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text or "").strip()


def _same_host(a: str, b: str) -> bool:
    return urlparse(a).netloc == urlparse(b).netloc


def _worth_following(href: str, anchor: str) -> bool:
    lower = f"{href.lower()} {anchor.lower()}"
    if not _MONEY_PRESENT_RE.search(anchor):
        if not any(word in lower for word in _FOLLOW_WORDS):
            return False
    return True


def _is_file(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in _FILE_EXTENSIONS)


def _linked_pages(page_url: str, parser: _PageParser) -> list[str]:
    """Same-host, vocabulary-matched, non-file links from one page, absolute."""
    out: list[str] = []
    for href, anchor in parser.links:
        absolute = urljoin(page_url, href)
        if not _same_host(page_url, absolute):
            continue
        if _is_file(absolute):
            continue
        if not _worth_following(absolute, anchor):
            continue
        out.append(absolute)
    return out


def extract_mentions(html: str) -> tuple[list[dict], list[tuple[str, str]]]:
    """(mentions, parse_failures) from one page.

    A mention is one sentence containing a £ figure, with the nearest
    preceding heading as its section. A sentence with more than one figure
    yields one mention whose salary line is parsed whole — the same rule
    m16 applies to an advert's salary field.
    """
    parser = _PageParser()
    parser.feed(html or "")
    parser.close()

    mentions: list[dict] = []
    failures: list[tuple[str, str]] = []
    current_section: str | None = None

    for kind, content in parser.parts:
        if kind == "heading":
            current_section = content
            continue
        if not _MONEY_PRESENT_RE.search(content):
            continue
        for sentence in _SENTENCE_SPLIT_RE.split(content):
            if not _MONEY_PRESENT_RE.search(sentence):
                continue
            salary = parse_salary(sentence)
            if salary["salary_basis"] == "unparsed":
                failures.append((sentence, salary["salary_raw"] or ""))
            mentions.append({
                "section": current_section,
                "mention_text": sentence,
                **salary,
            })
    return mentions, failures


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


def _store_page(conn, module_name: str, *, provider_key: str, page_url: str,
                role: str, title: str | None, mentions: list[dict],
                failures: list[tuple[str, str]], result) -> int:
    prov = _provenance(result)
    db.upsert(conn, "provider_pay_pages", {
        "provider_key": provider_key,
        "page_url": page_url,
        "page_role": role,
        "page_title": title,
        "pay_mentions": len(mentions),
        **prov,
    }, natural_key=["provider_key", "page_url"])

    # The mentions table is a rendering of the page as fetched, not a
    # history: a page that now carries fewer figures must not keep the old
    # rows under indexes that no longer mean anything. This table is the
    # re-observation case F-05 says not to version — it is replaced, not
    # accumulated, and the page row's count is what makes the two agree.
    conn.execute("DELETE FROM provider_pay_mentions WHERE page_url = ?", (page_url,))

    for index, mention in enumerate(mentions):
        db.upsert(conn, "provider_pay_mentions", {
            "page_url": page_url,
            "mention_index": index,
            "provider_key": provider_key,
            "section": mention["section"],
            "mention_text": mention["mention_text"],
            "salary_raw": mention["salary_raw"],
            "salary_min": mention["salary_min"],
            "salary_max": mention["salary_max"],
            "salary_period": mention["salary_period"],
            "salary_basis": mention["salary_basis"],
            "match_basis": "site_owned",
            **prov,
        }, natural_key=["page_url", "mention_index"])

    for sentence, raw in failures:
        db.record_parse_failure(
            conn, module_name, "pay_figure", raw or sentence[:200],
            "a currency figure was present but could not be read",
            source_url=result.url)
    return len(mentions)


def _fetch_page(client, conn, module_name: str, *, provider_key: str,
                page_url: str, role: str) -> tuple[int, list[str]]:
    """Fetch and store one page. Returns (mentions, links to follow)."""
    try:
        result = client.get(page_url)
    except RobotsDisallowed:
        db.record_review_item(
            conn, module_name, "pay_page_robots_disallowed",
            f"{provider_key} {page_url}",
            json.dumps({"note": "robots.txt disallows the page; it is not fetched"}))
        return 0, []
    if not result.ok:
        db.record_review_item(
            conn, module_name, "pay_page_unavailable",
            f"{provider_key} {page_url}",
            json.dumps({"status": result.status_code}))
        return 0, []

    html = result.body.decode("utf-8", "replace")
    parser = _PageParser()
    parser.feed(html)
    parser.close()
    mentions, failures = extract_mentions(html)
    count = _store_page(conn, module_name, provider_key=provider_key,
                        page_url=page_url, role=role, title=parser.title,
                        mentions=mentions, failures=failures, result=result)
    links = _linked_pages(page_url, parser)
    return count, links


@register_module(
    "m22_provider_pay_pages",
    supports_since=False,
    since_note="a provider's site is a current-state publication, not a dated stream",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m22_provider_pay_pages"
    conn = ctx.conn
    pages_fetched = 0
    mentions_written = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        for provider_key, registered in ctx.track(PROVIDER_PAY_PAGES.items(), "providers"):
            visited: set[str] = set()
            queue: list[tuple[str, str]] = [(url, "registered") for url, _note in registered]
            followed = 0
            while queue:
                page_url, role = queue.pop(0)
                if page_url in visited:
                    continue
                visited.add(page_url)
                count, links = _fetch_page(
                    client, conn, module_name, provider_key=provider_key,
                    page_url=page_url, role=role)
                pages_fetched += 1
                mentions_written += count
                if role == "followed":
                    followed += 1
                    if followed > MAX_FOLLOWED_PAGES:
                        break
                for link in links:
                    if link not in visited:
                        queue.append((link, "followed"))
                if not ctx.dry_run:
                    conn.commit()
                if ctx.limit and mentions_written >= ctx.limit:
                    break
            if ctx.limit and mentions_written >= ctx.limit:
                break

    log.info("provider_pay_pages.run_complete", pages=pages_fetched,
              mentions=mentions_written)
