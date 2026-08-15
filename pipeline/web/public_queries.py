"""Read-only queries behind the public evidence portal.

Separate from `queries.py`, which the operator UI owns, because the two have
different obligations. The operator UI shows the warehouse as it is, including
the personal-data tables, to one person on their own machine. The portal is
built to be handed to researchers and journalists, and everything it can reach
is a decision to publish.

Three rules hold everywhere in this file:

  * **No restricted_ anything.** Every function declares the tables it reads
    and `_public(...)` refuses the lot if one is a restricted_ table or
    carries a personal-data column. That reuses the guard the export layer
    already uses for constraint 3 rather than re-stating the rule in a weaker
    form: `pipeline.exports.guard_columns` knows about columns like
    `officer_name` that hold personal data without living in a restricted_
    table, and a fresh `startswith('restricted_')` check would not.

  * **No figure without its caveat.** Payloads carry the caveat text next to
    the number, read from the same `_note` columns the export layer uses. The
    portal renders them inline and cannot render a figure without one, which
    only works if they arrive together.

  * **No inference this pipeline refuses to make.** Nothing here divides
    treatment numbers by prevalence, differences workforce census years, or
    computes a per-employee salary. docs/CAVEATS.md leads with the things that
    must not be computed, and an API that computes them anyway would put them
    into circulation with this project's name on them.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date
from typing import Any, Iterator

from pipeline.exports import guard_columns, guard_not_restricted
from pipeline.exports.geojson import LAYER_CAVEATS
from pipeline.notice_urls import notice_page_url
from pipeline.web import health
from pipeline.web.queries import QueryError, _run

# Caveats that must travel with particular figures. Kept here, in one place,
# because the same warning has to appear identically wherever a figure does —
# and because a caveat written inline next to one chart is a caveat that will
# not be there when someone adds a second.
CAVEATS = {
    "indicative_wage": (
        "This is wages and salaries divided by an average employee count. It "
        "is not a pay scale, a median salary, or any individual's earnings. "
        "Headcount averages count part-time staff as whole people and read "
        "lower than actual pay per full-time worker."
    ),
    "nhs_jobs_floor": (
        "NHS Jobs figures cover only adverts whose employer field matched a "
        "known provider name. Providers advertising solely on their own sites "
        "are invisible here. Every count is a floor, not a total."
    ),
    "census_comparability": (
        "Provider participation varies between census rounds. These figures "
        "must not be used to infer overall workforce size, or change over "
        "time, by comparing one year with another."
    ),
    # Two texts, because the honest sentence changed once some figures were
    # checked and others were not. The old single caveat said "every metric is
    # unverified", which stops being true the moment one is -- and a pinned
    # caveat that disappears when it becomes partly wrong leaves the remaining
    # unverified figures charted with nothing said about them at all.
    "census_unverified": (
        "Every workforce census metric is unverified until a human checks it "
        "against the page it was parsed from. Filter on `verified` before "
        "publishing; the Verified column below says which is which."
    ),
    "census_partly_verified": (
        "Some workforce census metrics have been checked against their source "
        "page and some have not. Verified means transcribed correctly — it "
        "does not mean comparable between years. Filter on `verified` before "
        "publishing; the Verified column below says which is which."
    ),
    "grant_not_budget": (
        "A grant allocation is what an authority was allocated by DHSC. A "
        "budget is what the authority planned to spend. They are different "
        "figures from different documents and must not be compared or "
        "substituted for one another."
    ),
    "contract_value": (
        "Contract values are as published in the notice. They are the value "
        "of an award, not spend, and a notice may cover several years, "
        "several lots, or a framework nobody ever called off."
    ),
    "contract_value_sum": (
        "Do not read the sum of these values as sector spend. The corpus "
        "includes cross-government framework notices whose published value is "
        "a ceiling for the whole framework — a handful of them dominate any "
        "total, and none of that money is substance misuse treatment. The "
        "concentration figures beside this total show how much of it comes "
        "from the largest few notices."
    ),
    "contract_provider_match": (
        "Contracts are linked to a provider only where the supplier name in "
        "the notice exactly matches a known alias. Buyers type supplier names "
        "freely, so most notices are unmatched and provider totals here are a "
        "floor. An unmatched notice is not evidence that no known provider "
        "was involved."
    ),
    "contract_window": (
        "Notice dates span only the window the pipeline has collected, which "
        "is not the same as the period contracts were awarded over. Do not "
        "read a trend from it."
    ),
    "treatment_not_need": (
        "Prevalence estimates and treatment numbers use different methods and "
        "populations. This pipeline does not compute unmet need by "
        "subtracting one from the other, and neither should anything reading "
        "this API."
    ),
    "tribunal_component": (
        "A case marked `component` named the provider alongside "
        "co-respondents. It is not a case solely about them, and outcomes are "
        "derived from judgment text rather than structured metadata."
    ),
    "cqc_coverage": (
        "CQC registration covers only some service types. Most community drug "
        "and alcohol provision is not CQC-registered, so this is not a "
        "service map and absence does not mean absence of a service."
    ),
    "ndtms_estimates": (
        "These are modelled estimates published with 95% confidence "
        "intervals, not counts. The interval is part of the figure: an "
        "estimate quoted without it claims a precision the source does not. "
        "Two authorities whose intervals overlap have not been shown to "
        "differ."
    ),
    "ndtms_la_coverage": (
        "Only a small part of each NDTMS publication is local-authority "
        "level — 1 of 44 sheets in the 2024-25 adult report, down from 3 in "
        "2018-19. Numbers in treatment, waiting times and successful "
        "completions are published nationally; use Fingertips for those at "
        "authority level. About 5% of published area names do not resolve to "
        "a single ONS code and are absent here: national and regional "
        "aggregates, combined areas such as \"Cornwall & Isles of Scilly\", "
        "and pre-reorganisation authorities."
    ),
    "ndtms_suppressed": (
        "A cell showing a marker rather than a number is a statistical "
        "disclosure control, kept verbatim from the publication. It does not "
        "mean zero and must not be read, plotted or averaged as zero."
    ),
    "contract_end": (
        "An end date is the contract period as published at notice stage. "
        "Extensions mentioned in the notice are not applied, a framework's "
        "end is not a call-off's end, and none of this is a forecast of what "
        "will be retendered."
    ),
    "evidence_funnel": (
        "Every candidate, promotion and evidence row in this funnel records "
        "a human decision, and who made it. A zero is zero decisions "
        "recorded — it says nothing about the sector, and everything about "
        "how much verification has been done."
    ),
    "collection_freshness": (
        "The date each source table was last written by a pipeline run. A "
        "table that never shows a date has never been collected — absence of "
        "collection is not evidence of absence, and it is drawn as 'never' "
        "rather than as zero."
    ),
    "pfd_stubs": (
        "A large part of this corpus publishes only a metadata stub online, "
        "with the report itself as a PDF that is not linked in the published "
        "data. Those reports have no matters of concern to search. This is a "
        "source limitation, not a finding about the reports."
    ),
    "pfd_mentions": (
        "Being sent a report and being named in one are different facts, "
        "recorded as different mention types. A report can be addressed to a "
        "provider, or name one in its text, or both — and the two counts are "
        "never added together on this page."
    ),
    "pfd_terms": (
        "A term here means the word appears in a coroner's matters of "
        "concern. It is a finding aid — it points at reports worth reading — "
        "not a characterisation of what the coroner found. Read the report."
    ),
    "pfd_areas": (
        "Coroner areas are the districts of the coronial service, not local "
        "authorities. They do not share boundaries and are not mapped as if "
        "they did."
    ),
    "cqc_inspection_dates": (
        "A report date is when an inspection report was published, not when "
        "a rating changed. The ratings beside it are CQC's own record; the "
        "reports are the evidence behind them."
    ),
    "charity_share": (
        "Income from government contracts and grants is shown as a share of "
        "that year's own total income — both figures from the same row of "
        "the same filed accounts. Do not combine it with procurement "
        "contract values: that is arithmetic across different sources."
    ),
    "filing_records": (
        "Filing dates and categories are Companies House's own record of "
        "documents submitted. That a filing exists is a fact; what the "
        "document says is for the reader."
    ),
    "coverage_absence": (
        "A tick means the warehouse holds rows of this kind for this "
        "authority. Its absence is absence of collection, not evidence of "
        "absence — the pipeline has not looked everywhere, and what it has "
        "not looked at is not zero."
    ),
    "budget_detail": (
        "Each line is what the authority planned to spend, as reported to "
        "MHCLG. Amounts are shown as published: no per-capita figures, no "
        "inflation adjustment, and no ratio against the grant allocation or "
        "contract values elsewhere on this page."
    ),
    "compare_layers": (
        "Each chart on this page is one kind of figure from one kind of "
        "document: a grant allocation, a budgeted spend, a treatment estimate, "
        "a contract notice. The charts share axes with each other's "
        "authorities — never with each other's layers. Nothing here is "
        "combined, differenced or divided, and a gap between one chart and "
        "another is not a finding."
    ),
    "charity_accounts": (
        "Charity income and expenditure are as filed in the provider's "
        "registered accounts, per financial year end. They are one source's "
        "figures and may share an axis with each other, and with nothing else "
        "on this page."
    ),
}


def _public(tables: list[str], columns: list[str] | None = None) -> None:
    """Assert that a query reads nothing the portal may not publish.

    Belt and braces over the read-only connection, which stops writes but has
    no opinion about personal data. Called at the top of every function here
    with the tables it is about to read, so the guarantee is testable rather
    than a claim in a docstring.
    """
    for table in tables:
        guard_not_restricted(table)
        if columns:
            guard_columns(table, columns)


def _rows(conn: sqlite3.Connection, sql: str, params: Any = ()) -> list[dict]:
    return [dict(row) for row in _run(conn, sql, params)]


def _one(conn: sqlite3.Connection, sql: str, params: Any = ()) -> dict:
    rows = _run(conn, sql, params)
    return dict(rows[0]) if rows else {}


# --- summary ------------------------------------------------------------------


def _evidence_funnel(conn: sqlite3.Connection) -> dict:
    """Candidate discovery to evidence, in the four steps a person takes.

    The same semantics as the admin Candidates tab (`candidates.counts`):
    undecided is total minus promoted minus rejected, because a candidate
    that was rejected is not waiting and a candidate that was promoted is
    not undecided. Promoted means a human verified it, which is the only
    way anything crosses into an evidence table (migration `0030`).
    """
    discovered = promoted = rejected = 0
    for table in ("cdp_document_candidates", "committee_paper_candidates",
                  "foi_request_candidates"):
        row = _one(conn, f"SELECT COUNT(*) AS total, "
                          f"SUM(CASE WHEN verified = 1 THEN 1 ELSE 0 END) AS promoted, "
                          f"SUM(CASE WHEN rejected = 1 THEN 1 ELSE 0 END) AS rejected "
                          f"FROM {table}")
        discovered += row.get("total") or 0
        promoted += row.get("promoted") or 0
        rejected += row.get("rejected") or 0
    evidence_rows = sum(
        _one(conn, f"SELECT COUNT(*) AS n FROM {table}").get("n") or 0
        for table in ("cdp_documents", "committee_papers", "foi_requests"))
    return {
        "discovered": discovered,
        "undecided": discovered - promoted - rejected,
        "promoted": promoted,
        "rejected": rejected,
        "evidence_rows": evidence_rows,
        "caveat": CAVEATS["evidence_funnel"],
    }


def summary(conn: sqlite3.Connection) -> dict:
    """Landing-page figures. Every one carries what it is and what it is not."""
    _public(["providers", "authorities", "contracts", "workforce_census_metrics",
              "fingertips_indicators", "schema_migrations",
              "cdp_document_candidates", "committee_paper_candidates",
              "foi_request_candidates", "cdp_documents", "committee_papers",
              "foi_requests", "evidence_promotions"])

    providers = _one(conn, "SELECT COUNT(*) AS total, "
                            "SUM(is_target) AS targets FROM providers")
    target = _one(conn, "SELECT canonical_name FROM providers WHERE is_target = 1 LIMIT 1")
    authorities = _one(conn, "SELECT COUNT(*) AS total FROM authorities")
    with_contracts = _one(
        conn, "SELECT COUNT(DISTINCT buyer_ons_code) AS n FROM contracts "
               "WHERE buyer_ons_code IS NOT NULL")
    contracts = _one(
        conn,
        "SELECT COUNT(*) AS total_notices, "
        "       COALESCE(SUM(value_core), 0) AS total_value_gbp, "
        "       SUM(CASE WHEN psr_direct_award_option IS NOT NULL THEN 1 ELSE 0 END) "
        "           AS direct_awards, "
        "       SUM(CASE WHEN psr_basis IS NOT NULL THEN 1 ELSE 0 END) AS psr_notices "
        "FROM contracts")

    latest_census = _one(
        conn, "SELECT MAX(census_year) AS y FROM workforce_census_metrics").get("y")
    census_metrics = _rows(
        conn,
        "SELECT metric, workforce_segment, value, unit, verified "
        "FROM workforce_census_metrics WHERE census_year = ? "
        "  AND metric IN ('vacancy_rate', 'turnover_rate') "
        "ORDER BY metric, workforce_segment",
        (latest_census,)) if latest_census else []

    fingertips = _one(
        conn, "SELECT COUNT(*) AS indicators FROM fingertips_indicators")
    latest_period = _one(
        conn, "SELECT MAX(time_period) AS p FROM fingertips_la_values").get("p")

    modules = _rows(
        conn,
        "SELECT source_system, MAX(retrieved_at) AS last_retrieved FROM ("
        "  SELECT source_system, retrieved_at FROM contracts"
        "  UNION ALL SELECT source_system, retrieved_at FROM authorities"
        "  UNION ALL SELECT source_system, retrieved_at FROM public_health_grants"
        "  UNION ALL SELECT source_system, retrieved_at FROM fingertips_la_values"
        ") WHERE source_system IS NOT NULL GROUP BY source_system")

    return {
        "providers": {
            "total": providers.get("total", 0),
            "target": target.get("canonical_name"),
        },
        "authorities": {
            "total": authorities.get("total", 0),
            "with_contracts": with_contracts.get("n", 0),
        },
        "contracts": {
            "total_notices": contracts.get("total_notices", 0),
            "total_value_gbp": contracts.get("total_value_gbp", 0),
            "direct_awards": contracts.get("direct_awards", 0),
            "psr_notices": contracts.get("psr_notices", 0),
            # Sent so the portal can refuse to headline a total that a few
            # framework ceilings account for. Without it the hero card would
            # read "£15tn of contracts", which is not true of anything.
            "value_is_concentrated": _value_is_concentrated(conn),
            "caveat": CAVEATS["contract_value"],
            "sum_caveat": CAVEATS["contract_value_sum"],
        },
        "workforce": {
            "latest_census_year": latest_census,
            # Deliberately not flattened to a single headline rate. Every one
            # of these is verified = 0, and the portal renders them as
            # awaiting verification rather than as a finding.
            "metrics": census_metrics,
            "all_unverified": bool(census_metrics)
            and all(not m["verified"] for m in census_metrics),
            "caveat": CAVEATS["census_unverified"],
        },
        "fingertips": {
            "latest_period": latest_period,
            "indicators_collected": fingertips.get("indicators", 0),
        },
        "pipeline": {
            "sources": modules,
            "last_run": max((m["last_retrieved"] for m in modules
                              if m["last_retrieved"]), default=None),
        },
        # W-26: the overview's verification funnel. Loaded with the summary
        # because it is cheap -- three small candidate tables and three small
        # evidence tables, unlike freshness below, which is on its own route
        # because it is not cheap.
        "funnel": _evidence_funnel(conn),
    }


# --- providers ----------------------------------------------------------------


# The source tables whose collection recency the overview's freshness bars
# show. An explicit list rather than a scan of the schema, for the same
# reason the admin coverage matrix keeps one: what counts as a source is a
# statement about what the pipeline is for, and a new table appearing should
# not silently join the bars. Table names are module constants and never
# come from a request, so they are safe to interpolate.
FRESHNESS_TABLES: tuple[tuple[str, str], ...] = (
    ("Procurement notices", "contracts"),
    ("Public health grant", "public_health_grants"),
    ("LA revenue budgets", "la_revenue_budgets"),
    ("Fingertips values", "fingertips_la_values"),
    ("Workforce census", "workforce_census_metrics"),
    ("NDTMS statistics", "ndtms_la_statistics"),
    ("PFD reports", "pfd_reports"),
    ("CQC locations", "cqc_locations"),
    ("Charity financials", "charity_financials"),
    ("Company filings", "company_filings"),
    ("Annual report disclosure", "provider_report_disclosure"),
    ("NHS job adverts", "nhs_job_adverts"),
    ("Tribunal cases", "tribunal_cases"),
    ("Authorities", "authorities"),
)


def freshness(conn: sqlite3.Connection) -> dict:
    """Newest `retrieved_at` per source table, for the overview's bars.

    On its own route, not inside `summary`, for the same reason the admin
    freshness panel is: on the real warehouse this is seconds of full table
    scans -- contracts and la_revenue_budgets between them are most of it,
    and neither carries a `retrieved_at` index by decision (P-05 priced and
    declined the twenty-table index). The overview loads it lazily, after
    first paint, so the landing page does not wait for it.
    """
    _public([table for _label, table in FRESHNESS_TABLES])
    union = " UNION ALL ".join(
        f"SELECT '{label}' AS label, '{table}' AS table_name, "
        f"MAX(retrieved_at) AS retrieved_at FROM {table}"
        for label, table in FRESHNESS_TABLES)
    return {
        "tables": _rows(conn, union),
        "caveat": CAVEATS["collection_freshness"],
    }


def _value_is_concentrated(conn: sqlite3.Connection, threshold: float = 0.5) -> bool:
    """True when billion-pound notices carry most of the total value.

    The portal uses this to decide whether a summed headline figure is worth
    showing at all. It is a property of the corpus, measured on each request,
    rather than a threshold someone remembered to apply — so a future run that
    collects a corpus without framework ceilings gets its headline back
    automatically, and one that collects more does not quietly lose the
    warning.
    """
    share = _value_concentration(conn, "", {}).get("share_over_1bn")
    return bool(share and share > threshold)


def providers(conn: sqlite3.Connection) -> list[dict]:
    """Every provider with the counts that make them comparable.

    Contracts join through `supplier_aliases`, because a supplier's name in a
    notice is whatever the buyer typed. Counting on the raw name would split
    one provider across its spellings and undercount every one of them.
    """
    _public(["providers", "supplier_aliases", "contracts", "tribunal_cases",
              "cqc_locations", "nhs_job_adverts", "provider_identifiers",
              "charity_financials"])

    return _rows(conn, """
        SELECT p.provider_key,
               p.canonical_name,
               p.is_target,
               p.notes,
               (SELECT COUNT(*) FROM contracts c
                  JOIN supplier_aliases sa ON sa.alias_raw = c.supplier_name_raw
                 WHERE sa.supplier_key = p.provider_key) AS contract_count,
               (SELECT COALESCE(SUM(c.value_core), 0) FROM contracts c
                  JOIN supplier_aliases sa ON sa.alias_raw = c.supplier_name_raw
                 WHERE sa.supplier_key = p.provider_key) AS contract_value_gbp,
               (SELECT COUNT(*) FROM tribunal_cases t
                 WHERE t.provider_key = p.provider_key) AS tribunal_count,
               (SELECT COUNT(*) FROM cqc_locations l
                 WHERE l.provider_key = p.provider_key) AS cqc_locations,
               (SELECT COUNT(*) FROM nhs_job_adverts n
                 WHERE n.provider_key = p.provider_key) AS nhs_job_advert_count,
               (SELECT cf.total_income FROM charity_financials cf
                  JOIN provider_identifiers pi
                    ON pi.identifier = cf.charity_number
                   AND pi.scheme = 'charity_number'
                 WHERE pi.provider_key = p.provider_key
                 ORDER BY cf.financial_year_end DESC LIMIT 1) AS charity_income_latest,
               (SELECT cf.financial_year_end FROM charity_financials cf
                  JOIN provider_identifiers pi
                    ON pi.identifier = cf.charity_number
                   AND pi.scheme = 'charity_number'
                 WHERE pi.provider_key = p.provider_key
                 ORDER BY cf.financial_year_end DESC LIMIT 1) AS charity_year_latest,
               -- The register identifiers, so the portal can offer a link to
               -- the register rather than printing a number and leaving the
               -- reader to search for it. MIN() because a provider can carry
               -- more than one of a scheme -- a trading subsidiary, a merged
               -- predecessor -- and the list page shows one row per provider;
               -- the deep dive shows every edge.
               (SELECT MIN(pi.identifier) FROM provider_identifiers pi
                 WHERE pi.provider_key = p.provider_key
                   AND pi.scheme = 'company_number') AS company_number,
               (SELECT MIN(pi.identifier) FROM provider_identifiers pi
                 WHERE pi.provider_key = p.provider_key
                   AND pi.scheme = 'charity_number') AS charity_number
        FROM providers p
        ORDER BY p.is_target DESC, contract_value_gbp DESC, p.canonical_name
    """)


# --- contracts ----------------------------------------------------------------


# The value bands W-23's distribution chart is drawn over, in order. Fixed on
# purpose: a histogram whose buckets moved with the filters could not be
# compared with itself, so the same notice sits in the same band whatever
# filters are applied. This tuple is the single declaration -- the SQL CASE
# below is built from it, and the test pins it.
CONTRACT_VALUE_BANDS: tuple[tuple[int | None, int | None, str], ...] = (
    (None, 10_000, "under £10k"),
    (10_000, 100_000, "£10k–£100k"),
    (100_000, 1_000_000, "£100k–£1m"),
    (1_000_000, 10_000_000, "£1m–£10m"),
    (10_000_000, 100_000_000, "£10m–£100m"),
    (100_000_000, 1_000_000_000, "£100m–£1bn"),
    (1_000_000_000, None, "£1bn and above"),
)


def _value_band_case() -> str:
    """A CASE expression over `CONTRACT_VALUE_BANDS`.

    Built from the tuple rather than written alongside it, so the SQL cannot
    drift from the declaration the test pins. The boundaries are module-level
    constants; nothing from a request reaches this string.
    """
    arms = []
    for _lower, upper, label in CONTRACT_VALUE_BANDS:
        if upper is None:
            arms.append(f"ELSE '{label}'")
        else:
            arms.append(f"WHEN c.value_core < {upper} THEN '{label}'")
    return "CASE " + " ".join(arms) + " END"


def _quarter(column: str) -> str:
    """SQLite expression turning an ISO date column into 'YYYY-Qn'."""
    return (f"substr({column}, 1, 4) || '-Q' || "
            f"((CAST(substr({column}, 6, 2) AS INTEGER) + 2) / 3)")


def _ending_soon_window(now: date | None = None) -> tuple[str, str]:
    """The runway window: the two calendar years from `now`, as ISO dates."""
    if now is None:
        now = date.today()
    try:
        end = now.replace(year=now.year + 2)
    except ValueError:  # 29 February in a non-leap target year
        end = now.replace(year=now.year + 2, day=28)
    return now.isoformat(), end.isoformat()


def ending_soon(conn: sqlite3.Connection, clause: str, params: dict,
                now: date | None = None) -> dict:
    """Notices whose published `date_end` falls within two years of `now`.

    A runway, not a forecast: the end date is the period as published at
    notice stage, and the caveat that travels with it says what is not
    applied (extensions, call-offs, retendering). The matched count is the
    provider-match floor the rest of the page uses, so it can be compared
    with nothing it does not share a method with.
    """
    window_start, window_end = _ending_soon_window(now)
    rows = _rows(conn, f"""
        SELECT {_quarter('c.date_end')} AS quarter,
               COUNT(*) AS count,
               SUM(CASE WHEN c.supplier_name_raw IN
                 (SELECT alias_raw FROM supplier_aliases) THEN 1 ELSE 0 END)
                   AS matched
        FROM contracts c{clause}
        {'AND' if clause else 'WHERE'} c.date_end >= :window_start
              AND c.date_end <= :window_end
        GROUP BY quarter ORDER BY quarter""",
        {**params, "window_start": window_start, "window_end": window_end})
    return {
        "rows": rows,
        "window_start": window_start,
        "window_end": window_end,
        "caveat": CAVEATS["contract_end"],
    }


# The notice row, written once and read twice: by the page's table, which sees
# a window onto it, and by the complete CSV export, which sees all of it. They
# were separate SELECTs for exactly one commit, and that is one commit longer
# than two column lists stay identical -- an export whose columns differ from
# the ones the reader was looking at is a different dataset wearing the same
# name.
#
# `{clause}` is the filter fragment `_contract_filters` builds, which is
# assembled from fixed strings with bound parameters. Nothing from a request
# reaches this string.
_NOTICE_SELECT = """
        SELECT c.notice_id, c.title, c.buyer_name, c.buyer_ons_code,
               c.supplier_name_raw, c.value_core, c.value_max, c.currency,
               c.date_published, c.date_start, c.date_end, c.procedure_type,
               c.psr_basis, c.psr_direct_award_option, c.source_url,
               c.retrieved_at, c.payload_sha256,
               -- Appended, not inserted. The CSV export takes its column
               -- order from these keys, and a downstream reader who counted
               -- columns should not have them move underneath them.
               c.source_system, c.notice_web_url
        FROM contracts c{clause}
        ORDER BY c.date_published DESC, c.notice_id"""


def _contract_filters(provider_key, buyer_ons_code, year_from, year_to, psr_only):
    where, params = [], {}
    if provider_key:
        where.append(
            "c.supplier_name_raw IN (SELECT alias_raw FROM supplier_aliases "
            "WHERE supplier_key = :provider_key)")
        params["provider_key"] = provider_key
    if buyer_ons_code:
        where.append("c.buyer_ons_code = :buyer")
        params["buyer"] = buyer_ons_code
    if year_from:
        where.append("substr(c.date_published, 1, 4) >= :year_from")
        params["year_from"] = str(year_from)
    if year_to:
        where.append("substr(c.date_published, 1, 4) <= :year_to")
        params["year_to"] = str(year_to)
    if psr_only:
        where.append("c.psr_basis IS NOT NULL")
    return (f" WHERE {' AND '.join(where)}" if where else ""), params


def contracts(conn: sqlite3.Connection, *, provider_key=None, buyer_ons_code=None,
               year_from=None, year_to=None, psr_only=False, limit=500) -> dict:
    _public(["contracts", "supplier_aliases", "providers"])
    clause, params = _contract_filters(
        provider_key, buyer_ons_code, year_from, year_to, psr_only)

    totals = _one(conn, f"""
        SELECT COUNT(*) AS total,
               COALESCE(SUM(c.value_core), 0) AS total_value_gbp,
               SUM(CASE WHEN c.psr_direct_award_option IS NOT NULL THEN 1 ELSE 0 END)
                   AS direct_award_count
        FROM contracts c{clause}""", params)

    by_year = _rows(conn, f"""
        SELECT substr(c.date_published, 1, 4) AS year, COUNT(*) AS count,
               COALESCE(SUM(c.value_core), 0) AS value_gbp
        FROM contracts c{clause}
        {'AND' if clause else 'WHERE'} c.date_published IS NOT NULL
        GROUP BY year ORDER BY year""", params)

    by_provider = _rows(conn, f"""
        SELECT sa.supplier_key AS provider_key, sa.canonical_name,
               COUNT(*) AS count, COALESCE(SUM(c.value_core), 0) AS value_gbp
        FROM contracts c
        JOIN supplier_aliases sa ON sa.alias_raw = c.supplier_name_raw
        {clause}
        GROUP BY sa.supplier_key, sa.canonical_name
        ORDER BY value_gbp DESC""", params)

    by_procedure = _rows(conn, f"""
        SELECT COALESCE(c.procedure_type, 'not stated') AS procedure_type,
               COUNT(*) AS count
        FROM contracts c{clause}
        GROUP BY procedure_type ORDER BY count DESC""", params)

    # W-23: the corpus's shape, drawn on the contracts page. All three are
    # computed over the same filters as everything else here, so the charts
    # follow the page's controls rather than silently ignoring them.
    by_quarter = _rows(conn, f"""
        SELECT {_quarter('c.date_published')} AS quarter,
               COUNT(*) AS count,
               SUM(CASE WHEN c.value_core IS NOT NULL THEN 1 ELSE 0 END)
                   AS priced
        FROM contracts c{clause}
        {'AND' if clause else 'WHERE'} c.date_published IS NOT NULL
        GROUP BY quarter ORDER BY quarter""", params)

    # Bands in the fixed canonical order, zero-filled: a band that no notice
    # currently falls in renders as 0 rather than vanishing, and the axis
    # cannot reorder with the data.
    present = {row["band_label"]: row["count"] for row in _rows(conn, f"""
        SELECT {_value_band_case()} AS band_label, COUNT(*) AS count
        FROM contracts c{clause}
        {'AND' if clause else 'WHERE'} c.value_core IS NOT NULL
        GROUP BY band_label""", params)}
    value_bands = [{"band_label": label, "count": present.get(label, 0)}
                   for _lower, _upper, label in CONTRACT_VALUE_BANDS]

    top_buyers = _rows(conn, f"""
        SELECT c.buyer_name, c.buyer_ons_code, COUNT(*) AS count,
               COALESCE(SUM(c.value_core), 0) AS value_gbp
        FROM contracts c{clause}
        GROUP BY c.buyer_name, c.buyer_ons_code
        ORDER BY value_gbp DESC LIMIT 25""", params)

    notices = _rows(conn, _NOTICE_SELECT.format(clause=clause) + "\n        LIMIT :limit",
                     {**params, "limit": max(1, min(int(limit), 5000))})
    _add_notice_links(notices)

    return {
        **totals,
        "value_concentration": _value_concentration(conn, clause, params),
        "matched_to_provider": _one(conn, f"""
            SELECT COUNT(*) AS matched FROM contracts c{clause}
            {'AND' if clause else 'WHERE'} c.supplier_name_raw IN
                (SELECT alias_raw FROM supplier_aliases)""", params).get("matched", 0),
        "date_range": _one(conn, f"""
            SELECT MIN(c.date_published) AS earliest, MAX(c.date_published) AS latest
            FROM contracts c{clause}""", params),
        "by_year": by_year,
        "by_provider": by_provider,
        "by_procedure_type": by_procedure,
        "by_quarter": by_quarter,
        "value_bands": value_bands,
        "ending_soon": ending_soon(conn, clause, params),
        "top_buyers": top_buyers,
        "notices": notices,
        "caveats": {
            "value": CAVEATS["contract_value"],
            "value_sum": CAVEATS["contract_value_sum"],
            "provider_match": CAVEATS["contract_provider_match"],
            "window": CAVEATS["contract_window"],
            "contract_end": CAVEATS["contract_end"],
        },
    }


def all_contract_notices(conn: sqlite3.Connection, *, provider_key=None,
                          buyer_ons_code=None, year_from=None, year_to=None,
                          psr_only=False, batch: int = 2000
                          ) -> tuple[int, Iterator[dict]]:
    """Every notice matching these filters, counted first and then streamed.

    `contracts()` above returns a window — 500 rows by default, 5,000 at most —
    because it is answering a page that has to draw charts beside the table.
    This answers a download, where the window is the bug: an export that ships
    the first 500 of 98,636 rows and says nothing looks complete and is 0.5%
    of the corpus.

    The count comes back separately and first, because it has to be written
    into the file's header line before a single row is serialised. Two queries
    over the same filters, so on a warehouse being written to they could in
    principle disagree; the export is taken against a read-only connection and
    the write slot is held by whatever module is running, so in practice they
    see the same snapshot.

    No `deadline()` here, unlike every other read in this file. That guard
    exists to stop a mis-typed operator query hanging a page; a complete export
    of a six-figure corpus is *meant* to take as long as it takes, and the rows
    are handed to the socket as they arrive rather than assembled in memory.
    """
    _public(["contracts", "supplier_aliases"])
    clause, params = _contract_filters(
        provider_key, buyer_ons_code, year_from, year_to, psr_only)
    total = _one(conn, f"SELECT COUNT(*) AS n FROM contracts c{clause}",
                  params).get("n", 0)

    def rows() -> Iterator[dict]:
        cursor = conn.execute(_NOTICE_SELECT.format(clause=clause), params)
        try:
            while True:
                fetched = cursor.fetchmany(batch)
                if not fetched:
                    return
                chunk = [dict(row) for row in fetched]
                _add_notice_links(chunk)
                yield from chunk
        finally:
            cursor.close()

    return total, rows()


def _add_notice_links(notices: list[dict]) -> None:
    """Give every notice row the address a reader should follow, and say where
    that address came from.

    Three fields, and they are three different claims:

      * `source_url` is untouched. It is the API page these bytes came from --
        a paginated OCDS cursor, which is provenance and not a destination.
      * `notice_web_url` is what the release itself published, or NULL.
      * `notice_link` is what to put in front of a reader, with
        `notice_link_basis` saying whether it was published or constructed.

    The construction is a documented mapping from the notice id, verified
    against every archived page (see pipeline/notice_urls.py). It still gets
    labelled, because 84% of rows use it and a reader deserves to know which
    of the two they are following before they cite it.
    """
    for notice in notices:
        published = notice.get("notice_web_url")
        if published:
            notice["notice_link"] = published
            notice["notice_link_basis"] = "published"
            continue
        constructed = notice_page_url(notice.get("source_system"),
                                       notice.get("notice_id"))
        notice["notice_link"] = constructed
        notice["notice_link_basis"] = "constructed" if constructed else None


def _value_concentration(conn, clause: str, params: dict) -> dict:
    """How much of the total comes from how few notices.

    This exists because the honest answer to "what are these contracts worth?"
    in this corpus is "a handful of cross-government framework ceilings, plus
    everything else". A single summed figure states the opposite, and states
    it confidently. Publishing the concentration alongside makes the shape of
    the number visible instead of leaving it to be discovered by whoever
    quotes it.
    """
    total = _one(conn, f"SELECT COALESCE(SUM(value_core), 0) AS v FROM contracts c{clause}",
                  params).get("v") or 0
    largest = _rows(conn, f"""
        SELECT c.notice_id, c.buyer_name, c.title, c.value_core, c.source_url
        FROM contracts c{clause}
        {'AND' if clause else 'WHERE'} c.value_core IS NOT NULL
        ORDER BY c.value_core DESC LIMIT 10""", params)
    top_sum = sum(row["value_core"] or 0 for row in largest)
    # Notices above a billion, as a group. The ten largest were the obvious
    # measure and the wrong one: this corpus holds 130 notices at that scale,
    # so the top ten are a small slice of the distortion rather than the whole
    # of it, and a "top 10 share" of 8% reads as reassuring when 99% of the
    # total comes from framework ceilings.
    huge = _one(conn, f"""
        SELECT COUNT(*) AS n, COALESCE(SUM(c.value_core), 0) AS v
        FROM contracts c{clause}
        {'AND' if clause else 'WHERE'} c.value_core > 1000000000""", params)
    priced = _one(conn, f"""
        SELECT COUNT(*) AS n FROM contracts c{clause}
        {'AND' if clause else 'WHERE'} c.value_core IS NOT NULL""", params).get("n", 0)
    median = _median_value(conn, clause, params)
    mean = (total / priced) if priced else None

    return {
        "total_value_gbp": total,
        "priced_notices": priced,
        "top_10_value_gbp": top_sum,
        "top_10_share": (top_sum / total) if total else None,
        "notices_over_1bn": huge.get("n", 0),
        "value_over_1bn_gbp": huge.get("v", 0),
        "share_over_1bn": (huge.get("v", 0) / total) if total else None,
        "largest": largest,
        "median_value_gbp": median,
        "mean_value_gbp": mean,
        # The gap between these two is the headline. A mean thousands of times
        # its own median is not describing a typical contract, and the portal
        # uses this to decide whether to show a summed figure at all.
        "mean_to_median_ratio": (mean / median) if (mean and median) else None,
    }


def _median_value(conn, clause: str, params: dict) -> float | None:
    """The middle notice, which describes this corpus far better than its mean."""
    values = [r["value_core"] for r in _rows(
        conn,
        f"""SELECT c.value_core FROM contracts c{clause}
            {'AND' if clause else 'WHERE'} c.value_core IS NOT NULL
            ORDER BY c.value_core""", params)]
    if not values:
        return None
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2


# --- pay ----------------------------------------------------------------------


def pay(conn: sqlite3.Connection, *, provider_key=None, year_from=None,
         year_to=None) -> dict:
    """The campaign's central evidence, and the most caveat-heavy payload here."""
    _public(["v_wage_per_employee", "charity_financials", "provider_identifiers",
              "providers", "nhs_job_adverts", "v_nhs_repeat_advertised_roles",
              "workforce_census_metrics"])

    wage_where, wage_params = [], {}
    if provider_key:
        wage_where.append(
            "w.charity_number IN (SELECT identifier FROM provider_identifiers "
            "WHERE provider_key = :provider_key AND scheme = 'charity_number')")
        wage_params["provider_key"] = provider_key
    if year_from:
        wage_where.append("substr(w.financial_year_end, 1, 4) >= :year_from")
        wage_params["year_from"] = str(year_from)
    if year_to:
        wage_where.append("substr(w.financial_year_end, 1, 4) <= :year_to")
        wage_params["year_to"] = str(year_to)
    wage_clause = f" WHERE {' AND '.join(wage_where)}" if wage_where else ""

    charity_wage_series = _rows(conn, f"""
        SELECT w.*,
               pi.provider_key,
               p.canonical_name
        FROM v_wage_per_employee w
        LEFT JOIN provider_identifiers pi
               ON pi.identifier = w.charity_number AND pi.scheme = 'charity_number'
        LEFT JOIN providers p ON p.provider_key = pi.provider_key
        {wage_clause}
        ORDER BY p.canonical_name, w.financial_year_end""", wage_params)

    job_where, job_params = [], {}
    if provider_key:
        job_where.append("n.provider_key = :provider_key")
        job_params["provider_key"] = provider_key
    job_clause = f" WHERE {' AND '.join(job_where)}" if job_where else ""

    adverts = _rows(conn, f"""
        SELECT n.job_reference, n.provider_key, p.canonical_name, n.job_title,
               n.salary_raw, n.salary_min, n.salary_max, n.salary_period,
               n.salary_basis, n.contract_type, n.working_pattern,
               n.posted_date, n.closing_date, n.advert_url,
               n.provider_match_basis, n.source_url, n.retrieved_at
        FROM nhs_job_adverts n
        LEFT JOIN providers p ON p.provider_key = n.provider_key
        {job_clause}
        ORDER BY n.posted_date DESC""", job_params)

    # Banded on annual salaries only. Mixing an hourly rate into a £-per-year
    # histogram would produce a bar at "£12" that means nothing.
    by_band = _rows(conn, f"""
        SELECT CASE
                 WHEN n.salary_min < 20000 THEN 'under £20k'
                 WHEN n.salary_min < 25000 THEN '£20k–£25k'
                 WHEN n.salary_min < 30000 THEN '£25k–£30k'
                 WHEN n.salary_min < 35000 THEN '£30k–£35k'
                 WHEN n.salary_min < 40000 THEN '£35k–£40k'
                 ELSE '£40k and above' END AS salary_band_label,
               COUNT(*) AS count
        FROM nhs_job_adverts n
        {job_clause + (' AND' if job_clause else ' WHERE')}
             n.salary_period = 'year' AND n.salary_min IS NOT NULL
        GROUP BY salary_band_label
        ORDER BY MIN(n.salary_min)""", job_params)

    try:
        repeat_roles = _rows(conn, f"""
            SELECT r.* FROM v_nhs_repeat_advertised_roles r
            {' WHERE r.provider_key = :provider_key' if provider_key else ''}
            ORDER BY r.advert_count DESC""", job_params)
    except QueryError:
        repeat_roles = []

    census = _rows(conn, """
        SELECT census_year, metric, workforce_segment, value, unit, verified,
               source_page, source_url, retrieved_at
        FROM workforce_census_metrics
        ORDER BY census_year, metric, workforce_segment""")

    census_verified = sum(1 for row in census if row["verified"])

    return {
        "charity_wage_series": charity_wage_series,
        "nhs_job_adverts": adverts,
        "nhs_job_by_band": by_band,
        "repeat_advertised_roles": repeat_roles,
        "workforce_census": census,
        "census_all_unverified": bool(census) and census_verified == 0,
        # The counts, so the page can pin the caveat that is true rather than
        # only the one that is true while nothing has been checked. The chart
        # draws every figure whatever its flag, so "some of these are
        # unverified" has to stay pinned until none of them is.
        "census_verified_count": census_verified,
        "census_total": len(census),
        "caveats": {
            "indicative_wage_note": CAVEATS["indicative_wage"],
            "nhs_jobs_floor_note": CAVEATS["nhs_jobs_floor"],
            "census_comparability_note": CAVEATS["census_comparability"],
            "census_unverified_note": CAVEATS["census_unverified"],
            "census_partly_verified_note": CAVEATS["census_partly_verified"],
        },
    }


