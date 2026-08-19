You are conducting a public-source, provider-centred deep-research audit for
an England-wide substance-misuse sector evidence project used by a trade-union
pay campaign and its project maintainer.

The project’s standard is broad, source-backed coverage with explicit gaps.
It is not acceptable to fill a matrix by inference. A smaller evidence base
that can be defended line by line is more valuable than a larger one that
cannot.

Use the current date as the retrieval date. Optimise for the current position
and the previous five years. Go further back only when older evidence is
needed to establish a former name, legal identity, merger, successor,
subsidiary, contract continuity, or other historical relationship.

## A. Project context

The underlying project is a reproducible pipeline that collects public-domain
evidence about drug and alcohol treatment and recovery services across England.
It joins evidence to two separate entity spines:

- local authorities, identified primarily by ONS code; and
- tracked providers, identified by a `provider_key` only after an identity is
  supported by a verified identifier or authoritative cross-reference.

The project stores source URLs, retrieval/fetch dates, and hashes of archived
source bytes where its pipeline has collected the evidence. It treats
unparseable values as `NULL` plus a parse-failure record, and sends anything
requiring human judgement to a review queue. The project intentionally keeps
evidence layers separate and does not turn incomplete public data into a
composite score.

The repository, when available, is a Python/SQLite project with modules
`m00`–`m25`, a public evidence portal, and an operator review interface. The
research output is not authorised to modify production code, migrations,
configuration, the warehouse, or source data. If the external tool cannot
inspect the repository, it must say “repository state not independently
verified” rather than pretending that the embedded context is current.

### Module and source map

Use these module names when routing a finding. Do not propose a duplicate
module or table without first showing that the existing destination cannot
hold the evidence.

| Module | Main source | Evidence layer |
| --- | --- | --- |
| `m00_geography` | ONS Open Geography Portal | Local-authority spine, boundaries, reorganisations, successors |
| `m01_procurement` | Find a Tender and Contracts Finder | Contract notices, suppliers, values, direct awards, commissioners |
| `m02_tribunals` | GOV.UK employment tribunal decisions and EAT decisions | Published judgments involving providers, pseudonymised for export |
| `m03_charity_finance` | Charity Commission register and filed accounts | Charity identity, accounts, income, wages, employee counts, agency spend, pay bands |
| `m04_companies` | Companies House | Companies, former names, filings, group structure, PSC edges, insolvency, officer churn |
| `m05_cqc` | CQC public API | CQC provider identities, registered locations, ratings, inspection reports |
| `m06_workforce_census` | NHS Benchmarking Network / NHS England material | Sector-level vacancy, turnover, WTE, volunteer and contract-type metrics |
| `m07_ndtms` | OHID via GOV.UK | Published treatment statistics and local-authority tables |
| `m08_pfd_reports` | Courts and Tribunals Judiciary | Prevention of Future Deaths reports and workforce-related concerns |
| `m09_cdp_documents` | Local-authority websites | Combating Drugs Partnership document candidates requiring verification |
| `m10_committee_papers` | Council committee systems | Committee-paper candidates requiring verification |
| `m11_public_health_grant` | DHSC / GOV.UK | Public Health Grant allocations and drug/alcohol ring-fence material |
| `m12_fingertips` | OHID Fingertips | Local-authority treatment numbers, completions, waits and prevalence |
| `m13_la_budgets` | MHCLG and local-authority publications | Local-authority public-health budget information |
| `m14_annual_reports` | Provider annual reports, usually PDFs | Workforce narrative, financial narrative and disclosure gaps |
| `m15_foi` | mySociety register, WhatDoTheyKnow discovery and council disclosure logs | Discovery of public FOI requests and authoritative authority websites; not assumed response text |
| `m16_nhs_jobs` | NHS Jobs | Provider-related job adverts, advertised pay bands, contract type and closing dates |
| `m17_statutory_pay_rates` | GOV.UK rates page | National Minimum Wage and National Living Wage statutory floors by period and band |
| `m18_living_wage` | Living Wage Foundation register | Accreditation lookup outcomes for tracked provider names |
| `m19_data_gov_uk` | data.gov.uk CKAN | Dataset discovery metadata and resource URLs, not dataset contents |
| `m20_gender_pay_gap` | Gender Pay Gap service | Matched statutory filings; absence is a review item, never a zero |
| `m21_ons_ashe` | ONS developer API | Sector comparator median gross hourly pay by occupation/industry, UK and England |
| `m22_provider_pay_pages` | Tracked providers’ own websites | Provider-published career, reward and advertised-pay pages |
| `m23_sector_universe` | Reconciles already collected sources | Capture of tracked providers, companies, charities, CQC registrations, awardees and unmatched buyers |
| `m24_council_spend` | Council websites | Published spend-transparency rows, not contract totals |
| `m25_skills_for_care` | Skills for Care | Adult social-care workforce pay and turnover comparators |

