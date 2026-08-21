# Sources

Every source this pipeline collects from, with its licence, access
requirements and the rate limit applied. Unless stated otherwise, material is
published under the **Open Government Licence v3.0**, which requires
attribution.

Rate limits are the shared client's default of **one request per 2 seconds per
host** unless a per-host override is listed. `robots.txt` is checked before
every request via `urllib.robotparser`, and `Retry-After` is honoured on 429
and 503 responses.

The `User-Agent` on every request identifies the pipeline and includes the
contact email from `.env`, so any operator can reach the person running it.

**The licence rows below are also code.** Each module's licence is recorded in
[`pipeline/licences.py`](../pipeline/licences.py), which is what writes the
`# licence:` lines into every export header and names the terms in the
portal's provenance drawer. A new module's row here needs an entry there on
the same day — `tests/test_licences.py` fails for any registered module the
table does not name, because a source collected under terms nobody wrote down
is a source nothing may be published from. Where a licence is *not* a plain
open one — Module 6, Modules 9 and 10, Modules 14 to 16 — the entry carries
the reason next to it, so "Varies by authority" cannot be read as "probably
OGL".

---

## Module 0 — Geography

| | |
| --- | --- |
| Source | ONS Open Geography Portal (ArcGIS Online, org `ONSGeography_data`) |
| Endpoints | `https://www.arcgis.com/sharing/rest/search`, `.../content/items/{id}`, and the discovered FeatureServer query endpoints |
| Licence | OGL v3.0. Contains OS data © Crown copyright and database right |
| Key | None |
| Rate limit | Default |
| Notes | Layer IDs and field names are versioned per release (`CTYUA25CD` → `CTYUA26CD`), so they are discovered at run time rather than pinned |

## Module 1 — Procurement

| | |
| --- | --- |
| Sources | Find a Tender Service (FTS); Contracts Finder |
| Endpoints | `https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages`; `https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search` |
| Standard | OCDS 1.1.5 with UK extensions |
| Licence | OGL v3.0 |
| Key | None |
| Rate limit | FTS default; **Contracts Finder 5s** — it imposes a multi-minute block on repeat rate-limit violations, unlike FTS's simple `Retry-After` |
| Notice pages | `https://www.find-tender.service.gov.uk/Notice/{notice_id}`; `https://www.contractsfinder.service.gov.uk/Notice/{notice_guid}` |

### The notice's address is not the address it was fetched from

`contracts.source_url` is the OCDS API page a row was parsed from — a
paginated cursor. It is provenance and it is not a destination: following it
re-runs a page of a bulk feed, and once the window has moved it does not
return the same releases.

Two other columns answer "where is this notice?", and they are different
claims:

- **`contracts.notice_web_url`** — the address the release itself published,
  taken from `contracts[].documents[].url`, `awards[].documents[].url` or
  `tender.documents[].url`, and only when that URL is exactly this notice's
  page on the publishing service's own host. NULL where the release named
  none, which is the ordinary case: 15,736 of 98,636 collected rows carry one
  (98% of Contracts Finder rows, 15% of Find a Tender).
- **A constructed link**, computed at read time by
  [`pipeline/notice_urls.py`](../pipeline/notice_urls.py) and never stored.
  Find a Tender's notice id is used unchanged; a Contracts Finder release id
  is the notice GUID with a release sequence appended (`{guid}-{sequence}`)
  and the page is the GUID alone.

The mapping was verified against every OCDS page in `data/raw/` rather than
assumed: of 117,365 published notice URLs, 117,317 follow it exactly. The
exceptions are all `/Notice/Attachment/…`, `/Notice/SupplierAttachment/…`, or
a release citing a *different* notice — none of which is this row's notice
page, and all of which are excluded.

The portal shows both links (`notice ↗` and `api ↗`) and marks a constructed
one as constructed wherever it appears.

## Module 2 — Employment tribunals

