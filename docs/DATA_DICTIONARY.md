# Data dictionary

**Generated from the live schema — do not edit by hand.** Regenerate with:

```bash
./start.sh export docs
```

Generated 2026-08-12 08:09 UTC.

`restricted` columns hold personal data. They are excluded from every export by default and `pipeline.exports.guard_columns()` raises if one is referenced.

## Restricted tables

Never exported. Listed here so the boundary is visible, not to invite use.

- `restricted_committee_result_snippets`
- `restricted_company_insolvency_practitioners`
- `restricted_company_officers`
- `restricted_cqc_location_contacts`
- `restricted_officer_disqualifications`
- `restricted_pfd_persons`
- `restricted_pfd_report_text`
- `restricted_tribunal_parties`
- `restricted_v_officer_edges`
- `restricted_v_shared_officers`

## `authorities`

*table* — 347 rows.

Module 0: geography reference spine. authorities holds one row per ONS entity code ever observed within the window we track (never reused by ONS once retired, so ons_code is a stable natural key across time). active_to is set once a code is observed missing from a later vintage; NULL means still current.

Feeds Sheets tab(s): 01_Authorities.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `ons_code` | TEXT | NOT NULL | exportable |
| `name` | TEXT | NOT NULL | exportable |
| `type` | TEXT | NOT NULL | exportable |
| `region_code` | TEXT | nullable | exportable |
| `region` | TEXT | nullable | exportable |
| `parent_code` | TEXT | nullable | exportable |
| `active_from` | TEXT | NOT NULL | exportable |
| `active_to` | TEXT | nullable | exportable |
| `first_seen_vintage` | TEXT | NOT NULL | exportable |
| `last_seen_vintage` | TEXT | NOT NULL | exportable |
| `geometry_geojson` | TEXT | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `authority_committee_systems`

*table* — 1 rows.

Which committee system each authority runs, detected from path signatures rather than assumed. 'unknown' is a real, recorded answer: it routes the authority to the null adapter and into review_queue.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `ons_code` | TEXT | nullable | exportable |
| `committee_system` | TEXT | NOT NULL | exportable |
| `committee_url` | TEXT | nullable | exportable |
| `detected_by` | TEXT | nullable | exportable |
| `detected_at` | TEXT | NOT NULL | exportable |
| `url_source` | TEXT | nullable | exportable |

## `authority_foi_profiles`

*table* — 315 rows.

One row per English authority, from mySociety's published authority CSV. Their tags carry the GSS code, so this joins to `authorities` exactly. Also the first source in this pipeline of an authoritative website URL for every authority — Modules 9 and 10 fall back to it.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `ons_code` | TEXT | nullable | exportable |
| `authority_name` | TEXT | NOT NULL | exportable |
| `wdtk_body_slug` | TEXT | nullable | exportable |
| `wdtk_body_url` | TEXT | nullable | exportable |
| `home_page_url` | TEXT | nullable | exportable |
| `publication_scheme_url` | TEXT | nullable | exportable |
| `disclosure_log_url` | TEXT | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `authority_successors`

*table* — 32 rows.

Predecessor -> successor edges for local government reorganisation. Populated only when a real geometric overlap was measured between the retiring boundary and the incoming one (constraint 6: never guessed). A predecessor with no row here is a known gap, not a silent collapse — check review_queue (item_type='unresolved_successor') for those.

Feeds Sheets tab(s): 01_Authorities.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `predecessor_code` | TEXT | NOT NULL | exportable |
| `successor_code` | TEXT | NOT NULL | exportable |
| `overlap_fraction` | REAL | NOT NULL | exportable |
| `method` | TEXT | NOT NULL | exportable |
| `transition_from_vintage` | TEXT | NOT NULL | exportable |
| `transition_to_vintage` | TEXT | NOT NULL | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `authority_url_overrides`

*table* — 0 rows.

Authority URLs supplied by a reviewer, for Modules 9 and 10. Those two modules cannot derive where a council publishes: hostnames are genuinely unpredictable (democracy.kent.gov.uk works; the same pattern applied to five other authorities resolved to nothing). Until now the only way to teach them one was to edit pipeline/authority_websites.py, and the 304 items sitting in review_queue as `authority_website_unknown` and `committee_url_unknown` had nowhere to go but a code change. This is that missing destination. `website_for()` reads it ahead of the code registry, so resolving an item in the reviewer takes effect on the next run of m09/m10 without a deploy. It is deliberately NOT `authority_committee_systems`. That table is Module 10's own output — it records what the module found, including URLs it guessed from a homepage link and labelled `homepage_link` precisely so they would not be mistaken for confirmed. Writing human answers into it would mean the module reading its own guesses back as authority on the next run, and would erase the distinction that table exists to preserve. Asserted input and derived output stay in separate tables. Every row is verified by an actual request before it is written, which is the standard the code registry sets ("find the site, confirm it loads"). checked_status is what the server saw when it checked, not a claim by whoever typed the URL.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `ons_code` | TEXT | nullable | exportable |
| `base_url` | TEXT | nullable | exportable |
| `committee_url` | TEXT | nullable | exportable |
| `committee_system` | TEXT | nullable | exportable |
| `checked_url` | TEXT | nullable | exportable |
| `checked_status` | INTEGER | nullable | exportable |
| `checked_at` | TEXT | nullable | exportable |
| `verified_by` | TEXT | NOT NULL | exportable |
| `verified_at` | TEXT | NOT NULL | exportable |
| `note` | TEXT | nullable | exportable |
| `review_item_id` | INTEGER | nullable | exportable |

## `cdp_document_candidates`

*table* — 0 rows.

Module 9: Combating Drugs Partnership documents. DISCOVERY, NOT EXTRACTION. There is no common schema across 150+ authorities, so this module finds candidate documents and a human confirms them. Nothing reaches cdp_documents without that confirmation: a candidate is a URL that looked right, which is not the same as a document that is what it claims to be.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `authority_ons_code` | TEXT | NOT NULL | exportable |
| `candidate_url` | TEXT | NOT NULL | exportable |
| `title` | TEXT | nullable | exportable |
| `document_type_guess` | TEXT | nullable | exportable |
| `confidence` | REAL | NOT NULL | exportable |
| `discovered_at` | TEXT | NOT NULL | exportable |
| `discovery_method` | TEXT | nullable | exportable |
| `verified` | INTEGER | NOT NULL | exportable |
| `verified_at` | TEXT | nullable | exportable |
| `rejected` | INTEGER | NOT NULL | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `cdp_documents`

*table* — 0 rows.

Only verified candidates are promoted here, with their archived copy and extracted text, so the corpus is searchable for workforce references.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `authority_ons_code` | TEXT | NOT NULL | exportable |
| `document_url` | TEXT | NOT NULL | exportable |
| `title` | TEXT | nullable | exportable |
| `document_type` | TEXT | NOT NULL | exportable |
| `published_date` | TEXT | nullable | exportable |
| `archived_path` | TEXT | nullable | exportable |
| `full_text` | TEXT | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `charity_accounts_documents`

*table* — 5 rows.

Layer 2: the filed accounts PDFs themselves, archived and addressable.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `charity_number` | TEXT | NOT NULL | exportable |
| `financial_year_end` | TEXT | NOT NULL | exportable |
| `document_url` | TEXT | NOT NULL | exportable |
| `document_label` | TEXT | nullable | exportable |
| `archived_path` | TEXT | nullable | exportable |
| `page_count` | INTEGER | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `charity_accounts_extracts`

