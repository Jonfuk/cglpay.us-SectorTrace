"""Module 33 — HSE convictions (Health and Safety Executive), sibling to
`m33_hse_notices`.

HSE's public register of convictions lists prosecution cases that resulted in
a conviction, at breach level: a "Case" is the prosecution against a
defendant, and each separate failure to comply within that case is a
"Breach", the register's own unit (its help pages: "the case may involve one
or more instances when the defendant has failed to comply ... each one of
these is a Breach"). This module collects the breach list — hearing date,
result, fine and the Act/Regulation section breached — and keeps only the
rows whose defendant name exactly matches a tracked provider, using the same
organisation/individual and exact-match functions `m33_hse_notices` already
applies to the notices register (one discipline, both HSE sources).

Caveats that travel with any figure built from this (`docs/CAVEATS.md`):

  * **Breach-level only, not the full case file.** The case-detail page
    (address, industry, HSE division, total costs) is a separate fetch this
    module does not make; a case with several breaches produces several
    rows here, one per breach, and re-deriving a "one row per prosecution"
    count means grouping on `case_number` yourself.
  * **The register's own retention window, not this pipeline's.** HSE
    publishes a conviction on the public register for one year, then moves it
    to the conviction-history register for a further nine; convictions older
    than that are not published anywhere on the site. An absence here is not
    a clean record — it may be older than the retention window, prosecuted by
    a local authority rather than HSE, or simply not yet reached this
    register's nine-week post-conviction delay.
  * **Individuals are excluded, at parse time** — the same organisation/
    individual test `m33_hse_notices` uses, because the register lists
    breaches against named defendants (directors, sole traders) as well as
    organisations.
  * **Exact name match only**, same discipline as Modules 4, 18 and
    `m33_hse_notices`. A near-miss is a `review_queue` item, never a stored
    attribution.
  * **The search field code is not confirmed against the live register.**
    HSE's own advanced/standard search forms build their field-code dropdown
    server-side after a POST step that is not present in any archived
    capture; this module reuses `m33_hse_notices`'s confirmed-for-notices
    `SF=CN` contains-match convention on the assumption the two registers
    share the same underlying query engine (both live under
    `resources.hse.gov.uk`, both use the same `SN`/`ST`/`SF`/`EO`/`SV`
    grammar — confirmed by comparing archived notice and conviction search
    URLs). If that field code is wrong for this register, the search returns
    no rows rather than the wrong ones; it does not risk a false attribution,
    but it does mean an empty result here is not yet trustworthy as
    "no convictions" until the first live run confirms the query works.
  * **Live-fetch path not yet validated against the real register**, for the
    reason above and because `resources.hse.gov.uk` was unreachable from the
    preparation environment for this module (connection timeout, while
    `www.hse.gov.uk` answered normally) — the parser was written and
    exercised against real HTML retrieved from the Wayback Machine's archived
    captures of `breach_list.asp`, not a live fetch. The first real run
    should be watched by a person, per the project's reduced-testing policy
    for a new source — more so here than for `m33_hse_notices`, given the
    unconfirmed search parameter above.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

import structlog

from pipeline import db
from pipeline.http import PipelineHTTPClient
from pipeline.keywords import SUPPLIER_NAME_VARIANTS
from pipeline.modules.m33_hse_notices import is_organisation, name_matches
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "hse_enforcement_convictions"

# See the module docstring: this field code is confirmed for the notices
# register's company-name contains-search, not for this one.
SEARCH_URL = "https://resources.hse.gov.uk/convictions/breach/breach_list.asp"


def _search_params(name: str) -> dict:
    return {"ST": "B", "SN": "F", "EO": "LIKE", "SF": "CN", "SV": name}


_HEADER_MAP = {
    "casebreach": "case_breach",
    "defendantsname": "defendant_name",
    "defendantname": "defendant_name",
    "hearingdate": "hearing_date",
    "result": "result",
    "fine": "fine_text",
    "actorregulation": "legislation",
}


class _BreachListParser(HTMLParser):
    """One `<table>` of breach rows, read by header text like
    `m33_hse_notices._NoticeListParser` — a column reorder is a missing key,
    never a misread value.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict] = []
        self._headers: list[str] = []
        self._in_thead = False
        self._in_row = False
        self._in_cell = False
        self._is_header_cell = False
        self._cell_parts: list[str] = []
        self._row_cells: list[str] = []
        self._detail_href: str | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        a = dict(attrs)
        if tag == "thead":
            self._in_thead = True
        elif tag == "tr":
            self._in_row = True
            self._row_cells = []
            self._detail_href = None
        elif tag in ("td", "th"):
            self._in_cell = True
            self._is_header_cell = tag == "th"
            self._cell_parts = []
        elif tag == "a" and self._in_cell and a.get("href"):
            self._detail_href = a["href"]

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "thead":
            self._in_thead = False
        elif tag in ("td", "th"):
            text = re.sub(r"\s+", " ", "".join(self._cell_parts)).strip()
            if self._is_header_cell:
                key = re.sub(r"[^a-z]", "", text.lower())
                self._headers.append(_HEADER_MAP.get(key, ""))
            else:
                self._row_cells.append(text)
            self._in_cell = False
        elif tag == "tr":
            self._in_row = False
            if self._row_cells and self._headers and not self._in_thead:
                row: dict = {}
                for header, value in zip(self._headers, self._row_cells):
                    if header and value:
                        row[header] = value
                if self._detail_href:
                    row["_detail_href"] = self._detail_href
                if row.get("case_breach"):
                    self.rows.append(row)


