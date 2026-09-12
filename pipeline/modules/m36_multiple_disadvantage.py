"""Module 36 — Multiple Disadvantage Detailed Local Authority Data.

JON-39's own feasibility pass
(`docs/m30-multiple-disadvantage-feasibility.md`) verified this live: it is
a brand-new MHCLG product, launched 13 August 2026 with three quarters of
history released at once, and it lives as a *separate attachment* on the
exact evergreen page Module 30 already fetches
(`m30_statutory_homelessness.CONTENT_URL`) — not a sheet inside Module 30's
own Table A1 workbook. This module therefore reuses Module 30's discovery
and file-reading directly (`discover_publications`, `read_workbook_sheet`,
`find_anchor_row`, `extract_a1_rows`, `ONS_CODE_RE`, `SUPPORTED_MIMES`,
`to_int`, `to_float`) rather than duplicating them, passing `MD_TITLE_RE`
into `discover_publications` so the one content-API fetch is shared, not
repeated — the same relationship Module 31 already has with Module 30, for
the same reason: one source, shared discovery, not two coincidentally
similar implementations.

The source measures households MHCLG's H-CLIC collection already tracks
(Modules 29-31's own collection) who were assessed as experiencing three or
more of five disadvantages: homelessness/rough sleeping, substance
dependence, mental health issues, domestic abuse, and contact with the
criminal justice system (the source's own "Definitions" sheet). **This is
housing-assessment administrative data, not clinical or treatment data,
despite one column reading "substance dependency."** The flag is a
support-need/referral checkbox recorded by a housing officer at
homelessness assessment, not an NDTMS treatment episode or a diagnosis —
see `docs/CAVEATS.md`'s Module 36 entry, and never read this module's rows
against this pipeline's own NDTMS/Fingertips figures (Modules 7, 12, 27).

Four sheets are read from each edition's workbook:

* `Multiple_Disadvantage_values` (Table 1) — only its published percentage
  column (`md_pct`) is stored. Its other three columns (assessed/
  prevention-secured/relief-secured multiple-disadvantage totals) were
  confirmed, by downloading and comparing real editions, to be exact
  duplicates of the first data column of the three sheets below — reading
  them again would be redundant, not additional coverage.
* `A_Multiple_Disadvantage` (Table 2) — households assessed as owed a duty,
  by category, prefixed `assessed_`.
* `P_Multiple_Disadvantage` (Table 3) — households who secured
  accommodation for 6+ months after a prevention duty ended, by category,
  prefixed `prevention_secured_`.
* `R_Multiple_Disadvantage` (Table 4) — the same after a relief duty ended,
  prefixed `relief_secured_`.

Each of the three category sheets shares one five-category column shape
(`_CATEGORY_FIELDS`); the category label wording is not even consistent
within the source's own workbook ("Substance dependency" on two sheets,
"Substance misuse" on the third, both under the same "Substance dependence"
Definitions entry), so columns are located by keyword substring
(`substance`, `domestic abuse`, `mental health`, `homeless`/`rough
sleeping`, `criminal justice`, `multiple disadvantage`) rather than an
exact phrase.

**The five category totals are not mutually exclusive and must never be
summed to reconstruct the qualifying total** — a household qualifying for
"multiple disadvantage" (3+ of 5) is counted in at least three category
columns at once, so the five columns sum to several times the qualifying
total by construction. `docs/CAVEATS.md` states this in full; this
docstring is a pointer to it, not a restatement.
"""
from __future__ import annotations

import json
import re
from typing import Callable

import structlog

from pipeline import db
from pipeline.http import PipelineHTTPClient
from pipeline.modules.m30_statutory_homelessness import (
    SUPPORTED_MIMES,
    StatutoryHomelessnessParseError,
    discover_publications,
    extract_a1_rows,
    find_anchor_row,
    read_workbook_sheet,
    to_float,
    to_int,
)
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "mhclg_multiple_disadvantage"

