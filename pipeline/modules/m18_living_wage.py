"""Module 18 — Living Wage Foundation registrations.

One public lookup per provider against the accredited-employer list, binary,
citable: "N of the tracked providers are accredited living wage employers".
The register is a Drupal views page; the module drives the search box the
page itself offers (`search_api_fulltext`) and parses the result rows.

Matching discipline is the same as Module 4's: exact normalised name match
only. A shared name is not a shared identity, and here the consequence of a
wrong match is asserting accreditation of the wrong employer. So a hit that
does not exactly match the searched name is a review item, never a stored
accreditation — and a provider is accredited only under the names it was
searched under, which is deliberately one canonical variant per provider:
thirteen lookups, not a sweep. An employer list is a roster, not an entity
register; this module records what the roster says.

Two honest limits, both recorded rather than hidden:

  * The search window is the first MAX_PAGES result pages. Where the
    register's own count line exceeds what was read, a review item says so
    rather than letting "not found" silently mean "not in the checked
    window" — and where the count is within the window, "not found" is a
    complete answer.
  * `accredited = 0` is "no accredited employer under this name, as of this
    fetch". Accreditation could sit under another legal name (a trading
    subsidiary), which is exactly the case the review queue is for; the
    module does not guess it.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser

import structlog

from pipeline import db
from pipeline.http import PipelineHTTPClient
from pipeline.keywords import SUPPLIER_NAME_VARIANTS
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "living_wage_foundation"
LIST_URL = "https://www.livingwage.org.uk/accredited-living-wage-employers-list"
MAX_PAGES = 3
PER_PAGE = 10  # the views pager emits this many rows per page

# The register's own count line: "<n> Accredited Living Wage Employers found."
# (the number is inside a <strong>, which is why the tag appears in the
# pattern rather than a generic number-and-space).
_COUNT_RE = re.compile(r"([\d,]+)</strong>\s+Accredited Living Wage Employers found",
                       re.IGNORECASE)


def _normalise_employer_name(name: str) -> str:
    text = re.sub(r"[^\w\s]", " ", (name or "").lower())
    text = re.sub(r"\b(limited|ltd|llp|plc|cic|trust|foundation)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalise_match(name: str, searched: str) -> bool:
    """Exact match of the register's spelling against the searched variant,
    on normalised names. Deterministic only — see the module docstring."""
    return bool(_normalise_employer_name(name)) and \
        _normalise_employer_name(name) == _normalise_employer_name(searched)


class _EmployerListParser(HTMLParser):
    """Each result row is an <article data-history-node-id="N"> followed by a
    sibling modal whose heading carries the employer name. The node id and
    the name are therefore read as a pair: the last article seen supplies
    the id for the next title seen.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.employers: list[dict] = []
        self._pending_node_id: str | None = None
        self._in_title = False
        self._title_tag: str | None = None
        self._title: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "article":
            self._pending_node_id = dict(attrs).get("data-history-node-id")
        elif "teaser-modal__title" in dict(attrs).get("class", ""):
            # the name is on whatever heading element the theme uses (h3
            # today); matching the class rather than the tag is the point
            self._in_title = True
            self._title_tag = tag
            self._title = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._in_title and tag == self._title_tag:
            self._in_title = False
            title = " ".join("".join(self._title).split())
            if title:
                self.employers.append({"node_id": self._pending_node_id,
                                        "name": title})
            self._pending_node_id = None
            self._title = []
            self._title_tag = None


def parse_employer_list(page_html: str) -> tuple[list[dict], int | None]:
    """(employers, count_line) from one page of the list."""
    parser = _EmployerListParser()
    parser.feed(page_html)
    count = None
    m = _COUNT_RE.search(page_html)
    if m:
        try:
            count = int(m.group(1).replace(",", ""))
        except ValueError:
            count = None
    return parser.employers, count


@register_module(
    "m18_living_wage",
    supports_since=False,
    since_note="accreditation is a current-state roster, not a dated stream",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m18_living_wage"
    conn = ctx.conn

    written = 0
    accredited = 0
    unconfirmed = 0
    truncated = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        for provider_key, variants in ctx.track(
                SUPPLIER_NAME_VARIANTS.items(), "providers"):
            # One lookup per provider, per the module docstring: the canonical
            # (first) name variant. Searching the others too would multiply
            # the requests for names the register almost never uses.
            searched = variants[0]
            seen_names: dict[str, dict] = {}
            pages_checked = 0
            employers_total = None
            page_failed = False

            for page in range(MAX_PAGES):
                result = client.get(LIST_URL, params={
                    "search_api_fulltext": searched, "page": page})
                if not result.ok:
                    db.record_review_item(
                        conn, module_name, "living_wage_search_failed", f"{provider_key} {searched}",
                        json.dumps({"status": result.status_code}))
                    page_failed = True
                    break
                employers, count = parse_employer_list(result.body.decode("utf-8", "replace"))
                pages_checked += 1
                if count is not None:
                    employers_total = count
                for employer in employers:
                    seen_names.setdefault(employer["node_id"] or employer["name"], employer)
                if not employers:
                    break  # the register itself says the window is exhausted

            if page_failed:
                continue

            if employers_total is not None and employers_total > pages_checked * PER_PAGE:
                db.record_review_item(
                    conn, module_name, "living_wage_search_truncated", f"{provider_key} {searched}",
                    json.dumps({"employers_total": employers_total,
                                "pages_checked": pages_checked,
                                "note": "the register reports more matches than the checked "
                                        "window; 'not found' is not a complete answer here"}))
                truncated += 1

            found = next(
                (e for e in seen_names.values()
                 if normalise_match(e["name"], searched)), None)

            db.upsert(conn, "living_wage_accreditations", {
                "provider_key": provider_key,
                "searched_variant": searched,
                "accredited": 1 if found else 0,
                "employer_name": found["name"] if found else None,
                "employer_node_id": found["node_id"] if found else None,
                "match_basis": "exact" if found else None,
                "pages_checked": pages_checked,
                "employers_total": employers_total,
                "source_url": result.url if not page_failed else LIST_URL,
                "retrieved_at": result.retrieved_at.isoformat() if not page_failed else None,
                "http_status": result.status_code if not page_failed else None,
                "source_system": SOURCE_SYSTEM,
                "payload_sha256": result.payload_sha256 if not page_failed else None,
            }, natural_key=["provider_key", "searched_variant"])
            written += 1
            if found:
                accredited += 1
            else:
                # A search that returned rows but no exact match: the name the
                # register spells differently is the case a human should see.
                for employer in seen_names.values():
                    if not normalise_match(employer["name"], searched):
                        db.record_review_item(
                            conn, module_name, "unconfirmed_living_wage_name_match",
                            f"{provider_key} {searched}",
                            json.dumps({"register_name": employer["name"],
                                        "note": "the register lists an employer under this name "
                                                "but not exactly the searched one; NOT recorded as "
                                                "accredited"}))
                        unconfirmed += 1
                        break
            if not ctx.dry_run:
                conn.commit()

    log.info("living_wage.run_complete", providers=written, accredited=accredited,
              unconfirmed=unconfirmed, truncated_searches=truncated)