def _breach_id_from_href(href: str | None) -> str | None:
    """The breach id HSE's own link carries (`?SF=BID&SV=<id>`), rather than
    reconstructing it by stripping the "/" from the displayed "Case/Breach"
    text — the two are not guaranteed to agree in every row format."""
    if not href:
        return None
    query = parse_qs(urlparse(href).query)
    values = query.get("SV") or query.get("sv")
    return values[0] if values else None


def parse_breach_list(html: str) -> list[dict]:
    """Rows keyed by header, plus `breach_id`, `case_number` and
    `breach_sequence` split from the "Case/Breach" column (e.g.
    "47409320/01") and the detail link."""
    parser = _BreachListParser()
    parser.feed(html or "")
    rows = []
    for row in parser.rows:
        case_number, _, breach_sequence = row["case_breach"].partition("/")
        breach_id = _breach_id_from_href(row.get("_detail_href")) or row["case_breach"]
        rows.append({
            **row,
            "breach_id": breach_id,
            "case_number": case_number.strip(),
            "breach_sequence": breach_sequence.strip() or None,
        })
    return rows


@register_module(
    "m33_hse_convictions",
    supports_since=False,
    since_note="the register is a static list of published convictions; a "
               "run collects every current match rather than a dated window",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m33_hse_convictions"
    conn = ctx.conn

    written = 0
    attributed = 0
    dropped_individuals = 0
    near_misses = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        for provider_key, variants in ctx.track(
                SUPPLIER_NAME_VARIANTS.items(), "providers"):
            tracked = set(variants)

            # Same reconciliation as m33_hse_notices: search under every name
            # variant, then judge each breach once against the whole variant
            # set rather than whichever search happened to return it.
            merged: dict[str, tuple[dict, object]] = {}
            for searched in variants:
                result = client.get(SEARCH_URL, params=_search_params(searched))
                if not result.ok:
                    db.record_review_item(
                        conn, module_name, "hse_conviction_search_failed",
                        f"{provider_key} {searched}",
                        json.dumps({"status": result.status_code}))
                    continue
                for row in parse_breach_list(
                        result.body.decode("utf-8", "replace")):
                    merged.setdefault(row["breach_id"], (row, result))

            conviction_rows: list[dict] = []
            for row, result in merged.values():
                defendant = row.get("defendant_name", "")
                if not is_organisation(defendant, tracked_variants=tracked):
                    dropped_individuals += 1
                    continue
                if not any(name_matches(defendant, v) for v in variants):
                    # A same-ish name that is not an exact match to any
                    # tracked variant: a lead for a person, never a stored
                    # attribution (module docstring). Keyed so a re-run
                    # upserts rather than duplicates.
                    db.record_review_item(
                        conn, module_name, "hse_conviction_name_near_miss",
                        f"{provider_key} {row['breach_id']}",
                        json.dumps({"variants": list(variants),
                                    "register_name": defendant,
                                    "breach_id": row["breach_id"]}))
                    near_misses += 1
                    continue

                conviction_rows.append({
                    "breach_id": row["breach_id"],
                    "case_number": row["case_number"],
                    "breach_sequence": row.get("breach_sequence"),
                    "defendant_name": defendant,
                    "provider_key": provider_key,
                    "hearing_date": row.get("hearing_date"),
                    "result": row.get("result"),
                    "fine_text": row.get("fine_text"),
                    "legislation": row.get("legislation"),
                    "source_url": result.url,
                    "retrieved_at": result.retrieved_at.isoformat(),
                    "http_status": result.status_code,
                    "source_system": SOURCE_SYSTEM,
                    "payload_sha256": result.payload_sha256,
                })
                written += 1
                attributed += 1

            db.upsert_many(
                conn, "hse_enforcement_convictions", conviction_rows,
                natural_key=["breach_id"],
            )
            # One commit per provider, released as each provider's
            # convictions land (CLAUDE.md settled decision 10).
            if not ctx.dry_run:
                conn.commit()

    log.info("m33_hse_convictions.done", written=written, attributed=attributed,
             dropped_individuals=dropped_individuals, near_misses=near_misses)