# --- geography ----------------------------------------------------------------

# Grant types as they are actually recorded, not as they might be named. The
# warehouse holds 21 of them — projected populations, botox notional grants,
# uplifts — and picking the wrong string silently returns an empty map rather
# than failing, which is why each of these is pinned to a value confirmed
# present in the table.
GEOGRAPHY_METRICS = {
    "grant_drug_alcohol": {
        "label": "Public health grant ring-fenced for drug and alcohol treatment",
        "grant_type": "of_which_is_drug_&_alcohol_ring-fenced_funding_total",
        "unit": "gbp",
    },
    "grant_total": {
        "label": "Public health grant allocation, total",
        "grant_type": "allocation",
        "unit": "gbp",
    },
    "grant_per_head": {
        "label": "Public health grant allocation per head",
        "grant_type": "allocation_per_head",
        "unit": "gbp_per_head",
    },
    "budget_public_health": {
        "label": "Local authority budgeted public health spend",
        "unit": "gbp",
    },
    "treatment_numbers": {
        "label": "Numbers in treatment",
        "unit": "count",
    },
    "contract_value": {
        "label": "Contract value awarded, by buyer",
        "unit": "gbp",
    },
}


def geography(conn: sqlite3.Connection, *, metric="grant_total", year=None) -> dict:
    """One value per authority for the choropleth.

    Geometry is deliberately not included: it is 14MB across 317 authorities
    and does not change between metrics. The portal fetches it once from
    /api/v1/boundaries and joins on ons_code.
    """
    _public(["public_health_grants", "v_la_public_health_budget", "authorities",
              "fingertips_la_values", "contracts"])

    if metric not in GEOGRAPHY_METRICS:
        raise QueryError(
            f"Unknown metric {metric!r}. One of: {', '.join(GEOGRAPHY_METRICS)}.")

    spec = GEOGRAPHY_METRICS[metric]
    caveat = CAVEATS["grant_not_budget"]
    params: dict = {}
    unit = spec["unit"]
    status: list[dict] = []

    # A choropleth needs one value per authority. Without a year these
    # queries return one row per authority *per year*, and the map would
    # colour each area by whichever year happened to be drawn last. Default to
    # the most recent year the metric has rather than to "all of them".
    if year is None:
        available = geography_years(conn, metric)
        year = available[0] if available else None

    if "grant_type" in spec:
        year_clause = " AND g.financial_year = :year" if year else ""
        if year:
            params["year"] = year
        params["grant_type"] = spec["grant_type"]
        # Per-head is published as its own grant_type rather than derived by
        # dividing by a population this pipeline does not hold.
        sql = f"""
            SELECT g.ons_code, a.name AS authority_name, a.region,
                   SUM(g.amount) AS value, g.financial_year,
                   g.allocation_status
            FROM public_health_grants g
            JOIN authorities a ON a.ons_code = g.ons_code
            WHERE g.grant_type = :grant_type{year_clause}
            GROUP BY g.ons_code, a.name, a.region, g.financial_year,
                     g.allocation_status
            ORDER BY value DESC"""
        # Later years are published as indicative and firmed up afterwards.
        # Charting the two together would show a fall or rise that is an
        # artefact of how far ahead the announcement was made.
        status = _rows(conn, f"""
            SELECT g.financial_year, g.allocation_status, COUNT(*) AS n
            FROM public_health_grants g
            WHERE g.grant_type = :grant_type{year_clause}
            GROUP BY g.financial_year, g.allocation_status
            ORDER BY g.financial_year""", params)
    elif metric == "budget_public_health":
        year_clause = " AND b.financial_year = :year" if year else ""
        if year:
            params["year"] = year
        sql = f"""
            SELECT b.ons_code, b.authority_name, b.region,
                   SUM(b.budget_gbp) AS value, b.financial_year
            FROM v_la_public_health_budget b
            WHERE 1 = 1{year_clause}
            GROUP BY b.ons_code, b.authority_name, b.region, b.financial_year
            ORDER BY value DESC"""
    elif metric == "treatment_numbers":
        caveat = CAVEATS["treatment_not_need"]
        year_clause = " AND f.time_period = :year" if year else ""
        if year:
            params["year"] = year
        sql = f"""
            SELECT f.ons_code, a.name AS authority_name, a.region,
                   f.value, f.time_period AS financial_year
            FROM fingertips_la_values f
            JOIN authorities a ON a.ons_code = f.ons_code
            JOIN fingertips_indicators i ON i.indicator_id = f.indicator_id
            WHERE i.topic = 'numbers_in_treatment' AND f.value IS NOT NULL
                  AND f.area_level = 'local_authority'
                  {year_clause}
            ORDER BY f.value DESC"""
    else:  # contract_value
        caveat = CAVEATS["contract_value"]
        sql = """
            SELECT c.buyer_ons_code AS ons_code, a.name AS authority_name, a.region,
                   COALESCE(SUM(c.value_core), 0) AS value, NULL AS financial_year
            FROM contracts c
            JOIN authorities a ON a.ons_code = c.buyer_ons_code
            GROUP BY c.buyer_ons_code, a.name, a.region
            ORDER BY value DESC"""

    features = _rows(conn, sql, params)
    values = [f["value"] for f in features if f["value"] is not None]

    return {
        "metric": metric,
        "metric_label": spec["label"],
        "year": year,
        "unit": unit,
        "allocation_status": status,
        "features": features,
        # The mean across authorities, labelled as such. Not "the England
        # figure", which is a different number published separately and would
        # be wrong to imply.
        "authority_mean": (sum(values) / len(values)) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "caveat": caveat,
    }