| | |
| --- | --- |
| Source | GOV.UK Search API, formats `employment_tribunal_decision` and `employment_appeal_tribunal_decision` |
| Endpoints | `https://www.gov.uk/api/search.json`, `https://www.gov.uk/api/content/{path}` |
| Licence | OGL v3.0 |
| Key | None |
| Rate limit | Default |
| Personal data | Decision titles, URL slugs and indexed text name the parties. Names are stored only in `restricted_tribunal_parties` and `restricted_eat_parties` |
| Also collects | **Employment Appeal Tribunal decisions** (G4, Phase 15) — the appellate layer, in its own tables (`eat_cases`, `eat_documents`). An appeal is a different layer from the judgment it reviews and is never combined with it. Both sides of the title are matched because either party may be a provider; a decision that merely *mentions* a provider in its body is queued as `eat_body_mention_only` and never attributed |

## Module 3 — Charity finance

| | |
| --- | --- |
| Sources | Charity Commission register API; filed accounts PDFs from the public register |
| Endpoints | `https://api.charitycommission.gov.uk/register/api/...`; `https://register-of-charities.charitycommission.gov.uk/...` |
| Licence | OGL v3.0 |
| Key | **`CHARITY_COMMISSION_API_KEY`** — free registration. Sent as `Ocp-Apim-Subscription-Key` |
| Rate limit | Default |
| Notes | The API does not expose staff costs, employee numbers or pay bands; those come from the filed accounts PDFs |

## Module 4 — Corporate structure

