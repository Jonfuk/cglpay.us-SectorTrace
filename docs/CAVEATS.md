# Caveats

Limitations that must travel with any figure taken from this pipeline. Several
were found by running against the live sources, not by reading documentation.

If you publish a number from here, publish the caveat that belongs to it. The
export files carry the relevant ones in their headers and `.provenance.json`
companions for exactly this reason.

---

## Things you must not compute

**Do not compute a claims-per-employee rate, or any normalised tribunal
metric.** The judgment database captures only cases reaching a published
judgment. Settled, withdrawn and struck-out claims — the majority of all
claims — never appear. A rate built on these counts understates reality by an
unknown factor.

**Do not divide treatment statistics by workforce figures.** Caseload-per-
worker and similar ratios combine sources with different populations,
collection methods and reference periods. NDTMS/Fingertips and the workforce
census are kept in separate tables deliberately.

**Do not difference two workforce census years.** Provider participation
varies between rounds. The 2023 report states in terms that its data "should
not be used to infer that the workforce size overall" changed. **This survives
verification.** A metric with `verified = 1` has been read off its source page
by a named person and transcribed correctly, and that is the whole of what the
flag says; it is not a statement that the year is comparable with the year
before. Two verified figures are still two figures from two differently
participating samples.

**Do not attribute any census figure to a named provider.** The census
publishes sector aggregates only; there is no provider-level breakdown. The
schema has no provider column for this reason.

**Do not read `indicative_wage_per_head` as a salary.** See below.

**Do not annualise an advertised hourly rate, or convert between any two pay
periods.** `nhs_job_adverts.salary_period` records what the employer
published. The conversion depends on contracted hours nobody here knows, and
would put a figure in the warehouse that no source ever stated. Compare
hourly with hourly and annual with annual, or say plainly that you cannot.

**Do not read an advertised band as what staff are paid.** It is what an
employer is offering a new starter on a date. It is not a spine point, not a
pay scale, and not the pay of anyone currently in post.

**Do not compute a ratio between an advertised band and the statutory
floor.** "X% above the NLW" is arithmetic across two layers with different
reference periods and populations (Module 16's adverts, Module 17's rates).
The comparison is side-by-side only: state the floor and the band, and let
the reader do the arithmetic they can defend. The phase plan said this gate
applies to Module 17 in advance; it is written here because it governs
anyone using it.

---

## Per source

### Procurement (Modules 1)

- Contract values are **estimates at notice stage** and may differ from actual
  spend.
- Coverage is **incomplete before 24 February 2025** for below-threshold
  contracts, which were published on Contracts Finder rather than Find a
  Tender.
- `buyer_ons_code` is NULL where a free-text buyer name could not be matched
  deterministically. Those names are in `review_queue` — they are unmatched,
  not absent — and since Phase 18 (F1) they are also captured, name-only, in
  `sector_universe` as funders, where the systematic record replaces the
  item-by-item queue.
- **A `notice ↗` link may be constructed rather than published.**
  `notice_web_url` holds the address the release itself gave, and is NULL for
  84% of rows; for those the portal builds the link from the notice id under
  a mapping verified against every archived page, and labels it as built.
  Both reach the notice. Only the first is something the source stated, so
  cite `source_url` and the payload hash as provenance, never the link.

### Employment tribunals (Module 2)

- Only judgments are captured (see above).
- **`region` is NULL for every case.** No verified case-number-prefix to region
  mapping has been established, and guessing would attribute cases to the wrong
  region. `hearing_venue_raw` holds the "Heard at:" line from the judgment so
  the mapping can be built from a citable source.
- `outcome` is derived from judgment text, never structured metadata, and is
  always flagged low confidence.
- `provider_match_basis = 'component'` means the provider was named alongside
  co-respondents; the case is not solely about them.
- **Appeals are a different layer (G4, Phase 15).** EAT decisions live in
  `eat_cases` and are never combined with first-instance cases — a decision
  affirmed or overturned is a materially different datum, and the two layers
  do not add up to anything. `provider_side` says which party the provider
  was. `underlying_et_cases` lists the first-instance case numbers the
  judgment text cites; it is a list from the judgment, not a joined record.