*table* — 5 rows.

Layer 3: figures extracted from those PDFs. amounts_multiplier records how the source table was denominated (accounts are usually presented in £000). It is detected explicitly from the page, never assumed — a silent 1000x error here would be catastrophic in a pay campaign — and a row where it cannot be determined stores NULL amounts and a parse_failures entry instead. average_employees and average_employees_fte are SEPARATE columns because charities publish either or both, and conflating them is precisely the error the caveat in the brief warns about. employees_basis records what average_employees actually is, and is never defaulted.

Feeds Sheets tab(s): 05_Charity_Finance.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `charity_number` | TEXT | NOT NULL | exportable |
| `financial_year_end` | TEXT | NOT NULL | exportable |
| `amounts_multiplier` | INTEGER | nullable | exportable |
| `staff_costs_total` | REAL | nullable | exportable |
| `wages_and_salaries` | REAL | nullable | exportable |
| `social_security_costs` | REAL | nullable | exportable |
| `pension_costs` | REAL | nullable | exportable |
| `agency_and_third_party` | REAL | nullable | exportable |
| `redundancy_costs` | REAL | nullable | exportable |
| `average_employees` | REAL | nullable | exportable |
| `employees_basis` | TEXT | nullable | exportable |
| `average_employees_fte` | REAL | nullable | exportable |
| `senior_pay_bands_json` | TEXT | nullable | exportable |
| `senior_pay_band_headcount` | INTEGER | nullable | exportable |
| `key_management_remuneration` | REAL | nullable | exportable |
| `key_management_headcount` | INTEGER | nullable | exportable |
| `extraction_page` | INTEGER | nullable | exportable |
| `raw_text_block` | TEXT | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `charity_financials`

*table* — 5 rows.

Layer 1: the register API's financial history series.

Feeds Sheets tab(s): 05_Charity_Finance.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `charity_number` | TEXT | NOT NULL | exportable |
| `financial_year_end` | TEXT | NOT NULL | exportable |
| `ar_cycle_reference` | TEXT | nullable | exportable |
| `total_income` | REAL | nullable | exportable |
| `total_expenditure` | REAL | nullable | exportable |
| `income_from_govt_contracts` | REAL | nullable | exportable |
| `income_from_govt_grants` | REAL | nullable | exportable |
| `inc_charitable_activities` | REAL | nullable | exportable |
| `exp_charitable_activities` | REAL | nullable | exportable |
| `consolidated_account` | INTEGER | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `committee_paper_candidates`

*table* — 0 rows.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `authority_ons_code` | TEXT | NOT NULL | exportable |
| `document_url` | TEXT | NOT NULL | exportable |
| `committee_name` | TEXT | nullable | exportable |
| `meeting_date` | TEXT | nullable | exportable |
| `agenda_item_title` | TEXT | nullable | exportable |
| `report_title` | TEXT | nullable | exportable |
| `matched_terms` | TEXT | nullable | exportable |
| `committee_system` | TEXT | nullable | exportable |
| `verified` | INTEGER | NOT NULL | exportable |
| `verified_at` | TEXT | nullable | exportable |
| `rejected` | INTEGER | NOT NULL | exportable |
| `discovered_at` | TEXT | NOT NULL | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |
| `result_type` | TEXT | nullable | exportable |
| `match_quality` | TEXT | nullable | exportable |
| `item_reference` | TEXT | nullable | exportable |

## `committee_papers`

*table* — 0 rows.

Only verified candidates are promoted.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `authority_ons_code` | TEXT | NOT NULL | exportable |
| `document_url` | TEXT | NOT NULL | exportable |
| `committee_name` | TEXT | nullable | exportable |
| `meeting_date` | TEXT | nullable | exportable |
| `agenda_item_title` | TEXT | nullable | exportable |
| `report_title` | TEXT | nullable | exportable |
| `archived_path` | TEXT | nullable | exportable |
| `full_text` | TEXT | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `companies`

*table* — 9 rows.

Module 4: corporate structure (Companies House). Why this module exists: the entity that holds a contract is frequently not the entity that employs the staff. CGL's registered charity (03861209) and its trading subsidiary CHANGE, GROW, LIVE SERVICES LIMITED (06228752) are different legal persons, and which one appears on a notice determines who is the respondent in a tribunal claim and who is the transferor in a TUPE transfer. The schema therefore keeps companies as first-class rows linked to a provider, never collapsing a group into a single organisation.

Feeds Sheets tab(s): 04_Providers.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `company_number` | TEXT | nullable | exportable |
| `provider_key` | TEXT | nullable | exportable |
| `company_name` | TEXT | NOT NULL | exportable |
| `company_status` | TEXT | nullable | exportable |
| `company_type` | TEXT | nullable | exportable |
| `date_of_creation` | TEXT | nullable | exportable |
| `date_of_cessation` | TEXT | nullable | exportable |
| `sic_codes` | TEXT | nullable | exportable |
| `registered_address` | TEXT | nullable | exportable |
| `jurisdiction` | TEXT | nullable | exportable |
| `match_basis` | TEXT | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `company_filings`

*table* — 1,027 rows.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `company_number` | TEXT | NOT NULL | exportable |
| `transaction_id` | TEXT | NOT NULL | exportable |
| `filing_date` | TEXT | nullable | exportable |
| `category` | TEXT | nullable | exportable |
| `subcategory` | TEXT | nullable | exportable |
| `description` | TEXT | nullable | exportable |
| `document_url` | TEXT | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `company_insolvency_case_dates`

*table* — 0 rows.

Case dates, keeping Companies House's own date vocabulary rather than flattening it into columns this pipeline invented. The set of date types varies with the case type ('administration-started-on' and 'administration-ended-on' for one, 'wound-up-on' and 'dissolved-on' for another), and mapping them onto a fixed started/ended pair would mean deciding that an administration ending and a winding-up are the same kind of fact. They are not.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `company_number` | TEXT | NOT NULL | exportable |
| `case_number` | TEXT | NOT NULL | exportable |
| `date_type` | TEXT | NOT NULL | exportable |
| `date_value` | TEXT | nullable | exportable |

## `company_insolvency_cases`

*table* — 0 rows.

One row per insolvency case. A company can have several — Lifeline has two, an administration followed by a creditors' voluntary liquidation, and they are different events with different dates.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `company_number` | TEXT | NOT NULL | exportable |
| `case_number` | TEXT | NOT NULL | exportable |
| `case_type` | TEXT | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `company_previous_names`

*table* — 18 rows.

Former names, straight from Companies House. These are AUTHORITATIVE aliases, not inference: CGL's charity was "CRIME REDUCTION INITIATIVES" until 2016-04-01 and its subsidiary was "CRI UK LIMITED" until 2013, so a pre-2016 contract or judgment naming CRI is a CGL record. Modules 1 and 2 can use this table to widen their name matching without anyone guessing.

Feeds Sheets tab(s): 04_Providers.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `company_number` | TEXT | NOT NULL | exportable |
| `previous_name` | TEXT | NOT NULL | exportable |
| `effective_from` | TEXT | nullable | exportable |
| `ceased_on` | TEXT | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `contracts`

*table* — 748 rows.

Module 1: procurement notices (Find a Tender + Contracts Finder OCDS). One row per (notice_id, supplier_id): most notices have zero or one supplier, but a multi-lot notice can award to several suppliers, so supplier_id (default '' when no award/supplier exists yet, e.g. a planning or tender-stage notice) is part of the natural key rather than notice_id alone.

