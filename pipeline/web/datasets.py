"""The public dataset catalogue: what this warehouse contains, and its limits.

A reader should be able to discover what evidence the portal holds — its
official source, geography, cadence, licence and the one thing they most need
to know before quoting it — without reverse-engineering module names or
reading `README.md` prose.

This file is the checked-in registry. One row per collecting module (`mNN_`),
because a dataset is a property of its source, not of a table: some modules
write several public tables and they are one dataset here. The registry is
*static* metadata only — title, publisher, URL, layer, geography, cadence,
licence key, caveat. The live figures a reader also needs (exact row counts,
last-retrieved date) are computed against the warehouse in
`public_queries.catalogue()` at request time, never stored here.

Two guarantees hold, both pinned by `tests/test_web_catalogue.py`:

  * **Every collecting module appears exactly once.** A new `mNN_` module
    without a row here fails the coverage test — the same discipline
    `pipeline/licences.py` already carries, for the same reason: a source
    the portal serves without a stated licence and limitation is a source
    nothing should be quoted from.
  * **Every `public_tables` entry is portal-safe.** `_public()` in
    `public_queries` refuses any `restricted_` table or personal-data column,
    so a mistyped table name here cannot smuggle personal data into the
    catalogue's counts.
"""
from __future__ import annotations

from dataclasses import dataclass

# The layer vocabulary. A dataset belongs to exactly one, and the portal
# never does arithmetic across two of them (CLAUDE.md settled decision 2).
EVIDENCE_LAYERS: dict[str, str] = {
    "reference": "Reference & geography",
    "procurement": "Procurement & spend",
    "provider-pay": "Pay evidence",
    "workforce-benchmark": "Workforce benchmarks",
    "treatment": "Treatment demand & outcomes",
    "finance": "Public finance",
    "provider-identity": "Provider identity & structure",
    "accountability": "Accountability & scrutiny",
    "safety": "Safety & safeguarding",
    "comparator": "Comparator (never combined)",
    "sector-context": "Sector context",
}


@dataclass(frozen=True)
class Dataset:
    dataset_id: str          # stable slug, kebab-case, in the URL
    module: str              # the collecting module, e.g. "m01_procurement"
    title: str
    publisher: str
    official_url: str
    evidence_layer: str      # a key of EVIDENCE_LAYERS
    geography: str
    cadence: str
    public_tables: tuple[str, ...]
    caveat: str