def geography_years(conn: sqlite3.Connection, metric: str) -> list[str]:
    _public(["public_health_grants", "v_la_public_health_budget", "fingertips_la_values"])
    spec = GEOGRAPHY_METRICS.get(metric, {})
    if "grant_type" in spec:
        rows = _rows(conn, "SELECT DISTINCT financial_year AS y FROM public_health_grants "
                            "WHERE grant_type = ? ORDER BY y DESC", (spec["grant_type"],))
    elif metric == "budget_public_health":
        rows = _rows(conn, "SELECT DISTINCT financial_year AS y "
                            "FROM v_la_public_health_budget ORDER BY y DESC")
    elif metric == "treatment_numbers":
        rows = _rows(conn, "SELECT DISTINCT f.time_period AS y FROM fingertips_la_values f "
                            "JOIN fingertips_indicators i ON i.indicator_id = f.indicator_id "
                            "WHERE i.topic = 'numbers_in_treatment' "
                            "  AND f.area_level = 'local_authority' ORDER BY y DESC")
    else:
        rows = []
    return [r["y"] for r in rows if r["y"]]


def boundaries(conn: sqlite3.Connection) -> dict:
    """Authority boundaries as a GeoJSON FeatureCollection.

    From `authorities.geometry_geojson`, which Module 0 already collected from
    the ONS Open Geography Portal with provenance. The alternative — shipping
    a boundary file fetched separately at build time — would put a second,
    unversioned copy of the same geography in the tree and leave the portal
    drawing different boundaries from the ones every figure is keyed to.
    """
    _public(["authorities"])
    rows = _run(conn, """
        SELECT ons_code, name, region, geometry_geojson, source_url, retrieved_at
        FROM authorities
        WHERE geometry_geojson IS NOT NULL
        ORDER BY ons_code""")

    import json

    features = []
    for row in rows:
        try:
            geometry = json.loads(row["geometry_geojson"])
        except (TypeError, ValueError):
            continue
        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "ons_code": row["ons_code"],
                "name": row["name"],
                "region": row["region"],
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "source_url": rows[0]["source_url"] if rows else None,
            "retrieved_at": max((r["retrieved_at"] for r in rows if r["retrieved_at"]),
                                 default=None),
            "count": len(features),
        },
    }