Feeds Sheets tab(s): 03_Contracts.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `notice_id` | TEXT | NOT NULL | exportable |
| `supplier_id` | TEXT | NOT NULL | exportable |
| `ocid` | TEXT | NOT NULL | exportable |
| `notice_type` | TEXT | nullable | exportable |
| `buyer_name` | TEXT | nullable | exportable |
| `buyer_ons_code` | TEXT | nullable | exportable |
| `supplier_name_raw` | TEXT | nullable | exportable |
| `supplier_ppon` | TEXT | nullable | exportable |
| `title` | TEXT | nullable | exportable |
| `description` | TEXT | nullable | exportable |
| `cpv_codes` | TEXT | nullable | exportable |
| `value_core` | REAL | nullable | exportable |
| `value_max` | REAL | nullable | exportable |
| `currency` | TEXT | nullable | exportable |
| `date_published` | TEXT | nullable | exportable |
| `date_start` | TEXT | nullable | exportable |
| `date_end` | TEXT | nullable | exportable |
| `extension_terms_text` | TEXT | nullable | exportable |
| `procedure_type` | TEXT | nullable | exportable |
| `psr_basis` | INTEGER | NOT NULL | exportable |
| `psr_direct_award_option` | TEXT | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `cqc_location_reports`

*table* — 580 rows.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `location_id` | TEXT | NOT NULL | exportable |
| `report_link_id` | TEXT | NOT NULL | exportable |
| `report_date` | TEXT | nullable | exportable |
| `first_visit_date` | TEXT | nullable | exportable |
| `report_uri` | TEXT | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `cqc_locations`

*table* — 384 rows.

Feeds Sheets tab(s): 06_CQC_Locations.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `location_id` | TEXT | nullable | exportable |
| `provider_id` | TEXT | NOT NULL | exportable |
| `provider_key` | TEXT | nullable | exportable |
| `location_name` | TEXT | nullable | exportable |
| `postal_code` | TEXT | nullable | exportable |
| `latitude` | REAL | nullable | exportable |
| `longitude` | REAL | nullable | exportable |
| `local_authority_raw` | TEXT | nullable | exportable |
| `local_authority_ons_code` | TEXT | nullable | exportable |
| `region` | TEXT | nullable | exportable |
| `registration_status` | TEXT | nullable | exportable |
| `registration_date` | TEXT | nullable | exportable |
| `last_inspection_date` | TEXT | nullable | exportable |
| `overall_rating` | TEXT | nullable | exportable |
| `overall_rating_date` | TEXT | nullable | exportable |
| `regulated_activities` | TEXT | nullable | exportable |
| `service_types` | TEXT | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `cqc_providers`

*table* — 4 rows.

Module 5: CQC registered locations. IMPORTANT SCOPE LIMIT (also recorded in docs/CAVEATS.md): CQC registration covers only certain regulated activities — residential detoxification, inpatient care and some prescribing services. A large share of community drug and alcohol provision is NOT CQC-registered, so this table is a map of regulated locations, never a complete service map. Counting locations per authority and reading it as service coverage would be wrong.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `provider_id` | TEXT | nullable | exportable |
| `provider_key` | TEXT | nullable | exportable |
| `provider_name` | TEXT | NOT NULL | exportable |
| `companies_house_number` | TEXT | nullable | exportable |
| `charity_number` | TEXT | nullable | exportable |
| `registration_status` | TEXT | nullable | exportable |
| `registration_date` | TEXT | nullable | exportable |
| `ownership_type` | TEXT | nullable | exportable |
| `organisation_type` | TEXT | nullable | exportable |
| `postal_code` | TEXT | nullable | exportable |
| `match_basis` | TEXT | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `fingertips_indicators`

*table* — 10 rows.

Module 12: OHID Fingertips local-authority indicators. Exists to fill the gap Module 7 exposed: the GOV.UK NDTMS data tables publish numbers in treatment, waiting times and successful completions nationally, with only one local-authority sheet. Fingertips carries the same measures per authority, keyed by ONS area code. SAME SEPARATION RULE AS MODULE 7. This is service-demand and outcome context, not workforce data, and it is never merged into the workforce census tables. NO DERIVED UNMET NEED. Prevalence (indicator 91117) and numbers in treatment (92454, 91182) are stored exactly as published. Unmet need is conventionally the gap between them, but the two use different estimation methods, populations and confidence intervals, so this pipeline does not subtract one from the other — that is a downstream decision to document.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `indicator_id` | INTEGER | nullable | exportable |
| `indicator_name` | TEXT | NOT NULL | exportable |
| `slug` | TEXT | nullable | exportable |
| `topic` | TEXT | nullable | exportable |
| `substance` | TEXT | nullable | exportable |
| `definition` | TEXT | nullable | exportable |
| `unit` | TEXT | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `fingertips_la_values`

*table* — 22,667 rows.

One row per published data point. area_code is Fingertips' ONS code, so this joins to `authorities` directly with no name matching — unlike the NDTMS spreadsheets, which publish area names only. ons_code is set only when the code actually resolves against `authorities`; national (E92…) and regional (E12…) rows are retained with ons_code NULL because they are the published comparators for the LA figures, and dropping them would leave the LA values without the context they are read against.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `indicator_id` | INTEGER | NOT NULL | exportable |
| `area_code` | TEXT | NOT NULL | exportable |
| `area_type_id` | INTEGER | NOT NULL | exportable |
| `sex` | TEXT | NOT NULL | exportable |
| `age` | TEXT | NOT NULL | exportable |
| `category_type` | TEXT | NOT NULL | exportable |
| `category` | TEXT | NOT NULL | exportable |
| `time_period` | TEXT | NOT NULL | exportable |
| `area_name` | TEXT | nullable | exportable |
| `ons_code` | TEXT | nullable | exportable |
| `area_level` | TEXT | nullable | exportable |
| `value` | REAL | nullable | exportable |
| `lower_ci_95` | REAL | nullable | exportable |
| `upper_ci_95` | REAL | nullable | exportable |
| `count_numerator` | REAL | nullable | exportable |
| `denominator` | REAL | nullable | exportable |
| `value_note` | TEXT | nullable | exportable |
| `time_period_sortable` | TEXT | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `foi_attachments`

*table* — 0 rows.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `ons_code` | TEXT | NOT NULL | exportable |
| `request_url` | TEXT | NOT NULL | exportable |
| `attachment_url` | TEXT | NOT NULL | exportable |
| `file_name` | TEXT | nullable | exportable |
| `archived_path` | TEXT | nullable | exportable |

## `foi_request_candidates`

*table* — 850 rows.

Candidates found on a council's own disclosure log. Discovery only: a link whose text matched a search term is not an FOI response about substance misuse until someone opens it. Nothing is promoted without verification, the same discipline as Modules 9 and 10.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `ons_code` | TEXT | NOT NULL | exportable |
| `candidate_url` | TEXT | NOT NULL | exportable |
| `title` | TEXT | nullable | exportable |
| `matched_term` | TEXT | nullable | exportable |
| `topic` | TEXT | nullable | exportable |
| `discovered_at` | TEXT | NOT NULL | exportable |
| `discovery_source` | TEXT | NOT NULL | exportable |
| `verified` | INTEGER | NOT NULL | exportable |
| `verified_at` | TEXT | nullable | exportable |
| `rejected` | INTEGER | NOT NULL | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |
| `request_slug` | TEXT | nullable | exportable |
| `authority_slug` | TEXT | nullable | exportable |
| `wdtk_status` | TEXT | nullable | exportable |
| `disclosed` | INTEGER | nullable | exportable |
| `request_date` | TEXT | nullable | exportable |
| `last_updated` | TEXT | nullable | exportable |
| `event_type` | TEXT | nullable | exportable |
| `event_date` | TEXT | nullable | exportable |
| `snippet` | TEXT | nullable | exportable |