- **An appeal that merely mentions a provider is not a provider case.** The
  GOV.UK search engine indexes judgment bodies, so a hit can name a provider
  without either party being one (the Attorney General's restriction-order
  judgments list the target's litigation history, provider cases included, in
  the body). Such hits are queued as `eat_body_mention_only` and never
  attributed.

### Charity finance (Module 3)

- **`indicative_wage_per_head` is not an average salary.** The denominator is a
  headcount average that counts part-time staff as whole people, so it reads
  lower than actual pay. The numerator is total wages for all grades including
  senior staff, before employer NI and pension costs.
- CGL publishes both headcount and FTE averages and they differ materially
  (2025: 5,715 vs 4,623 — about 24% on the resulting per-head figure). Both are
  exported; state which you are using.
- Register figures and accounts figures come from **different documents**. Both
  appear per year, but neither was derived from the other.
- Amounts are only stored where the accounts' denomination (£000 / £m) could be
  determined explicitly. Where it could not, amounts are NULL rather than
  assumed.

### Corporate structure (Module 4)

- **`match_basis = 'name_only_unconfirmed'` means the company matched a
  provider name exactly but has not been confirmed as the same legal entity.**
  A shared name is not a shared identity: the "FORWARD TRUST LIMITED" that
  matches by name is a dissolved company formerly called Bradford & Bingley
  Personal Finance, and one exact "HUMANKIND LTD" match was incorporated in
  2025. Only `match_basis = 'seed'` rows are linked to a provider.
- Officer counts are aggregates. Individual officers are personal data and are
  never exported.
- **Dissolved is not insolvent, and the two must never be reported as one.** A
  company can be struck off having paid everyone. Of the dissolved companies
  this pipeline holds, none has an insolvency case. `company_status` says how a
  company ended; only `company_insolvency_cases` says whether it failed, and
  `v_provider_viability.viability_flag` keeps the two apart on purpose —
  `dissolved_no_insolvency_case` is not a failure.
- **An insolvency case is not a story about pay, and the dates are the
  evidence.** `company_insolvency_case_dates` keeps Companies House's own date
  vocabulary because an administration ending and a company being wound up are
  different events. Do not collapse them into a single "date failed".
- **`restricted_officer_disqualifications` may be empty, and that is the
  expected result.** Acting as a director while disqualified is a criminal
  offence, so a serving director of a large registered charity appearing on
  that register would be extraordinary. An empty table is a checkable
  negative, not a check that was skipped.
- **Nothing reaches that table on a name alone.** Companies House publishes no
  link from an appointment to a disqualification, so the register is searched
  by name and a match is stored only where the month and year of birth agree
  too, or where the person numbers match. Register records that came back for
  a director's name without corroborating are in `review_queue` under
  `unconfirmed_disqualification_name_match` — **those are not disqualified
  people**, they are names that happen to coincide, and the review rows
  deliberately carry none of the register's identifying detail.
- **PSC rows are ownership edges, not provider links (G3, Phase 15).** A
  person or company with significant control is recorded as a fact about the
  company, and nothing in `company_psc` links anyone to a provider on a name.
  A corporate PSC's company number arrives asserted by Companies House and is
  authoritative as an identifier; whether it belongs to a provider's group is
  the entity graph's question (F1). Individual PSCs are named only in
  `restricted_company_psc`, with the month and year of birth the register
  publishes. A company whose PSC register is redacted answers with a
  statement: `psc_register_statement` review items mean the absence of rows
  is a redaction, not a finding.

### CQC (Module 5)

- **This is not a service map.** CQC registration covers only some service
  types — residential detoxification, inpatient and certain prescribing
  services. Most community drug and alcohol provision is not CQC-registered.
- Counting locations per authority does not measure service coverage, and
  absence of a location does not mean absence of a service.

### Workforce census (Module 6)

- Years are not like-for-like (see above).
- **Every metric is unverified until a human checks it.** `verified = 0` is the
  default, and the database refuses `verified = 1` without a
  `census_verifications` row behind it (migration `0033`). Checking happens on
  the Census tab of `/admin`, which shows each figure beside the archived text
  of the page it was parsed from; see
  [`verification/census_metrics.md`](verification/census_metrics.md). Filter on
  `verified` before publishing.