# --- fingertips ---------------------------------------------------------------


def fingertips(conn: sqlite3.Connection, *, indicator_id=None, topic=None,
                ons_code=None, substance=None) -> dict:
    _public(["fingertips_indicators", "fingertips_la_values"])

    ind_where, params = [], {}
    if indicator_id:
        ind_where.append("i.indicator_id = :indicator_id")
        params["indicator_id"] = int(indicator_id)
    if topic:
        ind_where.append("i.topic = :topic")
        params["topic"] = topic
    if substance:
        ind_where.append("i.substance = :substance")
        params["substance"] = substance
    ind_clause = f" WHERE {' AND '.join(ind_where)}" if ind_where else ""

    indicators = _rows(conn, f"""
        SELECT i.indicator_id, i.indicator_name, i.topic, i.substance, i.unit,
               i.definition, i.source_url, i.retrieved_at
        FROM fingertips_indicators i{ind_clause}
        ORDER BY i.topic, i.indicator_name""", params)

    if not indicators:
        return {"indicators": [], "series": [], "england_series": [],
                 "caveat": CAVEATS["treatment_not_need"]}

    ids = [i["indicator_id"] for i in indicators]
    placeholders = ", ".join(f":i{n}" for n in range(len(ids)))
    value_params = {f"i{n}": v for n, v in enumerate(ids)}

    area_clause = ""
    if ons_code:
        area_clause = " AND f.ons_code = :ons_code"
        value_params["ons_code"] = ons_code

    series = _rows(conn, f"""
        SELECT f.indicator_id, f.ons_code, f.area_name AS authority_name,
               f.time_period, f.time_period_sortable, f.value,
               f.lower_ci_95, f.upper_ci_95, f.value_note,
               f.source_url, f.retrieved_at
        FROM fingertips_la_values f
        WHERE f.indicator_id IN ({placeholders}){area_clause}
          AND f.area_level = 'local_authority'
        ORDER BY f.indicator_id, f.time_period_sortable""", value_params)

    england = _rows(conn, f"""
        SELECT f.indicator_id, f.time_period, f.time_period_sortable, f.value
        FROM fingertips_la_values f
        WHERE f.indicator_id IN ({placeholders}) AND f.area_level = 'england'
        ORDER BY f.indicator_id, f.time_period_sortable""",
        {k: v for k, v in value_params.items() if k != "ons_code"})

    return {
        "indicators": indicators,
        "series": series,
        "england_series": england,
        "caveat": CAVEATS["treatment_not_need"],
    }