## `foi_requests`

*table* — 0 rows.

Verified promotions only.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `ons_code` | TEXT | NOT NULL | exportable |
| `request_url` | TEXT | NOT NULL | exportable |
| `subject` | TEXT | nullable | exportable |
| `request_date` | TEXT | nullable | exportable |
| `response_date` | TEXT | nullable | exportable |
| `status` | TEXT | nullable | exportable |
| `topic` | TEXT | nullable | exportable |
| `response_text` | TEXT | nullable | exportable |
| `archived_path` | TEXT | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `http_cache`

*table* — 1,005 rows.

Constraint 4: conditional requests on re-runs. Keyed by URL so http.py can send If-None-Match / If-Modified-Since without re-fetching unchanged docs.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `url` | TEXT | nullable | exportable |
| `host` | TEXT | NOT NULL | exportable |
| `etag` | TEXT | nullable | exportable |
| `last_modified` | TEXT | nullable | exportable |
| `payload_sha256` | TEXT | nullable | exportable |
| `updated_at` | TEXT | NOT NULL | exportable |

## `la_budget_publications`

*table* — 4 rows.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `publication_slug` | TEXT | NOT NULL | exportable |
| `document_url` | TEXT | NOT NULL | exportable |
| `financial_year` | TEXT | NOT NULL | exportable |
| `document_label` | TEXT | nullable | exportable |
| `amounts_multiplier` | INTEGER | nullable | exportable |
| `sheet_name` | TEXT | nullable | exportable |
| `data_rows` | INTEGER | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `la_revenue_budgets`

*table* — 237,831 rows.

Module 13: local authority revenue budgets (MHCLG). The structured national release, so 150+ council websites do not have to be scraped for the same numbers. Every authority's budgeted revenue expenditure by service line, including the Public Health line, keyed by ONS code — MHCLG publishes the code itself, so this joins to `authorities` without any name matching. SEPARATE FROM THE GRANT. This is what an authority BUDGETED. The public health grant (Module 11) is what it was ALLOCATED. They are different measurements from different departments and are not differenced here: an authority may budget above or below its grant for reasons this pipeline cannot see, and the gap is a finding to investigate rather than a number to publish unexamined. Stored tidy/long because MHCLG's column set (213 columns in 2026-27) changes between years, and a fixed wide table would silently drop whatever moved.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `ons_code` | TEXT | NOT NULL | exportable |
| `financial_year` | TEXT | NOT NULL | exportable |
| `line_code` | TEXT | NOT NULL | exportable |
| `section` | TEXT | nullable | exportable |
| `line_number` | TEXT | nullable | exportable |
| `column_label` | TEXT | nullable | exportable |
| `amounts_multiplier` | INTEGER | nullable | exportable |
| `amount` | REAL | nullable | exportable |
| `value_text` | TEXT | nullable | exportable |
| `body_type` | TEXT | nullable | exportable |
| `authority_class` | TEXT | nullable | exportable |
| `source_document` | TEXT | NOT NULL | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `module_cursors`

*table* — 2 rows.

Constraint 5: idempotent and resumable. Each module persists a cursor (e.g. last publication date processed) so an interrupted run resumes.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `module` | TEXT | nullable | exportable |
| `cursor_value` | TEXT | nullable | exportable |
| `updated_at` | TEXT | NOT NULL | exportable |

## `ndtms_la_statistics`

*table* — 17,231 rows.

One row per (publication, table, area, indicator, value type). ons_code is resolved from the published area name against `authorities`; it stays NULL and the name goes to review_queue when it cannot be matched deterministically, rather than being guessed.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `publication_slug` | TEXT | NOT NULL | exportable |
| `table_ref` | TEXT | NOT NULL | exportable |
| `area_name_raw` | TEXT | NOT NULL | exportable |
| `ons_code` | TEXT | nullable | exportable |
| `age_group` | TEXT | nullable | exportable |
| `time_period` | TEXT | nullable | exportable |
| `indicator` | TEXT | NOT NULL | exportable |
| `value` | REAL | nullable | exportable |
| `value_text` | TEXT | nullable | exportable |
| `cohort` | TEXT | NOT NULL | exportable |
| `financial_year` | TEXT | NOT NULL | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `ndtms_publications`

*table* — 11 rows.

Module 7: NDTMS published treatment statistics (OHID). SEPARATE EVIDENCE LAYER. This is service-demand context — how many people are in treatment, waiting times, treatment-related deaths — and it is NOT workforce data. It deliberately lives in its own tables and is never merged into the workforce census tables, because the two measure different populations by different methods. Dividing one by the other (caseload per worker, say) would combine sources the pipeline is not entitled to combine; that is a downstream decision for whoever documents it. Stored tidy/long because the published indicator set differs by year and by cohort (adults vs young people), so any fixed wide schema would drop whatever a given year happened to publish differently.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `publication_slug` | TEXT | nullable | exportable |
| `cohort` | TEXT | NOT NULL | exportable |
| `financial_year` | TEXT | NOT NULL | exportable |
| `title` | TEXT | nullable | exportable |
| `document_url` | TEXT | nullable | exportable |
| `archived_path` | TEXT | nullable | exportable |
| `sheets_total` | INTEGER | nullable | exportable |
| `sheets_local_authority` | INTEGER | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `ndtms_sheet_inventory`

*table* — 381 rows.

Records every sheet seen and whether it was LA-level, so the (large) share of this publication that is national-only is visible rather than looking like a extraction failure.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `publication_slug` | TEXT | NOT NULL | exportable |
| `table_ref` | TEXT | NOT NULL | exportable |
| `sheet_title` | TEXT | nullable | exportable |
| `is_local_authority` | INTEGER | NOT NULL | exportable |
| `row_count` | INTEGER | nullable | exportable |

## `nhs_job_advert_locations`

*table* — 0 rows.

One advert can name several sites ("Chichester PO19 1XP, CRAWLEY RH10 8GN, Worthing BN11 1UG"). Kept as its own rows rather than a joined string so a location can be counted or matched to an authority later without splitting text back apart. Not matched to an ONS code here: these are free-text place names and postcodes, and guessing an authority from them is the kind of inferred link this pipeline records rather than invents.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `job_reference` | TEXT | NOT NULL | exportable |
| `location_raw` | TEXT | NOT NULL | exportable |

## `nhs_job_adverts`

*table* — 0 rows.