- **`verified` means transcribed correctly, and nothing else.** Not comparable,
  not attributable to a provider, not a statement about the census's own
  methodology. The two caveats above apply to a checked figure exactly as they
  apply to an unchecked one.
- **A verification can go stale.** It records the value, unit and the SHA-256
  of the report it was taken against. If a parser revision reads a different
  number off the same line, or the publisher reissues the PDF, the flag is
  still up over something nobody checked. `census_verify.stale()` finds those
  and the Census tab lists them at the top.
- `source_page` is a **zero-based** index into the extracted pages. A PDF
  viewer's page numbers are one higher.
- `workforce_segment = 'ambiguous'` means the source line named more than one
  segment and attribution was not guessed. A live 2022 line naming all three
  segments would otherwise have attributed an all-sectors total of 11,851 WTE
  to a segment that has 398.
- The 2023 report is typeset in two columns, which the PDF extractor
  interleaves; treat page-level attributions from that year with extra care.

### NDTMS published statistics (Module 7)

- **The local-authority content is thin.** Only 1 of 44 sheets in the 2024-25
  adult publication is local-authority level. Numbers in treatment, waiting
  times and successful completions are published nationally there — use Module
  12 (Fingertips) for those at authority level.
- **LA-level detail has been reduced over time:** adult publications carried 3
  local-authority sheets from 2018-19 through 2021-22, and 1 from 2022-23
  onward.
- About 5% of published area names do not resolve to a single ONS code and are
  left unmatched: national and regional aggregates, combined reporting areas
  such as "Cornwall & Isles of Scilly", and pre-reorganisation authorities.
- Statistical disclosure markers (`c`, `*`) are kept verbatim in `value_text`
  with `value` NULL. They do not mean zero.
- **The local-authority figures are modelled estimates, and the confidence
  interval is part of the figure.** Opiate and crack use, alcohol dependency
  and deaths-in-treatment are all published with 95% bounds. Do not quote a
  point estimate without them, and do not treat two authorities as different
  because their point estimates are: overlapping intervals have not shown a
  difference. The portal charts only the figures the source published an
  interval for — the rest of each sheet is denominators (mid-year
  populations) and rates, which share no axis with a count.
- Bounds are paired to an estimate only where the publication makes the
  pairing unambiguous. Where a sheet carries several point estimates and one
  unlabelled pair of bounds, they are left unattached rather than assigned:
  a confidence interval put on the wrong estimate is invented.

### PFD reports (Module 8)

- **About two thirds of reports (1,067 of 1,539) publish only a metadata stub
  online**, with the report itself as a PDF that is not linked in the published
  data. Those have no `matters_of_concern`. This is a source limitation, not a
  parsing failure; the affected reports are listed in `review_queue`.
- Being **sent** a report and being **named** in one are different facts,
  recorded as different mention types. Do not add them together.
- Concern terms indicate a word appears. They are a finding aid, not a
  characterisation of what the coroner found — read the report.
- Coroner areas are not local authorities and do not share their boundaries.

### CDP documents and committee papers (Modules 9, 10)

- **Coverage is bounded by the committee URL, which cannot be derived** —
  council hostnames are genuinely unpredictable. Three sources, in precedence
  order: the hand-verified registry in `pipeline/authority_websites.py`; a
  committee-system link on the council's own home page, where the target then
  answers a ModernGov signature path; and otherwise nothing, recorded as
  `committee_url_unknown`. Councils that link their committee system only from
  a second-level navigation page are not found, and are countable in
  `review_queue` rather than silently absent.
- `authority_committee_systems.url_source` says which of those it was.
  `homepage_link` is weaker evidence than `registry`: the council published the
  link and the target answered, but nobody has confirmed it is the right
  system for that authority.
- Nothing is promoted without human verification. A candidate is a URL that
  looked right, which is not the same as a document that is what it claims.
- `match_quality` is **ModernGov's own three-star ranking**, not a relevance
  score this pipeline computed. It ranks textual match against the search term,
  which is not the same as relevance to drug and alcohol services: an
  "excellent match" for `public health grant` is frequently a COVID grant
  report.
