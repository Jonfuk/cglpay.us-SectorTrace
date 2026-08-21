"""Module 27 — NDTMS monthly provisional statistics.

`ndtms.net/Monthly/MonthlyProvisionalStatistics` is a Power BI dashboard, but
it links to an "old version" (`/Monthly` -> `/Monthly/Adults` and
`/Monthly/YoungPeople`) that is a plain self-posting ASP.NET Core form: no
Power BI, no client-rendered charts, just a `<form>` with Region/Local
Authority/Treatment provider/Report Date selects and a `<table>` per
indicator in the response HTML. That is what this module fetches.

The flow per cohort page:
  1. GET the page once for its anti-forgery token (`__RequestVerificationToken`,
     tied to a cookie the shared client already carries across requests) and
     the site's own default (selected) `ReportVersionId` -- the current month.
  2. GET `/Monthly/GetDATByPHECentre?pheCentre=<region>&vernum=<version>` for
     each of the nine English regions: a plain JSON list of that region's
     local authorities, `{"text": "Manchester", "value": "B18B"}`. These
     values are NDTMS's own area codes, not ONS codes -- Cheshire East's
     'B18B'-style codes coexist with ONS-style codes like '00EQ' in the same
     list, so ons_code is resolved by name (normalise_area_name, borrowed
     from m07_ndtms since it is the same NDTMS area-naming problem) rather
     than by treating the code as anything portable.
  3. POST the page's own URL with RegionId/DatCodeId/AgencyId=0/ReportVersionId
     and the token, once per local authority. The response is the same page,
     re-rendered for that area -- its <h1> names the area, which is checked
     against the area requested before any row from it is trusted: an
     anti-forgery failure here would silently re-render the England-wide
     page rather than erroring, and that is not something a status code
     catches.

Only the current default report month is fetched. `ReportVersionId` also
addresses months back to April 2014 (visible in the page's own dropdown),
but backfilling that would multiply every area by every month and nothing
has asked for it yet -- report_version_id and report_month are both stored
per row precisely so a future pass can add specific months without a schema
change.

This is service-demand context, not workforce data, and is kept in its own
table -- see the migration for why it is never merged with the census, the
same reasoning as m07_ndtms's ndtms_la_statistics.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from html.parser import HTMLParser

import structlog

from pipeline import db
from pipeline.http import PipelineHTTPClient
from pipeline.modules.m07_ndtms import (
    build_authority_lookup,
    build_transition_lookup,
    match_area_name,
)
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "ohid_ndtms_monthly"
BASE_URL = "https://www.ndtms.net"
COHORT_PATHS = {"adults": "/Monthly/Adults", "young_people": "/Monthly/YoungPeople"}

# The nine English NUTS1 regions as NDTMS's own "PHE Centre" filter presents
# them -- fixed ONS region codes, not scraped, because they are a stable
# geography and the page's England-wide default carries no LA breakdown to
# discover them from.
REGIONS = {
    "E12000001": "North East",
    "E12000002": "North West",
    "E12000003": "Yorkshire & the Humber",
    "E12000004": "East Midlands",
    "E12000005": "West Midlands",
    "E12000006": "East of England",
    "E12000007": "London",
    "E12000008": "South East",
    "E12000009": "South West",
}


class _LandingPageParser(HTMLParser):
    """Pulls the anti-forgery token and the currently-selected report month
    out of the self-posting filter form (`id="form1"`) -- the same form
    this module fills in and POSTs back to for each area.
    """

    def __init__(self) -> None:
        super().__init__()
        self.token: str | None = None
        self.report_version_id: str | None = None
        self.report_label: str | None = None
        self._in_form1 = False
        self._form_depth = 0
        self._in_report_select = False
        self._in_selected_option = False
        self._option_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form" and attrs.get("id") == "form1":
            self._in_form1 = True
            self._form_depth = 1
        elif self._in_form1 and tag == "form":
            self._form_depth += 1
        elif self._in_form1 and tag == "input" and attrs.get("name") == "__RequestVerificationToken":
            self.token = attrs.get("value")
        elif self._in_form1 and tag == "select" and attrs.get("id") == "ReportVersionId":
            self._in_report_select = True
        elif self._in_report_select and tag == "option" and "selected" in attrs:
            self.report_version_id = attrs.get("value")
            self._in_selected_option = True
            self._option_parts = []

    def handle_endtag(self, tag):
        if tag == "form" and self._in_form1:
            self._form_depth -= 1
            if self._form_depth <= 0:
                self._in_form1 = False
        elif tag == "select" and self._in_report_select:
            self._in_report_select = False
        elif tag == "option" and self._in_selected_option:
            self.report_label = "".join(self._option_parts).strip()
            self._in_selected_option = False

    def handle_data(self, data):
        if self._in_selected_option:
            self._option_parts.append(data)


class _ReportPageParser(HTMLParser):
    """Extracts each report `<table>` paired with the collapsible-panel
    heading that precedes it (e.g. "Number in treatment: Manchester").
    Pairing by document order rather than a fixed table index is what lets
    one parser handle both cohorts: Adults carries six sections
    (Number in treatment / New presentations YTD / Total exits YTD / three
    Effective Treatment splits), YoungPeople carries four (no Effective
    Treatment split), and hardcoding either shape would silently mislabel
    the other.
    """

    def __init__(self) -> None:
        super().__init__()
        self.h1: str | None = None
        self.sections: list[tuple[str, list[list[str]]]] = []
        self._in_h1 = False
        self._h1_parts: list[str] = []
        self._pending_heading: str | None = None
        self._in_heading_link = False
        self._heading_parts: list[str] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "h1":
            self._in_h1 = True
            self._h1_parts = []
        elif tag == "a" and (attrs.get("href") or "").startswith("#collapse"):
            self._in_heading_link = True
            self._heading_parts = []
        elif tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "h1" and self._in_h1:
            self.h1 = "".join(self._h1_parts).strip()
            self._in_h1 = False
        elif tag == "a" and self._in_heading_link:
            self._pending_heading = "".join(self._heading_parts).strip()
            self._in_heading_link = False
        elif tag == "table" and self._table is not None:
            self.sections.append((self._pending_heading or "", self._table))
            self._table = None
        elif tag == "tr" and self._row is not None:
            self._table.append(self._row)
            self._row = None
        elif tag in ("td", "th") and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None

    def handle_data(self, data):
        if self._in_h1:
            self._h1_parts.append(data)
        if self._in_heading_link:
            self._heading_parts.append(data)
        if self._cell is not None:
            self._cell.append(data)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def _to_number(raw: str) -> float | None:
    text = (raw or "").strip().replace(",", "").replace("%", "")
    if text in {"", "-", "–", "—", "*", "c", "z", "x", ":"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_report_month(label: str | None) -> str | None:
    """'June 2026' -> '2026-06-01'."""
    if not label:
        return None
    try:
        return datetime.strptime(label.strip(), "%B %Y").strftime("%Y-%m-01")
    except ValueError:
        return None


def _section_heading(heading: str) -> str:
    """"Number in treatment: Manchester" -> "Number in treatment". The area
    name after the colon changes per request; the section name before it
    does not.
    """
    return heading.split(":", 1)[0].strip()


def _h1_matches_area(h1: str | None, area_name: str) -> bool:
    """False on any mismatch, including a missing h1 or a page that came
    back England-wide -- both read as "this response cannot be trusted for
    the area requested" rather than as a parse failure to shrug off.
    """
    if not h1 or " - " not in h1:
        return False
    suffix = h1.rsplit(" - ", 1)[-1].strip().lower()
    return suffix == (area_name or "").strip().lower()


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


def _fetch_filters(client: PipelineHTTPClient, url: str) -> _LandingPageParser | None:
    landing = client.get(url)
    if not landing.ok:
        return None
    filters = _LandingPageParser()
    filters.feed(landing.body.decode("utf-8", errors="replace"))
    if not filters.token or not filters.report_version_id:
        return None
    return filters


@register_module(
    "m27_ndtms_monthly", supports_since=False,
    depends_on=("m00_geography",),
    depends_note="matches NDTMS's own area codes against the authorities table by name",
    since_note="the report is a live page showing one month, not a dated stream to "
                "resume; a month is selected by ReportVersionId, not by a date filter",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m27_ndtms_monthly"
    conn = ctx.conn
    authority_lookup = build_authority_lookup(conn)
    transitions = build_transition_lookup(conn)
    if not authority_lookup:
        log.info("ndtms_monthly.no_authorities",
                  note="run m00_geography first or every area will go to review_queue")

    stats_written = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        for cohort, path in COHORT_PATHS.items():
            url = f"{BASE_URL}{path}"
            filters = _fetch_filters(client, url)
            if filters is None:
                db.record_review_item(conn, module_name, "ndtms_monthly_form_not_found",
                                       url, json.dumps({}))
                continue

            report_month = _parse_report_month(filters.report_label)
            if report_month is None:
                db.record_review_item(conn, module_name, "ndtms_monthly_report_month_unparseable",
                                       url, json.dumps({"label": filters.report_label}))
                continue
            report_version_id = int(filters.report_version_id)

            areas: list[tuple[str, str, str]] = []
            for region_code in REGIONS:
                la_result = client.get(f"{BASE_URL}/Monthly/GetDATByPHECentre", params={
                    "pheCentre": region_code, "vernum": filters.report_version_id})
                if not la_result.ok:
                    db.record_review_item(conn, module_name, "ndtms_monthly_la_list_unavailable",
                                           region_code, json.dumps({"status": la_result.status_code}))
                    continue
                try:
                    options = json.loads(la_result.body)
                except json.JSONDecodeError:
                    db.record_review_item(conn, module_name, "ndtms_monthly_la_list_unparseable",
                                           region_code, json.dumps({}))
                    continue
                for opt in options:
                    dat_code, area_name = opt.get("value"), opt.get("text")
                    if dat_code and dat_code != "0" and area_name:
                        areas.append((region_code, dat_code, area_name))

            if ctx.limit:
                areas = areas[:ctx.limit]

            # The cohort goes in the phase line rather than the bar label:
            # each cohort is a full pass over every English local authority,
            # and a reader watching the bar needs to know which of the two
            # passes is running.
            ctx.phase(f"{cohort}: {filters.report_label or report_month}")
            for region_code, dat_code, area_name in ctx.track(areas, "local authority reports"):
                body = {
                    "RegionId": region_code, "DatCodeId": dat_code,
                    "AgencyId": "0", "ReportVersionId": filters.report_version_id,
                    "__RequestVerificationToken": filters.token,
                }
                result = client.post(url, data=body)
                if not result.ok:
                    # A stale anti-forgery token (long-idle session, cookie
                    # rotated mid-run) fails the same way a dead link would:
                    # one retry with a freshly issued token before giving up.
                    filters = _fetch_filters(client, url) or filters
                    body["ReportVersionId"] = filters.report_version_id
                    body["__RequestVerificationToken"] = filters.token
                    result = client.post(url, data=body)
                    if not result.ok:
                        db.record_review_item(conn, module_name, "ndtms_monthly_report_unavailable",
                                               dat_code, json.dumps({"status": result.status_code}))
                        continue

                page = _ReportPageParser()
                page.feed(result.body.decode("utf-8", errors="replace"))
                if not _h1_matches_area(page.h1, area_name):
                    db.record_review_item(conn, module_name, "ndtms_monthly_area_mismatch",
                                           dat_code, json.dumps({"expected": area_name, "h1": page.h1}))
                    continue

                ons_code = match_area_name(area_name, authority_lookup, transitions)
                if ons_code is None:
                    db.record_review_item(conn, module_name, "unmatched_ndtms_monthly_area",
                                           area_name, json.dumps({"dat_code": dat_code}))

                provenance = _provenance(result)
                for heading, rows in page.sections:
                    if len(rows) < 2:
                        continue
                    section = _slugify(_section_heading(heading))
                    header = rows[0]
                    for row in rows[1:]:
                        if not row or not row[0].strip():
                            continue
                        row_label = row[0].strip()
                        for i in range(1, min(len(row), len(header))):
                            raw = row[i]
                            if not raw.strip():
                                continue
                            db.upsert(conn, "ndtms_monthly_statistics", {
                                "report_version_id": report_version_id,
                                "report_month": report_month,
                                "cohort": cohort,
                                "area_name_raw": area_name,
                                "dat_code": dat_code,
                                "ons_code": ons_code,
                                "region_code": region_code,
                                "section": section,
                                "substance_category": row_label,
                                "time_period_raw": header[i].strip(),
                                "value": _to_number(raw),
                                "value_text": raw.strip(),
                                **provenance,
                            }, natural_key=["report_version_id", "cohort", "dat_code", "section",
                                             "substance_category", "time_period_raw"])
                            stats_written += 1

                if not ctx.dry_run:
                    conn.commit()

    log.info("ndtms_monthly.run_complete", stats_written=stats_written)