def authorities(conn: sqlite3.Connection) -> list[dict]:
    _public(["authorities"])
    return _rows(conn, "SELECT ons_code, name, type, region FROM authorities "
                        "ORDER BY name")


# --- NDTMS published statistics -----------------------------------------------
#
# 17,231 local-authority rows that the portal did not read at all until now.
# They are almost entirely modelled estimates published with 95% confidence
# intervals -- opiate and crack use, alcohol dependency, deaths in treatment --
# and the interval is not decoration on them. So the shape of this endpoint is
# built around keeping the bounds attached to the estimate they belong to,
# rather than returning a flat list of rows and hoping the page pairs them up.

# What each source table is, in a phrase. Keyed by the `table_ref` the parser
# recorded, which is the sheet name in the published ODS and varies between
# editions -- the same figures live under `Table_2_1` in one year and
# `2_1_Drug_prevalence` in another.
NDTMS_TABLES = {
    "Table_2_1": "Opiate and crack use, estimated",
    "2_1_Drug_prevalence": "Opiate and crack use, estimated",
    "Table_2_2": "Alcohol dependency, estimated",
    "2_2_Alcohol_prevalence": "Alcohol dependency, estimated",
    "Table_9_2": "Deaths in treatment, observed against expected",
    "Table_10_2": "Deaths in treatment, observed against expected",
    "10_2_Deaths": "Deaths in treatment, observed against expected",
}

# Indicator names carrying a bound, as published. Two shapes: a suffix on the
# measure's own name ("Crack cocaine (number) lower bound 95% CI"), and a
# standalone column belonging to whatever the sheet's point estimate is
# ("Lower bound to confidence interval (CI)"). Both are matched literally --
# no fuzzy matching, because a mis-paired bound would silently widen or
# narrow somebody's confidence interval.
_NDTMS_BOUNDS = {
    "lower bound 95% ci": "lower",
    "upper bound 95% ci": "upper",
    "lower bound to ci": "lower",
    "upper bound to ci": "upper",
    "lower bound to confidence interval (ci)": "lower",
    "upper bound to confidence interval (ci)": "upper",
    "lower ci": "lower",
    "upper ci": "upper",
}


def _ndtms_role(indicator: str) -> tuple[str, str]:
    """(measure, role) for a published indicator name.

    role is 'lower', 'upper' or 'point'. A measure of '' means the bound is
    a standalone column and belongs to the sheet's own point estimate, which
    `_ndtms_pair` resolves -- and refuses to guess at when there is more than
    one candidate.
    """
    name = (indicator or "").strip()
    lowered = name.lower()

    if lowered in _NDTMS_BOUNDS:
        return "", _NDTMS_BOUNDS[lowered]

    for suffix, role in _NDTMS_BOUNDS.items():
        if lowered.endswith(" " + suffix):
            return name[: -(len(suffix) + 1)].strip(), role

    return name, "point"