# Ordered for the list view: reference first, then the evidence layers roughly
# in the order the portal's own navigation presents them, comparators last.
DATASETS: tuple[Dataset, ...] = (
    Dataset(
        "geography", "m00_geography",
        "English local authority geography",
        "ONS Open Geography Portal",
        "https://geoportal.statistics.gov.uk/",
        "reference", "England — upper-tier and unitary authorities",
        "Annual boundary vintages",
        ("authorities",),
        "The reference spine every other dataset joins to. Boundary and code "
        "vintages change between releases; a code is resolved at collection "
        "time, not pinned.",
    ),
    Dataset(
        "procurement-notices", "m01_procurement",
        "Public procurement notices",
        "Find a Tender & Contracts Finder (Cabinet Office / Crown Commercial Service)",
        "https://www.find-tender.service.gov.uk/",
        "procurement", "United Kingdom",
        "Continuous; the pre-2020 CSV archive is daily files",
        ("contracts",),
        "A notice is an award, not spend. Values are as published and a "
        "handful of framework ceilings dominate any total, so the portal "
        "never sums them into a sector figure.",
    ),
    Dataset(
        "council-spend", "m24_council_spend",
        "Council spend-transparency payments",
        "Individual local authorities (over-£500 payment data)",
        "https://www.gov.uk/guidance/local-government-transparency-code-2015",
        "procurement", "England — publishing authorities only",
        "Monthly, per authority",
        ("council_spend", "council_spend_files"),
        "Each row is a payment a council published. A payment is linked to a "
        "provider only on an exact payee-name match, and unpublished or "
        "unparsed files leave real gaps — never read a total as complete.",
    ),
    Dataset(
        "nhs-job-adverts", "m16_nhs_jobs",
        "NHS Jobs advertised pay",
        "NHS Jobs (NHS Business Services Authority)",
        "https://www.jobs.nhs.uk/",
        "provider-pay", "England and Wales",
        "Continuous",
        ("nhs_job_adverts", "nhs_job_advert_locations"),
        "An advert states what one employer offered for one role on one date. "
        "Only adverts whose employer field matched a known provider are here, "
        "so every count is a floor.",
    ),
    Dataset(
        "provider-pay-pages", "m22_provider_pay_pages",
        "Provider pay and reward pages",
        "Tracked providers' own websites",
        "https://www.gov.uk/",  # no single canonical source; see per-provider source_url
        "provider-pay", "Not geographic — the tracked provider set",
        "Ad hoc, when a page changes",
        ("provider_pay_pages", "provider_pay_mentions"),
        "Pay figures a provider published on its own site — advertised bands "
        "or reward statements, not payroll. Held as evidence, quoted "
        "sparingly, and the provider holds the copyright.",
    ),
    Dataset(
        "gender-pay-gap", "m20_gender_pay_gap",
        "Gender pay gap reports",
        "Gender Pay Gap Service (Government Equalities Office)",
        "https://gender-pay-gap.service.gov.uk/",
        "provider-pay", "Great Britain — employers with 250+ staff",
        "Annual, by snapshot date",
        ("gender_pay_gap_reports",),
        "A mandatory filing of one employer's own figures. It is a gap "
        "measure, not a pay level, and says nothing about pay for any "
        "individual role.",
    ),
    Dataset(
        "statutory-pay-rates", "m17_statutory_pay_rates",
        "National Minimum and Living Wage rates",
        "GOV.UK (Department for Business and Trade)",
        "https://www.gov.uk/national-minimum-wage-rates",
        "provider-pay", "United Kingdom",
        "Annual, each April",
        ("statutory_pay_rates",),
        "The statutory hourly floor, transcribed from the GOV.UK rates page. "
        "A reference band, not a figure about any employer in this corpus.",
    ),
    Dataset(
        "living-wage-accreditation", "m18_living_wage",
        "Living Wage Foundation accreditation",
        "Living Wage Foundation (Citizens UK)",
        "https://www.livingwage.org.uk/",
        "provider-pay", "United Kingdom",
        "Continuous",
        ("living_wage_accreditations",),
        "A binary, citable fact: whether a tracked provider appears on the "
        "accredited-employer list on the date checked. Not open-licensed — "
        "check the Foundation's terms before republishing in bulk.",
    ),
    Dataset(
        "ashe-earnings", "m21_ons_ashe",
        "ASHE median earnings",
        "Office for National Statistics — Annual Survey of Hours and Earnings",
        "https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours/bulletins/annualsurveyofhoursandearnings/latest",
        "provider-pay", "United Kingdom, by occupation",
        "Annual",
        ("ons_ashe_observations",),
        "The external comparator market: median gross hourly pay as ONS "
        "publishes it, stored exactly. This pipeline never derives a rate of "
        "its own from it.",
    ),
    Dataset(
        "skills-for-care", "m25_skills_for_care",
        "Adult social care workforce estimates",
        "Skills for Care — Adult Social Care Workforce Data Set (ASC-WDS)",
        "https://www.skillsforcare.org.uk/Adult-Social-Care-Workforce-Data/Workforce-intelligence/publications/Topics/The-size-and-structure-of-the-adult-social-care-sector.aspx",
        "workforce-benchmark", "England — regional and role level",
        "Annual",
        ("skills_for_care_estimates", "skills_for_care_files"),
        "Modelled sector benchmarks, not a count of this corpus's providers. "
        "Rows without an hourly-pay figure are omitted from pay views rather "
        "than shown as zero.",
    ),
    Dataset(
        "workforce-census", "m06_workforce_census",
        "Drug and alcohol treatment workforce census",
        "NHS Benchmarking Network for NHS England",
        "https://www.nhsbenchmarking.nhs.uk/",
        "workforce-benchmark", "England",
        "Annual",
        ("workforce_census_metrics", "workforce_census_reports"),
        "NHS Benchmarking content, not open-licensed. Provider participation "
        "varies between rounds, so figures must not be compared year to year "
        "or read as total workforce size. Metrics are unverified until a "
        "person checks each against its source page.",
    ),
    Dataset(
        "ndtms-annual", "m07_ndtms",
        "NDTMS treatment statistics (annual)",
        "Office for Health Improvement and Disparities",
        "https://www.gov.uk/government/collections/alcohol-and-drug-misuse-and-treatment-statistics",
        "treatment", "England — mostly national, little at authority level",
        "Annual",
        ("ndtms_la_statistics", "ndtms_publications"),
        "Numbers in treatment, waiting times and completions are published "
        "nationally; only a small part is local-authority level. Use "
        "Fingertips for authority-level treatment figures.",
    ),
    Dataset(
        "ndtms-monthly", "m27_ndtms_monthly",
        "NDTMS provisional statistics (monthly)",
        "National Drug Treatment Monitoring System (OHID)",
        "https://www.ndtms.net/",
        "treatment", "England",
        "Monthly, provisional",
        ("ndtms_monthly_statistics",),
        "Provisional monthly figures from the server-rendered NDTMS form. "
        "They are revised in the annual release and should not be treated as "
        "final.",
    ),
    Dataset(
        "fingertips", "m12_fingertips",
        "Fingertips local-authority indicators",
        "Office for Health Improvement and Disparities — Fingertips",
        "https://fingertips.phe.org.uk/",
        "treatment", "England — local authority",
        "Varies by indicator, mostly annual",
        ("fingertips_la_values", "fingertips_indicators"),
        "Each indicator carries its own definition, period and confidence "
        "interval, kept with the value. Two authorities whose intervals "
        "overlap have not been shown to differ.",
    ),
    Dataset(
        "public-health-grant", "m11_public_health_grant",
        "Public health grant allocations",
        "Department of Health and Social Care",
        "https://www.gov.uk/government/collections/public-health-grants-to-local-authorities",
        "finance", "England — local authority",
        "Annual",
        ("public_health_grants",),
        "What an authority was allocated by DHSC — not what it planned to "
        "spend, and not substance-misuse spend specifically. Never "
        "substituted for or compared with a budget figure.",
    ),
    Dataset(
        "la-revenue-budgets", "m13_la_budgets",
        "Local authority revenue budgets",
        "Ministry of Housing, Communities and Local Government",
        "https://www.gov.uk/government/collections/local-authority-revenue-expenditure-and-financing",
        "finance", "England — local authority",
        "Annual",
        ("la_revenue_budgets", "la_budget_publications"),
        "Budgeted, not actual, spend, from the national MHCLG release. A "
        "budget line is a plan; it is not a grant and the two are never "
        "compared.",
    ),
    Dataset(
        "charity-finance", "m03_charity_finance",
        "Provider charity finances",
        "Charity Commission for England and Wales",
        "https://register-of-charities.charitycommission.gov.uk/",
        "finance", "England and Wales — the tracked charitable providers",
        "Annual filings",
        ("charity_financials", "charity_accounts_extracts"),
        "Register financials plus the staff-costs note extracted from filed "
        "accounts. Two separate evidence layers, never merged; extracts can "
        "carry a parse gap recorded as NULL.",
    ),
    Dataset(
        "annual-report-narrative", "m14_annual_reports",
        "Provider annual report narrative",
        "Charity Commission filed annual reports (tracked provider set)",
        "https://register-of-charities.charitycommission.gov.uk/",
        "finance", "England and Wales — the tracked charitable providers",
        "Annual",
        ("provider_report_disclosure", "provider_report_passages"),
        "Passages quoted from filed annual reports as evidence, with a "
        "disclosure flag for whether a staff-pay statement was present. Not "
        "republished wholesale — the charity holds the copyright.",
    ),
    Dataset(
        "companies-house", "m04_companies",
        "Provider corporate structure",
        "Companies House",
        "https://find-and-update.company-information.service.gov.uk/",
        "provider-identity", "United Kingdom",
        "Continuous",
        ("companies", "company_filings"),
        "Which legal entities make up each provider group, and their public "
        "filings. Personal data about officers and PSCs is held in "
        "restricted_ tables and never reaches this portal.",
    ),
    Dataset(
        "cqc-locations", "m05_cqc",
        "CQC registered locations",
        "Care Quality Commission (syndication API)",
        "https://www.cqc.org.uk/",
        "provider-identity", "England",
        "Continuous",
        ("cqc_locations", "cqc_location_reports"),
        "Registration covers only some service types — most community drug "
        "and alcohol provision is not CQC-registered — so this is not a "
        "service map and a location count is neither coverage nor quality.",
    ),
    Dataset(
        "cqc-bulk-crosscheck", "m26_cqc_directory",
        "CQC bulk-export cross-check",
        "Care Quality Commission bulk exports",
        "https://www.cqc.org.uk/about-us/transparency/using-cqc-data",
        "provider-identity", "England",
        "Weekly",
        ("cqc_providers",),
        "The bulk provider/location export, used to cross-check and fill "
        "company numbers the syndication walk missed. Same registration "
        "limits as the location dataset.",
    ),
    Dataset(
        "sector-universe", "m23_sector_universe",
        "Substance-misuse sector universe",
        "Derived from Companies House, the Charity Commission and CQC",
        "https://www.gov.uk/",  # a derived figure; component sources carry their own URLs
        "sector-context", "England",
        "Recomputed on each run",
        ("sector_universe",),
        "An estimate of how many organisations make up the sector — a "
        "denominator for coverage statements, not evidence about any one "
        "organisation.",
    ),
    Dataset(
        "data-gov-uk", "m19_data_gov_uk",
        "data.gov.uk catalogue entries",
        "data.gov.uk (Central Digital and Data Office)",
        "https://www.data.gov.uk/",
        "reference", "United Kingdom",
        "Continuous",
        ("data_gov_uk_datasets", "data_gov_uk_resources"),
        "Discovery metadata — dataset and resource records — not the "
        "underlying data. A catalogue entry is a pointer, and it can be "
        "stale on the publisher's side.",
    ),
    Dataset(
        "tribunals", "m02_tribunals",
        "Employment tribunal and EAT decisions",
        "HM Courts & Tribunals Service (via GOV.UK)",
        "https://www.gov.uk/employment-tribunal-decisions",
        "accountability", "England, Wales and Scotland",
        "Continuous",
        ("tribunal_cases", "eat_cases"),
        "Outcomes are read from judgment text, not structured metadata. A "
        "case marked as a component named the provider alongside "
        "co-respondents and is not solely about them.",
    ),
    Dataset(
        "foi", "m15_foi",
        "Published FOI evidence",
        "mySociety WhatDoTheyKnow and council disclosure logs",
        "https://www.whatdotheyknow.com/",
        "accountability", "United Kingdom",
        "Ad hoc",
        ("foi_requests", "foi_request_candidates"),
        "Published FOI evidence only, never \"all FOI responses\". Three "
        "limits stack — publication, discovery and matching — and belong on "
        "anything built from it. Share-alike applies to the mySociety half.",
    ),
    Dataset(
        "cdp-documents", "m09_cdp_documents",
        "Combating Drugs Partnership documents",
        "Local Combating Drugs Partnerships",
        "https://www.gov.uk/government/publications/combating-drugs-partnership-local-delivery",
        "accountability", "England — local partnerships",
        "Ad hoc",
        ("cdp_documents", "cdp_document_candidates"),
        "Discovery, not extraction: candidate documents a person confirms "
        "before they become evidence. Licence varies by publishing authority.",
    ),
    Dataset(
        "committee-papers", "m10_committee_papers",
        "Council committee papers",
        "Local authority committee-management systems",
        "https://www.gov.uk/find-your-local-council",
        "accountability", "England — councils",
        "Continuous",
        ("committee_papers", "committee_paper_candidates"),
        "One adapter per committee system, with a null adapter that records "
        "an unsearched authority rather than pretending coverage. Candidates "
        "need a person to promote them; licence varies by council.",
    ),
    Dataset(
        "pfd-reports", "m08_pfd_reports",
        "Prevention of Future Deaths reports",
        "Courts and Tribunals Judiciary",
        "https://www.judiciary.uk/prevention-of-future-death-reports/",
        "safety", "England and Wales",
        "Continuous",
        ("pfd_reports", "pfd_documents"),
        "A large part of the corpus is a metadata stub with no matters of "
        "concern online. Being sent a report and being named in one are "
        "different facts and are never added together. Personal detail is "
        "held in restricted_ tables.",
    ),
    Dataset(
        "sar-reports", "m28_sar_reports",
        "Safeguarding Adult Reviews (aggregated)",
        "National SAR Library and Safeguarding Adults Boards",
        "https://www.local.gov.uk/our-support/safeguarding/safeguarding-resources/safeguarding-adults-reviews",
        "safety", "England",
        "Ad hoc",
        ("sar_documents", "sar_provider_mentions"),
        "SARs discovered mainly through one aggregator. Board-name "
        "resolution is layered and imperfect. Report text and named "
        "individuals are held in restricted_ tables, never on this portal.",
    ),
    Dataset(
        "sab-site-reviews", "m32_sab_site_reviews",
        "SARs on Safeguarding Adults Board websites",
        "Safeguarding Adults Boards' own websites",
        "https://www.local.gov.uk/our-support/safeguarding/safeguarding-resources/safeguarding-adults-reviews",
        "safety", "England — participating boards",
        "Ad hoc",
        ("sab_site_crawls", "safeguarding_adults_boards"),
        "The deliberate exception to the aggregator-only rule: a crawl of "
        "specific board sites. Coverage is whichever boards have been "
        "crawled, not all of them.",
    ),
    Dataset(
        "rough-sleeping", "m29_rough_sleeping",
        "Rough sleeping snapshot",
        "Ministry of Housing, Communities and Local Government",
        "https://www.gov.uk/government/collections/homelessness-statistics",
        "comparator", "England — local authority",
        "Annual, autumn snapshot",
        ("rough_sleeping_snapshot",),
        "A comparator only. Methodology is not standardised between "
        "authorities — each picks its own counting approach and date — so a "
        "difference may be method, not the street. Never combined with the "
        "sector's own evidence.",
    ),
    Dataset(
        "statutory-homelessness", "m30_statutory_homelessness",
        "Statutory homelessness (H-CLIC Table A1)",
        "Ministry of Housing, Communities and Local Government",
        "https://www.gov.uk/government/collections/homelessness-statistics",
        "comparator", "England — local authority",
        "Quarterly",
        ("statutory_homelessness_snapshot",),
        "A comparator only. Just the flagship duty-assessment count is read; "
        "a quarter can be revised, and the figure reflects whichever edition "
        "was last fetched. Never combined with the sector's own evidence.",
    ),
    Dataset(
        "temporary-accommodation", "m31_temporary_accommodation",
        "Temporary accommodation (H-CLIC Table TA1)",
        "Ministry of Housing, Communities and Local Government",
        "https://www.gov.uk/government/collections/homelessness-statistics",
        "comparator", "England — local authority",
        "Quarterly",
        ("temporary_accommodation_snapshot",),
        "A comparator only. Top-level totals are read; the bed-and-breakfast "
        "breakdown is not. Never combined with the sector's own evidence.",
    ),
)


BY_ID: dict[str, Dataset] = {d.dataset_id: d for d in DATASETS}
BY_MODULE: dict[str, Dataset] = {d.module: d for d in DATASETS}