### Embedded warehouse snapshot

The following is a read-only baseline extracted from the project warehouse on
2026-08-19. It is included because an external research tool may not have
database access. Treat it as a starting snapshot, not as live truth: use the
retrieval date of the research session for public-source findings, and label
any later drift explicitly. Do not invent replacement counts if the warehouse
cannot be inspected.

| Area | Baseline as at 2026-08-19 |
| --- | --- |
| Tracked providers | 13; target provider is `change_grow_live` |
| Provider identifiers | 11 total: 1 verified charity number, 2 unverified charity numbers, 4 unverified Companies House numbers, 4 unverified CQC provider IDs |
| Verified identifier | CGL charity number `1079327` only |
| Provider-linked Companies House rows | 4 seed-linked rows: CGL, Delphi Medical, Turning Point and Waythrough; 5 additional exact-name rows are `name_only_unconfirmed` with no provider key |
| Companies House evidence | 9 companies, 18 former-name rows, 1,027 filing rows, 0 insolvency cases, 0 PSC rows |
| Charity finance | 15 rows: CGL, Turning Point and Waythrough, one account for each financial year ending 2021-03-31 through 2025-03-31 |
| Annual reports | 15 rows: CGL, Turning Point and Waythrough, five financial years each |
| CQC | 4 provider rows and 384 locations: CGL 157, Delphi Medical 6, Turning Point 187, Waythrough 34; 580 location-report rows |
| Tribunals | 31 published tribunal cases, all matched to CGL, dated 2017-04-07 through 2025-07-08; 0 EAT cases |
| Workforce census | 68 metrics for census years 2022, 2023 and 2024; 0 verified and 0 rejected at the snapshot date |
| NHS Jobs | 35 adverts: CGL 13, Turning Point 4, Waythrough 6, With You 12; posted dates fall between 2026-07-10 and 2026-08-11 |
| Provider pay pages | 0 pages and 0 pay mentions |
| Living Wage | 0 accreditation rows |
| Gender pay gap | 0 filing rows |
| Sector universe | 0 rows |
| Council spend | 0 rows |
| Procurement | 98,636 contract rows: 97,435 Find a Tender rows dated 2021-01-01 to 2026-08-12 and 1,201 Contracts Finder rows dated 2026-04-20 to 2026-08-12; the contract table has no `provider_key`, so supplier attribution still requires the alias/identity workflow |
| Persisted job history | 0 `job_runs` rows in the snapshot; do not assume a missing run record means a module was never run |

The principal review queue contained 4,822 items: 4,304 pending and 518
approved. The largest categories were:

- 2,667 pending `m01_procurement / unmatched_buyer_name` items;
- 608 pending `m08_pfd_reports / pfd_concerns_in_pdf_only` items, alongside
  459 approved items of the same type;
- 493 pending `m04_companies / possible_group_company` items;
- 150 pending `m09_cdp_documents / authority_website_unknown` items;
- 102 pending `m15_foi / foi_response_text_not_retrievable` items;
- 97 pending `m10_committee_papers / committee_url_unknown` items;
- 33 pending unmatched NHS-job employer items;
- 25 pending unmatched NDTMS-area items;
- 10 pending unmapped tribunal-office-prefix items;
- 10 pending partially parsed charity-account items; and
- 10 pending possible-CQC-provider items.