def _ndtms_pair(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split published rows into estimates-with-bounds and everything else.

    Rows are grouped by everything that makes a figure a different figure --
    publication, sheet, area, period, age group -- and bounds are attached
    within a group only.

    A standalone bound attaches to the group's point estimate when exactly one
    measure looks like one. Where a sheet has several (Table 2.2 carries a
    dependency estimate, a mid-year population and a rate side by side), the
    bound is left unattached and the estimate is drawn without a band rather
    than with somebody else's. Guessing here would be inventing a confidence
    interval, which is worse than not drawing one.
    """
    groups: dict[tuple, dict] = {}
    for row in rows:
        key = (row["publication_slug"], row["table_ref"], row["ons_code"],
                row["time_period"], row["age_group"])
        measure, role = _ndtms_role(row["indicator"])
        group = groups.setdefault(key, {"points": {}, "bounds": {}, "loose": {}})
        if role == "point":
            group["points"][measure] = row
        elif measure:
            group["bounds"].setdefault(measure, {})[role] = row
        else:
            group["loose"][role] = row

    estimates: list[dict] = []
    other: list[dict] = []

    for key, group in groups.items():
        # Which measure the standalone bounds belong to, if it is unambiguous.
        named = [m for m in group["points"] if "point estimate" in m.lower()]
        anchor = named[0] if len(named) == 1 else None

        for measure, row in group["points"].items():
            bounds = dict(group["bounds"].get(measure, {}))
            if measure == anchor:
                bounds = {**group["loose"], **bounds}

            # Non-numeric point rows are context, not measures: "Region" and
            # "PHE Region" arrive as indicators carrying a name in value_text.
            if row["value"] is None:
                other.append(_ndtms_row(row, measure))
                continue

            estimates.append({
                **_ndtms_row(row, measure),
                "value": row["value"],
                "lower": (bounds.get("lower") or {}).get("value"),
                "upper": (bounds.get("upper") or {}).get("value"),
                # Said plainly rather than left to be inferred from two nulls:
                # a missing band and an unpublished band look the same on a
                # chart and are not the same fact.
                "has_interval": bool(bounds.get("lower") and bounds.get("upper")),
            })

    estimates.sort(key=lambda e: (e["dataset"], e["measure"],
                                    e["time_period"] or "", e["published_in"] or ""))
    other.sort(key=lambda o: (o["dataset"], o["measure"]))
    return estimates, other


def _ndtms_row(row: dict, measure: str) -> dict:
    return {
        "dataset": NDTMS_TABLES.get(row["table_ref"], row["table_ref"]),
        "table_ref": row["table_ref"],
        "measure": measure or row["indicator"],
        "ons_code": row["ons_code"],
        "authority_name": row["authority_name"] or row["area_name_raw"],
        # Two different years, kept apart. `time_period` is the period the
        # estimate covers and is often absent; `financial_year` is the edition
        # of the publication it was read from. Folding one into the other
        # would date a 2017 mid-year estimate to 2019 because a 2019 report
        # reprinted it.
        "time_period": row["time_period"] or None,
        "age_group": row["age_group"],
        "published_in": row["financial_year"],
        # Kept whatever the value is. Where `value` is NULL this is the
        # published marker -- 'c', '*' -- and it is not zero.
        "value_text": row["value_text"],
        "source_url": row["source_url"],
        "retrieved_at": row["retrieved_at"],
    }


def ndtms(conn: sqlite3.Connection, *, ons_code=None, table_ref=None) -> dict:
    """Local-authority NDTMS figures for one authority, or the catalogue.

    Called without an authority this returns what is available rather than
    17,231 rows: which sheets, how many authorities each covers, and which
    publications they came from.
    """
    _public(["ndtms_la_statistics", "ndtms_publications", "authorities"])

    datasets = _rows(conn, """
        SELECT s.table_ref, COUNT(*) AS rows,
               COUNT(DISTINCT s.ons_code) AS authorities,
               COUNT(DISTINCT s.publication_slug) AS publications
        FROM ndtms_la_statistics s
        WHERE s.ons_code IS NOT NULL
        GROUP BY s.table_ref
        ORDER BY rows DESC""")
    for dataset in datasets:
        dataset["label"] = NDTMS_TABLES.get(dataset["table_ref"], dataset["table_ref"])

    publications = _rows(conn, """
        SELECT publication_slug, title, financial_year, cohort, document_url,
               sheets_total, sheets_local_authority, source_url, retrieved_at
        FROM ndtms_publications
        ORDER BY financial_year DESC""")

    payload = {
        "datasets": datasets,
        "publications": publications,
        "caveats": {
            "estimates": CAVEATS["ndtms_estimates"],
            "coverage": CAVEATS["ndtms_la_coverage"],
            "suppressed": CAVEATS["ndtms_suppressed"],
            "not_need": CAVEATS["treatment_not_need"],
        },
    }

    if not ons_code:
        return {**payload, "estimates": [], "other_rows": [], "authority": None}

    where = ["s.ons_code = :ons_code"]
    params: dict = {"ons_code": ons_code}
    if table_ref:
        where.append("s.table_ref = :table_ref")
        params["table_ref"] = table_ref

    rows = _rows(conn, f"""
        SELECT s.publication_slug, s.table_ref, s.ons_code, s.area_name_raw,
               s.age_group, s.time_period, s.indicator, s.value, s.value_text,
               s.financial_year, s.source_url, s.retrieved_at,
               a.name AS authority_name
        FROM ndtms_la_statistics s
        LEFT JOIN authorities a ON a.ons_code = s.ons_code
        WHERE {' AND '.join(where)}""", params)

    estimates, other = _ndtms_pair(rows)
    return {
        **payload,
        "authority": _one(conn, "SELECT ons_code, name, region FROM authorities "
                                 "WHERE ons_code = ?", (ons_code,)),
        "estimates": estimates,
        "other_rows": other,
    }


# --- PFD reports --------------------------------------------------------------
#
# W-25: 1,539 coroners' Prevention of Future Deaths reports were collected,
# caveated and never displayed. Three constraints from the finding are baked
# into the payload shape rather than left to the page:
#
#   * `restricted_pfd_persons` and `restricted_pfd_report_text` are not read,
#     not listed, and refused by `_public` if a future edit adds them. The
#     names live only there, on purpose.
#   * Being *sent* a report and being *named* in one are different facts
#     (`pfd_provider_mentions.mention_type`) and stay separate keys in
#     `mentions`, never one series.
#   * The metadata stubs -- reports whose PDF-only text was never published
#     as data -- are counted in `totals` and on the year chart, not in a
#     footnote.


def _pfd_year(report_date: str | None) -> int | None:
    """The year in a report date as judiciary.uk wrote it.

    `pfd_reports.report_date` is verbatim source text with no single shape
    -- '10/04/2026', '12 March 2026', 'March 2026' -- so the year is read
    with a pattern rather than assumed at a position, and the page shows the
    verbatim text in its table. A year this cannot find is absent from the
    year chart, not guessed.
    """
    if not report_date:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", report_date)
    return int(match.group(0)) if match else None


def pfd(conn: sqlite3.Connection) -> dict:
    """The sector-level view of the coroners' report corpus."""
    _public(["pfd_reports", "pfd_concern_terms", "pfd_provider_mentions",
              "pfd_recipients"])

    reports = _rows(conn, """
        SELECT report_ref, report_date, coroner_area, categories, report_url,
               matters_of_concern IS NOT NULL AS has_concerns,
               source_url, retrieved_at
        FROM pfd_reports""")

    by_year: dict[int, dict] = {}
    by_area: dict[str, int] = {}
    for report in reports:
        year = _pfd_year(report["report_date"])
        if year is not None:
            bucket = by_year.setdefault(
                year, {"year": year, "reports": 0, "with_concerns": 0})
            bucket["reports"] += 1
            bucket["with_concerns"] += int(report["has_concerns"])
        if report["coroner_area"]:
            by_area[report["coroner_area"]] = (
                by_area.get(report["coroner_area"], 0) + 1)

    mentions = _one(conn, """
        SELECT SUM(CASE WHEN mention_type = 'recipient' THEN 1 ELSE 0 END) AS sent,
               SUM(CASE WHEN mention_type = 'body_text' THEN 1 ELSE 0 END) AS named
        FROM pfd_provider_mentions""")

    return {
        "totals": {
            "reports": len(reports),
            "with_concerns": sum(1 for r in reports if r["has_concerns"]),
            # The rest are the metadata stubs: published as data without the
            # matters of concern, which live in a PDF the publication does
            # not link. Shown here and on the chart, never in a footnote.
            "stubs": sum(1 for r in reports if not r["has_concerns"]),
        },
        "by_year": [by_year[y] for y in sorted(by_year)],
        "by_coroner_area": [
            {"coroner_area": area, "reports": count}
            for area, count in sorted(by_area.items(),
                                      key=lambda kv: -kv[1])[:25]],
        # The finding aid: summed occurrences across reports, not a
        # characterisation of any one report.
        "concern_terms": _rows(conn, """
            SELECT term, SUM(occurrences) AS occurrences
            FROM pfd_concern_terms GROUP BY term
            ORDER BY occurrences DESC, term LIMIT 25"""),
        "mentions": {
            "sent_to_providers": mentions.get("sent") or 0,
            "naming_providers": mentions.get("named") or 0,
            "recipient_organisations": _one(
                conn, "SELECT COUNT(DISTINCT organisation_name) AS n "
                      "FROM pfd_recipients").get("n", 0),
        },
        # Ordered by the coroner's own reference, which opens with the year
        # ('2026-0213'), so newest-first is lexicographic rather than a sort
        # over the source's varied date text.
        "recent": _rows(conn, """
            SELECT report_ref, report_date, coroner_area, categories,
                   report_url, matters_of_concern IS NOT NULL AS has_concerns,
                   source_url, retrieved_at
            FROM pfd_reports ORDER BY report_ref DESC LIMIT 50"""),
        "caveats": {
            "stubs": CAVEATS["pfd_stubs"],
            "mentions": CAVEATS["pfd_mentions"],
            "terms": CAVEATS["pfd_terms"],
            "areas": CAVEATS["pfd_areas"],
        },
    }


# --- provider deep dive -------------------------------------------------------


def provider_timeline(conn: sqlite3.Connection, provider_key: str) -> dict:
    """Every dated piece of evidence about one provider, in order.

    Each event keeps its own source URL and retrieval stamp rather than the
    timeline carrying one for the lot: they come from five different sources
    fetched on different days, and a single provenance line covering all of
    them would be a claim nobody could check.
    """
    _public(["providers", "charity_financials", "provider_identifiers",
              "tribunal_cases", "nhs_job_adverts", "contracts", "supplier_aliases",
              "cqc_locations", "v_entity_edges", "cqc_location_reports",
              "provider_report_disclosure", "provider_annual_reports",
              "v_provider_disclosure_gaps", "company_filings",
              "pfd_provider_mentions", "pfd_reports"])

    provider = _one(conn, "SELECT * FROM providers WHERE provider_key = ?",
                     (provider_key,))
    if not provider:
        raise QueryError(f"No provider {provider_key!r}.")

    events: list[dict] = []

    for row in _rows(conn, """
        SELECT cf.financial_year_end AS date, cf.total_income, cf.total_expenditure,
               cf.source_url, cf.retrieved_at, cf.payload_sha256
        FROM charity_financials cf
        JOIN provider_identifiers pi ON pi.identifier = cf.charity_number
                                     AND pi.scheme = 'charity_number'
        WHERE pi.provider_key = ?""", (provider_key,)):
        events.append({
            "date": row["date"], "event_type": "charity_accounts",
            "label": "Annual accounts",
            "value_summary": f"Income £{(row['total_income'] or 0):,.0f}",
            "source_url": row["source_url"], "retrieved_at": row["retrieved_at"],
            "payload_sha256": row["payload_sha256"],
        })

    for row in _rows(conn, """
        SELECT decision_date AS date, case_number, outcome, outcome_confidence,
               provider_match_basis, source_url, retrieved_at
        FROM tribunal_cases WHERE provider_key = ?""", (provider_key,)):
        events.append({
            "date": row["date"], "event_type": "tribunal",
            "label": "Employment tribunal judgment",
            "value_summary": f"{row['case_number']} — {row['outcome'] or 'outcome not parsed'}",
            "confidence": row["outcome_confidence"],
            "caveat": CAVEATS["tribunal_component"]
            if row["provider_match_basis"] == "component" else None,
            "source_url": row["source_url"], "retrieved_at": row["retrieved_at"],
        })

    for row in _rows(conn, """
        SELECT posted_date AS date, job_title, salary_raw, advert_url,
               source_url, retrieved_at
        FROM nhs_job_adverts WHERE provider_key = ?""", (provider_key,)):
        events.append({
            "date": row["date"], "event_type": "nhs_job_advert",
            "label": row["job_title"],
            "value_summary": row["salary_raw"],
            "source_url": row["advert_url"] or row["source_url"],
            "retrieved_at": row["retrieved_at"],
        })

    for row in _rows(conn, """
        SELECT c.date_published AS date, c.buyer_name, c.value_core, c.title,
               c.notice_id, c.source_system, c.notice_web_url,
               c.source_url, c.retrieved_at
        FROM contracts c
        JOIN supplier_aliases sa ON sa.alias_raw = c.supplier_name_raw
        WHERE sa.supplier_key = ?""", (provider_key,)):
        value = f" — £{row['value_core']:,.0f}" if row["value_core"] else ""
        # The timeline's "source" link is the one a reader actually follows,
        # so it gets the notice rather than the API cursor the row came from.
        # source_url stays in the payload for anyone checking provenance.
        link = dict(row)
        _add_notice_links([link])
        events.append({
            "date": row["date"], "event_type": "contract_award",
            "label": f"Contract with {row['buyer_name']}{value}",
            "value_summary": row["title"],
            "source_url": row["source_url"], "retrieved_at": row["retrieved_at"],
            "notice_link": link["notice_link"],
            "notice_link_basis": link["notice_link_basis"],
        })

    events = [e for e in events if e["date"]]
    events.sort(key=lambda e: e["date"])

    locations = _rows(conn, """
        SELECT location_id, location_name, local_authority_raw, region,
               overall_rating, overall_rating_date, registration_status,
               source_url, retrieved_at
        FROM cqc_locations WHERE provider_key = ?
        ORDER BY location_name""", (provider_key,))

    edges = _rows(conn, """
        SELECT source_type, source_id, relationship, target_type, target_id,
               target_label, basis, source_url, retrieved_at
        FROM v_entity_edges WHERE source_id = ? OR target_id = ?""",
        (provider_key, provider_key))

    tribunals = _rows(conn, """
        SELECT case_number, decision_date, outcome, outcome_confidence, region,
               hearing_venue_raw, provider_match_basis, document_count, source_url
        FROM tribunal_cases WHERE provider_key = ?
        ORDER BY decision_date DESC""", (provider_key,))

    # --- W-24: the four sources the deep dive stopped at ---------------------
    #
    # Each is single-source and each carries its own caveat. The one rule
    # that matters across them: the government-contract share below is
    # computed within a single row of one source (filed accounts), which the
    # finding explicitly allows -- combining it with procurement values would
    # be the cross-source arithmetic docs/CAVEATS.md forbids, and the caveat
    # says so next to the figure.

    charity_finance = _rows(conn, """
        SELECT cf.financial_year_end, cf.total_income, cf.total_expenditure,
               cf.income_from_govt_contracts, cf.income_from_govt_grants,
               cf.source_url, cf.retrieved_at
        FROM charity_financials cf
        JOIN provider_identifiers pi ON pi.identifier = cf.charity_number
                                     AND pi.scheme = 'charity_number'
        WHERE pi.provider_key = ?
        ORDER BY cf.financial_year_end""", (provider_key,))
    for row in charity_finance:
        income = row["total_income"]
        # The share of one row of one source, computed here so the page does
        # not have to -- and NULL when there is no income to be a share of.
        row["govt_contracts_share"] = (
            (row["income_from_govt_contracts"] or 0) / income) if income else None
        row["govt_grants_share"] = (
            (row["income_from_govt_grants"] or 0) / income) if income else None

    # Inspection reports, not ratings. `report_uri` is a relative address
    # with no documented host (the CQC half of W-15), so the page shows the
    # dates and does not build a link it cannot verify.
    cqc_inspections = _rows(conn, """
        SELECT l.location_name, r.report_date, r.first_visit_date, r.report_uri,
               r.source_url, r.retrieved_at
        FROM cqc_location_reports r
        JOIN cqc_locations l ON l.location_id = r.location_id
        WHERE l.provider_key = ?
        ORDER BY r.report_date DESC""", (provider_key,))

    # What each report *does not* discuss, from the view built over m14's
    # disclosure summary. Every gap row carries the view's own caveat, which
    # says in terms that "not matched" means the search terms did not appear
    # in the extracted text -- a statement about the PDF and the terms, not
    # about the provider.
    disclosure_gaps = _rows(conn, """
        SELECT d.financial_year_end, d.topic, d.search_terms, d.caveat
        FROM v_provider_disclosure_gaps d
        WHERE d.provider_key = ?
        ORDER BY d.financial_year_end, d.topic""", (provider_key,))
    disclosed = _rows(conn, """
        SELECT d.financial_year_end, d.topic
        FROM provider_report_disclosure d
        WHERE d.provider_key = ? AND d.matched = 1
        ORDER BY d.financial_year_end, d.topic""", (provider_key,))
    # A year whose annual report was read but has no disclosure rows at all
    # was never searched. Distinct from every "not matched" cell above, and
    # carried under its own key so the matrix can draw it as its own state:
    # a report m14 did not get to is not a report that said nothing.
    disclosure_not_searched = _rows(conn, """
        SELECT ar.financial_year_end, ar.document_url
        FROM provider_annual_reports ar
        LEFT JOIN provider_report_disclosure d
               ON d.provider_key = ar.provider_key
              AND d.financial_year_end = ar.financial_year_end
        WHERE ar.provider_key = ? AND d.provider_key IS NULL
        ORDER BY ar.financial_year_end""", (provider_key,))

    filings = _rows(conn, """
        SELECT f.filing_date, f.category, f.subcategory, f.description,
               f.document_url, f.source_url, f.retrieved_at
        FROM company_filings f
        JOIN provider_identifiers pi ON pi.identifier = f.company_number
                                     AND pi.scheme = 'company_number'
        WHERE pi.provider_key = ?
        ORDER BY f.filing_date DESC""", (provider_key,))

    # --- W-25: the reports that mention this provider -------------------------
    #
    # The deep dive's half of the PFD finding: each report is linked to the
    # coroner's published page, and the mention type says which of the two
    # facts it is. The caveat about never summing them is pinned on the
    # sector page and carried here too, because this list has the same
    # trap in miniature.
    pfd_mentions = _rows(conn, """
        SELECT m.report_ref, m.mention_type, m.matched_name,
               r.report_date, r.coroner_area, r.report_url
        FROM pfd_provider_mentions m
        JOIN pfd_reports r ON r.report_ref = m.report_ref
        WHERE m.provider_key = ?
        ORDER BY r.report_ref DESC""", (provider_key,))

    return {
        "provider": provider,
        "events": events,
        "cqc_locations": locations,
        "entity_edges": edges,
        "tribunal_cases": tribunals,
        "charity_finance": charity_finance,
        "cqc_inspections": cqc_inspections,
        "disclosure": {
            "gaps": disclosure_gaps,
            "disclosed": disclosed,
            "not_searched": disclosure_not_searched,
            # The topics searched for this provider, for the matrix's rows.
            # m14 writes every topic for every report it reads, so a topic
            # absent from a searched year's cells is one that matched.
            "topics": sorted({row["topic"] for row in disclosure_gaps}
                             | {row["topic"] for row in disclosed}),
        },
        "filings": filings,
        "pfd_mentions": pfd_mentions,
        "caveats": {
            "cqc_coverage": CAVEATS["cqc_coverage"],
            "tribunal_component": CAVEATS["tribunal_component"],
            "cqc_inspection_dates": CAVEATS["cqc_inspection_dates"],
            "charity_share": CAVEATS["charity_share"],
            "filing_records": CAVEATS["filing_records"],
            "pfd_mentions": CAVEATS["pfd_mentions"],
        },
    }


# --- authority deep dive -------------------------------------------------------
#
# W-13: "what does my authority get?" is the campaign's own question and the
# portal had no surface that answered it, while /api/v1/contracts had accepted
# `buyer_ons_code` since it was written and no control anywhere set it. This is
# the provider deep-dive shape applied to an authority: grant allocation,
# budgeted spend, treatment estimates with their paired intervals, and
# contracts let.
#
# The four figure sections reuse the existing endpoint functions rather than
# re-writing their queries, so a number on this page cannot disagree with the
# same number on the page it came from — and the test that pins that agreement
# would fail the moment anyone replaced the reuse with a hand-written query.
# Grant and budget stay separate keys and are never summed or divided: the
# CAVEATS rule that a grant allocation is not a budgeted spend is exactly the
# reason they sit side by side on the page and nowhere else.


def _coverage_cells(conn: sqlite3.Connection, ons_code: str) -> dict[str, int]:
    """How many rows of each evidence kind the warehouse holds for one authority.

    The same declaration the admin Health tab's coverage matrix uses, read
    from health.py rather than re-declared here — a second copy of what
    "covered" means would be a second statement free to drift. W-12's pin is
    that the two answers agree row for row.
    """
    def exists(name: str) -> bool:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (name,)).fetchone() is not None

    cells: dict[str, int] = {}
    for label, table, column, _module in health.COVERAGE_COLUMNS:
        if not exists(table):
            cells[label] = 0
            continue
        # Table and column names come from health.COVERAGE_COLUMNS, which is
        # code, not a request, so interpolating them is the same trust as the
        # admin matrix.
        cells[label] = _one(
            conn, f"SELECT COUNT(*) AS n FROM {table} WHERE {column} = ?",
            (ons_code,)).get("n", 0)
    return cells


