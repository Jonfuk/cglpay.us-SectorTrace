"""Module 17 — National Minimum Wage and National Living Wage rates.

The statutory floor, as a small annual reference table from the gov.uk rates
page. Deliberately NOT an API: the government publishes no machine-readable
rates endpoint — the page *is* the publication, one row per year, updated
once a year, citable. This module reads that page through the GOV.UK content
API (the same host and client the tribunal, NDTMS, grant and budget modules
already use), which serves the page's own govspeak HTML in `details.body`.

What this table is the anchor for: every "advertised band versus the
statutory floor" statement the campaign will draft. The gate from the phase
plan applies here in advance: a floor comparison is **side-by-side**, and any
ratio ("X% above the NLW") is the CAVEATS reading's decision, not the
module's. Nothing in this file computes one.

Parsing rules, each chosen because a real page shape would otherwise break
them:

  * The band set changes between eras — the living wage column read
    "25 and over" until April 2021, "23 and over" to April 2024, and
    "21 and over" since. The band labels are stored verbatim, and the living
    wage band is identified by position: the page always leads each table
    with the living wage column, so the first data column gets
    band_role 'national_living_wage'. That rule is the page's own layout,
    not an inference about the law.
  * Cells carry trailing non-breaking spaces and whole-pound values without
    pence ("£8"). The amount is parsed after stripping whitespace, and the
    cell is stored verbatim in value_text either way — an amount this module
    cannot read is a NULL plus a parse_failure, never a guess and never a
    silently dropped figure.
  * The period label ("April 2026", "April 2025 to March 2026") is kept
    verbatim; effective_from is derived only where the label parses.

Re-runs are idempotent on (period_label, band_label), so the table reads
whatever the page says today — the "current rates" row of one year becomes a
"previous rates" row of the next, and nothing is deleted.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser

import structlog

from pipeline import db
from pipeline.http import PipelineHTTPClient
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "govuk_nmw_rates"
RATES_URL = "https://www.gov.uk/api/content/national-minimum-wage-rates"

# "April 2026" -> 2026-04-01; "April 2025 to March 2026" -> 2025-04-01. The
# page has never published a rate outside April, so the month is pinned by
# the source's own "rates change on 1 April every year" statement rather
# than guessed from the label.
_PERIOD_RE = re.compile(r"April (\d{4})")
_AMOUNT_RE = re.compile(r"£\s*(\d+(?:\.\d{1,2})?)")


class _RatesTableParser(HTMLParser):
    """Extracts (headers, rows) from the govspeak HTML tables.

    Govspeak writes each rates table as a thead with the empty corner cell
    as a <td> and the band labels as <th scope="col">, then body rows whose
    first cell is a <th scope="row"> period label followed by <td> rates.
    Both thead and tbody rows arrive as plain <tr> in some years, so the
    table is collected row by row and the first row of each table is taken
    as its header — which is what govspeak actually emits, whatever the
    markup declares.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[tuple[list[str], list[list[str]]]] = []
        self._in_table = False
        self._current: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "table":
            self._in_table = True
            self._current: list[list[str]] = []
            return
        if not self._in_table:
            return
        if tag == "tr":
            self._row = []
            self._current.append(self._row)  # type: ignore[union-attr]
        elif tag in ("th", "td") and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self._in_table:
            if self._current:
                headers, rows = self._current[0], self._current[1:]
                self.tables.append((headers, rows))
            self._in_table = False
        elif tag == "tr":
            self._row = None
        elif tag in ("th", "td"):
            if self._cell is not None:
                text = " ".join("".join(self._cell).split())
                self._row.append(text)  # type: ignore[union-attr]
            self._cell = None


def _text_of(cell: str) -> str:
    return " ".join(cell.split())


def parse_effective_from(period_label: str) -> str | None:
    m = _PERIOD_RE.search(period_label)
    if not m:
        return None
    return f"{m.group(1)}-04-01"


def parse_amount(value_text: str) -> float | None:
    m = _AMOUNT_RE.search(value_text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def parse_rates_table(html_body: str) -> list[dict]:
    """Rows as the module stores them, from the page's govspeak HTML."""
    parser = _RatesTableParser()
    parser.feed(html_body)
    rows: list[dict] = []
    for headers, body_rows in parser.tables:
        data_headers = [h for h in headers if h]
        if not data_headers:
            continue
        for body_row in body_rows:
            if not body_row:
                continue
            period_label = _text_of(body_row[0])
            if not period_label:
                continue
            cells = [_text_of(c) for c in body_row[1:]]
            for index, cell in enumerate(cells):
                if index >= len(data_headers):
                    break
                rows.append({
                    "period_label": period_label,
                    "band_label": data_headers[index],
                    "band_role": ("national_living_wage" if index == 0
                                  else "national_minimum_wage"),
                    "value_text": cell,
                })
    return rows


@register_module(
    "m17_statutory_pay_rates",
    supports_since=False,
    since_note="the page is the whole of the rates publication; --since has no meaning",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m17_statutory_pay_rates"
    conn = ctx.conn
    written = 0
    parse_failures = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        result = client.get(RATES_URL)
        if not result.ok:
            db.record_review_item(
                conn, module_name, "rates_page_unavailable", RATES_URL,
                json.dumps({"status": result.status_code}))
            log.info("rates.run_complete", page="unavailable", status=result.status_code)
            return

        data = json.loads(result.body)
        body = ((data.get("details") or {}).get("body") or "").strip()
        if not body:
            db.record_parse_failure(conn, module_name, "rates_body", RATES_URL,
                                    "content API returned no details.body",
                                    source_url=result.url)
            log.info("rates.run_complete", page="no body")
            return

        rows = parse_rates_table(body)
        if not rows:
            db.record_parse_failure(conn, module_name, "rates_table", RATES_URL,
                                    "no rates tables parsed from the page body",
                                    source_url=result.url)
            log.info("rates.run_complete", page="no tables parsed")
            return

        provenance = {
            "source_url": result.url,
            "retrieved_at": result.retrieved_at.isoformat(),
            "http_status": result.status_code,
            "source_system": SOURCE_SYSTEM,
            "payload_sha256": result.payload_sha256,
        }
        for row in ctx.track(rows, "rate rows"):
            amount = parse_amount(row["value_text"])
            if amount is None:
                db.record_parse_failure(
                    conn, module_name, "rate_amount", row["value_text"],
                    f"could not parse an hourly rate from the cell of {row['period_label']!r}",
                    source_url=result.url)
                parse_failures += 1
            db.upsert(conn, "statutory_pay_rates", {
                "period_label": row["period_label"],
                "effective_from": parse_effective_from(row["period_label"]),
                "band_label": row["band_label"],
                "band_role": row["band_role"],
                "amount": amount,
                "value_text": row["value_text"],
                **provenance,
            }, natural_key=["period_label", "band_label"])
            written += 1
            if not ctx.dry_run:
                conn.commit()

    log.info("rates.run_complete", rows=written, parse_failures=parse_failures)