MD_VALUES_SHEET = "Multiple_Disadvantage_values"
ASSESSED_SHEET = "A_Multiple_Disadvantage"
PREVENTION_SHEET = "P_Multiple_Disadvantage"
RELIEF_SHEET = "R_Multiple_Disadvantage"

# (record column prefix, sheet name) — same five-category shape on all three,
# confirmed against all three currently-published editions.
STAGES: tuple[tuple[str, str], ...] = (
    ("assessed", ASSESSED_SHEET),
    ("prevention_secured", PREVENTION_SHEET),
    ("relief_secured", RELIEF_SHEET),
)

# Matches this source's own title convention, confirmed against all three
# currently-attached editions (July-September 2025 (revised), October-
# December 2025 (revised), January-March 2026): identical shape to Module
# 30's own TITLE_RE (same three capture groups: start month, end month,
# year), just a different fixed prefix, so `parse_quarter_title` there
# parses this module's titles unchanged once handed this regex.
_MONTH = (r"January|February|March|April|May|June|July|August|September|"
          r"October|November|December")
MD_TITLE_RE = re.compile(
    rf"^Multiple Disadvantage Detailed Local Authority Data:\s*"
    rf"({_MONTH})\s+to\s+({_MONTH})\s+(\d{{4}})\s*(?:\(revised\))?\s*$",
    re.IGNORECASE)

# Table 1's headline metric — MHCLG's own published percentage, never
# recomputed here (it can legitimately exceed 100%; see the source's own
# [note 2] and docs/CAVEATS.md).
_PCT_RE = re.compile(r"\(%\)")

# The five disadvantage categories, plus the qualifying "multiple
# disadvantage" total each of the three stage sheets leads with. Keyword
# substrings, not exact phrases — confirmed necessary by reading all three
# stage sheets' own header text: the "substance" column is labelled
# "Substance dependency total" on two sheets and "Substance misuse total"
# on the third, under one "Substance dependence" Definitions entry.
_MD_TOTAL_RE = re.compile(r"multiple disadvantage total", re.IGNORECASE)
_DOMESTIC_ABUSE_RE = re.compile(r"domestic abuse", re.IGNORECASE)
_MENTAL_HEALTH_RE = re.compile(r"mental health", re.IGNORECASE)
_SUBSTANCE_RE = re.compile(r"substance", re.IGNORECASE)
_HOMELESSNESS_RE = re.compile(r"homeless|rough sleeping", re.IGNORECASE)
_CRIMINAL_JUSTICE_RE = re.compile(r"criminal justice", re.IGNORECASE)

_CATEGORY_FIELDS: tuple[tuple[str, re.Pattern], ...] = (
    ("md_total", _MD_TOTAL_RE),
    ("domestic_abuse_total", _DOMESTIC_ABUSE_RE),
    ("mental_health_total", _MENTAL_HEALTH_RE),
    ("substance_dependency_total", _SUBSTANCE_RE),
    ("homelessness_rough_sleeping_total", _HOMELESSNESS_RE),
    ("criminal_justice_total", _CRIMINAL_JUSTICE_RE),
)
_REQUIRED_CATEGORY_FIELDS = {code for code, _pattern in _CATEGORY_FIELDS}


def to_pct(raw: str) -> float | None:
    """MHCLG's own published percentage, stripped of its trailing '%' and
    handed to Module 30's `to_float` — which already knows this source's
    `[x]`/`[z]` placeholders mean NULL, not zero.
    """
    return to_float((raw or "").replace("%", ""))


def locate_pct_column(rows: list[list[str]], anchor: int) -> dict[str, int]:
    """Resolve `Multiple_Disadvantage_values`' one column this module
    reads. Keyword-located like Module 30's own column locators, even
    though a single header row has been enough in every edition seen so
    far — a future edition splitting the header across several rows (the
    way Module 30's older-era files do) would still resolve correctly.
    """
    header_rows = [r for r in rows[:anchor] if sum(1 for c in r if c) >= 2]
    width = max([len(r) for r in header_rows]
                + [len(rows[anchor]) if anchor < len(rows) else 0])

    def signature(column: int) -> str:
        return " ".join(r[column] for r in header_rows
                         if column < len(r) and r[column])

    for column in range(width):
        if _PCT_RE.search(signature(column)):
            return {"md_pct": column}

    raise StatutoryHomelessnessParseError(
        f"could not locate the percentage column in {MD_VALUES_SHEET!r}")