Module 16: NHS Jobs advertised pay. The only source in this pipeline that carries DIRECT pay evidence. Every other pay figure here is a composite or a proxy: the charity accounts give a wage bill over a headcount (v_wage_per_employee, and read its caveats), the workforce census gives sector aggregates attributable to nobody. An advert states what an employer offers for a named role, in its own words, on a date. WHAT THIS IS NOT.   1. It is not a pay scale. An advertised band is what the employer is      offering a new starter, which is not what incumbent staff are paid and      is not a spine point.   2. It is not a complete picture of a provider's vacancies. NHS Jobs      carries NHS and some commissioned-provider adverts. A charity      advertising only on its own site is invisible here, so every count off      this table is a FLOOR, never a total, and must be presented as one.   3. It is not the result set NHS Jobs returned. The search has no empty      answer: a nonsense employer name comes back "659 jobs found" of      unrelated adverts, and searching "Turning Point" returns West Point      Medical Centre alongside it. Rows here are the adverts whose OWN      employer field matched a known provider name; everything else the      search returned was discarded and counted. See the module docstring. HOURLY AND ANNUAL FIGURES ARE NOT CONVERTED into one another anywhere in this pipeline. salary_period says which the employer published, and an hourly rate multiplied into a year is a number the source never stated and that depends on contracted hours nobody here knows.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `job_reference` | TEXT | nullable | exportable |
| `provider_key` | TEXT | NOT NULL | exportable |
| `provider_match_basis` | TEXT | NOT NULL | exportable |
| `employer_name_raw` | TEXT | NOT NULL | exportable |
| `job_title` | TEXT | nullable | exportable |
| `advert_url` | TEXT | NOT NULL | exportable |
| `salary_raw` | TEXT | nullable | exportable |
| `salary_min` | REAL | nullable | exportable |
| `salary_max` | REAL | nullable | exportable |
| `salary_period` | TEXT | nullable | exportable |
| `salary_basis` | TEXT | NOT NULL | exportable |
| `contract_type` | TEXT | nullable | exportable |
| `working_pattern` | TEXT | nullable | exportable |
| `posted_date` | TEXT | nullable | exportable |
| `closing_date` | TEXT | nullable | exportable |
| `searched_variant` | TEXT | NOT NULL | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `parse_failures`

*table* — 23 rows.

Constraint 6: fail loudly, never silently guess. A field that could not be parsed is written as NULL and logged here with the raw fragment.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `id` | INTEGER | nullable | exportable |
| `module` | TEXT | NOT NULL | exportable |
| `source_url` | TEXT | nullable | exportable |
| `field_name` | TEXT | nullable | exportable |
| `raw_fragment` | TEXT | nullable | exportable |
| `reason` | TEXT | nullable | exportable |
| `created_at` | TEXT | NOT NULL | exportable |

## `pfd_concern_terms`

*table* — 73 rows.

Index of workforce-related terms found in MATTERS OF CONCERN. A hit means the word appears — it is a finding aid, not a judgement about the report.

Feeds Sheets tab(s): 08_PFD_Reports.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `report_ref` | TEXT | NOT NULL | exportable |
| `term` | TEXT | NOT NULL | exportable |
| `occurrences` | INTEGER | NOT NULL | exportable |

## `pfd_documents`

*table* — 22 rows.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `report_ref` | TEXT | NOT NULL | exportable |
| `document_url` | TEXT | NOT NULL | exportable |
| `document_type` | TEXT | nullable | exportable |

## `pfd_provider_mentions`

*table* — 32 rows.

Two distinct kinds of provider involvement, deliberately not collapsed:   'recipient'  -> the coroner addressed the report to this provider   'body_text'  -> the provider is named in the report but was NOT a recipient These mean very different things and must never be counted together.

Feeds Sheets tab(s): 08_PFD_Reports.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `report_ref` | TEXT | NOT NULL | exportable |
| `provider_key` | TEXT | NOT NULL | exportable |
| `mention_type` | TEXT | NOT NULL | exportable |
| `matched_name` | TEXT | nullable | exportable |

## `pfd_recipients`

*table* — 2,557 rows.

One row per organisation the report was sent to, rather than a blob, so a recipient can be matched and counted.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `report_ref` | TEXT | NOT NULL | exportable |
| `organisation_name` | TEXT | NOT NULL | exportable |

## `pfd_reports`

*table* — 1,539 rows.

Module 8: Prevention of Future Deaths reports (judiciary.uk). PERSONAL DATA BOUNDARY. Every PFD report names the deceased, in the page title and in a "Deceased name :" field. None of that reaches a public table: pfd_reports is keyed on the coroner's own report reference, and the name and raw title live only in restricted_pfd_persons. The coroner's name IS public here. They are a public official acting in that capacity, named on the face of a published report, and the brief lists coroner name among the fields to capture. NO AUTOMATED CHARACTERISATION. matters_of_concern is stored verbatim. The pipeline indexes it for workforce-related terms so a human can find the relevant reports quickly, but it never summarises, scores or paraphrases what a coroner found — that is for a person to read.

Feeds Sheets tab(s): 08_PFD_Reports.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `report_ref` | TEXT | nullable | exportable |
| `report_date` | TEXT | nullable | exportable |
| `coroner_name` | TEXT | nullable | exportable |
| `coroner_area` | TEXT | nullable | exportable |
| `categories` | TEXT | nullable | exportable |
| `report_url` | TEXT | NOT NULL | exportable |
| `matters_of_concern` | TEXT | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `provider_annual_reports`

*table* — 5 rows.

Module 14: provider annual report narrative. Module 3 already downloads and archives each charity's filed accounts, which for these providers ARE the annual report, but it only extracts the staff-costs note. This module reads the narrative around it: what the provider says about recruitment, retention, restructuring, wellbeing, equality and principal risks. It re-reads the PDFs already on disk rather than fetching them again. NOTHING IS SUMMARISED. Passages are stored verbatim with their page number, exactly as PFD matters of concern are. A term index says where to look; a person decides what it means. The disclosure-gap table is the point of the module as much as the passages. A provider writing at length about retention while publishing no retention figure is itself evidence — but see the wording of `search_terms`: this records that no passage matched those terms, which is weaker than "the provider does not disclose it" and must be read that way.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `provider_key` | TEXT | NOT NULL | exportable |
| `financial_year_end` | TEXT | NOT NULL | exportable |
| `charity_number` | TEXT | nullable | exportable |
| `document_url` | TEXT | NOT NULL | exportable |
| `archived_path` | TEXT | nullable | exportable |
| `page_count` | INTEGER | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `provider_identifiers`

*table* — 11 rows.

External identifiers for a provider. `status` distinguishes an identifier asserted in config (and therefore human-verified) from one discovered by a module, which must be confirmed before it's trusted for joins. Deliberately many-to-one: a provider commonly has several company numbers (the charity plus its trading subsidiaries), and the entity that holds a contract is often not the entity that employs the staff — which is exactly the distinction Module 4 exists to make visible, so the schema must not collapse it.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `provider_key` | TEXT | NOT NULL | exportable |
| `scheme` | TEXT | NOT NULL | exportable |
| `identifier` | TEXT | NOT NULL | exportable |
| `role` | TEXT | nullable | exportable |
| `status` | TEXT | NOT NULL | exportable |
| `discovered_by` | TEXT | nullable | exportable |

## `provider_report_disclosure`

*table* — 60 rows.

What a report did and did not appear to cover. `matched = 0` means no passage matched `search_terms` — NOT that the provider discloses nothing on the subject. A figure given only in a table, or described in wording the terms do not cover, would read the same way. Treat a gap as a prompt to look, not as a finding in itself.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `provider_key` | TEXT | NOT NULL | exportable |
| `financial_year_end` | TEXT | NOT NULL | exportable |
| `topic` | TEXT | NOT NULL | exportable |
| `matched` | INTEGER | NOT NULL | exportable |
| `pages_matched` | INTEGER | NOT NULL | exportable |
| `search_terms` | TEXT | NOT NULL | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `provider_report_passages`

*table* — 64 rows.

One row per (report, topic, page) where the topic's terms appear. The passage is the verbatim page text around the match.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `provider_key` | TEXT | NOT NULL | exportable |
| `financial_year_end` | TEXT | NOT NULL | exportable |
| `topic` | TEXT | NOT NULL | exportable |
| `page_number` | INTEGER | NOT NULL | exportable |
| `matched_term` | TEXT | NOT NULL | exportable |
| `passage_text` | TEXT | NOT NULL | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `providers`