The dominant parse-failure clusters were PFD reports with no usable `Ref :`
field (20), charity-account lines missing pension/agency/employee/redundancy
or total-staff-cost labels (7–8 each), PFD redaction safeguards, and budget
files whose monetary denomination could not be established. These are parser
or verification facts, not evidence that the underlying organisations or
events do not exist.

The current schema also contains a provider-research scaffold introduced by
migrations `0050_provider_research.sql` and
`0051_provider_research_candidate_keys.sql`:

- `provider_research_runs` records prompt version, actor/model, manifest hash,
  source bundle, status, item count and source count;
- `provider_research_items` is the candidate/review layer, with provider,
  entity, category, question, raw finding, interpretation, source, citation,
  identity basis, confidence, evidence status, destination, priority score,
  review states and stable candidate key;
- `provider_research_evidence` is the promoted evidence layer.

All three provider-research tables were empty in this baseline, and no
provider-research run had yet been recorded. The initial research should
therefore produce a clean first manifest and should not imply that prior
external research has already been completed.

### Important repository/data-model destinations

Where the repository is available, inspect and reuse these before proposing
new collection:

- identity: `providers`, `provider_identifiers`, `companies`,
  `company_previous_names`, `company_filings`, `company_psc` and entity-edge
  views;
- charity and annual-report evidence: `charity_financials`,
  `charity_accounts_documents`, `charity_accounts_extracts`,
  `provider_annual_reports`, `provider_report_passages`,
  `provider_report_disclosure`;
- CQC: `cqc_providers`, `cqc_locations`, `cqc_location_reports`;
- contracts and legal risk: `contracts`, `tribunal_cases`, `tribunal_documents`,
  `eat_cases`, `eat_documents`, `pfd_reports`, `pfd_recipients`,
  `pfd_provider_mentions`;
- pay and workforce: `nhs_job_adverts`, `nhs_job_advert_locations`,
  `provider_pay_pages`, `provider_pay_mentions`,
  `living_wage_accreditations`, `gender_pay_gap_reports`,
  `workforce_census_reports`, `workforce_census_metrics`,
  `ons_ashe_observations`;
- public-sector context: authority, procurement, FOI, CDP, committee, budget,
  grant, Fingertips, data.gov.uk, spend and sector-universe tables;
- human workflow: `review_queue`, `review_decisions`, `review_resolutions`,
  `parse_failures`, and existing verification notes.
- provider research workflow: `provider_research_runs` for run manifests,
  `provider_research_items` for candidates and review state, and
  `provider_research_evidence` for promoted evidence.

The project has a public/exportable boundary and restricted tables for personal
data. Do not recommend moving personal data into public evidence or exports.

## B. Exactly 13 providers to audit

The audit must contain one row for each provider key below. Never collapse two
rows simply because their current websites overlap or because one is a former
name of another.

| `provider_key` | Provider | Complication that must be resolved |
| --- | --- | --- |
| `change_grow_live` | Change Grow Live | Registered charity and trading subsidiaries may hold different contracts, accounts, employment relationships or legal claims. |
| `turning_point` | Turning Point | Resolve charity/company identities, subsidiaries, former names and similarly named bodies. |
| `with_you` | With You | Formerly Addaction; keep current and former-name evidence date-specific. |
| `addaction` | Addaction | Historical name of With You; preserve historical notices, judgments, accounts and contracts under this key. |
| `waythrough` | Waythrough | Formed through the Humankind/Richmond Fellowship merger chain; establish legal dates and successor relationships. |
| `humankind` | Humankind | Merged into Waythrough with Richmond Fellowship; distinguish predecessor evidence from post-merger brand/site evidence. |
| `richmond_fellowship` | Richmond Fellowship | Part of the Waythrough merger history; do not assume every Richmond Fellowship record concerns substance-misuse provision or one legal entity. |
| `via` | Via | Short and ambiguous trading name; very high false-positive risk in free text. |
| `westminster_drug_project` | Westminster Drug Project | Historical provider in the Via chain; preserve WDP evidence and establish the 2020 transition from authoritative sources. |
| `forward_trust` | Forward Trust | Resolve charity/company identities, former names, subsidiaries and service brands. |
| `phoenix_futures` | Phoenix Futures | Resolve current legal identity, identifiers, subsidiaries, former names and service-specific identities. |
| `delphi_medical` | Delphi Medical | Resolve legal identity, trading names, group relationships and similarly named organisations. |
| `inclusion` | Inclusion | Generic term with high false-positive risk; explicitly investigate the relationship with Midlands Partnership University NHS Foundation Trust. |