def locate_category_columns(rows: list[list[str]], anchor: int) -> dict[str, int]:
    """Resolve one stage sheet's six columns (the qualifying total plus its
    five disadvantage categories) by keyword. Shared across all three stage
    sheets (`STAGES`) since they carry one column shape, confirmed against
    all three currently-published editions.
    """
    header_rows = [r for r in rows[:anchor] if sum(1 for c in r if c) >= 2]
    width = max([len(r) for r in header_rows]
                + [len(rows[anchor]) if anchor < len(rows) else 0])

    def signature(column: int) -> str:
        return " ".join(r[column] for r in header_rows
                         if column < len(r) and r[column])

    claimed: dict[str, int] = {}
    taken: set[int] = set()
    for field, pattern in _CATEGORY_FIELDS:
        for column in range(width):
            if column in taken:
                continue
            if pattern.search(signature(column)):
                claimed[field] = column
                taken.add(column)
                break

    missing = _REQUIRED_CATEGORY_FIELDS - claimed.keys()
    if missing:
        raise StatutoryHomelessnessParseError(
            f"could not locate required columns: {sorted(missing)}")
    return claimed


def _read_sheet_columns(
    body: bytes, content_type: str, sheet_name: str,
    locator: Callable[[list[list[str]], int], dict[str, int]],
) -> tuple[list[list[str]], int, dict[str, int]]:
    """One sheet's rows, England-anchor row and resolved columns, or a
    `StatutoryHomelessnessParseError` naming which of the two steps failed
    — the caller turns that into one `multiple_disadvantage_sheet_unreadable`
    review item per sheet, with the sheet name and the exact reason in its
    context, rather than a family of per-sheet item-type strings for what is
    the same two failure modes four times over.
    """
    rows = read_workbook_sheet(body, content_type, sheet_name)
    anchor = find_anchor_row(rows)
    if anchor is None:
        raise StatutoryHomelessnessParseError(f"no anchor row in {sheet_name!r}")
    columns = locator(rows, anchor)
    return rows, anchor, columns