*table* — 13 rows.

Provider entity model: the second stable entity alongside `authorities`. Modules 2/3/4/5 (tribunals, charity finance, companies, CQC) and Module 1 (procurement) all hang off provider_key, so the whole evidence base can be navigated per-provider as well as per-authority. These two tables are REFERENCE/CONFIG, not evidence: they're seeded deterministically from pipeline/providers.py on every run and carry no provenance columns — same treatment as supplier_aliases. Anything fetched from a source (charity financials, filings, tribunal cases) goes in its own evidence table, references provider_key, and carries full provenance.

Feeds Sheets tab(s): 04_Providers.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `provider_key` | TEXT | nullable | exportable |
| `canonical_name` | TEXT | NOT NULL | exportable |
| `is_target` | INTEGER | NOT NULL | exportable |
| `notes` | TEXT | nullable | exportable |

## `public_health_grants`

*table* — 4,893 rows.

Module 11: Public Health Grant allocations (DHSC). Stored in tidy/long form — one row per (authority, financial year, grant line item) — rather than a wide fixed-column table, because DHSC's published spreadsheet structure changes shape most years (different sheet name, different header row position, different set of grant breakdowns). grant_type is a normalised slug of the actual source column header, with the raw header preserved in source_column_header for audit.

Feeds Sheets tab(s): 02_Public_Health_Grant.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `ons_code` | TEXT | NOT NULL | exportable |
| `financial_year` | TEXT | NOT NULL | exportable |
| `grant_type` | TEXT | NOT NULL | exportable |
| `allocation_status` | TEXT | NOT NULL | exportable |
| `unit` | TEXT | NOT NULL | exportable |
| `amount` | REAL | NOT NULL | exportable |
| `source_column_header` | TEXT | NOT NULL | exportable |
| `source_document` | TEXT | NOT NULL | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `restricted_committee_result_snippets`

*table* — 0 rows.

The matched text ModernGov prints under each hit. It is the single most useful thing for a reviewer deciding whether a candidate is relevant — and it routinely names officers by name and job title ("Presented by <officer>, Head of Health Improvement"). Public role or not, that is personal data, so it lives here rather than in committee_paper_candidates, which is exportable. Same rule as restricted_pfd_report_text.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `authority_ons_code` | TEXT | NOT NULL | restricted |
| `document_url` | TEXT | NOT NULL | restricted |
| `matched_term` | TEXT | NOT NULL | restricted |
| `snippet_text` | TEXT | nullable | restricted |
| `source_url` | TEXT | NOT NULL | restricted |
| `retrieved_at` | TEXT | NOT NULL | restricted |
| `http_status` | INTEGER | NOT NULL | restricted |
| `source_system` | TEXT | NOT NULL | restricted |
| `payload_sha256` | TEXT | NOT NULL | restricted |

## `restricted_company_insolvency_practitioners`

*table* — 0 rows.

RESTRICTED: named individuals. Insolvency practitioners are licensed professionals acting as statutory office-holders and their names are on the public register — but a pay campaign has no use for them, and the cheapest way to be sure a name is never exported is not to put it in an exportable table. Their firm addresses are not stored at all: they add nothing here, and an address that serves no evidential purpose is a personal-data footprint with no argument behind it.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `company_number` | TEXT | NOT NULL | restricted |
| `case_number` | TEXT | NOT NULL | restricted |
| `practitioner_name` | TEXT | NOT NULL | restricted |
| `role` | TEXT | nullable | restricted |
| `appointed_on` | TEXT | nullable | restricted |
| `ceased_to_act_on` | TEXT | nullable | restricted |

## `restricted_company_officers`

*table* — 265 rows.

RESTRICTED: named individuals. Excluded from every export by default. Officer changes matter analytically (a wave of resignations around a restructure is evidence), but the names themselves are personal data.

Feeds Sheets tab(s): 04_Providers.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `company_number` | TEXT | NOT NULL | restricted |
| `officer_ref` | TEXT | NOT NULL | restricted |
| `officer_name` | TEXT | nullable | restricted |
| `officer_role` | TEXT | nullable | restricted |
| `appointed_on` | TEXT | nullable | restricted |
| `resigned_on` | TEXT | nullable | restricted |
| `nationality` | TEXT | nullable | restricted |
| `occupation` | TEXT | nullable | restricted |
| `address_locality` | TEXT | nullable | restricted |

## `restricted_cqc_location_contacts`

*table* — 181 rows.

RESTRICTED: CQC embeds named registered managers inside each location's regulatedActivities. Named individuals never reach an export.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `location_id` | TEXT | NOT NULL | restricted |
| `contact_ref` | TEXT | NOT NULL | restricted |
| `person_name` | TEXT | nullable | restricted |
| `person_role` | TEXT | nullable | restricted |
| `regulated_activity` | TEXT | nullable | restricted |

## `restricted_officer_disqualifications`

*table* — 0 rows.

RESTRICTED: disqualified directors. READ THIS BEFORE USING THE TABLE. Companies House publishes no link from an officer's appointment to a disqualification, so the only route is to search the register by name. A name match is not an identity match — that is the lesson m04 already learned from FORWARD TRUST LIMITED — and getting it wrong here does not mis-attribute a contract, it says a named person was banned from being a director when they were not. So nothing reaches this table on a name alone. A row is written only where the register's record corroborates on BOTH the name and the month and year of birth that Companies House publishes for the serving director, or where the person numbers match outright. Everything weaker goes to review_queue as a candidate and is never stored as a fact. Expect this table to be empty, and that is the point. Acting as a director while disqualified is a criminal offence, so a serving director of a large registered charity being on this register would be extraordinary. An empty table is a checkable negative; it is not evidence that the check was skipped.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `company_number` | TEXT | NOT NULL | restricted |
| `officer_ref` | TEXT | NOT NULL | restricted |
| `officer_name` | TEXT | nullable | restricted |
| `case_identifier` | TEXT | NOT NULL | restricted |
| `disqualification_type` | TEXT | nullable | restricted |
| `disqualified_from` | TEXT | nullable | restricted |
| `disqualified_until` | TEXT | nullable | restricted |
| `reason_act` | TEXT | nullable | restricted |
| `reason_description` | TEXT | nullable | restricted |
| `disqualified_company_names` | TEXT | nullable | restricted |
| `match_basis` | TEXT | NOT NULL | restricted |
| `source_url` | TEXT | NOT NULL | restricted |
| `retrieved_at` | TEXT | NOT NULL | restricted |
| `http_status` | INTEGER | NOT NULL | restricted |
| `source_system` | TEXT | NOT NULL | restricted |
| `payload_sha256` | TEXT | NOT NULL | restricted |

## `restricted_pfd_persons`

*table* — 1,539 rows.

RESTRICTED: excluded from every export by default.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `report_ref` | TEXT | nullable | restricted |
| `deceased_name` | TEXT | nullable | restricted |
| `page_title_raw` | TEXT | nullable | restricted |

## `restricted_pfd_report_text`

*table* — 1,539 rows.

RESTRICTED: the full report text. Kept because it is the searchable corpus and the evidence behind every extracted field, but restricted because a PFD report names the deceased throughout — not only in the header field.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `report_ref` | TEXT | nullable | restricted |
| `body_text` | TEXT | NOT NULL | restricted |

## `restricted_tribunal_parties`