Build an identity ledger for every row containing canonical and source-used
names, charity number(s), Companies House number(s), CQC identity/registration,
employer or trading subsidiary, former names, parent/group relationships,
provider websites, effective dates, match basis, confidence and conflicts.

Important identity warnings:

- The project configuration and documentation must be reconciled, not blindly
  copied. In the current repository snapshot, `pipeline/providers.py` seeds a
  CGL charity identifier of `1079327`, while the data dictionary’s corporate
  example refers to `03861209` and trading subsidiary `06228752`. Treat this
  as an identity discrepancy requiring authoritative verification, not as
  three automatically confirmed facts.
- “Forward Trust Limited”, “Humankind Ltd”, “Via”, “Inclusion”, “CGL”, and
  other short or shared names can produce false matches. Name similarity is
  never sufficient.
- Richmond Fellowship and Humankind career pages may now be Waythrough’s after
  the October 2024 merger. Westminster Drug Project career pages may now be
  Via’s after the 2020 merger. Preserve the searched `provider_key` and explain
  the historical/current relationship.

## C. Known evidence limitations to recheck

These were identified as high-value asymmetries in the project brief. Treat
them as hypotheses to verify, not permanent facts:

- provider identifiers are sparse or unverified;
- Companies House coverage is limited;
- CQC coverage is limited;
- tribunal evidence is concentrated on Change Grow Live;
- NHS job evidence is limited;
- provider-pay, Living Wage and gender-pay tables are empty or sparse;
- large review-queue categories may not be cleared;
- many aliases may have few authoritative joins.

The following interpretation rules are material:

- CQC registration covers only some regulated services. It is not a complete
  map of community drug/alcohol provision; no CQC location does not prove no
  service exists.
- Workforce census figures are sector aggregates, not provider figures. They
  are not necessarily like-for-like across years, and “verified” means
  transcribed correctly, not that the metric is comparable or provider-
  attributable.
- Published tribunal judgments are a selected subset of disputes. Do not
  calculate claims-per-employee or a tribunal rate from them.
- An unlisted Living Wage lookup means no accredited employer was found under
  the checked name/window at that fetch; it does not prove the provider is not
  accredited or does not pay the Living Wage.
- A provider absent from a gender-pay file may be below the legal threshold,
  may not have filed, or may have been missed by matching. Absence is a review
  question, never a zero gap.
- NHS Jobs and provider-career pages show advertisements or published bands,
  not what existing employees actually earn. Keep annual and hourly figures as
  published; do not convert them without authorisation.
- ONS ASHE and Skills for Care are comparators, not provider-level pay data.
  Use side-by-side evidence only; do not calculate “X% below market” or similar
  ratios unless the project owner separately authorises that interpretation.
- A council spend row is not a contract total. Council files differ in period,
  threshold, layout and correction practice; do not sum them into a provider
  total without a separately approved method.
- The sector-universe table is a capture of what the pipeline encountered, not
  a census of the sector. It cannot support “we track N of the sector’s M”
  without stating its capture and match basis.
- A dissolved company is not automatically insolvent. Only an authoritative
  insolvency case supports an insolvency claim.
- PSC records are ownership edges about a company, not proof that a PSC belongs
  to a tracked provider group.
- A source or dataset absent from data.gov.uk is absent from that catalogue,
  not proof that it does not exist elsewhere.

## D. Non-negotiable research guardrails

1. Public sources only. Prefer primary and authoritative sources: Charity
   Commission, Companies House, CQC, GOV.UK, OHID, NHS, ONS, official court or
   tribunal sources, provider filings and official provider pages, procurement
   portals, commissioner documents and official council systems.