@register_module(
    "m36_multiple_disadvantage", supports_since=True,
    since_note="filters which quarters are written by the quarter's calendar "
               "year; the fetch itself always reads the whole attachment list",
    depends_on=("m00_geography",),
    depends_note="authority names come from the authorities table",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m36_multiple_disadvantage"
    conn = ctx.conn
    since_year = ctx.since_year()

    known_authorities = {row["ons_code"] for row in conn.execute(
        "SELECT ons_code FROM authorities")}
    unmatched_logged: set[str] = set()

    written = 0
    quarters_processed = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        publications = discover_publications(client, title_re=MD_TITLE_RE)
        if not publications:
            raise StatutoryHomelessnessParseError(
                "No Multiple Disadvantage local-authority-level files found "
                "— the GOV.UK title pattern may have changed. Check "
                "MD_TITLE_RE in m36_multiple_disadvantage.")
        log.info("multiple_disadvantage.publications_discovered", count=len(publications))

        if ctx.limit:
            publications = publications[-ctx.limit:]

        for pub in ctx.track(publications, "multiple disadvantage quarters"):
            if since_year and pub["year"] < since_year:
                continue

            attachment = pub["attachment"]
            content_type = attachment.get("content_type")
            if content_type not in SUPPORTED_MIMES:
                db.record_review_item(
                    conn, module_name, "multiple_disadvantage_unsupported_format",
                    attachment.get("url", ""), json.dumps({
                        "quarter": pub["quarter_label"],
                        "content_type": content_type,
                    }))
                continue

            file_result = client.get(attachment["url"])
            if not file_result.ok:
                db.record_review_item(
                    conn, module_name, "multiple_disadvantage_file_unavailable",
                    attachment["url"], json.dumps({"status": file_result.status_code}))
                continue

            try:
                pct_rows, pct_anchor, pct_columns = _read_sheet_columns(
                    file_result.body, content_type, MD_VALUES_SHEET, locate_pct_column)
            except Exception as exc:
                db.record_review_item(
                    conn, module_name, "multiple_disadvantage_sheet_unreadable",
                    attachment["url"], json.dumps({
                        "quarter": pub["quarter_label"], "sheet": MD_VALUES_SHEET,
                        "error": f"{type(exc).__name__}: {exc}"}))
                continue
            pct_by_code = {e["ons_code"]: e.get("md_pct", "")
                           for e in extract_a1_rows(pct_rows, pct_anchor, pct_columns)}

            stage_rows_by_code: dict[str, dict[str, dict]] = {}
            stage_failed = False
            for stage, sheet_name in STAGES:
                try:
                    rows, anchor, columns = _read_sheet_columns(
                        file_result.body, content_type, sheet_name,
                        locate_category_columns)
                except Exception as exc:
                    db.record_review_item(
                        conn, module_name, "multiple_disadvantage_sheet_unreadable",
                        attachment["url"], json.dumps({
                            "quarter": pub["quarter_label"], "sheet": sheet_name,
                            "error": f"{type(exc).__name__}: {exc}"}))
                    stage_failed = True
                    break
                stage_rows_by_code[stage] = {
                    e["ons_code"]: e for e in extract_a1_rows(rows, anchor, columns)}
            if stage_failed:
                continue

            provenance = {
                "source_url": file_result.url,
                "retrieved_at": file_result.retrieved_at.isoformat(),
                "http_status": file_result.status_code,
                "source_system": SOURCE_SYSTEM,
                "payload_sha256": file_result.payload_sha256,
            }

            all_codes = set(pct_by_code)
            for by_code in stage_rows_by_code.values():
                all_codes |= set(by_code)

            snapshot_rows: list[dict] = []
            for ons_code in sorted(all_codes):
                # Every code here already passed `extract_a1_rows`' own
                # ONS_CODE_RE filter when each per-sheet dict was built, so
                # region/England/[z] rows never reach `all_codes` at all.
                if ons_code not in known_authorities:
                    if ons_code not in unmatched_logged:
                        db.record_review_item(
                            conn, module_name, "multiple_disadvantage_unmatched_authority",
                            ons_code, json.dumps({
                                "note": "not in the authorities table — possibly a "
                                        "reorganisation predecessor/successor code "
                                        "this pipeline has not reconciled",
                            }))
                        unmatched_logged.add(ons_code)
                    continue

                record = {
                    "ons_code": ons_code,
                    "quarter_start": pub["quarter_start"],
                    "quarter_label": pub["quarter_label"],
                    **provenance,
                }
                raw_pct = pct_by_code.get(ons_code, "")
                record["md_pct"] = to_pct(raw_pct)
                record["md_pct_text"] = raw_pct or None

                for stage, _sheet_name in STAGES:
                    entry = stage_rows_by_code[stage].get(ons_code, {})
                    for field, _pattern in _CATEGORY_FIELDS:
                        column = f"{stage}_{field}"
                        raw = entry.get(field, "")
                        record[column] = to_int(raw)
                        record[f"{column}_text"] = raw or None

                snapshot_rows.append(record)
                written += 1

            db.upsert_many(
                conn, "multiple_disadvantage_snapshot", snapshot_rows,
                natural_key=["ons_code", "quarter_start"],
            )
            quarters_processed += 1
            if not ctx.dry_run:
                conn.commit()

    log.info("multiple_disadvantage.run_complete",
              quarters=quarters_processed, rows=written)