*table* — 31 rows.

RESTRICTED: excluded from every export by default (see pipeline/exports).

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `case_number` | TEXT | nullable | restricted |
| `claimant_name_raw` | TEXT | nullable | restricted |
| `page_title_raw` | TEXT | nullable | restricted |
| `source_slug` | TEXT | nullable | restricted |

## `review_decisions`

*table* — 0 rows.

A record of every human decision taken on a review-queue item. `review_queue.status` has always been the *current* state of an item, and until now nothing ever moved it off 'pending': the queue was written by modules and read by people, with the deciding done in someone's head. The reviewer UI (pipeline/web/) writes decisions back, so the queue has to be able to say who decided what, when, and on what basis. A status column alone cannot. Two things live here that `review_queue` has nowhere to put:   * History. An item can go pending -> approved -> pending -> rejected; a     decision taken in error is revertible, and the revert is itself a     decision worth keeping. Only the latest state lands on     `review_queue.status`, and every step is a row here.   * The context as it read at the time. `record_review_item()` refreshes     `context_json` whenever a module re-observes a *pending* item, so an     item reverted to pending and then re-run can have its context rewritten     underneath a decision that was already taken against the old text. The     snapshot is what the reviewer was actually looking at. Deciding is deliberately NOT promotion. Nothing here moves a value into a canonical table: what "approved" means for an unmatched buyer name (bind it to an authority) and for a PFD report whose concerns are PDF-only (nothing — it is an acknowledgement) are different operations, and neither exists yet. This table records the judgement so that acting on it is not also the work of remembering it. See README "Reviewing what a run produced".

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `id` | INTEGER | nullable | exportable |
| `review_item_id` | INTEGER | NOT NULL | exportable |
| `decision` | TEXT | NOT NULL | exportable |
| `status_before` | TEXT | NOT NULL | exportable |
| `note` | TEXT | nullable | exportable |
| `decided_by` | TEXT | NOT NULL | exportable |
| `decided_at` | TEXT | NOT NULL | exportable |
| `context_json` | TEXT | nullable | exportable |

## `review_queue`

*table* — 2,172 rows.