2. Never infer legal identity from name similarity. Require an authoritative
   identifier, an explicit official relationship, or a documented multi-source
   chain. Keep candidate matches separate from verified matches.
3. Never silently merge historical organisations. Preserve the source name,
   legal entity, date, relationship and confidence.
4. “No reliable public evidence found after a defined search” is the strongest
   permitted unsuccessful-search statement. It is not “the provider does not
   have/pay/file/operate X”.
5. Preserve direct URLs, publisher, source type, publication date, retrieval
   date, short quotation or exact page/table reference, and identity-match
   basis.
6. Mark blocked, inaccessible, robots-denied, JavaScript-only, paywalled,
   missing-document and rate-limited sources explicitly.
7. Do not collect unnecessary personal data. Do not publish claimant names,
   officer details, registered-manager details or named Responsible Persons.
8. Separate evidence, interpretation, recommendation and unresolved question.
9. Do not calculate prohibited ratios or cross-source metrics.
10. Recheck the existing repository/data model before proposing new collection.

## E. Research sequence

Follow this sequence in order.

### 1. Reconcile the project state

If the repository or a warehouse export is available, inspect it read-only.
Check the live provider configuration, schema, migrations, documentation,
tests, raw/archive references, exports, module run history, review queue and
parse failures. Recalculate counts and date ranges. Report any difference
between configuration, schema, documentation and data.

If the repository is not available, state that limitation at the beginning and
use the embedded module map and provider roster only as context. Do not invent
current row counts.

### 2. Ask high-value clarification questions

Before low-value or speculative web research, produce a ranked list of only
the questions that would change research scope, interpretation, prioritisation,
admissible claims or implementation destination.

For each question give:

- the decision requested;
- why it matters;
- affected providers and evidence layers;
- what research or implementation decision it unlocks;
- a recommended default;
- the consequence of another choice;
- whether safe research can continue before the answer.

Use a sensible default when the decision is not material. Do not ask merely
about formatting or presentation.

### 3. Resolve identity before enrichment

Search the relevant official registers and provider/commissioner documents for
charity numbers, Companies House numbers, former names, subsidiaries,
parent/group relationships, CQC identities, trading names, provider websites,
merger dates, successor/TUPE language and explicit commissioner links.

Treat each identity relationship as one of: verified, candidate, contradicted,
blocked, unresolved or not applicable. Date every relationship. Never use an
unverified identity to attribute pay, contracts, tribunal, finance or
regulatory evidence.

### 4. Research evidence gaps by value

Work in this priority order:

1. legal identity and entity relationships;
2. pay, recruitment, workforce, benefits and equality;
3. contracts, commissioners, service footprint and geography;
4. annual reports, financial health, regulation, tribunals, courts, coroners,
   insolvency and legal/risk evidence;
5. strategy, consultations, governance and disclosure gaps.

For each provider and category, record one of these outcomes:

- `verified_evidence_found`;
- `candidate_needs_human_confirmation`;
- `source_blocked_or_inaccessible`;
- `no_reliable_public_evidence_after_defined_search`;
- `not_applicable`;
- `already_covered_by_project`.

### 5. Define and document search boundaries

Before each category search, state the names/aliases/identifiers checked,
sources checked, date range, geography, search terms, search depth and
stopping rule. Search current sources first, then the previous five years,
then older history only where necessary.

For PDFs record title, publisher, publication date, direct URL and page.
For datasets record dataset/version, table/sheet, row/column or query. For
register/API results record profile/endpoint URL, identifier used, retrieval
date and match basis.

## F. Required evidence record

Every positive finding, candidate, blocked source, explicit no-evidence result
and not-applicable decision must use this structure:

```yaml
provider_key: ""
entity_or_subsidiary: ""
research_category: "identity|pay_workforce|contracts_footprint|finance_risk|strategy_governance"
specific_fact_or_unresolved_question: ""
value: ""
time_period: ""
source_publisher: ""
source_type: ""
direct_url: ""
publication_date: ""
retrieval_date: ""
quotation_or_exact_table_page_reference: ""
identity_match_basis: ""
confidence: "high|medium|low|unresolved"
evidence_status: "verified_evidence_found|candidate_needs_human_confirmation|source_blocked_or_inaccessible|no_reliable_public_evidence_after_defined_search|not_applicable|already_covered_by_project"
project_destination: "module/table/view/review_queue item or no existing destination"
recommended_next_action: ""
caveat_or_interpretation_limit: ""
```

For a candidate state the missing corroboration. For a blocked source state
the failure mode and attempted alternatives. For an unsuccessful search state
the exact search boundary and stopping rule. For an already-covered item cite
the existing repository table/module and its provenance.

## G. Prioritisation model

Score every missing, stale, blocked, unresolved or candidate item using:

`project impact × current evidence gap × downstream usefulness × source feasibility ÷ research effort`

Use a transparent 0–5 score for each factor. Show the component scores and
the result. Give extra weight or a tie-break flag to items that:

- affect multiple modules or providers;
- prevent entity misattribution;
- enable a defensible pay or workforce claim;
- clear a large review-queue category;
- distinguish current providers from historical/merged organisations;
- add evidence absent for most or all providers.

Separate repository implementation gaps from genuinely unavailable external
evidence. State dependencies, expected value, effort, owner/next actor and
the decision that would close the item.

## H. Required final output

Return the following sections in this order:

1. **Executive findings** — repository/context status, date window, highest-
   value findings, major asymmetries and interpretation risks.
2. **Ranked clarification questions** — with defaults and consequences.
3. **Method and source boundary** — retrieval date, search period, sources,
   queries/aliases, stopping rules and access limitations.
4. **13-provider completeness matrix** — one row for every provider key, with
   identity; pay/recruitment/workforce; contracts/footprint; finance/annual
   reports; regulation/legal risk; strategy/governance; status counts; and
   citations or evidence-record references.
5. **Identity and merger ledger** — all thirteen providers, with special
   treatment of CGL, Addaction–With You, Humankind–Richmond Fellowship–
   Waythrough, Westminster Drug Project–Via, and Inclusion–Midlands
   Partnership University NHS Foundation Trust.
6. **Provider-by-provider evidence dossier** — all high-value findings and
   controlled outcomes using the required record.
7. **Prioritised evidence backlog** — formula scores, rationale, dependencies,
   likely source, destination, effort and next action.
8. **Source register** — deduplicated citations with dates, direct URLs,
   quotations/page references, match basis and access status.
9. **Cross-provider patterns** — only evidence-supported patterns, with exact
   provider/date scope and limitations.
10. **Unresolved, blocked, stale and deliberately unanswerable questions** —
    separate lists, not one generic “gaps” section.
11. **Claims the project must not make** — especially unsupported negatives,
    provider attribution of sector aggregates, actual-pay claims from adverts,
    zero gender-pay interpretations, Living Wage conclusions from unlisted
    names, CQC-as-complete-map claims, and name-only merger/entity claims.
12. **Pilot** — run the method on Change Grow Live and one merger chain,
    preferably Humankind–Waythrough or Westminster Drug Project–Via. Show
    searches, identity decisions, evidence statuses, backlog items and what
    remains unresolved.

## I. Completion test

The audit is complete only when:

- all thirteen provider keys appear in the matrix;
- all identity and merger complications are explicit;
- clarification questions come before speculative research;
- repository gaps are separated from external-evidence gaps;
- each provider/category has evidence or a controlled outcome;
- the backlog is ranked, not an unstructured list of links;
- every finding maps to an existing module/table/review destination or clearly
  says that no destination exists;
- current, historical, merged, blocked, stale and not-applicable cases remain
  distinguishable;
- the Change Grow Live plus merger-chain pilot contains no invented evidence;
- each material conclusion has a direct citation, date, quotation/reference,
  identity basis, confidence and caveat;
- the final prohibited-claims list is explicit.

If evidence is incomplete, stop at the evidence boundary and state exactly
what remains unknown and what would resolve it.