- **Only ModernGov is searchable.** CMIS and other committee systems are
  detected and then recorded as `committee_system_unsupported`; no adapter
  exists. Do not read the absence of candidates for a CMIS council as an
  absence of papers.
- **Audit terms are qualified, not bare.** "internal audit public health"
  rather than "internal audit", because the bare term returns the audit
  committee's entire history on every council. A review worklist nobody can
  triage is worse than not searching — the same lesson as m14 and m15.
  "public interest report" is searched unqualified because it is rare and
  always serious: the auditor is formally telling the public something.
- Search results are capped at three pages (30 hits) per term per council. A
  council with more matches than that is truncated, not exhausted.
- `matched_terms` lists every configured term that found the document, sorted.
  It is not a relevance score and the number of terms is not a strength
  measure — "drug and alcohol" and "treatment and recovery" both match most
  substance misuse papers, so two terms is the common case rather than a
  strong signal.
- A council behind bot protection answers 403. That is recorded as
  `committee_search_blocked`, and is not the same fact as
  `committee_search_no_matches`, which is ModernGov itself reporting no hits.
- Earlier versions of this file recorded that ModernGov's document search
  "needs a POST with viewstate". That was wrong — it was inferred from two
  failing GETs against the wrong endpoints rather than read off the form,
  which has no viewstate field. The search is a plain GET on
  `/ieSearchResults2.aspx`. Both faults produced the same symptom: a council
  that looked like it published nothing.

### Public Health Grant (Module 11)

- Later years are **indicative allocations**, not confirmed funding; see
  `allocation_status`.
- Figures are cash. No inflation adjustment is applied — applying one is a
  decision for whoever publishes it to document.
- `grant_type` is a normalised form of DHSC's own column headers, which change
  between years.

### Fingertips (Module 12)

- **LA-level alcohol waiting-time data stopped being published after 2022/23.**
  Indicators 91123 and 91182 were discontinued before the current geography and
  return nothing under it.
- England and region rows are retained as published comparators, flagged by
  `area_level`. The `v_fingertips_la_latest` view exposes local-authority rows
  only — do not read a national comparator as an authority's own value.
- **Unmet need is not published.** Fingertips publishes prevalence and numbers
  in treatment separately. Unmet need is conventionally the gap between them,
  but they use different estimation methods, populations and confidence
  intervals. This pipeline stores both as published and does not subtract one
  from the other.

### FOI evidence (Module 15)

- **Discovery only. This module cannot tell you what an authority said.** The
  WhatDoTheyKnow search feed returns a truncated, search-highlighted snippet
  per event and never a message body. Full text requires the JSON read API,
  which returns a Cloudflare 403 to automated clients and is not worked
  around. Snippets are stored in `foi_request_candidates.snippet` and never in
  `foi_requests.response_text`. **Do not quote a snippet as an authority's
  response** — it is a mid-sentence extract chosen by a search engine, not a
  statement.
- **A term match is a candidate, not evidence.** Nothing reaches
  `foi_requests` without a human confirming it, the same discipline as
  Modules 9 and 10.
- **Coverage is unknowable.** WhatDoTheyKnow holds only requests routed
  through that platform; most UK FOI requests never appear there. The feed is
  additionally capped at 4 pages per search term. Never present a count from
  this module as "the number of FOI requests about X".
- **The feed is fetched against mySociety's `robots.txt`,** under an explicit
  logged exception pending their answer to
  `docs/mysociety-access-request.md`. Rows collected this way carry
  `discovery_source = 'wdtk_feed_search'`. If they decline, remove the
  exception and revisit those rows.

### NHS Jobs advertised pay (Module 16)

- **Counts are a floor, never a total.** NHS Jobs carries NHS and some
  commissioned-provider adverts. A provider advertising only on its own site
  is invisible here. "CGL advertised 20 posts" means "at least 20, on this one
  board"; it can never mean "CGL had 20 vacancies".
- **An advertised band is not a pay scale.** It is an offer to a new starter
  on a date, not what anyone in post is paid, and not a spine point.