Anything that requires human judgement before it can be promoted into a canonical table (unmatched buyer names, unverified CDP/committee document candidates, charities whose accounts don't parse cleanly, etc).

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `id` | INTEGER | nullable | exportable |
| `module` | TEXT | NOT NULL | exportable |
| `item_type` | TEXT | NOT NULL | exportable |
| `raw_value` | TEXT | NOT NULL | exportable |
| `context_json` | TEXT | nullable | exportable |
| `status` | TEXT | NOT NULL | exportable |
| `created_at` | TEXT | NOT NULL | exportable |
| `resolved_at` | TEXT | nullable | exportable |

## `schema_migrations`

*table* — 27 rows.

Core infrastructure tables shared by every module. Applied automatically by pipeline.db.apply_migrations before any module runs.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `filename` | TEXT | nullable | exportable |
| `applied_at` | TEXT | NOT NULL | exportable |

## `supplier_aliases`

*table* — 17 rows.

Deterministic supplier name-variant -> canonical key mapping. Seeded from pipeline/keywords.py's SUPPLIER_NAME_VARIANTS on every run; extend that file (not this table) to add variants — never fuzzy-match here.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `alias_raw` | TEXT | nullable | exportable |
| `supplier_key` | TEXT | NOT NULL | exportable |
| `canonical_name` | TEXT | NOT NULL | exportable |

## `tribunal_cases`

*table* — 31 rows.

Module 2: employment tribunal judgments. PERSONAL DATA BOUNDARY. GOV.UK publishes these decisions with the claimant's name in the page title, the URL slug, and the indexed full text. None of that may reach an export (constraint 3), so:   * tribunal_cases (public)      -> case_number, claim_ref pseudonym, no names   * restricted_tribunal_parties  -> the claimant name and source slug/title claim_ref is derived deterministically from the PUBLIC case number, so it is stable across re-runs and reversible only via the restricted table. Explicitly NOT modelled: any claims-per-employee rate or normalised metric. This database captures only cases reaching published judgment — settled, withdrawn and struck-out claims (the majority) are invisible here, so a rate computed from it would understate reality by an unknown factor. See docs/CAVEATS.md.

Feeds Sheets tab(s): 07_Tribunal_Cases.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `case_number` | TEXT | nullable | exportable |
| `claim_ref` | TEXT | NOT NULL | exportable |
| `provider_key` | TEXT | nullable | exportable |
| `provider_match_basis` | TEXT | nullable | exportable |
| `respondent_normalised` | TEXT | nullable | exportable |
| `office_prefix` | TEXT | nullable | exportable |
| `case_year` | TEXT | nullable | exportable |
| `region` | TEXT | nullable | exportable |
| `hearing_venue_raw` | TEXT | nullable | exportable |
| `decision_date` | TEXT | nullable | exportable |
| `country` | TEXT | nullable | exportable |
| `jurisdiction_codes` | TEXT | nullable | exportable |
| `outcome` | TEXT | nullable | exportable |
| `outcome_confidence` | TEXT | nullable | exportable |
| `document_count` | INTEGER | NOT NULL | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `tribunal_documents`

*table* — 39 rows.

A case can have several documents (e.g. a reserved judgment plus a reconsideration, or judgment and written reasons issued separately), so documents are modelled separately against one case rather than flattened.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `case_number` | TEXT | NOT NULL | exportable |
| `document_url` | TEXT | NOT NULL | exportable |
| `document_title` | TEXT | nullable | exportable |
| `document_type` | TEXT | nullable | exportable |
| `content_type` | TEXT | nullable | exportable |
| `archived_path` | TEXT | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `tribunal_office_regions`

*table* — 0 rows.

Case-number office prefix -> region. Deliberately seeded EMPTY: the prefix scheme is not published in a form this pipeline has verified, and guessing it would attribute cases to the wrong region. Unmapped prefixes are routed to review_queue, and hearing_venue_raw on tribunal_cases gives the raw material to populate this table from the judgments themselves.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `office_prefix` | TEXT | nullable | exportable |
| `region` | TEXT | NOT NULL | exportable |
| `office_name` | TEXT | nullable | exportable |
| `verified_source` | TEXT | NOT NULL | exportable |

## `workforce_census_metrics`

*table* — 68 rows.

Tidy/long form: one row per (year, metric, workforce segment). A wide table is impossible here because each year's report presents a different set of cuts, and forcing them into fixed columns would silently drop whatever that year happened to publish differently.

Feeds Sheets tab(s): 09_Workforce_Census.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `census_year` | INTEGER | NOT NULL | exportable |
| `metric` | TEXT | NOT NULL | exportable |
| `workforce_segment` | TEXT | NOT NULL | exportable |
| `value` | REAL | nullable | exportable |
| `unit` | TEXT | nullable | exportable |
| `source_page` | INTEGER | nullable | exportable |
| `raw_text` | TEXT | NOT NULL | exportable |
| `verified` | INTEGER | NOT NULL | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `workforce_census_page_text`

*table* — 233 rows.

Full text of every page an extractor read, kept so a figure can be checked against its page without re-downloading, and so a later parser revision can be re-run over the same text.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `census_year` | INTEGER | NOT NULL | exportable |
| `page_number` | INTEGER | NOT NULL | exportable |
| `page_text` | TEXT | NOT NULL | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `workforce_census_reports`

*table* — 3 rows.

Module 6: National Drug and Alcohol Treatment and Recovery Services Workforce Census (NHS England / NHS Benchmarking Network). TWO HARD LIMITS, both enforced by this schema rather than left to convention: 1. NO PROVIDER ATTRIBUTION. The census publishes sector-level aggregates    only; there is no provider-level breakdown. There is deliberately no    provider_key column here, because attributing a census figure to CGL or    any named provider would be inference presented as measurement. 2. NOT LIKE-FOR-LIKE ACROSS YEARS. Provider participation varies between    census rounds — the 2023 report says in terms that its data "should not    be used to infer that the workforce size overall" changed. Rows carry    the year they came from and must not be differenced without reading the    participation caveat for both years. See docs/CAVEATS.md. Every extracted figure keeps the verbatim source line next to it, and nothing is treated as publishable until a human has ticked it off against docs/verification/census_{year}_tables.md.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `census_year` | INTEGER | nullable | exportable |
| `report_title` | TEXT | nullable | exportable |
| `document_url` | TEXT | NOT NULL | exportable |
| `archived_path` | TEXT | nullable | exportable |
| `page_count` | INTEGER | nullable | exportable |
| `publisher` | TEXT | nullable | exportable |
| `source_url` | TEXT | NOT NULL | exportable |
| `retrieved_at` | TEXT | NOT NULL | exportable |
| `http_status` | INTEGER | NOT NULL | exportable |
| `source_system` | TEXT | NOT NULL | exportable |
| `payload_sha256` | TEXT | NOT NULL | exportable |

## `restricted_v_officer_edges`

*view* — 265 rows.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `source_id` | TEXT | nullable | restricted |
| `relationship` |  | nullable | restricted |
| `target_id` | TEXT | nullable | restricted |
| `target_label` | TEXT | nullable | restricted |
| `provider_key` | TEXT | nullable | restricted |
| `officer_role` | TEXT | nullable | restricted |
| `appointed_on` | TEXT | nullable | restricted |
| `resigned_on` | TEXT | nullable | restricted |
| `source_url` | TEXT | nullable | restricted |
| `retrieved_at` | TEXT | nullable | restricted |

## `restricted_v_shared_officers`

*view* — 29 rows.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `officer_name` | TEXT | nullable | restricted |
| `company_number_a` | TEXT | nullable | restricted |
| `company_number_b` | TEXT | nullable | restricted |
| `company_name_a` | TEXT | nullable | restricted |
| `company_name_b` | TEXT | nullable | restricted |
| `provider_key_a` | TEXT | nullable | restricted |
| `provider_key_b` | TEXT | nullable | restricted |
| `basis` |  | nullable | restricted |
| `source_url` | TEXT | nullable | restricted |
| `retrieved_at` | TEXT | nullable | restricted |

## `v_company_officer_changes`

*view* — 9 rows.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `company_number` | TEXT | nullable | exportable |
| `officers_total` |  | nullable | exportable |
| `officers_active` |  | nullable | exportable |
| `officers_resigned` |  | nullable | exportable |
| `earliest_appointment` |  | nullable | exportable |
| `latest_change` |  | nullable | exportable |

## `v_entity_edge_confidence`

*view* — 9 rows.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `relationship` |  | nullable | exportable |
| `basis` | TEXT | nullable | exportable |
| `edges` |  | nullable | exportable |

## `v_entity_edges`

*view* — 262 rows.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `source_type` |  | nullable | exportable |
| `source_id` | TEXT | nullable | exportable |
| `relationship` |  | nullable | exportable |
| `target_type` |  | nullable | exportable |
| `target_id` | TEXT | nullable | exportable |
| `target_label` | TEXT | nullable | exportable |
| `basis` | TEXT | nullable | exportable |
| `source_url` | TEXT | nullable | exportable |
| `retrieved_at` | TEXT | nullable | exportable |

## `v_fingertips_la_latest`

*view* — 19,937 rows.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `indicator_id` | INTEGER | nullable | exportable |
| `slug` | TEXT | nullable | exportable |
| `topic` | TEXT | nullable | exportable |
| `substance` | TEXT | nullable | exportable |
| `indicator_name` | TEXT | nullable | exportable |
| `ons_code` | TEXT | nullable | exportable |
| `authority_name` | TEXT | nullable | exportable |
| `time_period` | TEXT | nullable | exportable |
| `value` | REAL | nullable | exportable |
| `lower_ci_95` | REAL | nullable | exportable |
| `upper_ci_95` | REAL | nullable | exportable |
| `count_numerator` | REAL | nullable | exportable |
| `denominator` | REAL | nullable | exportable |
| `value_note` | TEXT | nullable | exportable |

## `v_la_public_health_budget`

*view* — 4,936 rows.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `ons_code` | TEXT | nullable | exportable |
| `authority_name` | TEXT | nullable | exportable |
| `region` | TEXT | nullable | exportable |
| `financial_year` | TEXT | nullable | exportable |
| `line_code` | TEXT | nullable | exportable |
| `column_label` | TEXT | nullable | exportable |
| `budget_gbp` | REAL | nullable | exportable |
| `basis_note` |  | nullable | exportable |

## `v_nhs_repeat_advertised_roles`

*view* — 0 rows.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `provider_key` | TEXT | nullable | exportable |
| `employer_name_raw` | TEXT | nullable | exportable |
| `job_title_normalised` |  | nullable | exportable |
| `advert_count` |  | nullable | exportable |
| `first_posted_date` |  | nullable | exportable |
| `last_posted_date` |  | nullable | exportable |
| `lowest_advertised` |  | nullable | exportable |
| `highest_advertised` |  | nullable | exportable |
| `distinct_salary_periods` |  | nullable | exportable |
| `job_references` |  | nullable | exportable |

## `v_provider_disclosure_gaps`

*view* — 24 rows.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `provider_key` | TEXT | nullable | exportable |
| `provider_name` | TEXT | nullable | exportable |
| `financial_year_end` | TEXT | nullable | exportable |
| `topic` | TEXT | nullable | exportable |
| `search_terms` | TEXT | nullable | exportable |
| `caveat` |  | nullable | exportable |

## `v_provider_viability`

*view* — 9 rows.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `provider_key` | TEXT | nullable | exportable |
| `company_number` | TEXT | nullable | exportable |
| `company_name` | TEXT | nullable | exportable |
| `company_status` | TEXT | nullable | exportable |
| `date_of_cessation` | TEXT | nullable | exportable |
| `match_basis` | TEXT | nullable | exportable |
| `insolvency_cases` |  | nullable | exportable |
| `insolvency_case_types` |  | nullable | exportable |
| `first_insolvency_date` |  | nullable | exportable |
| `last_insolvency_date` |  | nullable | exportable |
| `officers_active` |  | nullable | exportable |
| `officers_resigned` |  | nullable | exportable |
| `viability_flag` |  | nullable | exportable |

## `v_wage_per_employee`

*view* — 5 rows.

| Column | Type | Null | Export |
| --- | --- | --- | --- |
| `charity_number` | TEXT | nullable | exportable |
| `financial_year_end` | TEXT | nullable | exportable |
| `wages_and_salaries` | REAL | nullable | exportable |
| `average_employees` | REAL | nullable | exportable |
| `employees_basis` | TEXT | nullable | exportable |
| `average_employees_fte` | REAL | nullable | exportable |
| `indicative_wage_per_head` |  | nullable | exportable |
| `indicative_wage_per_fte` |  | nullable | exportable |
| `denominator_basis_note` |  | nullable | exportable |
| `numerator_scope_note` |  | nullable | exportable |
