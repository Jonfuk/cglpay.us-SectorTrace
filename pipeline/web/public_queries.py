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
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterator

from pipeline import catalog, db
from pipeline.exports import guard_columns, guard_not_restricted
from pipeline.exports.geojson import LAYER_CAVEATS
from pipeline.licences import for_module, statement
from pipeline.notice_urls import notice_page_url
from pipeline.web import datasets, health
from pipeline.web.datasets import EVIDENCE_LAYERS
from pipeline.web.queries import QueryError, _run, escape_like

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
    "provider_lineage": (
        "The verified administrative record of an organisation's identity — "
        "renamed, merged into another body, or dissolved — from the pipeline's "
        "lifecycle config, cross-checked against the registered company and "
        "charity record. It is not a statement about continuity of service, of "
        "staff, of contracts or of quality: a merged charity's services and "
        "workforce may have moved, stayed, or ended, and this does not say "
        "which. Evidence that names an older identity stays attached to that "
        "identity and is not rewritten. No ownership structure is inferred and "
        "no individual officer is named."
    ),
    "cqc_locations_explorer": (
        "CQC registration covers only certain regulated activities — "
        "residential detox, inpatient care, some prescribing. Most community "
        "drug and alcohol provision is not registered, so this is a map of "
        "regulated locations, never a complete service map. A location count "
        "is neither coverage nor quality: do not rank authorities or providers "
        "by it, and do not combine it with any other layer. A rating is CQC's "
        "own published judgement as at its last inspection; where the API gave "
        "none, the bulk export's rating is shown and labelled as such. "
        "Locations with no coordinate are listed in the table but cannot be "
        "placed on the map."
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
    "hse_notices": (
        "Each row is an enforcement notice the Health and Safety Executive "
        "served on an organisation whose name exactly matches a tracked "
        "provider. It is a point-in-time fact, not a settled outcome: the "
        "published `result` — which can be 'Under appeal', 'Withdrawn', or an "
        "appeal decision — travels with every notice, and this portal never "
        "infers compliance. Notices served on individuals are excluded, and "
        "the register covers only HSE-enforced workplaces, so an absence of "
        "notices is not a safety rating."
    ),
    "contract_process": (
        "These are the official notices published under one OCID, grouped by "
        "the lifecycle stage each notice's own OCDS tag names — never a stage "
        "inferred from what is missing. A stage with no notice was not "
        "published to this feed, or has not been collected here: it is not "
        "evidence that the stage did not happen, that the contract completed, "
        "was renewed, met its targets, or that the supplier performed. No "
        "completion, performance or continuity is computed from this view."
    ),
    "evidence_funnel": (
        "Every candidate, promotion and evidence row in this funnel records "
        "a human decision, and who made it. A zero is zero decisions "
        "recorded — it says nothing about the sector, and everything about "
        "how much verification has been done."
    ),
    "commissioning_relationship_timeline": (
        "Each row is one contract notice that named this authority as buyer "
        "and this provider as supplier, dated as the notice published it. "
        "Missing dates are left blank, not inferred. The list is the source "
        "events behind one relationship — not a history of the working "
        "relationship itself, a measure of its value or reliance, or "
        "evidence of organisational continuity between differently-named "
        "entities. Only notices with an exact supplier-name match appear, "
        "the same floor as the contracts page."
    ),
    "commissioning_relationship": (
        "A line means a contract notice named this authority as buyer and "
        "this provider as supplier — a commissioning relationship, not a "
        "measure of size, value, importance or reliance. Coverage is the "
        "same floor as the contracts page: only notices with an exact "
        "supplier-name match are here, so an authority or provider with no "
        "lines shown may still have unmatched notices. This is not the "
        "whole evidence graph — ownership and corporate-group relationships "
        "are a separate, not-yet-published view."
    ),
    "collection_freshness": (
        "The date each source table was last written by a pipeline run. A "
        "table that never shows a date has never been collected — absence of "
        "collection is not evidence of absence, and it is drawn as 'never' "
        "rather than as zero."
    ),
    "catalogue": (
        "This catalogue describes what the portal collects and the single "
        "limitation that matters most for each source — it is not the full "
        "caveat set. Row counts and dates are measured against the warehouse "
        "on each request; a count of zero means that dataset has not been "
        "collected here, not that the source is empty. Datasets in different "
        "evidence layers are never added together."
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
    "sar_scope": (
        "Read from the National SAR Library, which boards submit their "
        "published reviews to rather than a directory the pipeline built "
        "itself. It is not known to be complete for any board or any year, "
        "so an absence here is a gap in the library, not evidence that no "
        "review was carried out."
    ),
    "sar_board": (
        "sab_name is read from the words the document itself uses to name "
        "its commissioning board, not validated against a fixed list of the "
        "~150 Safeguarding Adults Boards. A document with no board named "
        "plainly in its opening pages carries no board name here."
    ),
    "sar_mentions": (
        "A provider mention is not a finding of fault, causation, "
        "prevalence, or responsibility. The library gives no distribution "
        "list, so unlike the PFD reports above there is only one kind of "
        "mention: named somewhere in the text."
    ),
    "sar_terms": (
        "A term here means the word appears somewhere in the document. It "
        "is a finding aid — it points at reviews worth reading — not a "
        "characterisation of what the review found. Read the review."
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
    "provider_compare": (
        "Each layer below is one kind of evidence about one thing — an "
        "accreditation status, a gender pay gap filing, a figure a provider "
        "published on its own site, an advertised salary range. They are "
        "placed side by side, not combined: this comparison produces no "
        "ranking, score, difference or ratio, and a provider missing from a "
        "layer has not been shown to be worse or better on it. Read each "
        "layer with its own caveat before drawing anything from the "
        "arrangement."
    ),
    "statutory_pay_rates": (
        "Statutory rates are published hourly floors. They are shown as the "
        "government published them: this portal does not annualise them or "
        "calculate a percentage difference from an advertised rate."
    ),
    "living_wage_accreditations": (
        "A result of 'not found' means no accredited employer was found under "
        "the checked name on the retrieval date. Accreditation can sit under "
        "another legal name, so it is not evidence that a provider is not "
        "accredited."
    ),
    "gender_pay_gap": (
        "Gender pay gap figures are the employer's submitted filing. A missing "
        "filing is not a zero gap: the employer may be out of scope or may not "
        "have filed."
    ),
    "ashe": (
        "ASHE is a sample survey of PAYE jobs. These are published median gross "
        "hourly pay figures excluding overtime, shown alongside other hourly "
        "evidence only; this portal does not calculate a pay gap or ratio."
    ),
    "provider_published_pay": (
        "Provider-owned pages show what the provider published for a role or "
        "offer on a retrieval date. They are not a pay scale or evidence of "
        "what staff currently earn, and hourly and annual values are not "
        "converted."
    ),
    "skills_for_care": (
        "Skills for Care figures are rounded modelled estimates for the adult "
        "social-care workforce. They are labour-market comparators, not a "
        "measure of a tracked provider's workforce or pay."
    ),
    "council_spend": (
        "Each row is a payment line a council published in a spend-transparency "
        "file. It is actual published payment evidence, not a procurement notice "
        "or a budget, and this portal does not add payments into a sector total."
    ),
    "council_spend_match": (
        "A payment is linked to a tracked provider only when the council's payee "
        "name exactly matches a known provider name variant. Unmatched rows are "
        "not evidence that no tracked provider was paid."
    ),
    "rough_sleeping_comparator": (
        "This is a comparator, shown here because rough sleeping and substance "
        "misuse are widely documented as overlapping populations — never "
        "combined, ratioed or correlated with this authority's own evidence "
        "above. Methodology is not standardised between authorities: each "
        "chooses its own counting approach and date within the autumn window, "
        "so a difference between two authorities may reflect a difference in "
        "method, not only on the street."
    ),
    "statutory_homelessness_comparator": (
        "This is a comparator, shown for the same reason as the rough sleeping "
        "figures above — never combined, ratioed or correlated with this "
        "authority's own evidence. Only the flagship duty-assessment count "
        "(Table A1) is read; a quarter can later be revised, and this figure "
        "reflects whichever edition was most recently fetched."
    ),
    "temporary_accommodation_comparator": (
        "This is a comparator, shown for the same reason as the homelessness "
        "figures above — never combined, ratioed or correlated with this "
        "authority's own evidence. Only the top-level totals are read, plus "
        "the bed-and-breakfast breakdown where Table TA1 publishes it."
    ),
    "temporary_accommodation_breakdown": (
        "The bed-and-breakfast 'of which' rows of Table TA1, as published. "
        "The set of B&B columns changes across the series — older quarters "
        "split households with children out, recent quarters give only the "
        "households total — so a missing measure for a quarter means the "
        "source did not publish it, not zero. Context only: not a rate, not "
        "compared between authorities, not differenced across quarters."
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
    not undecided. Promoted means an eligible recorded decision exists in
    `evidence_promotions`; its actor type distinguishes human and autonomous
    decisions (migration `0049`).
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
    _public(["providers", "authorities", "contracts", "supplier_aliases",
              "workforce_census_metrics",
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
    # Same "matched to a known provider" measure as the contracts page --
    # exact supplier-name match only, so this is a floor. Shown on the
    # overview strip instead of the old "active evidence signals" count,
    # which counted how many layers were non-zero rather than measuring
    # anything about the evidence itself.
    matched_to_provider = _one(
        conn, "SELECT COUNT(*) AS matched FROM contracts WHERE supplier_name_raw IN "
               "(SELECT alias_raw FROM supplier_aliases)").get("matched", 0)

    # Per-region breakdown of the same "appears as a contract buyer" signal
    # as `with_contracts` above, for the hero's England silhouette. A count
    # and a ratio within one evidence layer, same as `matched_to_provider` —
    # nothing here is summed or compared across layers.
    regions = _rows(
        conn,
        "SELECT a.region, COUNT(DISTINCT a.ons_code) AS authorities_total, "
        "       COUNT(DISTINCT CASE WHEN c.buyer_ons_code IS NOT NULL "
        "                            THEN a.ons_code END) AS authorities_with_contracts "
        "FROM authorities a "
        "LEFT JOIN contracts c ON c.buyer_ons_code = a.ons_code "
        "WHERE a.region IS NOT NULL "
        "GROUP BY a.region")

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
            "regions": regions,
            "regions_caveat": CAVEATS["contract_value"],
        },
        "contracts": {
            "total_notices": contracts.get("total_notices", 0),
            "total_value_gbp": contracts.get("total_value_gbp", 0),
            "direct_awards": contracts.get("direct_awards", 0),
            "psr_notices": contracts.get("psr_notices", 0),
            "matched_to_provider": matched_to_provider,
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
    ("Statutory pay rates", "statutory_pay_rates"),
    ("Living Wage accreditation", "living_wage_accreditations"),
    ("data.gov.uk catalogue", "data_gov_uk_datasets"),
    ("Gender pay gap reports", "gender_pay_gap_reports"),
    ("ONS ASHE observations", "ons_ashe_observations"),
    ("Provider pay pages", "provider_pay_pages"),
    # File-level rows survive a parser gap. They therefore distinguish a
    # source that has gone stale from a current publication whose data rows
    # could not be read, just as the authority coverage matrix does for m24.
    ("Council spend files", "council_spend_files"),
    ("Skills for Care files", "skills_for_care_files"),
    ("Rough sleeping snapshot", "rough_sleeping_snapshot"),
    ("Statutory homelessness", "statutory_homelessness_snapshot"),
    ("Temporary accommodation", "temporary_accommodation_snapshot"),
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


# --- release identity -------------------------------------------------------


def _git_revision_from_checkout() -> str | None:
    """The current commit, read straight from `.git` — no subprocess.

    Only the local-checkout fallback: a hosted deployment injects
    `GIT_REVISION` because the Docker image carries no `.git` directory. Any
    read problem (detached checkout, packed refs, no `.git` at all) returns
    None rather than raising — an unknown revision is a fine answer here and a
    500 on the footer is not.
    """
    git_dir = Path(__file__).resolve().parents[2] / ".git"
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head.split(":", 1)[1].strip()
            ref_file = git_dir / ref
            if ref_file.is_file():
                return ref_file.read_text(encoding="utf-8").strip() or None
            packed = git_dir / "packed-refs"
            if packed.is_file():
                for line in packed.read_text(encoding="utf-8").splitlines():
                    if line.startswith(("#", "^")) or " " not in line:
                        continue
                    sha, name = line.split(" ", 1)
                    if name.strip() == ref:
                        return sha or None
            return None
        return head or None
    except OSError:
        return None


def meta(conn: sqlite3.Connection, settings) -> dict:
    """Release identity for the beta: which build, schema and capabilities.

    Deliberately cheap — the portal footer and the beta smoke gate both read
    it, so it touches only two tiny tables (`schema_migrations`, `http_cache`)
    and the server's own extension catalogue. Per-source collection times are
    `/api/v1/freshness`, which this points at rather than recomputing.

    `/health` stays the plain-text `ok` liveness probe; this is the auditable
    identity beside it.
    """
    _public(["schema_migrations", "http_cache", "run_ledger"])

    applied = db.applied_migrations(conn)
    schema_row = _one(
        conn, "SELECT MAX(applied_at) AS migrated_at FROM schema_migrations")

    objects = {obj["name"] for obj in catalog.list_objects(conn)}
    last_fetch_at = None
    if "http_cache" in objects:
        last_fetch_at = _one(
            conn, "SELECT MAX(updated_at) AS t FROM http_cache").get("t")

    # The last durable run-ledger row (BETA-058), if the table exists — a
    # cheap "when did collection last run, and how" signal beside the
    # per-source retrieval times.
    last_run = None
    if "run_ledger" in objects:
        row = _one(conn, "SELECT origin, status, started_at, finished_at, "
                          "modules_ok, modules_failed FROM run_ledger "
                          "ORDER BY started_at DESC LIMIT 1")
        last_run = row or None

    backend = db.backend_of(conn)
    extension_state = {
        ext["name"]: bool(ext["installed"]) for ext in health.extensions(conn)
    }

    return {
        "service": "sectortrace",
        "environment": settings.environment,
        "revision": settings.git_revision or _git_revision_from_checkout(),
        "revision_source": "deployment" if settings.git_revision else "checkout",
        "build_time": settings.build_time,
        "backend": backend,
        "schema": {
            "latest_migration": max(applied) if applied else None,
            "applied_count": len(applied),
            "migrated_at": schema_row.get("migrated_at"),
        },
        "data": {
            # The freshest signal of collection activity, cheaply: when this
            # warehouse last spoke to any source. The authoritative per-table
            # retrieval times are their own route.
            "last_fetch_at": last_fetch_at,
            "per_source": "/api/v1/freshness",
            # The last module-run recorded in the durable ledger (BETA-058):
            # origin, status and timestamps. None if none has run.
            "last_run": last_run,
        },
        "capabilities": {
            "admin_ui": bool(settings.admin_ui_enabled),
            "api_response_cache": bool(settings.cache_enabled),
            "api_rate_limit": bool(settings.api_rate_limit_enabled),
            "document_analysis": bool(settings.document_analysis_enabled),
            "semantic_search": bool(settings.nlp_enabled),
            # {} on SQLite; on PostgreSQL, name -> installed-in-this-database.
            "postgres_extensions": extension_state,
        },
    }


# --- dataset catalogue ----------------------------------------------------


def _table_last_retrieved(conn: sqlite3.Connection, table: str) -> str | None:
    """MAX(retrieved_at) for a table that has that column, else None.

    The catalogue spans the whole pipeline and the reference and derived
    tables (`authorities`, `sector_universe`) carry no `retrieved_at`. Ask
    the schema first so this does not raise on them.
    """
    if not any(col["name"] == "retrieved_at"
               for col in catalog.columns_of(conn, table)):
        return None
    return _one(conn, f"SELECT MAX(retrieved_at) AS t FROM {table}").get("t")


def _dataset_figures(conn: sqlite3.Connection, ds: "datasets.Dataset") -> dict:
    """One catalogue row: the static registry entry plus live counts/freshness.

    `_public()` here is the same guard every other function in this file
    runs — a mistyped table name in `datasets.py` that named a restricted_
    table would fail the request rather than count its rows.
    """
    _public(list(ds.public_tables))
    counts = catalog.row_counts(conn, ds.public_tables)
    retrieved = {t: _table_last_retrieved(conn, t) for t in ds.public_tables}
    dates = [d for d in retrieved.values() if d]
    licence = for_module(ds.module)
    return {
        "dataset_id": ds.dataset_id,
        "module": ds.module,
        "title": ds.title,
        "publisher": ds.publisher,
        "official_url": ds.official_url,
        "evidence_layer": ds.evidence_layer,
        "evidence_layer_label": EVIDENCE_LAYERS.get(
            ds.evidence_layer, ds.evidence_layer),
        "geography": ds.geography,
        "cadence": ds.cadence,
        "licence": (
            {"id": licence.id, "name": licence.name, "url": licence.url}
            if licence else None),
        "tables": [
            {"name": t, "rows": counts.get(t, 0),
             "last_retrieved_at": retrieved.get(t)}
            for t in ds.public_tables
        ],
        "row_count": sum(counts.get(t, 0) for t in ds.public_tables),
        "last_retrieved_at": max(dates) if dates else None,
        "caveat": ds.caveat,
    }


def catalogue(conn: sqlite3.Connection) -> dict:
    """Every dataset the portal serves, with measured counts and freshness.

    The static half — title, publisher, official URL, evidence layer,
    geography, cadence, licence key, caveat — is `pipeline/web/datasets.py`.
    The counts and last-retrieved dates are read from the warehouse here so
    the catalogue can never claim a figure the data does not support.
    `tests/test_web_catalogue.py` pins that every collecting `mNN_` module
    has exactly one entry.
    """
    return {
        "datasets": [_dataset_figures(conn, ds) for ds in datasets.DATASETS],
        "evidence_layers": EVIDENCE_LAYERS,
        "count": len(datasets.DATASETS),
        "caveat": CAVEATS["catalogue"],
    }


def catalogue_detail(conn: sqlite3.Connection, dataset_id: str) -> dict:
    """One dataset, with the full licence statement and its caution."""
    ds = datasets.BY_ID.get(dataset_id)
    if ds is None:
        raise QueryError(f"No dataset {dataset_id!r}.")
    figures = _dataset_figures(conn, ds)
    licence = for_module(ds.module)
    figures["licence_statement"] = statement(licence) if licence else None
    figures["licence_caution"] = (licence.caution or None) if licence else None
    figures["caveat_common"] = CAVEATS["catalogue"]
    return figures


# --- source publication calendar (BETA-091) ---------------------------------
#
# Freshness alone cannot tell a reader why a dataset looks old: a publisher
# that has released nothing and a collection here that has not run are
# different conditions. This view keeps them apart. For each dataset it shows,
# side by side and never merged into one figure:
#
#   * the publisher's *stated* cadence — the number transcribed in
#     `datasets._STATED_CADENCE_DAYS`, or nothing where the source names no
#     calendar;
#   * an *observed* interval — the median gap between the distinct calendar
#     dates this warehouse holds retrieval timestamps for, reported only with
#     three or more such dates and always labelled an estimate;
#   * the last retrieval held here, and a next-expected date projected from
#     whichever basis applies (stated preferred over observed).
#
# `status` is "overdue" only when that projected date is past by more than a
# quarter of the cadence (minimum one week); "due" inside that window;
# "current" before it; "unknown" with no basis or nothing retrieved. No
# arithmetic crosses datasets and there is no headline total.
_CALENDAR_MIN_OBSERVED = 3
_CALENDAR_STATUS_ORDER = {"overdue": 0, "due": 1, "unknown": 2, "current": 3}


def _distinct_retrieval_dates(conn: sqlite3.Connection, table: str) -> list[str]:
    """Every distinct YYYY-MM-DD this table carries a `retrieved_at` for.

    Ask the schema first — reference tables such as `authorities` have no
    `retrieved_at` — so this stays quiet on them rather than raising.
    """
    if not any(col["name"] == "retrieved_at"
               for col in catalog.columns_of(conn, table)):
        return []
    return [r["d"] for r in _rows(
        conn,
        f"SELECT DISTINCT substr(retrieved_at, 1, 10) AS d FROM {table} "
        "WHERE retrieved_at IS NOT NULL AND retrieved_at <> '' ORDER BY d")]


def _observed_interval_days(dates: list[str]) -> int | None:
    """Median gap in days between consecutive distinct retrieval dates.

    None below `_CALENDAR_MIN_OBSERVED` dates: two points make one gap, and
    one gap is not a cadence. `dates` arrives sorted ascending.
    """
    if len(dates) < _CALENDAR_MIN_OBSERVED:
        return None
    gaps: list[int] = []
    for a, b in zip(dates, dates[1:]):
        try:
            delta = (date.fromisoformat(b) - date.fromisoformat(a)).days
        except ValueError:
            continue
        if delta > 0:
            gaps.append(delta)
    if len(gaps) < _CALENDAR_MIN_OBSERVED - 1:
        return None
    gaps.sort()
    mid = len(gaps) // 2
    if len(gaps) % 2:
        return gaps[mid]
    return round((gaps[mid - 1] + gaps[mid]) / 2)


def publication_calendar(conn: sqlite3.Connection, *,
                          today: str | None = None) -> dict:
    """Per-source release cadence, last publication and overdue/unknown status.

    Read-only and derived: the stated cadence is registry metadata, everything
    else is measured from retrieval history on this request. Stated and
    observed cadences are reported in separate fields and never combined.
    """
    as_of = date.fromisoformat(today) if today else date.today()

    rows: list[dict] = []
    by_status: dict[str, int] = {}
    by_basis: dict[str, int] = {}
    for ds in datasets.DATASETS:
        _public(list(ds.public_tables))
        seen: set[str] = set()
        for t in ds.public_tables:
            seen.update(_distinct_retrieval_dates(conn, t))
        dated = sorted(seen)
        last_pub = dated[-1] if dated else None
        observed = _observed_interval_days(dated)
        stated = ds.stated_cadence_days

        if stated is not None:
            basis, cadence_days = "stated", stated
        elif observed is not None:
            basis, cadence_days = "observed", observed
        else:
            basis, cadence_days = "unknown", None

        next_expected = None
        status = "unknown"
        overdue_by_days = None
        if cadence_days and last_pub:
            try:
                nxt = date.fromisoformat(last_pub) + timedelta(days=cadence_days)
            except ValueError:
                nxt = None
            if nxt is not None:
                next_expected = nxt.isoformat()
                grace = max(7, round(cadence_days * 0.25))
                if as_of <= nxt:
                    status = "current"
                elif as_of <= nxt + timedelta(days=grace):
                    status = "due"
                else:
                    status = "overdue"
                    overdue_by_days = (as_of - nxt).days

        by_status[status] = by_status.get(status, 0) + 1
        by_basis[basis] = by_basis.get(basis, 0) + 1
        rows.append({
            "dataset_id": ds.dataset_id,
            "title": ds.title,
            "publisher": ds.publisher,
            "official_url": ds.official_url,
            "evidence_layer": ds.evidence_layer,
            "evidence_layer_label": EVIDENCE_LAYERS.get(
                ds.evidence_layer, ds.evidence_layer),
            "stated_cadence": ds.cadence,
            "stated_cadence_days": stated,
            "observed_interval_days": observed,
            "observed_sample": len(dated),
            "cadence_basis": basis,
            "cadence_days": cadence_days,
            "last_publication": last_pub,
            "next_expected": next_expected,
            "status": status,
            "overdue_by_days": overdue_by_days,
        })

    rows.sort(key=lambda r: (
        _CALENDAR_STATUS_ORDER.get(r["status"], 9),
        r["next_expected"] or "9999",
        r["title"].lower()))

    return {
        "as_of": as_of.isoformat(),
        "datasets": rows,
        "counts": {"by_status": by_status, "by_basis": by_basis},
        "statuses": list(_CALENDAR_STATUS_ORDER),
        "note": "The stated cadence is what the publisher says. The observed "
                "interval is the median gap between retrievals this warehouse "
                "holds — an estimate, shown only with three or more dated "
                "retrievals, and never merged with the stated figure.",
        "caveat": "A next-expected date is projected from the last retrieval "
                  "here, not a publisher commitment. “Overdue” can mean "
                  "the source has not released, or that collection here has "
                  "not run — this view does not tell the two apart, only that "
                  "the freshness needs explaining.",
    }


# --- "what changed?" evidence feed (BETA-090) ---------------------------------
#
# There is no persisted change-event table and this adds none — no new
# collection-time write path. The feed is *derived* on each request from
# signals the warehouse already records, each classed as one kind:
#
#   release     — a run of the shared module runner (`run_ledger`)
#   refreshed   — a source table's most recent retrieval moved (catalogue
#                 freshness), i.e. a collection changed it
#   reparsed    — a document got a new active parsed version (parser change)
#   superseded  — a provider now trades as a successor (verified lineage)
#   verified    — a human review decision resolved a candidate (alias review)
#
# The three axes the objective names are kept apart: a collection change
# (`refreshed`/`release`), a parser change (`reparsed`) and a human-review
# change (`verified`/`superseded`) are different kinds and are never merged
# into one count.
CHANGE_KINDS = ("release", "refreshed", "reparsed", "superseded", "verified")
_CHANGE_MAX = 500


def change_feed(conn: sqlite3.Connection, *, kind=None, source=None,
                 evidence_type=None, since=None, limit: int = 200) -> dict:
    _public(["run_ledger", "document_versions", "document_records", "providers",
              "alias_decisions"])
    if kind is not None and kind not in CHANGE_KINDS:
        raise QueryError(f"unknown change kind {kind!r}")
    limit = max(1, min(int(limit), _CHANGE_MAX))
    present = {obj["name"] for obj in catalog.list_objects(conn)}
    events: list[dict] = []

    def keep(**event) -> None:
        events.append({
            "kind": event["kind"], "at": event.get("at"),
            "source": event.get("source"),
            "evidence_type": event.get("evidence_type"),
            "entity": event.get("entity"),
            "detail": event.get("detail"),
            "release": event.get("release"),
        })

    if "run_ledger" in present:
        for r in _rows(conn, """
            SELECT run_id, origin, status, finished_at, started_at,
                   modules_ok, modules_failed
            FROM run_ledger ORDER BY started_at DESC LIMIT 30"""):
            keep(kind="release", at=r["finished_at"] or r["started_at"],
                 source="pipeline", evidence_type=None, entity=r["origin"],
                 detail=(f"run {r['origin']} {r['status']} — "
                         f"{r['modules_ok'] or 0} ok"
                         + (f", {r['modules_failed']} failed"
                            if r["modules_failed"] else "")),
                 release=r["run_id"])

    # `refreshed`: the catalogue's measured last-retrieval per dataset.
    for figures in (_dataset_figures(conn, ds) for ds in datasets.DATASETS):
        last = figures.get("last_retrieved_at")
        if last:
            keep(kind="refreshed", at=last, source=figures.get("publisher"),
                 evidence_type=figures.get("dataset_id"),
                 entity=None,
                 detail=f"{figures.get('title')}: latest retrieval {last[:10]}")

    if {"document_versions", "document_records"} <= present:
        for r in _rows(conn, """
            SELECT v.document_id, v.parser_name, v.parser_version, v.created_at,
                   d.title
            FROM document_versions v
            JOIN document_records d ON d.document_id = v.document_id
            WHERE v.is_active = 1
              AND EXISTS (SELECT 1 FROM document_versions v2
                          WHERE v2.document_id = v.document_id
                            AND v2.is_active = 0)
            ORDER BY v.created_at DESC LIMIT 60"""):
            keep(kind="reparsed", at=r["created_at"], source="document parser",
                 evidence_type="document", entity=r["document_id"],
                 detail=(f"{r['title'] or r['document_id']}: reparsed with "
                         f"{r['parser_name']} {r['parser_version']}"))

    if "providers" in present:
        for r in _rows(conn, """
            SELECT p.provider_key, p.canonical_name, s.canonical_name AS successor
            FROM providers p
            LEFT JOIN providers s ON s.provider_key = p.superseded_by
            WHERE p.superseded_by IS NOT NULL"""):
            keep(kind="superseded", at=None, source="provider lineage",
                 evidence_type="provider", entity=r["provider_key"],
                 detail=(f"{r['canonical_name']} now trades as "
                         f"{r['successor'] or r['provider_key']}"))

    if "alias_decisions" in present:
        for r in _rows(conn, """
            SELECT decision_id, unmatched_name, canonical_name, target_scheme,
                   status, decided_by, decided_at
            FROM alias_decisions
            WHERE status = 'confirmed'
            ORDER BY decided_at DESC LIMIT 60"""):
            keep(kind="verified", at=r["decided_at"], source="alias review",
                 evidence_type=r["target_scheme"], entity=r["canonical_name"],
                 detail=(f"“{r['unmatched_name']}” confirmed as "
                         f"{r['canonical_name']} by {r['decided_by']}"))

    if kind:
        events = [e for e in events if e["kind"] == kind]
    if source:
        events = [e for e in events if e["source"] == source]
    if evidence_type:
        events = [e for e in events if e["evidence_type"] == evidence_type]
    if since:
        events = [e for e in events if e["at"] and e["at"][:10] >= str(since)[:10]]

    events.sort(key=lambda e: (e["at"] or ""), reverse=True)
    truncated = len(events) > limit
    events = events[:limit]

    by_kind: dict[str, int] = {}
    for e in events:
        by_kind[e["kind"]] = by_kind.get(e["kind"], 0) + 1

    return {
        "events": events,
        "truncated": truncated,
        "counts": {"by_kind": by_kind},
        "kinds": list(CHANGE_KINDS),
        "note": "Derived from the run ledger, catalogue freshness, document "
                "reparses and verified provider/alias changes. A collection "
                "change, a parser change and a human-review change are "
                "distinct kinds and their counts are never added.",
        "caveat": "This feed reveals what the warehouse recorded changing. It "
                  "is not a record of what a source published — a source can "
                  "change with no collection here, and this feed will not show "
                  "it until the next run.",
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
               p.status,
               p.superseded_by,
               (SELECT sp.canonical_name FROM providers sp
                 WHERE sp.provider_key = p.superseded_by) AS superseded_by_name,
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
               c.source_system, c.notice_web_url,
               -- The OCDS id that links related releases of one procurement
               -- (BETA-050). Stable across the lifecycle; the process view is
               -- keyed by it.
               c.ocid
        FROM contracts c{clause}
        -- NULLS LAST is said rather than left to the engine: SQLite puts them
        -- last under DESC and PostgreSQL puts them first, so the same list
        -- would open on a different notice depending on which backend
        -- answered. SQLite is the backend of record, so its order is the one
        -- written down. It is also what idx_contracts_date_published is built
        -- to answer (migration 0044) — an ORDER BY the index does not match
        -- is a sort of the whole table.
        ORDER BY c.date_published DESC NULLS LAST, c.notice_id"""


def _contract_filters(provider_key, buyer_ons_code, year_from, year_to, psr_only,
                      q=None, since_retrieved_at=None, *, ilike=False):
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
    if q:
        # BETA-040: case-insensitive substring over the two names a reader
        # recognises a notice by. On PostgreSQL this is ILIKE, which the
        # pg_trgm GIN indexes on buyer_name / supplier_name_raw (migration
        # 0069) turn into an index scan; on SQLite it is LIKE, whose ASCII
        # case-folding is enough and whose plan is the documented
        # sequential-scan fallback that same migration describes. A caller's
        # `%` and `_` are escaped so the term cannot act as a wildcard.
        op = "ILIKE" if ilike else "LIKE"
        term = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params["contract_q"] = f"%{term}%"
        where.append(
            f"(c.buyer_name {op} :contract_q ESCAPE '\\' "
            f"OR c.supplier_name_raw {op} :contract_q ESCAPE '\\')")
    if since_retrieved_at:
        # A plain string comparison, like the year bounds above: retrieved_at
        # is an ISO-8601 timestamp and sorts lexically. Lets a reader ask
        # "notices this warehouse has seen since <date>" and get a result set
        # a shared link reproduces.
        where.append("c.retrieved_at >= :since_retrieved_at")
        params["since_retrieved_at"] = since_retrieved_at
    return (f" WHERE {' AND '.join(where)}" if where else ""), params


def contracts(conn: sqlite3.Connection, *, provider_key=None, buyer_ons_code=None,
               year_from=None, year_to=None, psr_only=False, q=None,
               since_retrieved_at=None, limit=500, offset=0) -> dict:
    _public(["contracts", "supplier_aliases", "providers"])
    clause, params = _contract_filters(
        provider_key, buyer_ons_code, year_from, year_to, psr_only,
        q=q, since_retrieved_at=since_retrieved_at,
        ilike=db.backend_of(conn) == "postgres")

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

    page_limit = max(1, min(int(limit), 5000))
    page_offset = max(0, int(offset))
    notices = _rows(
        conn,
        _NOTICE_SELECT.format(clause=clause) + "\n        LIMIT :limit OFFSET :offset",
        {**params, "limit": page_limit, "offset": page_offset})
    _add_notice_links(notices)

    # The overview's "largest notices" list, narrowed to notices matched to a
    # tracked provider by exact supplier-name -- otherwise the largest values
    # in the corpus are dominated by cross-government framework notices with
    # no provider attached at all, which is not a useful "biggest deal we
    # found" list for the campaign.
    largest_matched_to_provider = _rows(conn, f"""
        SELECT c.notice_id, c.buyer_name, c.title, c.value_core, c.source_url,
               sa.canonical_name
        FROM contracts c
        JOIN supplier_aliases sa ON sa.alias_raw = c.supplier_name_raw
        {clause}
        {'AND' if clause else 'WHERE'} c.value_core IS NOT NULL
        ORDER BY c.value_core DESC LIMIT 5""", params)

    return {
        **totals,
        "value_concentration": _value_concentration(conn, clause, params),
        "largest_matched_to_provider": largest_matched_to_provider,
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
        # BETA-040: what window of the matching set `notices` is, so the page
        # can offer "show more" and a reader can tell a short list from a
        # complete one. `total` above is the count over the same filters.
        "page": {
            "limit": page_limit,
            "offset": page_offset,
            "returned": len(notices),
            "q": q or None,
            "since_retrieved_at": since_retrieved_at or None,
        },
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
                          psr_only=False, q=None, since_retrieved_at=None,
                          batch: int = 2000
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
        provider_key, buyer_ons_code, year_from, year_to, psr_only,
        q=q, since_retrieved_at=since_retrieved_at,
        ilike=db.backend_of(conn) == "postgres")
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


# OCDS release tags -> the lifecycle stage they name. The stage a notice
# belongs to is the one its own `tag` declares (stored in
# `contracts.notice_type` as a comma-joined string by m01) — this view never
# infers a stage from the absence of another.
_OCDS_STAGE: dict[str, str] = {
    "planning": "planning",
    "tender": "tender", "tenderAmendment": "tender", "tenderUpdate": "tender",
    "tenderCancellation": "tender",
    "award": "award", "awardUpdate": "award", "awardCancellation": "award",
    "contract": "contract", "contractUpdate": "contract",
    "contractAmendment": "amendment",
    "contractTermination": "termination",
    "implementation": "implementation", "implementationUpdate": "implementation",
}
# Display / lifecycle order.
_STAGE_ORDER: tuple[str, ...] = (
    "planning", "tender", "award", "contract", "amendment", "termination",
    "implementation", "other")
# Classification order: when a notice carries tags mapping to more than one
# stage, the most specific / latest one wins — a `contractAmendment` also
# tagged `contract` is an amendment.
_STAGE_PRECEDENCE: tuple[str, ...] = (
    "termination", "amendment", "implementation", "contract", "award",
    "tender", "planning", "other")


def _stage_of(notice_type: str | None) -> tuple[str, list[str]]:
    """The lifecycle stage a notice belongs to, and its raw OCDS tags.

    A notice can carry several tags; `_STAGE_PRECEDENCE` picks the most
    specific. An unrecognised or absent tag is `other` — surfaced, not dropped.
    """
    tags = [t.strip() for t in (notice_type or "").split(",") if t.strip()]
    stages = {_OCDS_STAGE[t] for t in tags if t in _OCDS_STAGE}
    for candidate in _STAGE_PRECEDENCE:
        if candidate in stages:
            return candidate, tags
    return "other", tags


def contract_process(conn: sqlite3.Connection, ocid: str) -> dict:
    """The notices that share one OCID, grouped into published lifecycle
    stages (BETA-050).

    Deterministic and additive: it reads `contracts` rows for `ocid`, buckets
    each by the stage its own OCDS tag names, and returns them ordered by
    publication date within each stage. It computes no completion, renewal,
    performance or continuity — see `CAVEATS["contract_process"]`.
    """
    _public(["contracts", "supplier_aliases"])

    rows = _rows(conn, """
        SELECT c.notice_id, c.supplier_id, c.notice_type, c.notice_web_url,
               c.buyer_name, c.buyer_ons_code, c.supplier_name_raw,
               c.title, c.description, c.value_core, c.value_max, c.currency,
               c.date_published, c.date_start, c.date_end, c.procedure_type,
               c.source_url, c.retrieved_at, c.source_system,
               CASE WHEN c.supplier_name_raw IN
                    (SELECT alias_raw FROM supplier_aliases) THEN 1 ELSE 0 END
                    AS supplier_is_tracked
        FROM contracts c
        WHERE c.ocid = :ocid
        ORDER BY c.date_published, c.notice_id, c.supplier_id""",
        {"ocid": ocid})
    if not rows:
        raise QueryError(f"No contract notices for OCID {ocid!r}.")

    # One entry per notice_id; a multi-supplier award is several rows.
    notices: dict[str, dict] = {}
    for row in rows:
        stage, tags = _stage_of(row["notice_type"])
        entry = notices.setdefault(row["notice_id"], {
            "notice_id": row["notice_id"],
            "stage": stage,
            "ocds_tags": tags,
            "title": row["title"],
            "notice_type_raw": row["notice_type"],
            "date_published": row["date_published"],
            "date_start": row["date_start"],
            "date_end": row["date_end"],
            "procedure_type": row["procedure_type"],
            "value_core": row["value_core"],
            "value_max": row["value_max"],
            "currency": row["currency"],
            "buyer_name": row["buyer_name"],
            "buyer_ons_code": row["buyer_ons_code"],
            "source_url": row["source_url"],
            "retrieved_at": row["retrieved_at"],
            "notice_web_url": row["notice_web_url"] or notice_page_url(
                row["source_system"], row["notice_id"]),
            "suppliers": [],
        })
        if row["supplier_name_raw"]:
            entry["suppliers"].append({
                "name": row["supplier_name_raw"],
                "is_tracked_provider": bool(row["supplier_is_tracked"]),
            })

    ordered = sorted(
        notices.values(),
        key=lambda n: (n["date_published"] or "", n["notice_id"]))
    by_stage: dict[str, list[dict]] = {}
    for notice in ordered:
        by_stage.setdefault(notice["stage"], []).append(notice)

    stages = [
        {"stage": name, "present": name in by_stage,
         "notices": by_stage.get(name, [])}
        for name in _STAGE_ORDER
    ]
    published_at = [n["date_published"] for n in ordered if n["date_published"]]
    buyer = ordered[0]
    return {
        "ocid": ocid,
        "buyer": {"name": buyer["buyer_name"],
                   "ons_code": buyer["buyer_ons_code"]},
        "stage_order": list(_STAGE_ORDER),
        "stages": stages,
        "notice_count": len(ordered),
        "date_range": {
            "earliest": min(published_at) if published_at else None,
            "latest": max(published_at) if published_at else None,
        },
        "caveat": CAVEATS["contract_process"],
    }


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


# The workforce pay explorer (BETA-070). A closed registry: each source group
# names the response arrays it owns, the role-text field to match a `role`
# filter against in each, and the pay units it can legitimately carry. The
# groups are never summed or ranked against one another — this is an index
# over unlike evidence, not a composite. `role`/`pay_unit`/`source` narrow
# what is returned; they add nothing and combine nothing.
PAY_SOURCE_GROUPS = {
    "indicative_wage": {
        "label": "Indicative wage",
        # `arrays` is everything the group owns and every `source`/`role`/
        # `pay_unit` filter narrows; `primary` is the discrete-evidence
        # array(s) whose length the explorer's group count reports, so a
        # derived chart aggregate does not inflate the number.
        "arrays": ("charity_wage_series",),
        "primary": ("charity_wage_series",),
        "role_fields": {},                      # no role dimension
        "units": ("per employee, per year",),
    },
    "advertised_roles": {
        "label": "Advertised roles",
        "arrays": ("nhs_job_adverts", "nhs_job_by_band", "repeat_advertised_roles"),
        "primary": ("nhs_job_adverts",),
        "role_fields": {
            "nhs_job_adverts": ("job_title",),
            "repeat_advertised_roles": ("job_title_normalised",),
        },
        "units": ("annual", "hourly"),
    },
    "published_statutory": {
        "label": "Published & statutory pay",
        "arrays": ("provider_published_pay", "statutory_pay_rates",
                   "living_wage_accreditations", "gender_pay_gap_reports"),
        "primary": ("provider_published_pay", "statutory_pay_rates",
                    "living_wage_accreditations", "gender_pay_gap_reports"),
        "role_fields": {
            "provider_published_pay": ("section", "mention_text"),
            "statutory_pay_rates": ("band_role", "band_label"),
        },
        "units": ("hourly", "percent"),
    },
    "workforce_census": {
        "label": "Workforce census",
        "arrays": ("workforce_census",),
        "primary": ("workforce_census",),
        "role_fields": {"workforce_census": ("workforce_segment", "metric")},
        "units": ("varies by metric",),
    },
    "external_comparators": {
        "label": "External comparators",
        "arrays": ("ons_ashe_observations", "skills_for_care_estimates"),
        "primary": ("ons_ashe_observations", "skills_for_care_estimates"),
        "role_fields": {
            "ons_ashe_observations": ("dimension_label",),
            "skills_for_care_estimates": ("job_role", "job_role_group"),
        },
        "units": ("hourly", "annual"),
    },
}

PAY_UNITS = ("hourly", "annual", "other")

# Which pay unit a row of a given array carries, as a callable. `None` means
# the array has no single unit to filter on and a `pay_unit` filter drops it.
_PAY_UNIT_OF = {
    "nhs_job_adverts": lambda r: {"year": "annual", "annum": "annual",
                                   "hour": "hourly"}.get(
        (r.get("salary_period") or "").lower(), "other"),
    "provider_published_pay": lambda r: {"year": "annual", "annum": "annual",
                                          "hour": "hourly"}.get(
        (r.get("salary_period") or "").lower(), "other"),
    "statutory_pay_rates": lambda r: "hourly",
    "ons_ashe_observations": lambda r: "hourly"
        if "hour" in (r.get("unit_of_measure") or "").lower() else "annual",
    "skills_for_care_estimates": lambda r: "hourly"
        if r.get("hourly_pay") is not None else "annual",
    "charity_wage_series": lambda r: "annual",
}


def _pay_role_match(row: dict, fields: tuple[str, ...], term: str) -> bool:
    term = term.lower()
    return any(term in str(row.get(f) or "").lower() for f in fields)


def _apply_pay_filters(payload: dict, *, role: str | None, source: str | None,
                        pay_unit: str | None) -> None:
    """Narrow the already-built pay arrays in place (BETA-070).

    Order does not matter: each filter is a row predicate on one array, never
    a join or a rollup across arrays. A group the `source` filter excludes is
    emptied, not removed, so the payload shape is unchanged.
    """
    active_arrays: set[str] = set()
    for key, group in PAY_SOURCE_GROUPS.items():
        if source and key != source:
            for name in group["arrays"]:
                if name in payload:
                    payload[name] = []
            continue
        active_arrays.update(group["arrays"])

    for key, group in PAY_SOURCE_GROUPS.items():
        if source and key != source:
            continue
        for name in group["arrays"]:
            rows = payload.get(name)
            if not isinstance(rows, list) or not rows:
                continue
            if role:
                fields = group["role_fields"].get(name)
                rows = [r for r in rows if fields and _pay_role_match(r, fields, role)] \
                    if fields else []
            if pay_unit:
                unit_of = _PAY_UNIT_OF.get(name)
                rows = [r for r in rows if unit_of and unit_of(r) == pay_unit] \
                    if unit_of else []
            payload[name] = rows


def _pay_source_groups(payload: dict) -> list[dict]:
    """One entry per source group: label, row count, units, caveat keys.

    The count is the sum of the group's array lengths *after* filtering — an
    index the explorer can show, not a figure to quote. Groups stay separate.
    """
    out = []
    for key, group in PAY_SOURCE_GROUPS.items():
        count = sum(len(payload.get(name) or [])
                    for name in group["primary"] if isinstance(payload.get(name), list))
        out.append({
            "key": key,
            "label": group["label"],
            "count": count,
            "units": list(group["units"]),
            "arrays": list(group["arrays"]),
        })
    return out


def _pay_filters_available(payload: dict) -> dict:
    """Distinct role labels and units present in the current payload, so the
    explorer's selects are populated from data rather than a hard-coded list
    that drifts."""
    roles: set[str] = set()
    for group in PAY_SOURCE_GROUPS.values():
        for name, fields in group["role_fields"].items():
            for row in payload.get(name) or []:
                for f in fields:
                    value = str(row.get(f) or "").strip()
                    if value:
                        roles.add(value)
    return {
        "roles": sorted(roles)[:200],
        "pay_units": list(PAY_UNITS),
        "sources": [{"key": k, "label": v["label"]}
                    for k, v in PAY_SOURCE_GROUPS.items()],
    }


def pay(conn: sqlite3.Connection, *, provider_key=None, year_from=None,
         year_to=None, role=None, source=None, pay_unit=None) -> dict:
    """The campaign's central evidence, and the most caveat-heavy payload here.

    BETA-070: `role` (case-insensitive substring on each source's role text),
    `source` (one closed `PAY_SOURCE_GROUPS` key) and `pay_unit` (`hourly` /
    `annual` / `other`) narrow the returned rows. They never combine sources
    or produce a rate, ratio or score — the groups remain separate arrays.
    """
    if source is not None and source not in PAY_SOURCE_GROUPS:
        raise QueryError(f"unknown pay source {source!r}")
    if pay_unit is not None and pay_unit not in PAY_UNITS:
        raise QueryError(f"pay_unit must be one of {', '.join(PAY_UNITS)}")
    role = (role or "").strip() or None

    _public(["v_wage_per_employee", "charity_financials", "provider_identifiers",
              "providers", "nhs_job_adverts", "v_nhs_repeat_advertised_roles",
              "workforce_census_metrics", "statutory_pay_rates",
              "living_wage_accreditations", "gender_pay_gap_reports",
              "ons_ashe_observations", "provider_pay_mentions",
              "skills_for_care_estimates"])

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

    # These evidence layers deliberately remain separate arrays. The browser
    # can place two compatible hourly figures beside one another, but it has
    # no total or percentage to quote as though different sources measured the
    # same population and period.
    statutory_rates = _rows(conn, """
        SELECT period_label, effective_from, band_label, band_role, amount,
               value_text, source_url, retrieved_at, source_system, payload_sha256
        FROM statutory_pay_rates
        ORDER BY effective_from DESC, period_label DESC, band_label""")

    provider_params = {"provider_key": provider_key} if provider_key else {}
    living_wage = _rows(conn, f"""
        SELECT l.provider_key, p.canonical_name, l.searched_variant, l.accredited,
               l.employer_name, l.employer_node_id, l.match_basis, l.pages_checked,
               l.employers_total, l.source_url, l.retrieved_at, l.source_system,
               l.payload_sha256
        FROM living_wage_accreditations l
        LEFT JOIN providers p ON p.provider_key = l.provider_key
        {'WHERE l.provider_key = :provider_key' if provider_key else ''}
        ORDER BY p.canonical_name, l.searched_variant""", provider_params)
    gender_pay_gap = _rows(conn, f"""
        SELECT g.provider_key, p.canonical_name, g.reporting_year,
               g.reporting_year_label, g.employer_name, g.employer_id,
               g.match_basis, g.diff_mean_hourly_percent,
               g.diff_median_hourly_percent, g.diff_mean_bonus_percent,
               g.diff_median_bonus_percent, g.employer_size,
               g.written_statement_url, g.source_url, g.retrieved_at,
               g.source_system, g.payload_sha256
        FROM gender_pay_gap_reports g
        LEFT JOIN providers p ON p.provider_key = g.provider_key
        {'WHERE g.provider_key = :provider_key' if provider_key else ''}
        ORDER BY g.reporting_year DESC, p.canonical_name, g.employer_name""",
        provider_params)
    provider_published_pay = _rows(conn, f"""
        SELECT m.provider_key, p.canonical_name, m.page_url, m.section,
               m.mention_text, m.salary_raw, m.salary_min, m.salary_max,
               m.salary_period, m.salary_basis, m.match_basis, m.source_url,
               m.retrieved_at, m.source_system, m.payload_sha256
        FROM provider_pay_mentions m
        LEFT JOIN providers p ON p.provider_key = m.provider_key
        {'WHERE m.provider_key = :provider_key' if provider_key else ''}
        ORDER BY p.canonical_name, m.page_url, m.mention_index""", provider_params)
    ashe = _rows(conn, """
        SELECT dataset_id, dataset_title, edition, version, dimension_kind,
               dimension_code, dimension_label, geography_code, geography_label,
               time, value, value_text, unit_of_measure, source_url, retrieved_at,
               source_system, payload_sha256
        FROM ons_ashe_observations
        ORDER BY time DESC, dimension_kind, dimension_label, geography_label""")
    skills_for_care = _rows(conn, """
        SELECT file_url, year, area_code, area_level, region, area, sector,
               service, job_role_group, job_role, fte_annual_pay, hourly_pay,
               turnover_rate, vacancy_rate, source_url, retrieved_at,
               source_system, payload_sha256
        FROM skills_for_care_estimates
        WHERE area_level = 'National'
        ORDER BY year DESC, sector, service, job_role_group, job_role
        LIMIT 500""")

    payload = {
        "charity_wage_series": charity_wage_series,
        "nhs_job_adverts": adverts,
        "nhs_job_by_band": by_band,
        "repeat_advertised_roles": repeat_roles,
        "workforce_census": census,
        "statutory_pay_rates": statutory_rates,
        "living_wage_accreditations": living_wage,
        "gender_pay_gap_reports": gender_pay_gap,
        "provider_published_pay": provider_published_pay,
        "ons_ashe_observations": ashe,
        "skills_for_care_estimates": skills_for_care,
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
            "statutory_pay_rates_note": CAVEATS["statutory_pay_rates"],
            "living_wage_note": CAVEATS["living_wage_accreditations"],
            "gender_pay_gap_note": CAVEATS["gender_pay_gap"],
            "ashe_note": CAVEATS["ashe"],
            "provider_published_pay_note": CAVEATS["provider_published_pay"],
            "skills_for_care_note": CAVEATS["skills_for_care"],
        },
    }

    # BETA-070: the role picker is populated from every role present at the
    # current provider/year scope, before the role/unit filters narrow the
    # rows — otherwise choosing a role would empty its own picker.
    payload["filters_available"] = _pay_filters_available(payload)
    # Then narrow the arrays to the requested role / source group / pay unit
    # and attach the per-group index. `source_groups` counts are computed from
    # the final arrays, so a filtered view's counts match what it shows.
    # `census_*` counts above describe the unfiltered census and stay the
    # page's caveat basis.
    _apply_pay_filters(payload, role=role, source=source, pay_unit=pay_unit)
    payload["source_groups"] = _pay_source_groups(payload)
    payload["filters_applied"] = {
        "role": role, "source": source, "pay_unit": pay_unit,
        "provider_key": provider_key, "year_from": year_from, "year_to": year_to,
    }
    return payload


def council_spend(conn: sqlite3.Connection, *, authority_ons_code=None,
                  provider_key=None, limit: int = 500) -> dict:
    """Published council payment lines, kept separate from contract notices."""
    _public(["council_spend", "council_spend_files", "authorities", "providers"])

    where, params = [], {}
    if authority_ons_code:
        where.append("s.authority_ons_code = :authority_ons_code")
        params["authority_ons_code"] = authority_ons_code
    if provider_key:
        where.append("s.provider_key = :provider_key")
        params["provider_key"] = provider_key
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    total = _one(conn, f"SELECT COUNT(*) AS n FROM council_spend s{clause}", params).get("n", 0)
    rows = _rows(conn, f"""
        SELECT s.authority_ons_code, a.name AS authority_name, s.file_url,
               s.row_index, s.period, s.payee, s.amount, s.amount_text,
               s.description, s.provider_key, p.canonical_name,
               s.source_url, s.retrieved_at, s.source_system, s.payload_sha256
        FROM council_spend s
        LEFT JOIN authorities a ON a.ons_code = s.authority_ons_code
        LEFT JOIN providers p ON p.provider_key = s.provider_key
        {clause}
        ORDER BY s.retrieved_at DESC, s.authority_ons_code, s.file_url, s.row_index
        LIMIT :limit""", {**params, "limit": limit})

    file_where, file_params = [], {}
    if authority_ons_code:
        file_where.append("f.authority_ons_code = :authority_ons_code")
        file_params["authority_ons_code"] = authority_ons_code
    file_clause = f" WHERE {' AND '.join(file_where)}" if file_where else ""
    files = _rows(conn, f"""
        SELECT f.authority_ons_code, a.name AS authority_name, f.file_url,
               f.discovered_from, f.file_format, f.parse_status, f.row_count,
               f.source_url, f.retrieved_at, f.source_system, f.payload_sha256
        FROM council_spend_files f
        LEFT JOIN authorities a ON a.ons_code = f.authority_ons_code
        {file_clause}
        ORDER BY f.retrieved_at DESC, f.authority_ons_code, f.file_url""", file_params)
    return {
        "total": total,
        "payments": rows,
        "files": files,
        "caveats": {
            "payments": CAVEATS["council_spend"],
            "provider_match": CAVEATS["council_spend_match"],
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


# --- unified evidence atlas (BETA-078) ------------------------------------
#
# One closed registry of every layer the atlas can show. Exactly one is drawn
# at a time — there is no overlay, no arithmetic between layers and no
# composite score. Each entry carries everything a client needs to render the
# layer and its accessible table without knowing anything else about it:
# which existing endpoint serves it, the legend, the unit, the caveat, the
# GeoJSON property that keys a feature, and the table columns.
#
# `kind`:
#   "choropleth" — an authority fill from /api/v1/geography?metric=<param>
#   "points"     — markers/clusters from /api/v1/layers, layer <layer>
#   "authority"  — an authority fill from /api/v1/layers, layer <layer>

def _atlas_choropleth(key: str, legend: str, caveat: str) -> dict:
    meta = GEOGRAPHY_METRICS[key]
    return {
        "key": key, "label": meta["label"], "kind": "choropleth",
        "endpoint": "geography", "param": {"metric": key}, "unit": meta["unit"],
        "legend": legend, "geometry_key": "ons_code", "caveat": caveat,
        "table_columns": ["authority_name", "region", "value"],
    }


def atlas_layers() -> dict:
    """The closed atlas layer registry (BETA-078). No DB read: this is a
    manifest the geography workspace uses to offer one layer at a time."""
    layers = [
        _atlas_choropleth(
            "grant_drug_alcohol", "Darker = larger ring-fenced allocation",
            "The ring-fenced figure is part of the total grant, not additional "
            "to it. It is never summed with or differenced from the total."),
        _atlas_choropleth(
            "grant_total", "Darker = larger total allocation",
            CAVEATS["grant_not_budget"]),
        _atlas_choropleth(
            "grant_per_head", "Darker = higher allocation per head",
            "Per-head figures use the grant's own published denominator; they "
            "are not recomputed here."),
        _atlas_choropleth(
            "budget_public_health", "Darker = larger budgeted spend",
            CAVEATS["budget_detail"]),
        _atlas_choropleth(
            "treatment_numbers", "Darker = more people in treatment",
            "A published service-demand figure, not a workforce or need "
            "figure, and never divided by one."),
        _atlas_choropleth(
            "contract_value", "Darker = higher awarded notice value",
            CAVEATS["contract_value"]),
        {
            "key": "cqc_locations", "label": "CQC-registered locations",
            "kind": "points", "endpoint": "layers", "layer": "cqc_locations",
            "unit": "one marker per registered location",
            "legend": "Clusters show a count; a single marker is one location",
            "geometry_key": "location_id",
            "table_columns": ["location_name", "region", "overall_rating"],
            "caveat": " ".join(LAYER_CAVEATS["cqc_locations"]),
        },
        {
            "key": "coverage", "label": "What evidence is held here",
            "kind": "authority", "endpoint": "layers", "layer": "coverage",
            "unit": "count of evidence kinds held",
            "legend": "Darker = more kinds of evidence held for this authority",
            "geometry_key": "ons_code",
            "table_columns": ["authority_name", "kinds_held"],
            "caveat": CAVEATS["coverage_absence"],
        },
    ]
    return {
        "layers": layers,
        "note": "Exactly one layer is shown at a time. The atlas performs no "
                "arithmetic between layers and produces no composite score.",
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


def treatment_metrics(conn: sqlite3.Connection) -> dict:
    """A catalogue of treatment metrics, shown before a chart is drawn
    (BETA-075).

    Definition, unit, whether a 95% CI is published, the exact periods held,
    authority and England coverage, and provenance — computed from the same
    tables the treatment page charts, so a catalogue row cannot claim coverage
    the chart does not have. Missing periods stay missing: `periods` is exactly
    what was published for that metric, ordered, with no gap filled or zeroed.
    """
    _public(["fingertips_indicators", "fingertips_la_values",
              "ndtms_la_statistics"])

    metrics: list[dict] = []

    indicators = _rows(conn, """
        SELECT indicator_id, indicator_name, topic, substance, unit,
               definition, source_url, retrieved_at
        FROM fingertips_indicators
        ORDER BY topic, indicator_name""")
    for ind in indicators:
        cov = _one(conn, """
            SELECT COUNT(DISTINCT CASE WHEN area_level = 'local_authority'
                                       THEN ons_code END) AS authority_count,
                   MAX(CASE WHEN area_level = 'england' THEN 1 ELSE 0 END) AS england,
                   MAX(CASE WHEN lower_ci_95 IS NOT NULL THEN 1 ELSE 0 END) AS has_ci,
                   MAX(retrieved_at) AS retrieved_at
            FROM fingertips_la_values WHERE indicator_id = ?""",
            (ind["indicator_id"],))
        periods = [r["time_period"] for r in _rows(conn, """
            SELECT DISTINCT time_period, time_period_sortable
            FROM fingertips_la_values WHERE indicator_id = ?
            ORDER BY time_period_sortable""", (ind["indicator_id"],))]
        metrics.append({
            "source": "fingertips",
            "key": f"fingertips:{ind['indicator_id']}",
            "indicator_id": ind["indicator_id"],
            "name": ind["indicator_name"],
            "topic": ind["topic"],
            "substance": ind["substance"],
            "unit": ind["unit"],
            "definition": ind["definition"],
            "has_confidence_interval": bool(cov.get("has_ci")),
            "periods": periods,
            "period_count": len(periods),
            "period_range": [periods[0], periods[-1]] if periods else None,
            "authority_count": cov.get("authority_count") or 0,
            "england_available": bool(cov.get("england")),
            "source_url": ind["source_url"],
            "retrieved_at": cov.get("retrieved_at") or ind["retrieved_at"],
        })

    # NDTMS: one catalogue row per source table seen, labelled from the
    # edition-independent map. Every NDTMS figure is a modelled estimate
    # published with a 95% CI, so `has_confidence_interval` is always true.
    ndtms_refs = _rows(conn, """
        SELECT table_ref,
               COUNT(DISTINCT ons_code) AS authority_count,
               COUNT(DISTINCT time_period) AS period_count,
               MIN(time_period) AS first_period,
               MAX(time_period) AS last_period,
               MAX(retrieved_at) AS retrieved_at,
               MAX(source_url) AS source_url
        FROM ndtms_la_statistics
        GROUP BY table_ref ORDER BY table_ref""")
    for r in ndtms_refs:
        ref = r["table_ref"] or ""
        prevalence = ref in ("Table_2_1", "2_1_Drug_prevalence", "Table_2_2",
                              "2_2_Alcohol_prevalence") or "prevalence" in ref.lower()
        metrics.append({
            "source": "ndtms",
            "key": f"ndtms:{ref}",
            "name": NDTMS_TABLES.get(ref, ref or "NDTMS estimate"),
            "topic": "prevalence" if prevalence else "harm",
            "substance": None,
            "unit": "modelled estimate with 95% CI",
            "definition": "NDTMS modelled local-authority estimate, published "
                          "by OHID with a 95% confidence interval.",
            "has_confidence_interval": True,
            "periods": None,
            "period_count": r["period_count"] or 0,
            "period_range": [r["first_period"], r["last_period"]],
            "authority_count": r["authority_count"] or 0,
            "england_available": False,
            "source_url": r["source_url"],
            "retrieved_at": r["retrieved_at"],
        })

    return {
        "metrics": metrics,
        "count": len(metrics),
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


def _sar_payload(conn: sqlite3.Connection) -> dict:
    """The sector-level view of the Safeguarding Adult Review corpus.

    Deliberately thinner than the PFD payload above it: the source gives no
    structured date and no per-document excerpt to show (see
    m28_sar_reports's docstring on why no section is auto-extracted), so
    there is no "matters of concern" equivalent and no by-year concerns
    split -- only what the source actually supports: counts, the boards that
    named themselves, term frequency, and provider mentions.
    """
    _public(["sar_documents", "sar_concern_terms", "sar_provider_mentions"])

    documents = _rows(conn, """
        SELECT document_url, document_ext, library_year, sab_name,
               has_body_text, source_url, retrieved_at
        FROM sar_documents""")

    by_year: dict[int, dict] = {}
    by_board: dict[str, int] = {}
    for document in documents:
        bucket = by_year.setdefault(
            document["library_year"], {"year": document["library_year"],
                                         "documents": 0, "with_text": 0})
        bucket["documents"] += 1
        bucket["with_text"] += int(document["has_body_text"])
        if document["sab_name"]:
            by_board[document["sab_name"]] = by_board.get(document["sab_name"], 0) + 1

    return {
        "totals": {
            "documents": len(documents),
            "with_text": sum(1 for d in documents if d["has_body_text"]),
            "with_board_name": sum(1 for d in documents if d["sab_name"]),
        },
        "by_year": [by_year[y] for y in sorted(by_year)],
        "by_board": [
            {"sab_name": name, "documents": count}
            for name, count in sorted(by_board.items(), key=lambda kv: -kv[1])[:25]],
        "concern_terms": _rows(conn, """
            SELECT term, SUM(occurrences) AS occurrences
            FROM sar_concern_terms GROUP BY term
            ORDER BY occurrences DESC, term LIMIT 25"""),
        "mentions": {
            "naming_providers": _one(
                conn, "SELECT COUNT(DISTINCT document_url) AS n "
                      "FROM sar_provider_mentions").get("n", 0),
        },
        # Newest library year first; there is no finer-grained date to sort
        # on, so within a year the order is whatever SQLite returns.
        "recent": _rows(conn, """
            SELECT document_url, document_ext, library_year, sab_name,
                   has_body_text, source_url, retrieved_at
            FROM sar_documents ORDER BY library_year DESC LIMIT 50"""),
        "caveats": {
            "scope": CAVEATS["sar_scope"],
            "board": CAVEATS["sar_board"],
            "mentions": CAVEATS["sar_mentions"],
            "terms": CAVEATS["sar_terms"],
        },
    }


def safety(conn: sqlite3.Connection) -> dict:
    """HSE enforcement notices attributed to a tracked provider (BETA-051).

    Only `provider_key IS NOT NULL` rows — an exact tracked-name match, made
    by `m33_hse_notices` — reach here; notices served on individuals were
    excluded at collection. Every field is the register's own text, and the
    published `result` (which may be an appeal decision or a withdrawal)
    travels with each notice. Nothing here infers a compliance outcome.
    """
    _public(["hse_enforcement_notices", "providers"])

    if not any(obj["name"] == "hse_enforcement_notices"
               for obj in catalog.list_objects(conn)):
        return {"notices": [], "by_provider": [], "by_type": [],
                "total": 0, "caveat": CAVEATS["hse_notices"]}

    notices = _rows(conn, """
        SELECT h.notice_number, h.recipient_name, h.provider_key,
               p.canonical_name AS provider_name,
               h.notice_type, h.issuing_body, h.issue_date, h.compliance_date,
               h.revised_compliance_date, h.result, h.industry, h.legislation,
               h.contravention_text, h.local_authority,
               h.source_url, h.retrieved_at
        FROM hse_enforcement_notices h
        LEFT JOIN providers p ON p.provider_key = h.provider_key
        WHERE h.provider_key IS NOT NULL
        ORDER BY h.issue_date DESC NULLS LAST, h.notice_number""")

    by_provider = _rows(conn, """
        SELECT h.provider_key, p.canonical_name AS provider_name,
               COUNT(*) AS notice_count
        FROM hse_enforcement_notices h
        LEFT JOIN providers p ON p.provider_key = h.provider_key
        WHERE h.provider_key IS NOT NULL
        GROUP BY h.provider_key, p.canonical_name
        ORDER BY notice_count DESC, p.canonical_name""")

    by_type = _rows(conn, """
        SELECT h.notice_type, COUNT(*) AS notice_count
        FROM hse_enforcement_notices h
        WHERE h.provider_key IS NOT NULL
        GROUP BY h.notice_type ORDER BY notice_count DESC, h.notice_type""")

    return {
        "notices": notices,
        "by_provider": by_provider,
        "by_type": by_type,
        "total": len(notices),
        "caveat": CAVEATS["hse_notices"],
    }


# --- safety and legal evidence hub (BETA-079) ---------------------------------
#
# Five distinct accountability sources on one filterable chronology. They
# encode materially different relationships and standards, so each event is
# tagged with exactly one of these — and the four are NEVER summed, NEVER
# treated as interchangeable, and a mention is NEVER a finding of fault:
#
#   addressed_to  — the document was formally sent to this organisation
#   named_in      — the organisation is mentioned in the source text
#   matched_to    — attributed by an exact name match in a public register
#   regulated_by  — the organisation holds a registration/inspection record
#
SAFETY_LEGAL_LABELS = {
    "addressed_to": "Addressed to — the source document was formally sent to "
                    "this organisation.",
    "named_in": "Named in — this organisation is mentioned in the source text. "
                "A mention is not a finding, an allegation or a fault.",
    "matched_to": "Matched to — attributed by an exact match of the "
                  "organisation's name in a public register.",
    "regulated_by": "Regulated by — this organisation holds a registration or "
                    "inspection record with the regulator.",
}

SAFETY_LEGAL_SOURCES = ("pfd", "sar", "hse", "tribunal", "cqc")

_SAFETY_LEGAL_MAX = 2000


def safety_legal(conn: sqlite3.Connection, *, source=None, relationship=None,
                  provider_key=None, year_from=None, year_to=None) -> dict:
    """One filterable chronology over PFD reports, Safeguarding Adult Reviews,
    HSE notices, employment-tribunal cases and CQC inspections (BETA-079).

    Each event carries exactly one relationship label; the per-source and
    per-relationship counts are returned separately and are never added
    together. Personal data stays in the `restricted_` tables this does not
    read.
    """
    _public(["pfd_reports", "pfd_provider_mentions", "sar_documents",
              "sar_provider_mentions", "hse_enforcement_notices",
              "tribunal_cases", "cqc_locations", "providers"])

    present = {obj["name"] for obj in catalog.list_objects(conn)}
    events: list[dict] = []

    def keep(row: dict) -> None:
        events.append(row)

    if {"pfd_reports", "pfd_provider_mentions"} <= present:
        for r in _rows(conn, """
            SELECT m.mention_type, m.matched_name, m.provider_key,
                   p.canonical_name, r.report_date, r.report_ref, r.report_url,
                   r.coroner_area, r.source_url
            FROM pfd_provider_mentions m
            JOIN pfd_reports r ON r.report_ref = m.report_ref
            LEFT JOIN providers p ON p.provider_key = m.provider_key
            ORDER BY r.report_date DESC NULLS LAST"""):
            keep({
                "source": "pfd",
                "relationship": "addressed_to"
                    if r["mention_type"] == "recipient" else "named_in",
                "date": r["report_date"],
                "entity_key": r["provider_key"],
                "entity_name": r["canonical_name"] or r["matched_name"],
                "entity_type": "provider",
                "title": f"Prevention of Future Deaths report {r['report_ref']}",
                "detail": f"Coroner area: {r['coroner_area'] or 'not recorded'}",
                "result": None,
                "source_url": r["report_url"] or r["source_url"],
            })

    if {"sar_documents", "sar_provider_mentions"} <= present:
        for r in _rows(conn, """
            SELECT m.matched_name, m.provider_key, p.canonical_name,
                   d.document_url, d.sab_name, d.library_year
            FROM sar_provider_mentions m
            JOIN sar_documents d ON d.document_url = m.document_url
            LEFT JOIN providers p ON p.provider_key = m.provider_key"""):
            keep({
                "source": "sar",
                "relationship": "named_in",
                "date": None,
                "entity_key": r["provider_key"],
                "entity_name": r["canonical_name"] or r["matched_name"],
                "entity_type": "provider",
                "title": "Safeguarding Adult Review"
                         + (f" — {r['sab_name']}" if r["sab_name"] else ""),
                "detail": "National SAR Library"
                          + (f", library year {r['library_year']}"
                             if r["library_year"] else "")
                          + "; no structured report date is published.",
                "result": None,
                "source_url": r["document_url"],
            })

    if "hse_enforcement_notices" in present:
        for r in _rows(conn, """
            SELECT h.notice_number, h.provider_key, p.canonical_name,
                   h.recipient_name, h.notice_type, h.issue_date, h.result,
                   h.source_url
            FROM hse_enforcement_notices h
            LEFT JOIN providers p ON p.provider_key = h.provider_key
            WHERE h.provider_key IS NOT NULL
            ORDER BY h.issue_date DESC NULLS LAST"""):
            keep({
                "source": "hse",
                "relationship": "matched_to",
                "date": r["issue_date"],
                "entity_key": r["provider_key"],
                "entity_name": r["canonical_name"] or r["recipient_name"],
                "entity_type": "provider",
                "title": f"HSE {r['notice_type'] or 'enforcement'} notice {r['notice_number']}",
                "detail": "Register text as published.",
                # The published result may be an appeal decision or a
                # withdrawal — it travels with the notice, never inferred.
                "result": r["result"],
                "source_url": r["source_url"],
            })

    if "tribunal_cases" in present:
        for r in _rows(conn, """
            SELECT t.case_number, t.provider_key, p.canonical_name,
                   t.respondent_normalised, t.decision_date, t.outcome,
                   t.outcome_confidence, t.source_url
            FROM tribunal_cases t
            LEFT JOIN providers p ON p.provider_key = t.provider_key
            WHERE t.provider_key IS NOT NULL
            ORDER BY t.decision_date DESC NULLS LAST"""):
            keep({
                "source": "tribunal",
                "relationship": "named_in",
                "date": r["decision_date"],
                "entity_key": r["provider_key"],
                "entity_name": r["canonical_name"] or r["respondent_normalised"],
                "entity_type": "provider",
                "title": f"Employment tribunal case {r['case_number']}",
                "detail": "A case with this organisation as a party. The "
                          "outcome and its confidence are the source's.",
                "result": (f"{r['outcome']} ({r['outcome_confidence']} confidence)"
                           if r["outcome"] else None),
                "source_url": r["source_url"],
            })

    if "cqc_locations" in present:
        for r in _rows(conn, """
            SELECT c.location_id, c.provider_key, p.canonical_name,
                   c.location_name, c.last_inspection_date, c.overall_rating,
                   c.overall_rating_date, c.source_url
            FROM cqc_locations c
            LEFT JOIN providers p ON p.provider_key = c.provider_key
            WHERE c.provider_key IS NOT NULL
              AND (c.last_inspection_date IS NOT NULL
                   OR c.overall_rating_date IS NOT NULL)
            ORDER BY COALESCE(c.last_inspection_date, c.overall_rating_date) DESC"""):
            keep({
                "source": "cqc",
                "relationship": "regulated_by",
                "date": r["last_inspection_date"] or r["overall_rating_date"],
                "entity_key": r["provider_key"],
                "entity_name": r["canonical_name"],
                "entity_type": "provider",
                "title": f"CQC inspection — {r['location_name']}",
                "detail": "A regulated location's most recent inspection. "
                          "CQC registration covers only some service types.",
                "result": r["overall_rating"],
                "source_url": r["source_url"],
            })

    def year_of(value: str | None) -> str:
        return (value or "")[:4]

    if source:
        events = [e for e in events if e["source"] == source]
    if relationship:
        events = [e for e in events if e["relationship"] == relationship]
    if provider_key:
        events = [e for e in events if e["entity_key"] == provider_key]
    if year_from:
        events = [e for e in events
                  if e["date"] and year_of(e["date"]) >= str(year_from)]
    if year_to:
        events = [e for e in events
                  if e["date"] and year_of(e["date"]) <= str(year_to)]

    # Dated first (newest first), then the undated (SAR) at the end.
    events.sort(key=lambda e: (e["date"] or "", ), reverse=True)
    truncated = len(events) > _SAFETY_LEGAL_MAX
    events = events[:_SAFETY_LEGAL_MAX]

    by_source: dict[str, int] = {}
    by_relationship: dict[str, int] = {}
    for e in events:
        by_source[e["source"]] = by_source.get(e["source"], 0) + 1
        by_relationship[e["relationship"]] = \
            by_relationship.get(e["relationship"], 0) + 1

    return {
        "events": events,
        "truncated": truncated,
        "counts": {"by_source": by_source, "by_relationship": by_relationship},
        "labels": SAFETY_LEGAL_LABELS,
        "sources": list(SAFETY_LEGAL_SOURCES),
        "caveats": {
            "pfd": CAVEATS["pfd_mentions"],
            "sar": "SAR reports carry no structured date or excerpt; this "
                   "stream is a finding aid to the National SAR Library.",
            "hse": CAVEATS["hse_notices"],
            "tribunal": "A tribunal case names an organisation as a party. It "
                        "is not a finding against a named provider unless the "
                        "decision itself says so.",
            "cqc": "CQC registration covers only some service types; most "
                   "community drug and alcohol provision is not CQC-registered.",
        },
        "note": "Five distinct evidence streams. Their counts are shown by "
                "source and by relationship and are never added together. A "
                "mention is never a finding of fault.",
    }


# The exact columns the CQC-location explorer publishes. An allowlist, not a
# `SELECT *`: `cqc_locations` carries no personal data (registered managers
# are in `restricted_cqc_location_contacts`, a separate table), but naming
# the columns keeps it that way through a future ALTER.
_CQC_LOCATION_COLUMNS = (
    "location_id", "provider_id", "provider_key", "location_name", "postal_code",
    "latitude", "longitude", "local_authority_raw", "local_authority_ons_code",
    "region", "registration_status", "registration_date", "last_inspection_date",
    "overall_rating", "overall_rating_date", "regulated_activities",
    "service_types", "source_url", "retrieved_at",
)

_CQC_LOCATION_PAGE = 100
_CQC_LOCATION_MAX = 500


def cqc_locations(conn: sqlite3.Connection, *,
                  provider_key: str | None = None,
                  authority_ons_code: str | None = None,
                  registration_status: str | None = None,
                  regulated_activity: str | None = None,
                  service_type: str | None = None,
                  rating: str | None = None,
                  limit: int = _CQC_LOCATION_PAGE, offset: int = 0) -> dict:
    """CQC-registered locations of tracked providers (BETA-065).

    Only `provider_key IS NOT NULL` rows — a location matched to a provider
    this pipeline tracks. Read-only, no personal data (registered managers
    live in `restricted_cqc_location_contacts`, never touched here). Every
    field is CQC's own; `rating_source` names whether the rating came from
    the API or the bulk-export fallback. This is not a service map and a
    location count is not coverage — see the caveat.

    `regulated_activity` is a contains match because CQC's activity names
    themselves contain commas, so the comma-joined column cannot be split
    unambiguously; `service_type` is an exact token match on the
    (comma-separated, comma-free) gacServiceType names.
    """
    _public(["cqc_locations", "providers"], list(_CQC_LOCATION_COLUMNS)
            + ["bulk_overall_rating", "bulk_overall_rating_date",
               "bulk_rating_source_url"])

    where = ["l.provider_key IS NOT NULL"]
    binds: list = []
    if provider_key:
        where.append("l.provider_key = ?")
        binds.append(provider_key)
    if authority_ons_code:
        where.append("l.local_authority_ons_code = ?")
        binds.append(authority_ons_code)
    if registration_status:
        where.append("l.registration_status = ?")
        binds.append(registration_status)
    if rating:
        where.append("COALESCE(l.overall_rating, l.bulk_overall_rating) = ?")
        binds.append(rating)
    if regulated_activity:
        where.append("COALESCE(l.regulated_activities, '') LIKE ? ESCAPE '\\'")
        binds.append(f"%{escape_like(regulated_activity)}%")
    if service_type:
        where.append(
            "(',' || COALESCE(l.service_types, '') || ',') LIKE ? ESCAPE '\\'")
        binds.append(f"%,{escape_like(service_type)},%")

    clause = " AND ".join(where)
    limit = max(1, min(int(limit), _CQC_LOCATION_MAX))
    offset = max(0, int(offset))

    cols = ", ".join(f"l.{c}" for c in _CQC_LOCATION_COLUMNS)
    total = conn.execute(
        f"SELECT COUNT(*) FROM cqc_locations l WHERE {clause}", binds).fetchone()[0]
    without_coordinate = conn.execute(
        f"SELECT COUNT(*) FROM cqc_locations l WHERE {clause} "
        "AND (l.latitude IS NULL OR l.longitude IS NULL)", binds).fetchone()[0]

    rows = _rows(conn, f"""
        SELECT {cols}, p.canonical_name AS provider_name,
               l.bulk_overall_rating, l.bulk_overall_rating_date
        FROM cqc_locations l
        LEFT JOIN providers p ON p.provider_key = l.provider_key
        WHERE {clause}
        ORDER BY p.canonical_name, l.location_name, l.location_id
        LIMIT ? OFFSET ?""", [*binds, limit, offset])

    for row in rows:
        bulk = row.pop("bulk_overall_rating")
        bulk_date = row.pop("bulk_overall_rating_date")
        if row["overall_rating"] is None and bulk is not None:
            row["overall_rating"] = bulk
            row["overall_rating_date"] = bulk_date
            row["rating_source"] = "bulk_export"
        else:
            row["rating_source"] = "api" if row["overall_rating"] is not None else None

    # Facets over the base tracked-location scope (the provider_key filter),
    # not the other selections — so the buckets a reader can switch to stay
    # visible with their sizes while a selection narrows the table.
    facet_where = "l.provider_key IS NOT NULL"
    facet_binds: list = []
    if provider_key:
        facet_where += " AND l.provider_key = ?"
        facet_binds.append(provider_key)

    def _facet(expr: str) -> list[dict]:
        return _rows(conn, f"""
            SELECT {expr} AS value, COUNT(*) AS count
            FROM cqc_locations l WHERE {facet_where} AND {expr} IS NOT NULL
            GROUP BY value ORDER BY count DESC, value""", facet_binds)

    # Split in Python rather than a recursive CTE: the separator is a plain
    # comma and this keeps the query dialect-free.
    service_type_counts: dict[str, int] = {}
    for row in _rows(conn,
                     f"SELECT service_types FROM cqc_locations l WHERE {facet_where}",
                     facet_binds):
        for token in (row["service_types"] or "").split(","):
            token = token.strip()
            if token:
                service_type_counts[token] = service_type_counts.get(token, 0) + 1
    service_type_facet = [
        {"value": value, "count": count}
        for value, count in sorted(service_type_counts.items(),
                                    key=lambda kv: (-kv[1], kv[0]))]

    return {
        "results": rows,
        "total": total,
        "without_coordinate": without_coordinate,
        "limit": limit,
        "offset": offset,
        "filters": {
            "provider_key": provider_key,
            "authority_ons_code": authority_ons_code,
            "registration_status": registration_status,
            "regulated_activity": regulated_activity,
            "service_type": service_type,
            "rating": rating,
        },
        "facets": {
            "registration_status": _facet("l.registration_status"),
            "overall_rating": _facet(
                "COALESCE(l.overall_rating, l.bulk_overall_rating)"),
            "region": _facet("l.region"),
            "service_type": service_type_facet,
        },
        "caveat": CAVEATS["cqc_locations_explorer"],
    }


def pfd(conn: sqlite3.Connection) -> dict:
    """The sector-level view of the coroners' report corpus, plus Safeguarding
    Adult Reviews (see `_sar_payload`) -- two distinct evidence streams under
    one "Safety & legal evidence" page, never combined into one series."""
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
        "sar": _sar_payload(conn),
    }


def all_pfd_reports(conn: sqlite3.Connection, *, batch: int = 2000
                     ) -> tuple[int, Iterator[dict]]:
    """Every PFD report, counted first and then streamed.

    `pfd()` above returns `recent` — the newest 50, because it is answering
    a page that already has other things to show beside the table. This
    answers a download, where the cap is the bug: an export that ships the
    newest 50 of 1,500+ reports and says nothing looks complete and is a few
    percent of the corpus — the same failure `all_contract_notices` exists
    to refuse (see its own docstring; this follows the identical shape:
    count first, stream second, no `deadline()` guard because a complete
    export is meant to take as long as it takes).

    No filters, because `pfd()` itself takes none — every report is public
    and there is no per-authority or per-provider slice of this corpus the
    way contracts has one.
    """
    _public(["pfd_reports"])
    total = _one(conn, "SELECT COUNT(*) AS n FROM pfd_reports").get("n", 0)

    def rows() -> Iterator[dict]:
        cursor = conn.execute("""
            SELECT report_ref, report_date, coroner_area, categories,
                   report_url, matters_of_concern IS NOT NULL AS has_concerns,
                   source_url, retrieved_at
            FROM pfd_reports ORDER BY report_ref DESC""")
        try:
            while True:
                fetched = cursor.fetchmany(batch)
                if not fetched:
                    return
                yield from (dict(row) for row in fetched)
        finally:
            cursor.close()

    return total, rows()


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

    # The successor's display name, so the portal can link "now trading as X"
    # / "merged into X" rather than printing a slug.
    if provider.get("superseded_by"):
        successor = _one(conn, "SELECT canonical_name FROM providers WHERE provider_key = ?",
                          (provider["superseded_by"],))
        provider["superseded_by_name"] = successor.get("canonical_name") if successor else None

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
               source_url, retrieved_at,
               bulk_overall_rating, bulk_overall_rating_date, bulk_rating_source_url
        FROM cqc_locations WHERE provider_key = ?
        ORDER BY location_name""", (provider_key,))
    # m26_cqc_directory backfills these two only when the API supplied
    # nothing at all for a location -- see its module docstring for why a
    # re-run of m05_cqc does not fix that. overall_rating/overall_rating_date
    # stay in the payload exactly as the API said (including staying None);
    # rating_source names which one a reader is actually looking at.
    for row in locations:
        if row["overall_rating"] is None and row["bulk_overall_rating"] is not None:
            row["overall_rating"] = row["bulk_overall_rating"]
            row["overall_rating_date"] = row["bulk_overall_rating_date"]
            row["rating_source"] = "bulk_export"
        else:
            row["rating_source"] = "api" if row["overall_rating"] is not None else None

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
        SELECT l.location_id, l.location_name, r.report_date, r.first_visit_date, r.report_uri,
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

    Thirteen statements until Phase 4 — one asking which tables exist, per
    column, plus a count per column — and one now. The authority page is the
    heaviest payload the portal serves (40 statements, of which round-trips
    over a LAN were most of the 380ms), and this was the only part of it that
    could be folded: everything else here is `fingertips`, `ndtms` and
    `contracts` composed rather than re-written, which is a guarantee that a
    figure on this page matches the page it came from and worth more than the
    statements it costs.
    """
    # `sqlite_master` has no PostgreSQL equivalent, so "does the warehouse
    # hold this table?" is asked through catalog, which speaks to both. Named
    # directly here until Phase 4, which made this route fail outright on
    # PostgreSQL.
    present = set(catalog.table_names(conn))

    # Table and column names come from health.COVERAGE_COLUMNS, which is code,
    # not a request, so interpolating them is the same trust as the admin
    # matrix. The ordinal carries the position back: `UNION ALL` does not
    # promise to return branches in the order they were written.
    counted = [(label, table, column)
                for label, table, column, _module in health.COVERAGE_COLUMNS
                if table in present]
    cells = {label: 0 for label, _t, _c, _m in health.COVERAGE_COLUMNS}
    if not counted:
        return cells

    sql = " UNION ALL ".join(
        f"SELECT {i} AS i, COUNT(*) AS n FROM {table} WHERE {column} = ?"
        for i, (_label, table, column) in enumerate(counted)
    ) + " ORDER BY i"
    for row in conn.execute(sql, tuple(ons_code for _ in counted)):
        cells[counted[row["i"]][0]] = row["n"]
    return cells


# provider status -> the forward relationship it implies, when there is a
# `superseded_by`. `dissolved` has no target and is terminal.
_LINEAGE_FORWARD = {
    "renamed": "renamed_to",
    "merged": "merged_into",
}
_LINEAGE_REVERSE = {
    "renamed": "renamed_from",
    "merged": "merged_from",
}
_LINEAGE_CHAIN_CAP = 20


def provider_lineage(conn: sqlite3.Connection, provider_key: str) -> dict:
    """The verified administrative lineage of one provider entity (BETA-066).

    Reads only the lifecycle config already on `providers` (`status`,
    `superseded_by`, seeded from `pipeline/providers.py::PROVIDER_STATUS`) and
    the config-verified rows of `provider_identifiers`. It produces explicit
    typed edges — `renamed_to` / `merged_into` / `dissolved` forward,
    `renamed_from` / `merged_from` back — never an inferred ownership link and
    never a person. Evidence that names an old identity stays attached to its
    own `provider_key`; this describes the entity, not the evidence.
    """
    _public(["providers", "provider_identifiers"])

    provider = _one(
        conn,
        "SELECT provider_key, canonical_name, status, superseded_by, is_target "
        "FROM providers WHERE provider_key = ?", (provider_key,))
    if not provider:
        raise QueryError(f"No provider {provider_key!r}.")

    def _name(key: str) -> str | None:
        row = _one(conn, "SELECT canonical_name FROM providers WHERE provider_key = ?",
                    (key,))
        return row["canonical_name"] if row else None

    edges: list[dict] = []
    basis = ("provider lifecycle config (pipeline/providers.py PROVIDER_STATUS), "
             "cross-checked against the registered company/charity record")

    status = provider["status"]
    superseded_by = provider["superseded_by"]
    if status == "dissolved":
        edges.append({
            "relationship": "dissolved", "direction": "terminal",
            "provider_key": None, "canonical_name": None, "basis": basis})
    elif status in _LINEAGE_FORWARD and superseded_by:
        edges.append({
            "relationship": _LINEAGE_FORWARD[status], "direction": "successor",
            "provider_key": superseded_by, "canonical_name": _name(superseded_by),
            "basis": basis})

    # Reverse edges: every provider whose config points at this one.
    for row in _rows(
        conn,
        "SELECT provider_key, canonical_name, status FROM providers "
        "WHERE superseded_by = ? ORDER BY canonical_name", (provider_key,)):
        edges.append({
            "relationship": _LINEAGE_REVERSE.get(row["status"], "superseded_from"),
            "direction": "predecessor",
            "provider_key": row["provider_key"],
            "canonical_name": row["canonical_name"], "basis": basis})

    # The forward chain to the surviving entity, with a cycle guard.
    chain: list[dict] = [{
        "provider_key": provider["provider_key"],
        "canonical_name": provider["canonical_name"],
        "status": provider["status"]}]
    seen = {provider_key}
    cursor = superseded_by
    while cursor and cursor not in seen and len(chain) < _LINEAGE_CHAIN_CAP:
        seen.add(cursor)
        row = _one(conn,
                    "SELECT provider_key, canonical_name, status, superseded_by "
                    "FROM providers WHERE provider_key = ?", (cursor,))
        if not row:
            break
        chain.append({"provider_key": row["provider_key"],
                       "canonical_name": row["canonical_name"],
                       "status": row["status"]})
        cursor = row["superseded_by"]

    identifiers = _rows(
        conn,
        "SELECT scheme, identifier, role FROM provider_identifiers "
        "WHERE provider_key = ? AND status = 'verified' "
        "ORDER BY scheme, identifier", (provider_key,))

    return {
        "provider": {
            "provider_key": provider["provider_key"],
            "canonical_name": provider["canonical_name"],
            "status": provider["status"],
            "is_target": bool(provider["is_target"]),
        },
        "edges": edges,
        "chain": chain,
        "identifiers": identifiers,
        "caveat": CAVEATS["provider_lineage"],
    }


def authority(conn: sqlite3.Connection, ons_code: str) -> dict:
    """Everything the warehouse holds about one authority, in one payload."""
    _public(["authorities", "public_health_grants", "la_revenue_budgets",
              "v_la_public_health_budget", "fingertips_indicators",
              "fingertips_la_values", "ndtms_la_statistics", "ndtms_publications",
              "contracts", "supplier_aliases", "providers", "cqc_locations",
              "cdp_documents", "cdp_document_candidates", "committee_papers",
              "committee_paper_candidates", "foi_requests",
              "foi_request_candidates", "rough_sleeping_snapshot",
              "statutory_homelessness_snapshot",
              "temporary_accommodation_snapshot",
              "temporary_accommodation_breakdowns"])

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

    # Comparators (Modules 29-31): rough sleeping, statutory homelessness and
    # temporary accommodation, requested and built specifically to sit beside
    # this authority's own substance-misuse evidence — never combined with
    # it, never a ratio, never a score. Each carries its own caveat rather
    # than sharing one, because each source's own limitations differ (an
    # unstandardised annual methodology; a quarterly figure that can be
    # revised; a table that reads only the top-level totals).
    rough_sleeping = _rows(conn, """
        SELECT snapshot_year, count, count_text, rate_per_100k, rate_text,
               source_url, retrieved_at, payload_sha256
        FROM rough_sleeping_snapshot WHERE ons_code = ?
        ORDER BY snapshot_year""", (ons_code,))
    statutory_homelessness = _rows(conn, """
        SELECT quarter_start, quarter_label, total_initial_assessments,
               total_initial_assessments_text, total_owed_duty,
               total_owed_duty_text, prevention_duty_owed, relief_duty_owed,
               source_url, retrieved_at, payload_sha256
        FROM statutory_homelessness_snapshot WHERE ons_code = ?
        ORDER BY quarter_start""", (ons_code,))
    temporary_accommodation = _rows(conn, """
        SELECT quarter_start, quarter_label, total_households_ta,
               total_households_ta_text, households_ta_with_children,
               children_in_ta, source_url, retrieved_at, payload_sha256
        FROM temporary_accommodation_snapshot WHERE ons_code = ?
        ORDER BY quarter_start""", (ons_code,))
    temporary_accommodation_breakdown = _rows(conn, """
        SELECT quarter_start, quarter_label, measure, unit, households,
               households_text, source_url, retrieved_at, payload_sha256
        FROM temporary_accommodation_breakdowns WHERE ons_code = ?
        ORDER BY quarter_start, measure""", (ons_code,))

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
        "comparators": {
            "rough_sleeping": {"rows": rough_sleeping,
                                "caveat": CAVEATS["rough_sleeping_comparator"]},
            "statutory_homelessness": {
                "rows": statutory_homelessness,
                "caveat": CAVEATS["statutory_homelessness_comparator"]},
            "temporary_accommodation": {
                "rows": temporary_accommodation,
                "breakdown": temporary_accommodation_breakdown,
                "breakdown_caveat": CAVEATS["temporary_accommodation_breakdown"],
                "caveat": CAVEATS["temporary_accommodation_comparator"]},
        },
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


# The pay-evidence layers a provider comparison keeps strictly separate. Each
# is one source, with its own unit and its own caveat; the response places
# them side by side and never derives a rank, score, difference or ratio
# across them or within them. Larger selections stay well-defined: the API
# accepts 2-4 keys and returns the same shape whatever the count.
_PROVIDER_COMPARE_MIN = 2
_PROVIDER_COMPARE_MAX = 4


def providers_compare(conn: sqlite3.Connection, provider_keys) -> dict:
    """Two to four providers across four separate pay-evidence layers.

    Unlike `compare` (which plots authority *and* provider time series on
    shared axes), this is provider-only and deliberately non-temporal: it
    lays out Living Wage accreditation, the latest gender pay gap filing,
    provider-published pay and recent NHS Jobs adverts as four independent
    blocks. No layer is combined with another, and nothing here ranks,
    scores, differences or ratios the providers — `tests/test_web_provider_compare.py`
    pins the absence.
    """
    _public(["providers", "living_wage_accreditations", "gender_pay_gap_reports",
              "provider_pay_mentions", "nhs_job_adverts"])

    keys = list(dict.fromkeys(k for k in provider_keys if k))
    if not _PROVIDER_COMPARE_MIN <= len(keys) <= _PROVIDER_COMPARE_MAX:
        raise QueryError(
            f"providers/compare needs between {_PROVIDER_COMPARE_MIN} and "
            f"{_PROVIDER_COMPARE_MAX} distinct `provider_key` values.")

    placeholders = ", ".join(f":p{n}" for n in range(len(keys)))
    params = {f"p{n}": v for n, v in enumerate(keys)}
    known = {row["provider_key"]: row["canonical_name"] for row in _rows(
        conn, f"SELECT provider_key, canonical_name FROM providers "
              f"WHERE provider_key IN ({placeholders})", params)}
    missing = [k for k in keys if k not in known]
    if missing:
        raise QueryError(f"No provider {missing[0]!r}.")

    providers_list = [
        {"provider_key": k, "canonical_name": known[k]} for k in keys]

    def _by_provider(rows: list[dict]) -> dict:
        out: dict[str, list[dict]] = {k: [] for k in keys}
        for row in rows:
            out.setdefault(row["provider_key"], []).append(row)
        return out

    living_wage = _by_provider(_rows(conn, f"""
        SELECT l.provider_key, l.accredited, l.employer_name, l.match_basis,
               l.searched_variant, l.pages_checked, l.source_url, l.retrieved_at
        FROM living_wage_accreditations l
        WHERE l.provider_key IN ({placeholders})
        ORDER BY l.provider_key, l.retrieved_at DESC""", params))

    # The latest reporting year only — an older filing is a different figure,
    # not a trend point, and this view is not a time series.
    gender_pay_gap = _by_provider(_rows(conn, f"""
        SELECT g.provider_key, g.reporting_year, g.reporting_year_label,
               g.employer_name, g.diff_mean_hourly_percent,
               g.diff_median_hourly_percent, g.employer_size,
               g.written_statement_url, g.source_url, g.retrieved_at
        FROM gender_pay_gap_reports g
        WHERE g.provider_key IN ({placeholders})
          AND g.reporting_year = (
            SELECT MAX(g2.reporting_year) FROM gender_pay_gap_reports g2
            WHERE g2.provider_key = g.provider_key)
        ORDER BY g.provider_key, g.employer_name""", params))

    provider_pay = _by_provider(_rows(conn, f"""
        SELECT m.provider_key, m.page_url, m.section, m.mention_text,
               m.salary_raw, m.salary_min, m.salary_max, m.salary_period,
               m.salary_basis, m.match_basis, m.source_url, m.retrieved_at
        FROM provider_pay_mentions m
        WHERE m.provider_key IN ({placeholders})
        ORDER BY m.provider_key, m.page_url, m.mention_index""", params))

    # Recent adverts only — bounded per provider so one prolific employer
    # cannot dominate the block, and never summed into a count that would
    # read as sector demand. The cap is a portable correlated count (top-N
    # per group without a window function), the same shape both backends run.
    nhs_jobs = _by_provider(_rows(conn, f"""
        SELECT n.provider_key, n.job_title, n.salary_raw, n.salary_min,
               n.salary_max, n.salary_period, n.salary_basis, n.contract_type,
               n.working_pattern, n.posted_date, n.closing_date, n.advert_url,
               n.provider_match_basis, n.source_url, n.retrieved_at
        FROM nhs_job_adverts n
        WHERE n.provider_key IN ({placeholders})
          AND (SELECT COUNT(*) FROM nhs_job_adverts n2
               WHERE n2.provider_key = n.provider_key
                 AND (n2.posted_date > n.posted_date
                      OR (n2.posted_date = n.posted_date
                          AND n2.job_reference < n.job_reference))) < 10
        ORDER BY n.provider_key, n.posted_date DESC, n.job_reference""", params))

    return {
        "providers": providers_list,
        "layers": {
            "living_wage": {
                "unit": "accreditation status on the date checked (yes / no)",
                "temporal": False,
                "by_provider": living_wage,
                "caveat": CAVEATS["living_wage_accreditations"],
            },
            "gender_pay_gap": {
                "unit": "percentage gap in hourly pay, women vs men, from the "
                        "employer's own latest filing",
                "temporal": False,
                "by_provider": gender_pay_gap,
                "caveat": CAVEATS["gender_pay_gap"],
            },
            "provider_pay": {
                "unit": "pay text as published on the provider's own website; "
                        "mixed periods and bases, shown as found",
                "temporal": False,
                "by_provider": provider_pay,
                "caveat": CAVEATS["provider_published_pay"],
            },
            "nhs_jobs": {
                "unit": "advertised salary range per NHS Jobs advert; the "
                        "10 most recent per provider, matched employer only",
                "temporal": False,
                "by_provider": nhs_jobs,
                "caveat": CAVEATS["nhs_jobs_floor"],
            },
        },
        "caveat": CAVEATS["provider_compare"],
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


# --- relationship explorer -----------------------------------------------------
#
# One authority or provider's commissioning neighbourhood from the evidence
# graph (docs/evidence-graph.md, migration 0050) — not the whole graph, and
# not a force-directed map of the entire corpus. A one-hop view centred on
# whichever entity the reader picked, the same "the reader picks the peers"
# shape W-11's compare view already established, because a graph of
# everything at once would invite exactly the size/importance/centrality
# reading this pipeline never asserts.
#
# Reads the warehouse tables (entities, entity_relationships,
# evidence_records), never Neo4j: Neo4j is an explicitly disposable
# projection of these same rows (docs/evidence-graph.md — "delete
# SectorTrace-managed Neo4j nodes and rebuild them from the warehouse
# whenever recovery is needed"), so the citable source is here.
#
# predicate = 'AWARDED_TO' and derivation_type IN ('SOURCE_FACT',
# 'DERIVED_RELATIONSHIP') only. Excluded explicitly, not by their current
# absence:
#   - REGISTERED_AS (provider -> company ownership) — a separate,
#     not-yet-scoped view; this one is commissioning relationships only.
#   - EXTRACTED_CLAIM / ANALYTICAL_SIGNAL — reserved for a not-yet-built
#     extraction pipeline (see the graph_claims.review_status gate); nothing
#     writes them today, but nothing here may assume that stays true.


def relationships(conn: sqlite3.Connection, *,
                   ons_code: str | None = None,
                   provider_key: str | None = None) -> dict:
    """The commissioning relationships touching one authority or provider.

    Exactly one of `ons_code` or `provider_key` selects the centre entity.
    """
    _public(["entities", "entity_identifiers", "entity_relationships",
              "evidence_records", "authorities", "providers"])

    if bool(ons_code) == bool(provider_key):
        raise QueryError(
            "relationships needs exactly one of `ons_code` or `provider_key`.")

    if catalog.object_type(conn, "entities") != "table":
        # The evidence graph is optional infrastructure (migration 0050) and
        # a warehouse that predates it, or has never run `graph backfill`,
        # must render an empty neighbourhood rather than a 500 — the same
        # primitive health.graph_status's own table-existence guard uses.
        return _relationships_fallback(conn, ons_code, provider_key)

    scheme, value = (("ons_code", ons_code) if ons_code
                     else ("sectortrace_provider_key", provider_key))
    center = _one(conn, """
        SELECT e.entity_id, e.entity_type, e.canonical_name
        FROM entity_identifiers i JOIN entities e ON e.entity_id = i.entity_id
        WHERE i.identifier_scheme = :scheme AND i.identifier_value = :value
        """, {"scheme": scheme, "value": value})
    if not center:
        return _relationships_fallback(conn, ons_code, provider_key)

    edges = _rows(conn, """
        SELECT r.relationship_id, r.subject_entity_id, r.object_entity_id,
               r.valid_from, r.valid_to, r.confidence,
               ev.source_url, ev.retrieved_at, ev.source_system
        FROM entity_relationships r
        LEFT JOIN evidence_records ev ON ev.evidence_id = r.evidence_id
        WHERE (r.subject_entity_id = :id OR r.object_entity_id = :id)
          AND r.predicate = 'AWARDED_TO'
          AND r.derivation_type IN ('SOURCE_FACT', 'DERIVED_RELATIONSHIP')
        ORDER BY r.valid_from DESC""", {"id": center["entity_id"]})

    neighbour_ids = sorted({
        e["object_entity_id"] if e["subject_entity_id"] == center["entity_id"]
        else e["subject_entity_id"] for e in edges})
    neighbours = []
    if neighbour_ids:
        placeholders = ", ".join(f":n{n}" for n in range(len(neighbour_ids)))
        params = {f"n{n}": v for n, v in enumerate(neighbour_ids)}
        neighbours = _rows(conn, f"""
            SELECT entity_id, entity_type, canonical_name FROM entities
            WHERE entity_id IN ({placeholders})""", params)

    return {"center": center, "neighbours": neighbours, "edges": edges,
            "caveat": CAVEATS["commissioning_relationship"]}


def _relationships_fallback(conn: sqlite3.Connection,
                             ons_code: str | None,
                             provider_key: str | None) -> dict:
    """No graph entity for this authority/provider — not backfilled yet, or
    the graph tables don't exist at all. Absence of a connection, not
    absence of the authority or provider itself, so this still has to name
    who was asked about rather than just failing."""
    if ons_code:
        row = _one(conn, "SELECT name FROM authorities WHERE ons_code = :v",
                   {"v": ons_code})
        entity_type, name = "LOCAL_AUTHORITY", row.get("name")
    else:
        row = _one(conn, "SELECT canonical_name AS name FROM providers "
                          "WHERE provider_key = :v", {"v": provider_key})
        entity_type, name = "PROVIDER", row.get("name")
    if not name:
        raise QueryError(f"No {'authority' if ons_code else 'provider'} "
                          f"{(ons_code or provider_key)!r}.")
    return {"center": {"entity_id": None, "entity_type": entity_type,
                        "canonical_name": name},
            "neighbours": [], "edges": [],
            "caveat": CAVEATS["commissioning_relationship"]}


def relationship_detail(conn: sqlite3.Connection, relationship_id: str) -> dict:
    """One `AWARDED_TO` edge, its two entities, and the dated contract notices
    behind every edge between the same authority and provider (BETA-044).

    Deterministic only. The edge is resolved to the authority/provider pair it
    connects, then every `AWARDED_TO` edge between that pair is listed as a
    timeline, each resolved back to its source notice through
    `evidence_records.payload_sha256` — the same key the graph backfill wrote
    it from. Nothing here manufactures a `REGISTERED_AS`, claim or signal
    edge, and a missing notice date is left blank rather than inferred.
    """
    _public(["entities", "entity_identifiers", "entity_relationships",
              "evidence_records", "contracts"])

    if catalog.object_type(conn, "entity_relationships") != "table":
        raise QueryError("The evidence graph is not built in this warehouse.")

    edge = _one(conn, """
        SELECT relationship_id, subject_entity_id, object_entity_id, predicate
        FROM entity_relationships
        WHERE relationship_id = :id AND predicate = 'AWARDED_TO'
          AND derivation_type IN ('SOURCE_FACT', 'DERIVED_RELATIONSHIP')
        """, {"id": relationship_id})
    if not edge:
        raise QueryError(f"No AWARDED_TO relationship {relationship_id!r}.")

    ends = _rows(conn, """
        SELECT e.entity_id, e.entity_type, e.canonical_name
        FROM entities e
        WHERE e.entity_id IN (:a, :b)
        """, {"a": edge["subject_entity_id"], "b": edge["object_entity_id"]})
    by_id = {row["entity_id"]: row for row in ends}
    subject = by_id.get(edge["subject_entity_id"], {})
    obj = by_id.get(edge["object_entity_id"], {})
    authority = subject if subject.get("entity_type") == "LOCAL_AUTHORITY" else obj
    provider = obj if authority is subject else subject
    if not authority or not provider:
        raise QueryError(
            f"Relationship {relationship_id!r} does not connect an authority "
            "and a provider.")

    def _identifier(entity_id: str, scheme: str) -> str | None:
        row = _one(conn, "SELECT identifier_value FROM entity_identifiers "
                          "WHERE entity_id = :id AND identifier_scheme = :s",
                   {"id": entity_id, "s": scheme})
        return row.get("identifier_value")

    # Every AWARDED_TO edge between this exact pair, with the notice each was
    # written from. LEFT JOIN so an edge whose notice is no longer in
    # `contracts` still appears (dates come from the edge in that case).
    # Bounded (BETA-049): a drawer showing one relationship's history is not a
    # place to stream a five-figure result set. `truncated` says when the cap
    # bit; the full set is the contracts page, filtered to the pair.
    TIMELINE_CAP = 500
    timeline = _rows(conn, """
        SELECT r.relationship_id, r.valid_from, r.valid_to, r.confidence,
               ev.source_url AS evidence_source_url,
               ev.retrieved_at AS evidence_retrieved_at,
               ev.source_system,
               c.notice_id, c.title, c.value_core, c.currency,
               c.buyer_name, c.supplier_name_raw,
               c.date_published, c.source_url AS notice_source_url,
               c.retrieved_at AS notice_retrieved_at
        FROM entity_relationships r
        JOIN evidence_records ev ON ev.evidence_id = r.evidence_id
        LEFT JOIN contracts c
          ON c.payload_sha256 = ev.payload_sha256
         AND c.source_system = ev.source_system
        WHERE r.subject_entity_id = :subj AND r.object_entity_id = :obj
          AND r.predicate = 'AWARDED_TO'
          AND r.derivation_type IN ('SOURCE_FACT', 'DERIVED_RELATIONSHIP')
        ORDER BY COALESCE(r.valid_from, c.date_published) DESC NULLS LAST,
                 r.relationship_id
        LIMIT :cap
        """, {"subj": edge["subject_entity_id"], "obj": edge["object_entity_id"],
              "cap": TIMELINE_CAP + 1})
    truncated = len(timeline) > TIMELINE_CAP
    timeline = timeline[:TIMELINE_CAP]

    events = []
    for row in timeline:
        events.append({
            "relationship_id": row["relationship_id"],
            "valid_from": row["valid_from"],
            "valid_to": row["valid_to"],
            "confidence": row["confidence"],
            "notice": {
                "notice_id": row["notice_id"],
                "title": row["title"],
                "value_core": row["value_core"],
                "currency": row["currency"],
                "buyer_name": row["buyer_name"],
                "supplier_name_raw": row["supplier_name_raw"],
                "date_published": row["date_published"],
                "source_url": row["notice_source_url"],
                "retrieved_at": row["notice_retrieved_at"],
                "notice_web_url": notice_page_url(
                    row["source_system"], row["notice_id"]),
            } if row["notice_id"] else None,
            "source_url": row["evidence_source_url"],
            "retrieved_at": row["evidence_retrieved_at"],
        })

    return {
        "relationship_id": relationship_id,
        "predicate": "AWARDED_TO",
        "authority": {
            "entity_id": authority["entity_id"],
            "name": authority["canonical_name"],
            "ons_code": _identifier(authority["entity_id"], "ons_code"),
        },
        "provider": {
            "entity_id": provider["entity_id"],
            "name": provider["canonical_name"],
            "provider_key": _identifier(
                provider["entity_id"], "sectortrace_provider_key"),
        },
        "timeline": events,
        "edge_count": len(events),
        "truncated": truncated,
        "caveat": CAVEATS["commissioning_relationship_timeline"],
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
        SELECT location_id, location_name, region,
               COALESCE(overall_rating, bulk_overall_rating) AS overall_rating,
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
    present = set(catalog.table_names(conn))
    # By column name rather than `dict(rows)`: that shorthand relies on a row
    # being a two-element sequence, which is true of both backends' rows and
    # is not the thing this line is about.
    names = {row["ons_code"]: row["name"] for row in
              conn.execute("SELECT ons_code, name FROM authorities")}

    held: dict[str, set[str]] = {}
    for label, table, column, _module in health.COVERAGE_COLUMNS:
        if table not in present:
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


# --- claims (Workstream C, Phase 17) ------------------------------------------
#
# The "What we can say" page: campaign claims as rows, each with its citations
# and its caveats. Everything here is the registry rendered — nothing is
# computed, which is the point of the phase. The claim text is what a person
# wrote, the citations are rows a person picked (resolved here to something
# the reader can follow), and the caveats are lines a person wrote about what
# may not be computed from it.
#
# Two rules shape the payload:
#
#   * Only published claims are served. Drafts, rejections and retractions
#     are the worklist, not the portal: 'published' is the one status a
#     reviewer authorised making public, and the registry's trigger
#     discipline is what guarantees it got there through a named decision.
#   * A citation that no longer resolves is shown as unresolvable, not
#     dropped and not guessed at. A module re-run can replace the row a
#     citation names, and the reader deserves to see that the claim rests on
#     rows the warehouse no longer holds rather than a link that silently
#     went elsewhere.

# The page's own pinned caveat: a claim is a statement, not a figure this
# pipeline computed. It travels with every response, like every other caveat
# here.
CLAIMS_CAVEAT = (
    "A claim is a statement the campaign makes, written by a person, linked "
    "to the evidence rows that support it, and approved by a named reviewer. "
    "It is not a figure computed by this pipeline, and the caveats on each "
    "claim say what may not be computed from its citations."
)


def claims(conn: sqlite3.Connection) -> dict:
    """Published claims with their citations and caveats, for the portal."""
    _public(["claims", "claim_citations", "claim_verifications",
              *claims_registry_tables()])

    rows = _rows(conn, """
        SELECT c.id, c.claim_text, c.caveats, c.created_by, c.created_at,
               c.note, v.decided_by, v.decided_at AS published_at
        FROM claims c
        JOIN claim_verifications v ON v.claim_id = c.id
          AND v.decision = 'published'
          AND v.id = (SELECT MAX(w.id) FROM claim_verifications w
                       WHERE w.claim_id = c.id AND w.decision = 'published')
        WHERE c.status = 'published'
        ORDER BY v.decided_at DESC, c.id""")

    out = []
    for row in rows:
        citations = []
        for citation in _rows(conn, """
                SELECT evidence_table, evidence_key, cited_by, cited_at, note
                FROM claim_citations WHERE claim_id = ? ORDER BY id""",
                              (row["id"],)):
            resolved = claims_resolve(
                conn, citation["evidence_table"], citation["evidence_key"])
            citations.append({
                "table": citation["evidence_table"],
                "key": citation["evidence_key"],
                "resolved": resolved,
            })
        out.append({
            "id": row["id"],
            "claim_text": row["claim_text"],
            # The claim's own "you may not compute this from it" lines, as a
            # list. Empty when the author wrote none — the portal then shows
            # the page caveat only.
            "caveats": [line for line in (row["caveats"] or "").splitlines()
                        if line.strip()],
            "citations": citations,
            "created_by": row["created_by"],
            "created_at": row["created_at"],
            "published_by": row["decided_by"],
            "published_at": row["published_at"],
            "note": row["note"],
        })

    return {"claims": out, "caveat": CLAIMS_CAVEAT}


def claims_registry_tables() -> list[str]:
    """The evidence tables the claims registry may cite.

    Imported lazily: `pipeline.claims` pulls in the citation registry, and
    this module's import is not the place for a chain it does not always
    need.
    """
    from pipeline import claims as claims_module

    return claims_module.citable_tables()


def claims_resolve(conn: sqlite3.Connection, table: str,
                   key: str) -> dict | None:
    """Resolve one citation to what the reader can follow, or None.

    None means the row is no longer in the warehouse — a module re-run
    replaced it — and the portal renders that rather than a dead link. Same
    shape census_verify.stale() gives a verification whose source moved.
    """
    from pipeline import claims as claims_module

    resolved = claims_module.resolve_citation(conn, table, key)
    if resolved is None:
        return None
    return {
        "label": resolved["label"],
        "url": resolved["url"],
        "source_url": resolved["source_url"],
        "retrieved_at": resolved["retrieved_at"],
    }


# --- document search (BETA-022) ------------------------------------------------
#
# `pipeline/documents/` (docs/document-analysis.md) already parses PDFs into
# page-aware, provenanced, full-text-searchable elements — SQLite FTS5 on one
# backend, PostgreSQL `tsvector` on the other — and `pipeline documents
# search` has worked at the CLI since that layer shipped. Nothing before this
# put it behind a web route. `docs/upgrade-roadmap.md`'s own "Corpus-wide
# search" and "Full-text search over archived documents" entries both said to
# revisit "once the promotion work has given it verified documents to search
# rather than candidates" — which is exactly what has since happened here
# (13,249 documents parsed, confirmed against the live warehouse before
# writing this), so this is wiring an existing backend to a route, not
# building search infrastructure from nothing.

# The only two source systems actually bridged into `document_records` today
# — confirmed against the live warehouse, not assumed from the docs:
# `SELECT DISTINCT e.source_system FROM document_records d JOIN
# evidence_records e ON e.evidence_id = d.evidence_id` returns exactly these
# two. Both are public council governance papers (committee agendas/papers
# via m09/m10, and community drug partnership documents); neither has a
# restricted_ counterpart.
#
# This allowlist, not `_public()` alone, is the real safety boundary for this
# route: `document_records`/`document_elements` are not `restricted_`-prefixed
# tables and hold a generic `text` column no export guard recognises as
# personal data (see `pipeline/exports/__init__.py`'s own `PERSONAL_DATA_COLUMNS`
# comment: "exports must fail closed if one is ever added, rather than leaking
# it because the prefix check passed" — the same principle applies here). If a
# future session runs `pipeline documents register-existing --source
# annual_reports`, or bridges PFD report bodies or tribunal judgment text
# (both restricted per docs/CAVEATS.md's "Personal data" section) into this
# same schema, it must NOT become searchable here just by existing in the
# table. Fail closed: a source_system not in this tuple is never searched.
DOCUMENT_SEARCH_SOURCES = ("committee_paper_promotion", "cdp_document_promotion")

DOCUMENT_SEARCH_CAVEAT = (
    "This searches page-level text extracted from published committee papers "
    "and community drug partnership documents only — not the whole warehouse, "
    "and not every document type the pipeline collects. A result is a page "
    "that contains the term, not a finding: read the source page, and its own "
    "caveats, before citing anything found here."
)

# The window a result shows around its first match. Sized to what the portal
# renders without further truncation, so the client never has to guess where
# in the page the match was.
_SNIPPET_RADIUS = 140
_SNIPPET_MAX = 320


def _search_terms(query: str) -> list[str]:
    """The words a reader typed, for locating where a page matched.

    The FTS layer receives the raw query and interprets its own syntax; these
    terms exist only to find the matching passage afterwards. Quoted spans
    are kept whole and listed first — FTS5 reads "rough sleeping" as a
    required phrase, so the passage that matched contains it verbatim, and
    both this window and the portal's highlighter should prefer the phrase
    over its words occurring separately. Bare operators like OR/NEAR are not
    carried over: they are query syntax, not strings the page text contains.
    """
    value = query or ""
    phrases = [p.strip().lower() for p in re.findall(r'"([^"]+)"', value)
               if len(p.strip()) >= 2]
    words = [w.lower() for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9']*", value)
             if len(w) >= 2]
    return list(dict.fromkeys(phrases + words))


def _match_snippet(text: str | None, terms: list[str]) -> str:
    """A window onto the passage that matched, not the top of the page.

    Computed here rather than with SQLite's snippet() and PostgreSQL's
    ts_headline separately so both backends return byte-identical snippets
    for the same text — the two engines' headline functions differ in their
    splitting rules, and a result that changes shape depending on which
    backend the warehouse runs on is a result that cannot be pinned by test.
    Falls back to the head of the page when no term can be located (a
    one-character query, punctuation-only input).
    """
    value = str(text or "")
    if len(value) <= _SNIPPET_MAX:
        return value
    lower = value.lower()
    # Phrase occurrences anchor the window before bare-word ones: a query
    # like "sleeping duty" also contributes the words `sleeping`/`duty`, and
    # whichever word happens to appear earliest in the page must not drag
    # the window away from the passage that actually matched as a phrase.
    phrases = [t for t in terms if " " in t]
    words = [t for t in terms if " " not in t]
    hit = -1
    for group in (phrases, words):
        hit = min((i for t in group for i in (lower.find(t),) if i >= 0),
                  default=-1)
        if hit >= 0:
            break
    if hit < 0:
        return value[: _SNIPPET_MAX - 1] + "…"
    start = max(0, hit - _SNIPPET_RADIUS)
    end = min(len(value), start + _SNIPPET_MAX)
    if start > 0:
        boundary = value.find(" ", start)
        if boundary != -1 and boundary < hit:
            start = min(boundary + 1, hit)
    if end < len(value):
        boundary = value.rfind(" ", max(start, hit), end)
        if boundary > start:
            end = boundary
    return ("…" if start > 0 else "") + value[start:end].strip() + ("…" if end < len(value) else "")


# The two document facets a reader can narrow by (BETA-041). `document_type`
# is `document_records`'s own classification label; `source_system` is
# constrained to the allowlist above, so a facet value that is not in
# DOCUMENT_SEARCH_SOURCES can never be selected and never appears in a count.
_DOCUMENT_SEARCH_FACETS = ("source_system", "document_type")


def _document_scope_filters(document_type, year_from, year_to, since_retrieved_at):
    """Structured filters shared by both backends, as `" AND ..."` fragments.

    Column expressions are the same on SQLite and PostgreSQL here —
    `d`/`e` are the `document_records`/`evidence_records` aliases in both
    branches — so this builds one list. `substr(published_at, 1, 4)` is a
    string year on either engine; a row with no `published_at` drops out of a
    year-bounded search, which is the honest answer for "documents from 2024".
    Returned split in two: the date/source scope (which the facet counts also
    apply) and the `document_type` narrowing (which they do not).
    """
    scope, scope_params = [], []
    if year_from:
        scope.append("substr(d.published_at, 1, 4) >= ?")
        scope_params.append(str(year_from))
    if year_to:
        scope.append("substr(d.published_at, 1, 4) <= ?")
        scope_params.append(str(year_to))
    if since_retrieved_at:
        scope.append("e.retrieved_at >= ?")
        scope_params.append(since_retrieved_at)
    type_sql, type_params = "", []
    if document_type:
        type_sql = " AND d.document_type = ?"
        type_params = [document_type]
    return "".join(f" AND {c}" for c in scope), scope_params, type_sql, type_params


def document_search(conn: sqlite3.Connection, *, query: str,
                    source_system: str | None = None,
                    document_type: str | None = None,
                    year_from: str | None = None, year_to: str | None = None,
                    since_retrieved_at: str | None = None,
                    limit: int = 25, offset: int = 0) -> dict:
    _public(["document_records", "document_elements", "document_versions",
             "evidence_records"])
    query = (query or "").strip()
    if not query:
        raise QueryError("document_search needs a `q` parameter.")
    if source_system is not None and source_system not in DOCUMENT_SEARCH_SOURCES:
        # Fail closed, like the allowlist itself: an unknown source is not an
        # empty result, it is a request for something this route does not
        # publish.
        raise QueryError(f"unknown source_system {source_system!r}")
    limit = max(1, min(limit, 50))
    # A negative offset would make PostgreSQL raise and SQLite silently walk
    # backwards off the front of the ranked list; clamping keeps one behaviour.
    offset = max(0, int(offset))

    sources = (source_system,) if source_system else DOCUMENT_SEARCH_SOURCES
    src_ph = ", ".join("?" for _ in sources)
    all_src_ph = ", ".join("?" for _ in DOCUMENT_SEARCH_SOURCES)
    scope_sql, scope_params, type_sql, type_params = _document_scope_filters(
        document_type, year_from, year_to, since_retrieved_at)

    is_sqlite = db.backend_of(conn) == "sqlite"
    _tail_cols = ("d.document_type, d.title, d.display_title, d.title_basis, "
                  "d.filename, d.published_at, "
                  "e.source_url, e.retrieved_at, e.source_system")

    if is_sqlite:
        frm = (
            "FROM document_element_search s "
            "JOIN document_records d ON d.document_id = s.document_id "
            "JOIN evidence_records e ON e.evidence_id = d.evidence_id"
        )
        cols = ("s.document_element_id, s.document_id, s.page_number, "
                "s.element_type, s.text, " + _tail_cols)
        # FTS5 `rank` is ascending (best first). A total order after it —
        # document, page, element — makes `limit`/`offset` paging stable
        # rather than dependent on the engine's row order for ties.
        match = "document_element_search MATCH ?"
        order = "ORDER BY rank, s.document_id, s.page_number, s.document_element_id"
    else:
        frm = (
            "FROM document_elements de "
            "JOIN document_versions dv ON dv.document_version_id = de.document_version_id "
            "JOIN document_records d ON d.document_id = dv.document_id "
            "JOIN evidence_records e ON e.evidence_id = d.evidence_id"
        )
        cols = ("de.document_element_id, d.document_id, de.page_number, "
                "de.element_type, de.text, " + _tail_cols)
        # websearch_to_tsquery over plainto_tsquery: it accepts a reader's
        # quotes, OR and -term without raising, and ts_rank_cd gives an honest
        # relevance order where before there was none — the old query had no
        # ORDER BY at all, so paging was whatever order the plan produced.
        _tsv = "to_tsvector('simple', COALESCE(de.text, ''))"
        _tsq = "websearch_to_tsquery('simple', ?)"
        match = f"dv.is_active = 1 AND {_tsv} @@ {_tsq}"
        order = (f"ORDER BY ts_rank_cd({_tsv}, {_tsq}) DESC, "
                 "d.document_id, de.page_number, de.document_element_id")

    where = f"WHERE {match} AND e.source_system IN ({src_ph}){scope_sql}{type_sql}"
    # PostgreSQL's ORDER BY repeats the tsquery bind; SQLite's does not.
    order_binds = () if is_sqlite else (query,)
    filt_params = (*scope_params, *type_params)

    sql = f"SELECT {cols} {frm} {where} {order} LIMIT ? OFFSET ?"
    params = (query, *sources, *filt_params, *order_binds, limit, offset)
    count_sql = f"SELECT COUNT(*) {frm} {where}"
    count_params = (query, *sources, *filt_params)

    # Facet counts: over the text query and the date/source scope only, not
    # the `source_system` / `document_type` selection — so the buckets a
    # reader can switch to stay visible with their sizes while a selection
    # narrows the results below.
    facet_where = f"WHERE {match} AND e.source_system IN ({all_src_ph}){scope_sql}"
    facet_params = (query, *DOCUMENT_SEARCH_SOURCES, *scope_params)

    try:
        rows = _rows(conn, sql, params)
        total = conn.execute(count_sql, count_params).fetchone()[0]
        facets = {
            facet: _rows(
                conn,
                f"SELECT {'e.source_system' if facet == 'source_system' else 'd.document_type'} "
                f"AS value, COUNT(*) AS count {frm} {facet_where} "
                f"GROUP BY value ORDER BY count DESC, value",
                facet_params)
            for facet in _DOCUMENT_SEARCH_FACETS
        }
    except sqlite3.OperationalError as error:
        # FTS5 MATCH raises on malformed query syntax (an unbalanced quote, a
        # bare trailing operator) rather than returning no rows — a reader's
        # search term is not a schema problem this route should crash on.
        raise QueryError(f"Could not search for {query!r}: {error}") from None

    terms = _search_terms(query)
    return {
        "results": [{
            "document_id": r["document_id"],
            # The exact element that matched — the anchor GET
            # /api/v1/documents/{id}?element_id=… needs for the context view.
            "document_element_id": r["document_element_id"],
            "document_type": r["document_type"],
            "source_system": r["source_system"],
            # BETA-062: the derived display title, falling back to the raw
            # source label then the filename for rows the backfill has not
            # reached. `title_basis` says which rung `title` came from so the
            # portal can mark a title it did not get from the source itself.
            "title": r["display_title"] or r["title"] or r["filename"],
            "title_basis": r["title_basis"],
            "source_title": r["title"],
            "page_number": r["page_number"],
            "element_type": r["element_type"],
            "text": r["text"],
            # The window the portal renders: centred on what matched, so a
            # result is self-explaining even when the match sits mid-page.
            "snippet": _match_snippet(r["text"], terms),
            "source_url": r["source_url"],
            "retrieved_at": r["retrieved_at"],
            "published_at": r["published_at"],
        } for r in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
        "query": query,
        "facets": facets,
        "filters": {
            "source_system": source_system,
            "document_type": document_type,
            "year_from": year_from or None,
            "year_to": year_to or None,
            "since_retrieved_at": since_retrieved_at or None,
        },
        "caveat": DOCUMENT_SEARCH_CAVEAT,
    }


# At most this many elements either side of a matched element (BETA-042). A
# ceiling, not a default a caller can raise: bounded context aids scrutiny of
# one hit; an unbounded one is a way to reassemble a whole copyrighted
# document a page at a time, which docs/CAVEATS.md does not allow.
#
# BETA-081 (the reading room) raised this from 3 to 8. A single response is
# still a bounded window — a readable passage, not the document — and the
# reading room's "earlier/later" re-anchors on an edge element rather than
# asking for one enormous window. The source URL is always shown for the
# whole document.
_DOCUMENT_CONTEXT_MAX = 8


def document_context(conn: sqlite3.Connection, document_id: str, *,
                     element_id: str | None = None, context: int = 3) -> dict:
    """The passage around one matched element, from the active parse only.

    `GET /api/v1/documents/{id}?element_id=…&context=…`. The same
    `DOCUMENT_SEARCH_SOURCES` allowlist as `document_search` is the safety
    boundary — a document from an unlisted source is not published here at
    all — and only the `is_active` version's elements are ever returned, so a
    link made before a reparse refuses rather than anchoring on stale text.
    """
    _public(["document_records", "document_elements", "document_versions",
             "evidence_records"])
    context = max(0, min(int(context), _DOCUMENT_CONTEXT_MAX))

    meta = _one(
        conn,
        "SELECT d.document_id, d.document_type, d.title, d.display_title, "
        "d.title_basis, d.filename, "
        "d.published_at, e.source_url, e.retrieved_at, e.source_system "
        "FROM document_records d "
        "JOIN evidence_records e ON e.evidence_id = d.evidence_id "
        "WHERE d.document_id = ?", (document_id,))
    if not meta or meta["source_system"] not in DOCUMENT_SEARCH_SOURCES:
        raise QueryError(f"No document {document_id!r}.")

    version = _one(
        conn,
        "SELECT document_version_id, parser_name, parser_version "
        "FROM document_versions WHERE document_id = ? AND is_active = 1",
        (document_id,))
    if not version:
        raise QueryError(f"Document {document_id!r} has no active parsed version.")

    elements = _rows(
        conn,
        "SELECT document_element_id, sequence, page_number, element_type, "
        "heading_level, text FROM document_elements "
        "WHERE document_version_id = ? ORDER BY sequence",
        (version["document_version_id"],))

    anchor_index = None
    if element_id is not None:
        anchor_index = next(
            (i for i, e in enumerate(elements)
             if e["document_element_id"] == element_id), None)
        if anchor_index is None:
            raise QueryError(
                f"Element {element_id!r} is not in the active version of "
                f"document {document_id!r}.")
        lo = max(0, anchor_index - context)
        hi = min(len(elements), anchor_index + context + 1)
    else:
        # No anchor: the head of the document, same window size.
        lo, hi = 0, min(len(elements), 2 * context + 1)

    window = [{
        "document_element_id": e["document_element_id"],
        "sequence": e["sequence"],
        "page_number": e["page_number"],
        "element_type": e["element_type"],
        "heading_level": e["heading_level"],
        "text": e["text"],
        "is_anchor": element_id is not None
        and e["document_element_id"] == element_id,
    } for e in elements[lo:hi]]

    return {
        "document_id": meta["document_id"],
        "document_type": meta["document_type"],
        "title": meta["display_title"] or meta["title"] or meta["filename"],
        "title_basis": meta["title_basis"],
        "source_title": meta["title"],
        "source_url": meta["source_url"],
        "retrieved_at": meta["retrieved_at"],
        "published_at": meta["published_at"],
        "source_system": meta["source_system"],
        "parser": {"name": version["parser_name"],
                   "version": version["parser_version"]},
        "anchor_element_id": element_id,
        "context": context,
        "element_count": len(elements),
        "range": {"from": lo, "to": hi},
        "has_more_before": lo > 0,
        "has_more_after": hi < len(elements),
        "elements": window,
        "caveat": DOCUMENT_SEARCH_CAVEAT,
    }