- **Searching by employer does not filter by employer, so a count from the
  search is not a measurement of anything.** Searching an employer that does
  not exist returns "659 jobs found" of unrelated adverts; searching "Richmond
  Fellowship" returns eighteen, all of them Kingston and Richmond NHS
  Foundation Trust. Every row in `nhs_job_adverts` was attributed on the
  advert's **own** employer field; the search that surfaced it is recorded in
  `searched_variant` and means nothing on its own. Employers the search
  returned and this pipeline could not attribute are in `review_queue` under
  `unmatched_nhs_jobs_employer` — they were **not** stored.
- **The role-keyword pass finds the same rows by the same rule.** Since the
  sustained crawl, every provider name is searched *and* the sector's role
  vocabulary is searched (recovery worker, substance misuse, ...). The
  keyword that surfaced an advert never decides whose it is — attribution is
  still the advert's own employer field — and `surfaced_by` records which
  pass first found each advert (`employer_search` or `role_search`), stable
  across runs. A role search that found nothing, or returned only other
  employers' adverts, is a normal outcome and is not queued — the
  `nhs_jobs_search_no_matches` and `unmatched_nhs_jobs_employer` items exist
  for employer searches and a keyword pass must not flood them.
- **`salary_basis = 'not_stated'` is not zero pay.** It means the employer
  published "Depends on experience" or similar. Exclude those adverts from a
  pay comparison; do not treat them as £0, and do not silently drop them from
  a denominator without saying so.
- **A single-figure advert is stored with `salary_min = salary_max`,** so a
  range query returns it. If you count adverts "with a range", filter on
  `salary_basis = 'range'` rather than on the two columns differing.
- **`v_nhs_repeat_advertised_roles` lists candidates, not findings.** The same
  title under two references is equally consistent with two genuine vacancies
  at two sites and with one post re-advertised after a failed round. The view
  cannot tell those apart and does not try. Read the adverts before calling
  anything a recruitment failure.
- **Coverage of comparators is uneven and that is not a finding about them.**
  A provider with no rows here may simply not advertise on NHS Jobs. The run
  records which of the two it was rather than leaving a silent zero:
  `nhs_jobs_search_no_matches` where the service itself said it found nothing,
  `nhs_jobs_search_matched_nothing` where it returned adverts that all belonged
  to somebody else. Neither is evidence that a provider is not recruiting.

### Statutory pay rates (Module 17)

- **The living wage band is identified by layout, not by law.** The page
  always leads each rates table with the living wage column, and that
  position is what sets `band_role = 'national_living_wage'`. The verbatim
  `band_label` ("25 and over", "23 and over", "21 and over") is the record of
  which band that was in each era, and the band set changing is itself the
  finding — do not normalise it away.
- **An unparseable amount is NULL plus a `parse_failures` row, and the cell is
  kept verbatim in `value_text`.** The table is the source's own spelling;
  never round, annualise or convert these rates — they are published as
  hourly figures and that is all they are.
- **The table holds every era the page publishes**, so "the current rate" is
  the row whose period contains today, not the newest row. The page's
  "current rates" block is the authoritative current state.

### Living Wage Foundation (Module 18)

- **`accredited = 0` means "no accredited employer under this name, as of
  this fetch"** — never "this provider is not accredited". Accreditation can
  sit under another legal name (a trading subsidiary, a holding company), and
  that is exactly the case the review queue is for. A count of accredited
  providers is a floor against the checked names, citable with its fetch
  date.
- **The check is a window, and truncation is said out loud.** The module
  reads the first 3 result pages of the register's own search; where the
  register's count line exceeds that window, a `living_wage_search_truncated`
  review item attaches to the provider, so "not found" is never silently
  "not in the checked window".
- **A near-miss name is not accreditation.** Exact normalised match only;
  anything else is an `unconfirmed_living_wage_name_match` review item.

### data.gov.uk catalogue (Module 19)

- **Discovery metadata, not data.** This module records that a dataset exists
  and where its resources live. It never fetches or stores dataset contents;
  a resource URL is a pointer to fetch with the dataset's own terms.
- **The catalogue is only what data.gov.uk harvests.** A dataset that exists
  but is not catalogued is invisible here. Absence from this table is absence
  from the index — never evidence that the data does not exist.
- **`matched_terms` is a record of discovery, not of relevance.** A term that
  found a dataset means the catalogue's own search matched it; the terms
  accumulate across runs and passes. `matched_ons_code` / `matched_provider_key`
  are set only by exact organisation-name matches, and most authorities will
  never have one — their catalogue sits under a differently-spelled
  organisation, which is the universe work's (F1's) reconciliation, not a
  gap in this table.