def authority(conn: sqlite3.Connection, ons_code: str) -> dict:
    """Everything the warehouse holds about one authority, in one payload."""
    _public(["authorities", "public_health_grants", "la_revenue_budgets",
              "v_la_public_health_budget", "fingertips_indicators",
              "fingertips_la_values", "ndtms_la_statistics", "ndtms_publications",
              "contracts", "supplier_aliases", "providers", "cqc_locations",
              "cdp_documents", "cdp_document_candidates", "committee_papers",
              "committee_paper_candidates", "foi_requests",
              "foi_request_candidates"])

    authority_row = _one(
        conn, "SELECT ons_code, name, type, region FROM authorities "
              "WHERE ons_code = ?", (ons_code,))
    if not authority_row:
        raise QueryError(f"No authority {ons_code!r}.")

    # Grant allocation by year, every grant type as recorded. The page draws
    # the allocation and the ring-fenced drug-and-alcohol share as separate
    # lines: the second is part of the first, so they are never summed into
    # one series. Provenance per row, like every other payload here.
    grant = _rows(conn, """
        SELECT financial_year, grant_type, allocation_status, amount, unit,
               source_url, retrieved_at, payload_sha256
        FROM public_health_grants WHERE ons_code = ?
        ORDER BY financial_year, grant_type""", (ons_code,))

    # Budgeted public health spend by year. The same aggregation the geography
    # page's budget metric uses, so the two cannot disagree.
    budget = _rows(conn, """
        SELECT b.financial_year, SUM(b.budget_gbp) AS amount
        FROM v_la_public_health_budget b WHERE b.ons_code = ?
        GROUP BY b.financial_year ORDER BY b.financial_year""", (ons_code,))

    # W-27: the drill-down, by section and line code as published. Amounts
    # only — no per-capita, no deflation, no ratio against the grant. A row
    # whose denomination could not be read carries a NULL amount and a
    # verbatim value_text, kept as it was stored.
    budget_detail = _rows(conn, """
        SELECT financial_year, section, line_code, line_number, column_label,
               amounts_multiplier, amount, value_text
        FROM la_revenue_budgets WHERE ons_code = ?
        ORDER BY financial_year, section, line_number""", (ons_code,))

    # Treatment with its paired intervals, straight from the functions the
    # Treatment page itself uses. `fingertips` carries the series with its
    # lower/upper columns; `ndtms` carries the pairing discipline — a bound
    # attaches to an estimate only where the source's own naming makes it
    # unambiguous.
    treatment = {
        "fingertips": fingertips(conn, topic="numbers_in_treatment",
                                 ons_code=ons_code),
        "ndtms": ndtms(conn, ons_code=ons_code),
    }

    contract_payload = contracts(conn, buyer_ons_code=ons_code, limit=200)
    contracts_held = {
        "total": contract_payload["total"],
        "notices": contract_payload["notices"],
        "caveats": contract_payload["caveats"],
    }

    return {
        "authority": authority_row,
        "coverage": {
            "labels": [label for label, _t, _c, _m in health.COVERAGE_COLUMNS],
            "cells": _coverage_cells(conn, ons_code),
            "caveat": CAVEATS["coverage_absence"],
        },
        "grant": {"rows": grant, "unit": "gbp"},
        "budget": {"rows": budget, "unit": "gbp"},
        "budget_detail": {"rows": budget_detail},
        "treatment": treatment,
        "contracts": contracts_held,
        "caveats": {
            "grant_not_budget": CAVEATS["grant_not_budget"],
            "budget_detail": CAVEATS["budget_detail"],
            "contract_value": CAVEATS["contract_value"],
            "contract_provider_match": CAVEATS["contract_provider_match"],
        },
    }


# --- compare (W-11) -----------------------------------------------------------
#
# "How does my authority compare?" is the campaign's central question, and
# this is the answer in the only shape this pipeline may give it: the reader
# picks the authorities (or providers), and each series is drawn on a shared
# axis with its peers — never on an axis with a different layer. Every series
# here is the existing endpoint's series, composed rather than re-written, so
# a number on this page cannot disagree with the page it came from; the pin
# test holds that composition the same way W-13's does.
#
# The rule this endpoint exists to keep: the four authority charts are four
# different kinds of figure from four different documents. There is no
# cross-chart series, no summed, differenced or divided figure, and each
# series carries the caveat of the layer it came from — comparison is the
# first thing this portal does that is an inference, and the caveats are why
# it stays a reader's inference rather than this project's.