| | |
| --- | --- |
| Source | Companies House public API |
| Endpoint | `https://api.company-information.service.gov.uk` |
| Licence | OGL v3.0 |
| Key | **`COMPANIES_HOUSE_API_KEY`** — free registration. HTTP basic auth, key as username |
| Rate limit | Default (the API's own documented limit is 600 requests / 5 minutes) |
| Personal data | Officers are named. Stored only in `restricted_company_officers` |
| Also collects | **Insolvency cases** (`/company/{n}/insolvency`), **People with Significant Control** (`/company/{n}/persons-with-significant-control`, Phase 15/G3), and a **disqualified-director check** (`/search/disqualified-officers`) — see below |

**Insolvency.** Fetched only where the company profile publishes
`links.insolvency` or `has_insolvency_history`, so a company with no case
costs no request. A company with no case answers 404, which is "no case
published" and not a failure.

Not hypothetical for this sector: **LIFELINE PROJECT (01842240)** — large
enough to appear as a co-respondent alongside CGL in employment tribunal
judgments — went into administration on 2017-06-02, was wound up on
2018-06-07 and dissolved on 2024-01-25.

**Dissolved is not insolvent.** Both dissolved companies this pipeline holds
have no insolvency case at all: a company can be struck off having paid
everyone. `company_status` says how a company ended; only
`company_insolvency_cases` says whether it failed.

**Disqualified directors.** Companies House publishes no link from an
appointment to a disqualification, so the only route is a name search of the
register — the exact kind of match this module already refuses to trust, and
the one where being wrong is worst: it would record that a named person had
been banned from directing companies. So the sweep covers **serving directors
only**, and a row is stored only where the register corroborates on the
published **month and year of birth** as well as the name, or where the person
numbers match outright. Anything weaker is a review item. Expect the table to
be empty — acting while disqualified is a criminal offence, so this is a
checkable negative, not a discovery engine.

**People with Significant Control.** The ownership edges for the entity
graph — who owns or controls the companies that hold the sector's contracts.
Fetched per target company on the same key and client. A corporate PSC's own
company number arrives asserted by Companies House and is stored on the
public row; individual PSCs are named, and the name (and the month-and-year
of birth Companies House publishes with it) lives only in
`restricted_company_psc`. A company whose register is redacted answers with a
statement rather than a list — recorded as a review item, because the absence
of PSCs is then a redaction, not a finding.

## Module 5 — CQC

| | |
| --- | --- |
| Source | CQC public API, plus the bulk care-directory CSV (`pipeline/cqc_bulk.py`, shared with Module 26) for provider discovery |
| Endpoint | `https://api.service.cqc.org.uk/public/v1` |
| Licence | OGL v3.0 |
| Key | **`CQC_SUBSCRIPTION_KEY`** — free registration. Sent as `Ocp-Apim-Subscription-Key`. Not sent to the bulk-export host, which needs no key |
| Rate limit | Default |
| Personal data | Registered managers are named inside each location's regulated activities. Stored only in `restricted_cqc_location_contacts` |
| Notes | Provider discovery reads the bulk CSV rather than paging the API's ~64k-row `/providers` index; falls back to that paging if the bulk export is unreachable or reshaped. Resumes at provider granularity: `module_cursors` records which tracked providers this pass has fully walked, so an interrupted run picks up past them rather than re-walking the target provider from the start — cleared once the pass reaches the end of the matched list, so the next invocation still does the full refresh this module always promises (`supports_since=False`). See the module docstring. |

## Module 6 — Workforce census

| | |
| --- | --- |
| Source | NHS Benchmarking Network for NHS England; the 2022 edition is hosted on the former HEE site |
| Endpoints | `https://www.wfbenchmarking.nhs.uk/drug-and-alcohol-treatment-and-recovery`, `.../national-reports-archive`, plus the report PDFs |
| Licence | Not OGL. NHS England / NHS Benchmarking Network content — check terms before republishing figures |
| Key | None |
| Rate limit | Default |

## Module 7 — NDTMS published statistics

| | |
| --- | --- |
| Source | OHID, published on GOV.UK |
| Endpoints | `https://www.gov.uk/api/search.json`, `https://www.gov.uk/api/content/{path}`, and the attached ODS files |
| Licence | OGL v3.0 |
| Key | None |
| Rate limit | Default |

## Module 8 — Prevention of Future Deaths reports

| | |
| --- | --- |
| Source | Courts and Tribunals Judiciary |
| Endpoint | `https://www.judiciary.uk/wp-json/wp/v2/pfd` (WordPress REST) |
| Licence | OGL v3.0 |
| Key | None |
| Rate limit | Default. `robots.txt` is `Disallow:` (allow all) |
| Personal data | Every report names the deceased, throughout the body as well as in the header. Names and full body text are restricted |

## Modules 9 and 10 — CDP documents and committee papers

| | |
| --- | --- |
| Sources | Individual local authority websites and committee management systems (ModernGov, CMIS, Democracy) |
| Licence | Varies by authority; most publish under OGL v3.0 but this is not guaranteed — check per document before republishing |
| Key | None |
| Rate limit | Default, per host |
| Endpoints | ModernGov document search: `{committee_url}/ieSearchResults2.aspx?SS={term}&DT=3&ADV=0&CA=false&SB=true&PG={n}` — a plain GET; the parameters are the search form's own hidden defaults |
| Coverage | Bounded by `pipeline/authority_websites.py`, which holds only entries verified by request, plus committee-system links a council publishes on its own home page where the target then answers a ModernGov signature path. Authorities with neither are queued in `review_queue`. Only ModernGov is searchable — CMIS and others are detected and recorded as unsupported |
| Notes | Verified live against Kent, Kirklees and Darlington on 2026-08-11. `/mgSearchResults.aspx` and `/mgDocumentSearch.aspx` are **not** the document search and 302 to `mgError.aspx`. Capped at 3 result pages per term per council |

## Module 11 — Public Health Grant

| | |
| --- | --- |
| Source | DHSC, published on GOV.UK |
| Endpoints | `https://www.gov.uk/api/search.json`, `https://www.gov.uk/api/content/{path}`, and the attached ODS allocations files |
| Licence | OGL v3.0 |
| Key | None |
| Rate limit | Default |

## Module 12 — OHID Fingertips

| | |
| --- | --- |
| Source | OHID Fingertips |
| Endpoints | `https://fingertips.phe.org.uk/api/all_data/csv/by_indicator_id`, `.../indicator_metadata/by_indicator_id` |
| Licence | OGL v3.0 |
| Key | None |
| Rate limit | Default |
| Notes | Area types are versioned by local government reorganisation period; indicator IDs are pinned in `pipeline/fingertips_indicators.py` so the collected set cannot change silently |

## Module 13 — Local authority revenue budgets

| | |
| --- | --- |
| Source | MHCLG local authority revenue expenditure and financing, published on GOV.UK |
| Endpoints | `https://www.gov.uk/api/search.json`, `https://www.gov.uk/api/content/{path}`, and the attached ODS budget returns |
| Licence | OGL v3.0 |
| Key | None |
| Rate limit | Default |
| Notes | Budgeted, not outturn. Line codes and column labels are stored as published rather than mapped to a normalised chart of accounts |

## Module 14 — Provider annual reports

| | |
| --- | --- |
| Source | The accounts PDFs Module 3 has already downloaded from the Charity Commission — **no new fetching** |
| Licence | The charity's own copyright; filed accounts are a public record. Passages are extracted for evidence, not republished wholesale |
| Key | None |
| Rate limit | N/A — reads the local raw archive |
| Notes | Records disclosure gaps as facts: a topic with no matching passage is recorded as not disclosed, which is a finding about the report rather than a failure to find one |

## Module 15 — FOI evidence

| | |
| --- | --- |
| Sources | mySociety's published authority register (WhatDoTheyKnow); WhatDoTheyKnow search feed; council disclosure logs |
| Endpoints | `/body/all-authorities.csv`; `/feed/search/<query>.json`; per-council disclosure log pages |
| Licence | mySociety data under CC BY-SA; FOI responses generally OGL v3.0; council disclosure logs vary |
| Key | None |
| Rate limit | Default (2s/host), conditional requests |
| Notes | **Publicly published FOI evidence, with discovery first and human promotion required.** The feed returns a truncated search snippet per event and never a message body. With provider permission, one canonical `/request/<slug>` page may be retrieved during human promotion through the m15-only Bright Data Web Unlocker or ZenRows setting; both are disabled by default. The feed is fetched under an explicit, logged exception to mySociety's robots.txt (`Settings.robots_exceptions`) — see `docs/mysociety-access-request.md` |

## Module 16 — NHS Jobs advertised pay

| | |
| --- | --- |
| Source | NHS Jobs candidate search |
| Endpoint | `https://www.jobs.nhs.uk/candidate/search/results?employer=…&page=N` and `?keyword=…&page=N` (the sustained crawl's role-keyword pass) |
| Licence | Crown copyright on the service; the advert content is the employer's |
| Key | None |
| Rate limit | Default (2s/host), conditional requests, max 5 result pages per search |
| robots.txt | Answers with an **HTML page, not a rules file** — a "Service Domain Information" shell containing no user-agent, allow or disallow directives. Verified rather than assumed, and asserted in the tests. Re-check it if the service is redesigned |
| Notes | The only **direct** pay evidence in this pipeline. Read the two limits below before using any figure from it |

**Searching by employer does not filter by employer.** Measured against the
live service:

| Query | Result |
| --- | --- |
| `employer=Change Grow Live` | "20 jobs found"; page 1 all CGL, page 2 drifting into other employers |
| `employer=Turning Point` | "5 jobs found", one of them **West Point Medical Centre** |
| `employer=Richmond Fellowship` | "18 jobs found", **every one** Kingston and Richmond NHS Foundation Trust |
| `employer=Zzqxwv Nonexistent Employer Ltd` | **"659 jobs found"** — Employ-Ability, NHS Employers, Nimbuscare and others |
| `keyword=zzqxwv nonexistent role` | "11537 jobs found"; `skipPhraseSuggester=true` changes nothing |
| `employer=Addaction` | **"No result found for Addaction"** — a distinct page with its own markup |

So a non-empty result set says nothing about who was searched for. An advert
is attributed on **its own employer field**, never on the search that surfaced
it, and adverts whose employer matches no known provider are discarded and
counted (`review_queue`, `unmatched_nhs_jobs_employer`).

The last row matters as much as the rest: the service *does* have an empty
answer and states it explicitly, so "searched and found nothing"
(`nhs_jobs_search_no_matches`) stays distinguishable from "could not read the
page" (`nhs_jobs_results_unrecognised`). Paging stops as soon as a page
attributes nothing, because results are relevance-ranked and everything past
that point is the fallback.

Coverage is a **floor, never a total.** NHS Jobs carries NHS and some
commissioned-provider adverts; a provider advertising only on its own site is
invisible here.

## Module 17 — National Minimum Wage and National Living Wage rates

| | |
| --- | --- |
| Source | The GOV.UK rates page — **deliberately not an API**: the government publishes no machine-readable rates endpoint; the page is the publication |
| Endpoint | `https://www.gov.uk/api/content/national-minimum-wage-rates` (the content API serves the page's own HTML) |
| Licence | OGL v3.0 |
| Key | None |
| Rate limit | Default |
| Notes | One row per (period, band), the band labels verbatim because the living-wage band itself changes between eras ("25 and over" → "23 and over" → "21 and over"). The living wage band is identified by the page's own layout (it always leads each table). The gate applies in advance: a floor comparison is **side-by-side**, and any ratio ("X% above the NLW") is a CAVEATS decision, not this module's |

## Module 18 — Living Wage Foundation registrations

| | |
| --- | --- |
| Source | Living Wage Foundation accredited-employer list (Drupal views page) |
| Endpoint | `https://www.livingwage.org.uk/accredited-living-wage-employers-list?search_api_fulltext={name}` |
| Licence | Not OGL. The list is factual data published by a charity; check the foundation's terms before republishing it in bulk |
| Key | None |
| Rate limit | Default (robots.txt checked; the list path is allowed) |
| Notes | One lookup per provider, its canonical name variant. Exact normalised name match only — a near miss is a review item, never a stored accreditation. The search window is the first 3 result pages; where the register's own count exceeds the window, a review item says so. `accredited = 0` is "no accredited employer under this name as of this fetch", not "this employer is not accredited anywhere" — accreditation could sit under another legal name |

## Module 19 — data.gov.uk CKAN catalogue

| | |
| --- | --- |
| Source | data.gov.uk CKAN API (the central open-data catalogue) |
| Endpoints | `https://www.data.gov.uk/api/3/action/package_search`, `.../organization_list` |
| Licence | OGL v3.0 for the catalogue metadata this module records; each dataset's own terms travel on its row (`license_*`), because the catalogue mixes OGL and non-OGL |
| Key | None |
| Rate limit | Default |
| Notes | Discovery metadata — what datasets exist and where their resources live — not the data itself. Two passes: the substance-misuse keyword vocabulary, and exact-normalised organisation-name matches against the authorities and providers tables. A query is read to the catalogue's own count, capped at 300 datasets; hitting the cap raises a review item. The catalogue is only what data.gov.uk harvests: absence from this table is absence from the index, never absence of the data |

## Module 20 — Gender pay gap reports

| | |
| --- | --- |
| Source | Gender Pay Gap service (GOV.UK) |
| Endpoints | `https://gender-pay-gap.service.gov.uk/viewing/download` (the year list), `https://gender-pay-gap.service.gov.uk/viewing/download-data/{year}` (one bulk CSV per reporting year) |
| Licence | OGL v3.0 (service content; the underlying data is statutory disclosure) |
| Key | None |
| Rate limit | Default |
| Notes | A mandatory annual filing by employers with 250+ staff. One row per **matched** filing: company number first (the identifiers m04 discovered), exact-normalised name second — never a near-miss. A provider with no matched filing for a year is a `gender_pay_gap_absence` review item naming what was searched, because it may be out of scope (fewer than 250 staff) or may not have filed — never a stored zero. `ResponsiblePerson` (the name of the person who confirmed the figures) is deliberately not collected. Only completed reporting years are read (deadlines: 30 March / 4 April of the end year) |

## Module 21 — ONS ASHE earnings

| | |
| --- | --- |
| Source | ONS developer API (the Data Explorer; `api.beta.ons.gov.uk/v1`) |
| Endpoints | `/datasets/ashe-tables-3` (occupation by two-digit SOC), `/datasets/ashe-table-5` (industry by two-digit SIC), each with its time-series edition, dimension options and observations |
| Licence | OGL v3.0 |
| Key | None |
| Rate limit | Default |
| Notes | Median gross hourly pay **excluding overtime**, all employees, all working patterns, UK and England, every published tax year of the version the API serves. Pinned dimension codes are queried against the version's own options (a code the version no longer serves is a review item); labels come from the options response. **Known access shape:** the observations endpoint answered 502 for every ASHE query at verification on 2026-08-15 (a cpih01 query answered), and the API's ASHE versions lag the publication — so this module currently fails loudly against the live API rather than collecting nothing quietly. The phase gate applies: an ASHE-versus-adverts statement is **side-by-side**, never a ratio |

## Module 22 — Provider career and reward pages

| | |
| --- | --- |
| Source | The tracked providers' own websites, from the hand-verified registry in `pipeline/provider_websites.py` (the D-05 lesson applied to providers: answers live in a committed file) |
| Endpoints | The registered pages, plus same-host links whose anchor or URL carries the pay/careers vocabulary, one hop deep, max 10 followed pages per provider |
| Licence | Not OGL — the provider's own copyright. Passages are held as evidence, not republished wholesale |
| Key | None |
| Rate limit | Default; a robots.txt disallow is recorded as a review item |
| Notes | Pay figures on career and reward pages — advertised bands, rewards pages, listed rates. Attribution is exact by construction: the page is the provider's own site (`match_basis = 'site_owned'`). A page that answered with no figures is recorded with `pay_mentions = 0` — an answer about that page; a page that did not answer is a review item, never a zero row. Coverage is a floor, the same caveat as Module 16: a provider whose site publishes no figures here may publish them on a jobs board or in PDFs this module does not read |

## Module 23 — The sector universe (Phase 18, F1)

| | |
| --- | --- |
| Source | **None — fetches nothing.** A reconciliation over what the other modules collected: `contracts` awardees, `charity_financials`, `companies`, `cqc_providers`, the tracked `providers`, and the `review_queue` items m01 and m04 filed |
| Licence | OGL v3.0 — every row is derived from sources that are themselves OGL v3.0 (the universe invents no data of its own) |
| Key | None |
| Rate limit | None — no requests are made |
| Notes | Reconstructs the sector population: the tracked providers, the companies/charities/CQC registrations collected about them, every distinct awardee in the notices, and every buyer no authority matched (captured as funders). `match_basis` keeps m04's discipline exactly — 'seed' (config or verified authoritative cross-reference), 'register' (source-published identifier), 'ppon' (the buyer platform's supplier registration id, never a legal-entity claim), 'name_only_unconfirmed' (captured from a name; never linked to a provider). The universe is a capture of who shows up in the corpus, never a complete list of the sector — the notices were matched by CPV prefix and keyword, so one-off awardees of in-scope lots appear. Capturing an `unmatched_buyer_name`, `possible_group_company`, or `unconfirmed_name_match` creates an unresolved lead; it does not answer the identity question, so the review item remains pending for a person. |

## Module 24 — Council spend-transparency files (Phase 19, G5)

| | |
| --- | --- |
| Source | Each council's own website — **deliberately not an API**: there is no central service for £500+ spend files, so the module discovers them on the authority's own domain (B4's full website coverage is the prerequisite) |
| Endpoints | Likely transparency paths per authority (e.g. `/transparency`, `/open-data`, `/finance-and-governance`), then the data-file links those pages carry (CSV, XLSX, ODS) |
| Licence | Varies by authority — same rule as Modules 9 and 10: most councils publish under OGL v3.0 and none of them is guaranteed to. Check the individual file before republishing it |
| Key | None |
| Rate limit | Default (2s/host), conditional requests, at most 3 files per authority |
| Notes | Actual money flows: "council X paid provider Y £Z in [period]". Line-item quality varies council to council, so the NULL discipline does the work: `payee` and `amount_text` are verbatim, `amount` is parsed beside them (NULL where the council's formatting could not be read, never a zero), and an unreadable file is a `parse_failures` row plus a review item — never a silent skip. `provider_key` is set only by an exact-normalised payee match against the tracked providers' own name variants (m04's discipline); name reconciliation at scale is the universe work's (m23). No arithmetic across rows or sources: no totals, no share-of-spend, no comparison against contracts |

## Module 25 — Skills for Care workforce intelligence (Phase 19, G2)

| | |
| --- | --- |
| Source | Skills for Care ASC-WDS workforce estimates, published as Excel data downloads |
| Endpoints | The Data downloads page (`.../workforceintelligence/About-our-data/Data-downloads.aspx`); five workbooks under `.../resources/Our-data/` |
| Licence | OGL v3.0 for the ASC-WDS data per the data.gov.uk catalogue entry (verified 2026-08-16); the publisher's own pages carry a site-wide copyright line. Official statistics under the Code of Practice for Statistics |
| Key | None |
| Rate limit | Default (2s/host), conditional requests |
| robots.txt | No directives for these paths (verified by request 2026-08-16) |
| Notes | Adult social care pay and headcount benchmarks — the contextual comparator for the sector's workforce market, on the same side-by-side footing as Module 21 (ASHE). Three current-year workbooks (regional, local-area, ICB) share a data-sheet shape and are parsed: `fte_annual_pay`, `hourly_pay`, `turnover_rate` and `vacancy_rate` per (area, sector, service, job role), stored as the workbook published them (its `*` suppression marker is NULL, not a failure). The statistical appendix (report tables) and the trended workbook (the change-over-time series F-05 declined history for) are fetched and archived but their shapes are not parsed — recorded per file, never silently skipped. Figures are modelled estimates, rounded, for the whole adult social care workforce — a comparator, never an attribution to a tracked provider |

## Module 26 — CQC bulk-export cross-check

| | |
| --- | --- |
| Source | CQC bulk data downloads (care directory CSV, weekly; ratings export ODS, monthly) plus, only when the API supplied no rating at all, the location's own page on cqc.org.uk |
| Endpoints | `https://www.cqc.org.uk/about-us/transparency/using-cqc-data` (landing page, scraped for the current dated file links), then the linked `*_CQC_directory.csv` and `*_Latest_ratings.ods`; `https://www.cqc.org.uk/location/{id}` per location being backfilled |
| Licence | OGL v3.0 |
| Key | None — a different host to Module 5's API, and no subscription key |
| Rate limit | Default (2s/host), conditional requests |
| Notes | Cross-checks what `m05_cqc`'s per-location API walk produced against CQC's own bulk snapshot, and flags a gap to `review_queue` (`cqc_directory_location_missing`, `cqc_directory_rating_stale`) for a person to act on. The one exception, confirmed for real (location `1-12790083928`, "Aspire Havering"): when the API returns no rating for a location at all — not older, nothing — re-running `m05_cqc` does not fix that, so this module backfills `cqc_locations.bulk_overall_rating`/`bulk_overall_rating_date` (migration 0055, kept separate from the API's own `overall_rating`/`overall_rating_date`) and, since the same silence extends to `cqc_location_reports`, scrapes the location's own page for its published report link and date (`_extract_report_info` — plain server-rendered HTML, no JavaScript execution needed, confirmed against two differently-shaped real pages). Both are cleared once the API supplies its own data, rather than left sitting beside a real value with nothing marking them stale. The ratings ODS is read by hand (stdlib `zipfile` + `xml.etree.iterparse`) rather than with odfpy (Module 13's ODS library): its `content.xml` runs past a gigabyte uncompressed, and odfpy's full-DOM load was observed still running past a gigabyte of resident memory without finishing. The streamed reader completes a pass over ~320k rows in about a minute with flat memory use — see the module docstring for the row-alignment trap ODS's repeated-cell compression sets for a naive version of this |

---

## Viability checks

Probed live on 2026-08-11 with the pipeline's own User-Agent, one request
each. Reachability is not the same as buildability — the notes say which.

### NHS Jobs — VIABLE, highest value of the candidates — **BUILT, see Module 16**

Advertised pay bands are **direct pay evidence**, not a proxy and not a
composite — the only candidate of which that is true. Vacancy duration and
re-advertisement are the empirical form of "we cannot recruit at this rate",
which the annual workforce census cannot show.

Built as Module 16 on 2026-08-11. Building it turned up one thing the
viability probe had not: searching by employer does not filter by employer,
and there is no empty result set at all. That is written up under Module 16
above, and it changed the design — attribution is on the advert's own employer
field rather than on the search.

### HSE enforcement — VIABLE

| | |
| --- | --- |
| Endpoints | `https://resources.hse.gov.uk/notices/`, `.../convictions/` |
| Result | Both 200, server-rendered HTML |
| robots.txt | `resources.hse.gov.uk` serves none (404) — no directives. Note `www.hse.gov.uk` disallows `/data`; that is a different host and does not cover these |
| Licence | OGL v3.0 |

Buildable. Worth knowing it is a **risk signal about the employer, not about
pay** — it belongs in the enforcement chronology rather than in any pay
figure.

### Insolvency — VIABLE, but not by the proposed route — **BUILT into Module 4**

| | |
| --- | --- |
| Individual Insolvency Register | 200, but it is a register of **individuals**, not companies — personal data, and the wrong entity for provider viability |
| The Gazette | **403** on `robots.txt` — bot protection, same posture as WhatDoTheyKnow |
| Companies House disqualified directors | 200, 60 KB |

The useful route is the one already open: company insolvency status and
disqualification both come through Companies House, where this pipeline
already holds a key and a working client (m04). That makes it an **extension
of m04 rather than a new module** — `company_status` already distinguishes
liquidation and administration.

Built on 2026-08-11; see Module 4 above. Two things the probe had not
established, both found by building it:

* `/company/{n}/insolvency` answers **404 when there is no case**, and the
  company profile carries `links.insolvency` and `has_insolvency_history` — so
  the case list is fetched only where the register says there is one, and no
  company is asked a question it will answer 404 to.
* There is **no link from an officer's appointment to a disqualification**, so
  the register can only be searched by name. That is what forced the
  name-plus-date-of-birth corroboration rule rather than a simple lookup.

### Land Registry — PARTLY VIABLE

| | |
| --- | --- |
| Price Paid | 200, **15.7 MB CSV**, no authentication, OGL v3.0 |
| CCOD / OCOD (corporate ownership) | Landing page 200, but the data itself is behind registration and a licence |

Price Paid is open and buildable. It is also a whole-of-England transaction
file with no provider dimension — matching it to providers means address
matching, which is the hard part and the part that produces false links.

Corporate ownership is the dataset that would actually answer "does the
provider own or lease?", and its licence terms restrict republication. That
needs reading against the export model **before** any collection, not after.

Neither speaks to pay. Estate intelligence is interesting; it is not evidence
about what these employers pay, and it should not displace anything that is.

## Considered and not collected

Sources that were scoped and then deliberately left out. Recorded here so the
absence is a decision with reasons attached rather than an oversight.

### Care Opinion

| | |
| --- | --- |
| Source | `https://www.careopinion.org.uk` — first-person stories about health and care services |
| Status | **Not collected.** See the decision below |
| Licence | CC BY-NC-SA 4.0 — non-commercial, attribution, share-alike |
| Checked | 2026-08-11 |

Four findings, any one of which would be enough:

1. **The API is subscriber-only.** "API access is always in the context of a
   subscription on Care Opinion." There is no free non-commercial tier, so the
   brief's "prefer official APIs over scraping" route is closed without the
   campaign buying a subscription.
2. **`robots.txt` disallows every path that would make crawling useful** —
   `/api/`, `/opinions/searchresults`, `/tagstats`, `/activitystats`, `/feed/`.
   The service pages that remain crawlable render their content through those
   same disallowed endpoints, so a compliant fetch returns "Loading stories".
3. **There is no filtered route to the relevant stories.** The sitemap offers
   774,150 individual opinion URLs and 53,996 service pages with no way to
   narrow to substance misuse services without the disallowed search. Reading
   them all is precisely the behaviour that robots.txt spends a hundred lines
   objecting to.
4. **It is the wrong kind of evidence, collected the wrong way.** These are
   first-person health narratives written by patients and their families to
   improve their own care. Corpus-collecting them into a pay campaign database
   is not what they were published for, and what they speak to is service
   quality — turning that into an argument about pay is exactly the inference
   this pipeline refuses to manufacture elsewhere.

The share-alike licence is a fifth problem for exports, which are otherwise
OGL throughout.

If a subscription is obtained, (1) and (2) resolve and the module becomes
buildable against API v2 (documented at 5 requests per second). (4) would
still need answering, and it is not a technical question.

## Exports

`GOOGLE_SERVICE_ACCOUNT_JSON` (a **path** to a credential file, not the JSON
itself) and `GOOGLE_SHEETS_SPREADSHEET_ID` are needed only to push tabs to
Google Sheets. The CSV exports are produced with or without them.