- **Licences vary per dataset.** The catalogue mixes OGL and non-OGL; the
  `license_*` columns carry each dataset's own published terms, and the OGL
  line on the module applies only to the metadata rows themselves.

### Gender pay gap reports (Module 20)

- **A provider absent from the file is not a zero gap.** The module stores
  only matched filings. A provider with no matched filing for a reporting
  year is a `gender_pay_gap_absence` review item: it may be out of scope
  (fewer than 250 staff on its snapshot date — the law's reach) or it may
  not have filed. The claim shape "of the tracked providers that must file"
  is built from the decided set, never from a count that treats absence as
  0%. Only the review decision can tell the two apart.
- **The figures are the employer's own submission, as submitted.** The
  service does not audit them, and neither does this pipeline. A blank cell
  is stored as NULL — a filing that left a cell blank is not a filing
  reporting 0%.
- **Attribution is company number first, exact name second.** A charity files
  under its own name with no company number; the exact-normalised name
  fallback is the m18 discipline — a near-miss name is not a filing. One
  provider can have several legal entities in the file; each matched filing
  is its own row, keyed by the service's employer id.
- **`ResponsiblePerson` is not collected.** It is the name of the person who
  confirmed the figures, and the schema has no column for it.
- **Only completed reporting years are read.** The service also lists the
  current, incomplete year ("the most recent year for which the reporting
  deadlines have passed" is its own wording); the module reads the newest
  completed years by the deadline rule (30 March / 4 April of the end year).

### ONS ASHE earnings (Module 21)

- **ASHE is a sample survey.** The figures are estimates from a 1% sample of
  PAYE jobs, and the API serves them as the survey published them, with no
  confidence intervals in this table. Every observation records the version
  it came from, and the API's ASHE versions lag the publication — at
  verification (2026-08-15) table 3 served version 7, released 2024-01-19.
  "The current year's ASHE" is the version the API serves, said out loud.
- **The comparison gate applies in advance: side-by-side only.** The module
  exists to sit beside `nhs_job_adverts` and `provider_pay_mentions` — "the
  sector's advertised band vs ASHE's median for that occupation" — and any
  ratio or "X% below the market" is the CAVEATS reading's decision, not a
  number this pipeline computes. Hourly stays with hourly; the measure is
  median gross hourly pay excluding overtime.
- **A suppressed cell is NULL, never zero.** ASHE suppresses some cells;
  they are stored with the observation text verbatim and a `parse_failures`
  row.
- **The observations endpoint was answering 502 at verification.** The shared
  client retries a 5xx and then fails the run loudly, so a run against the
  broken endpoint reports a failed module rather than a quiet empty table.

### Provider career and reward pages (Module 22)

- **The pages are the provider's own site, so attribution is exact** — there
  is no free-text matching, and `match_basis = 'site_owned'` on every
  mention. The registry (`pipeline/provider_websites.py`) is hand-verified
  and committed; the D-05 lesson applied to providers.
- **A page with no figures is an answer about that page, and a page that did
  not answer is a review item** (`pay_page_unavailable`,
  `pay_page_robots_disallowed`). Neither is evidence about what the provider
  pays — coverage is the same floor as Module 16's, written for websites: a
  provider may publish its pay on a jobs board or in PDFs this module does
  not read.
- **An advertised band here is what the provider's site offered a new
  starter on a date**, the same reading as Module 16's adverts. Not a spine
  point, not what anyone in post is paid.
- **Hourly and annual figures are kept as published.** `salary_period` says
  which is which; nothing converts between them (the CAVEATS rule that
  governs Module 16 applies to these mentions too).
- **Mergers are recorded, not smoothed over.** Richmond Fellowship's and
  Humankind's careers pages are Waythrough's (the October 2024 merger), and
  WDP's are Via's (the 2020 merger); the registry notes say which, and rows
  stay under the provider_key that searched its own site.

### Sector universe (Module 23)

- **The universe is a capture, never a census.** Every row was derived from
  what the pipeline already collects: awardees of notices matched by CPV
  prefix or keyword, the tracked providers' companies/charities/CQC
  registrations, and unmatched buyer names. An organisation that never
  appears in the corpus is not in the universe, and an organisation that
  appears is not thereby a substance misuse service — a care provider that
  won one in-scope lot is captured like any other. **Do not read a universe
  count as the size of the sector.**
- **`match_basis` says how a row entered the universe, and the rows you may
  call providers are the identified ones.** 'seed' and 'register' rows are
  identified by an identifier a source published. 'ppon' rows carry the
  buyer platform's supplier registration id — it identifies the
  registration, not the legal entity. 'name_only_unconfirmed' rows were
  captured from a name alone: sharing a name is not sharing an identity
  (m04's rule verbatim), and such a row is never linked to a tracked
  provider. A coverage statement ("we track N of the sector's ~M") must
  count identified rows for N and name its basis, or it is not the statement
  it looks like.
- **`provider_key` is set only through an identifier** in
  `provider_identifiers` (or a company row m04 seeded) — never through a
  name. This is the one rule the whole universe exists to enforce.
- **A funder is a buyer that matched no authority.** The funder rows include
  NHS bodies, police and other public bodies, suppliers that also
  commission, and names that are simply unidentifiable; they were captured
  from the name as published. A funder that is also an awardee appears under
  its awardee row.
- **The 3,160 `unmatched_buyer_name` and `possible_group_company` items
  were answered, not decided.** Phase 18 captured their names
  systematically; `resolve-answered` then marked each item answered with its
  evidence in `review_resolutions`, and `--reopen` undoes it. An answered
  `possible_group_company` is still NOT a confirmed group company — the
  evidence says so, and confirmation remains a human decision recorded on
  the universe row.
- **`notices_count` is one layer and nothing more.** It counts distinct
  notices naming the organisation, by ppon or exact normalised name. It may
  be used as a share of that layer; it is not a size measure of the
  organisation, and it is never combined with figures from any other layer.

### Council spend files (Module 24)

- **A published payment row is not a contract total.** Councils choose their
  own periods, thresholds, column layouts and correction practices. Rows are
  retained as published and are not summed across files, councils or periods.
- **A matched provider is an exact-name result only.** `provider_key` is set
  only when the payee exactly normalises to a tracked provider variant. A NULL
  key is an unresolved payee, not evidence that the payment was unrelated to
  the sector.
- **File coverage and parsed evidence are different.** An unreadable workbook
  remains in `council_spend_files` with its parse status and review item. It
  must not be reported as a council that published no spend or as a successful
  zero-row collection.
- **Amounts are never repaired or inferred.** `amount_text` is the council's
  value; `amount` is NULL when that text cannot be parsed. Period labels and
  descriptions are likewise kept verbatim rather than standardised into a
  comparison the source did not publish.

### Skills for Care estimates (Module 25)

- **These are modelled adult social care estimates, not provider evidence.**
  They describe the ASC-WDS workforce population and are contextual labour-
  market comparators; no figure may be attributed to a tracked provider.
- **The workbook's values are stored, not derived.** Annual pay, hourly pay,
  turnover and vacancy rates remain in their published units and categories.
  The pipeline does not convert between hourly and annual pay or calculate a
  change between years.
- **Published categories are not interchangeable.** Area level, sector,
  service and job role define the estimate. Aggregating across overlapping
  categories can double-count the same workforce and is not performed here.
- **An unreadable workbook is a known gap, not an empty result.** It remains in
  `skills_for_care_files` with its parse status, archived bytes, parse failure
  and review item.

---

## Personal data

Named individuals — tribunal claimants, deceased persons in coroners' reports,
company officers, CQC registered managers — are stored only in tables prefixed
`restricted_`. These are excluded from every export, and
`pipeline.exports.guard_columns()` raises if one is referenced.

Two things this required beyond the obvious:

- PFD report bodies name the deceased **throughout**, not only in a header
  field, so the full text is restricted rather than public.
- A coroner's concerns can name a **third party** who is a different report's
  deceased, which per-report redaction cannot catch. A second pass redacts
  every known name from `matters_of_concern` across the whole corpus.

Coroners' own names are public: they are public officials named on the face of
a published report.