def compare(conn: sqlite3.Connection, *, ons_codes=(), provider_keys=()) -> dict:
    """The existing series for two or more authorities or providers.

    `ons_code` and `provider_key` are each repeatable, named as the rest of
    the API names them. At least one is required. Series are keyed by layer
    and never mixed; `provider_*` series exist because grant, budget and
    treatment are authority figures a provider cannot be plotted against.
    """
    _public(["authorities", "public_health_grants", "v_la_public_health_budget",
              "fingertips_indicators", "fingertips_la_values", "contracts",
              "supplier_aliases", "providers", "charity_financials",
              "provider_identifiers"])

    ons = list(dict.fromkeys(ons_codes))
    keys = list(dict.fromkeys(provider_keys))
    if not ons and not keys:
        raise QueryError("compare needs at least one `ons` or `provider` parameter.")

    authority_rows: list[dict] = []
    provider_rows: list[dict] = []
    if ons:
        placeholders = ", ".join(f":o{n}" for n in range(len(ons)))
        params = {f"o{n}": v for n, v in enumerate(ons)}
        authority_rows = _rows(conn, f"""
            SELECT ons_code, name, region, type FROM authorities
            WHERE ons_code IN ({placeholders}) ORDER BY name""", params)
        missing = [c for c in ons
                   if c not in {a["ons_code"] for a in authority_rows}]
        if missing:
            raise QueryError(f"No authority {missing[0]!r}.")
    if keys:
        placeholders = ", ".join(f":p{n}" for n in range(len(keys)))
        params = {f"p{n}": v for n, v in enumerate(keys)}
        provider_rows = _rows(conn, f"""
            SELECT provider_key, canonical_name, is_target FROM providers
            WHERE provider_key IN ({placeholders}) ORDER BY canonical_name""", params)
        missing = [k for k in keys
                   if k not in {p["provider_key"] for p in provider_rows}]
        if missing:
            raise QueryError(f"No provider {missing[0]!r}.")

    series: dict[str, dict] = {}

    if ons:
        in_clause = ", ".join(f":o{n}" for n in range(len(ons)))
        on_params = {f"o{n}": v for n, v in enumerate(ons)}

        # The allocation series, as the authority page draws it: `allocation`
        # rows in gbp only, with the published status travelling per row so the
        # page can warn when a year is still indicative.
        series["grant"] = {
            "rows": _rows(conn, f"""
                SELECT g.ons_code, a.name AS authority_name, g.financial_year,
                       g.allocation_status, g.amount,
                       g.source_url, g.retrieved_at, g.payload_sha256
                FROM public_health_grants g
                JOIN authorities a ON a.ons_code = g.ons_code
                WHERE g.grant_type = 'allocation' AND g.unit = 'gbp'
                  AND g.ons_code IN ({in_clause})
                ORDER BY g.financial_year, g.ons_code""", on_params),
            "caveat": CAVEATS["grant_not_budget"],
        }

        # The same aggregation the geography page's budget metric uses, scoped
        # to the chosen authorities. The view carries no provenance of its
        # own, so it is attached from the rows the view reads.
        series["budget"] = {
            "rows": _rows(conn, f"""
                SELECT b.ons_code, b.authority_name, b.financial_year,
                       SUM(b.budget_gbp) AS amount
                FROM v_la_public_health_budget b
                WHERE b.ons_code IN ({in_clause})
                GROUP BY b.ons_code, b.authority_name, b.financial_year
                ORDER BY b.financial_year, b.ons_code""", on_params),
            "caveat": CAVEATS["grant_not_budget"],
            "provenance": _source_meta(
                conn, "la_revenue_budgets", "ons_code", "IN", in_clause, on_params),
        }

        # Treatment is the treatment page's own payload per authority,
        # concatenated: same indicators, same series, same paired intervals.
        # The England series is identical for every authority and returned
        # once.
        treatment: dict = {
            "rows": [], "england": [], "indicators": [],
            "caveat": CAVEATS["treatment_not_need"],
        }
        for index, code in enumerate(ons):
            ft = fingertips(conn, topic="numbers_in_treatment", ons_code=code)
            if index == 0:
                treatment["indicators"] = ft["indicators"]
                treatment["england"] = ft["england_series"]
            treatment["rows"].extend(ft["series"])
        series["treatment"] = treatment

        # Contracts by publication year, from the contracts endpoint's own
        # by_year aggregation — so the count and value here are the count and
        # value on the contracts page for each buyer.
        contract_rows: list[dict] = []
        names = {a["ons_code"]: a["name"] for a in authority_rows}
        for code in ons:
            payload = contracts(conn, buyer_ons_code=code)
            for row in payload["by_year"]:
                contract_rows.append({
                    "ons_code": code, "authority_name": names[code], **row})
        series["contracts"] = {
            "rows": contract_rows,
            "caveats": {
                "value": CAVEATS["contract_value"],
                "window": CAVEATS["contract_window"],
            },
            "provenance": _source_meta(
                conn, "contracts", "buyer_ons_code", "IN", in_clause, on_params),
        }

    if keys:
        in_clause = ", ".join(f":p{n}" for n in range(len(keys)))
        key_params = {f"p{n}": v for n, v in enumerate(keys)}

        # Income and expenditure as filed, per financial year end — one
        # source's figures on one axis, the same pairing the deep dive draws.
        series["charity"] = {
            "rows": _rows(conn, f"""
                SELECT pi.provider_key, p.canonical_name, cf.financial_year_end,
                       cf.total_income, cf.total_expenditure,
                       cf.source_url, cf.retrieved_at, cf.payload_sha256
                FROM charity_financials cf
                JOIN provider_identifiers pi
                  ON pi.identifier = cf.charity_number AND pi.scheme = 'charity_number'
                JOIN providers p ON p.provider_key = pi.provider_key
                WHERE pi.provider_key IN ({in_clause})
                ORDER BY cf.financial_year_end, pi.provider_key""", key_params),
            "caveat": CAVEATS["charity_accounts"],
        }

        provider_contract_rows: list[dict] = []
        names = {p["provider_key"]: p["canonical_name"] for p in provider_rows}
        for key in keys:
            payload = contracts(conn, provider_key=key)
            for row in payload["by_year"]:
                provider_contract_rows.append({
                    "provider_key": key, "provider_name": names[key], **row})
        series["provider_contracts"] = {
            "rows": provider_contract_rows,
            "caveats": {
                "provider_match": CAVEATS["contract_provider_match"],
                "window": CAVEATS["contract_window"],
            },
            "provenance": _provider_source_meta(conn, "contracts", keys),
        }

    return {
        "authorities": authority_rows,
        "providers": provider_rows,
        "series": series,
        "caveats": {"cross_layer": CAVEATS["compare_layers"]},
    }


def _source_meta(conn: sqlite3.Connection, table: str, column: str,
                 operator: str, in_clause: str, params: dict) -> dict:
    """Provenance for an aggregated series whose rows do not carry it per
    record: the newest retrieval and a few of the source URLs the rows came
    from. Table and column names are code, not request input — the same trust
    as every other interpolated identifier in this file.
    """
    return {
        "retrieved_at": _one(conn, f"""
            SELECT MAX(retrieved_at) AS retrieved_at FROM {table}
            WHERE {column} {operator} ({in_clause})""", params)
            .get("retrieved_at"),
        "sources": [r["source_url"] for r in _rows(conn, f"""
            SELECT DISTINCT source_url FROM {table}
            WHERE {column} {operator} ({in_clause}) AND source_url IS NOT NULL
            LIMIT 6""", params)],
    }


def _provider_source_meta(conn: sqlite3.Connection, table: str,
                          keys: list[str]) -> dict:
    in_clause = ", ".join(f":p{n}" for n in range(len(keys)))
    params = {f"p{n}": v for n, v in enumerate(keys)}
    return {
        "retrieved_at": _one(conn, f"""
            SELECT MAX(retrieved_at) AS retrieved_at FROM {table}
            WHERE supplier_name_raw IN (
                SELECT alias_raw FROM supplier_aliases WHERE supplier_key IN ({in_clause})
            )""", params).get("retrieved_at"),
        "sources": [r["source_url"] for r in _rows(conn, f"""
            SELECT DISTINCT source_url FROM {table}
            WHERE supplier_name_raw IN (
                SELECT alias_raw FROM supplier_aliases WHERE supplier_key IN ({in_clause})
            ) AND source_url IS NOT NULL LIMIT 6""", params)],
    }


# --- geography map layers (W-19) ----------------------------------------------
#
# The map's overlay layers. Three of them are the export layers from
# pipeline/exports/geojson.py — contracts, CQC locations, treatment numbers —
# and their caveats are read from there rather than copied, so the portal and
# the downloads cannot drift apart; the pin test holds that identity. The
# fourth, coverage, is W-12's "what is held here" data as an outline layer,
# carrying the absence caveat.
#
# PFD reports are deliberately not a layer. They have no geometry — coroner
# areas are not local authorities and must not be mapped as if they were
# (docs/CAVEATS.md) — and the export keeps them geometry-free for the same
# reason. The absence is pinned by a test, in the same shape as W-15's CQC
# decision: what is not drawn is a decision rather than an oversight.
#
# The contracts layer is aggregated to one feature per buyer authority, where
# the export emits one feature per notice: 98,636 points would be a payload
# and a canvas no reader could use. The aggregation is stated in the layer's
# caveats, which is how the export's "placed at the commissioning authority's
# boundary" warning survives the change of shape.


def layers(conn: sqlite3.Connection) -> dict:
    """The geography map's toggleable overlay layers, each with its caveats."""
    _public(["contracts", "authorities", "cqc_locations", "fingertips_la_values",
              "fingertips_indicators", "public_health_grants",
              "la_revenue_budgets", "ndtms_la_statistics",
              "cdp_documents", "cdp_document_candidates", "committee_papers",
              "committee_paper_candidates", "foi_requests",
              "foi_request_candidates"])

    contracts_features = _rows(conn, """
        SELECT c.buyer_ons_code AS ons_code, a.name AS authority_name,
               COUNT(*) AS count, COALESCE(SUM(c.value_core), 0) AS value_gbp
        FROM contracts c
        JOIN authorities a ON a.ons_code = c.buyer_ons_code
        GROUP BY c.buyer_ons_code, a.name
        ORDER BY count DESC""")

    cqc_features = _rows(conn, """
        SELECT location_id, location_name, region, overall_rating,
               latitude, longitude, local_authority_ons_code AS ons_code
        FROM cqc_locations
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        ORDER BY location_name""")

    # The same query the export uses: latest published period per authority,
    # so the overlay and the treatment_numbers.geojson download agree row for
    # row — pinned by test.
    treatment_features = _rows(conn, """
        SELECT v.ons_code, a.name AS authority_name, v.time_period, v.value
        FROM fingertips_la_values v
        JOIN fingertips_indicators i ON i.indicator_id = v.indicator_id
        JOIN authorities a ON a.ons_code = v.ons_code
        WHERE v.area_level = 'local_authority'
          AND i.topic = 'numbers_in_treatment'
          AND a.geometry_geojson IS NOT NULL
          AND v.value IS NOT NULL
          AND v.time_period = (
              SELECT MAX(v2.time_period) FROM fingertips_la_values v2
               WHERE v2.indicator_id = v.indicator_id AND v2.ons_code = v.ons_code)""")
    for feature in treatment_features:
        feature["unit"] = "rate per 1,000 population"

    coverage = _coverage_layer(conn)

    return {
        "layers": {
            "contracts": {
                "label": "Contracts",
                "features": contracts_features,
                "caveats": [
                    "Aggregated to one point per commissioning authority — "
                    f"{sum(f['count'] for f in contracts_features)} notices "
                    "in total. The exports carry every notice individually.",
                    *LAYER_CAVEATS["contracts"],
                ],
            },
            "cqc_locations": {
                "label": "CQC locations",
                "features": cqc_features,
                "caveats": LAYER_CAVEATS["cqc_locations"],
            },
            "treatment": {
                "label": "Treatment numbers",
                "features": treatment_features,
                "caveats": LAYER_CAVEATS["treatment_numbers"],
            },
            "coverage": {
                "label": "What is held here",
                "features": coverage,
                "caveats": [CAVEATS["coverage_absence"]],
            },
        },
    }


def _coverage_layer(conn: sqlite3.Connection) -> list[dict]:
    """How many evidence kinds the warehouse holds per authority.

    The W-12 ticks for every authority at once, counting distinct kinds from
    the same COVERAGE_COLUMNS declaration the admin matrix uses. The count is
    a statement about the pipeline's own knowledge, not about the authority —
    the caveat is the whole point of the layer.
    """
    exists = {row["name"] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    names = dict(conn.execute("SELECT ons_code, name FROM authorities"))

    held: dict[str, set[str]] = {}
    for label, table, column, _module in health.COVERAGE_COLUMNS:
        if table not in exists:
            continue
        # Table and column names come from health.COVERAGE_COLUMNS, which is
        # code, not a request — the same trust as the admin matrix.
        for (code,) in conn.execute(
                f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL"):
            if code in names:
                held.setdefault(code, set()).add(label)

    return [
        {"ons_code": code, "authority_name": names[code],
         "kinds_held": len(kinds)}
        for code, kinds in held.items()
    ]
