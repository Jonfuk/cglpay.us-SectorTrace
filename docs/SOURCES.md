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

## Module 2 — Employment tribunals

| | |
| --- | --- |
| Source | GOV.UK Search API, format `employment_tribunal_decision` |
| Endpoints | `https://www.gov.uk/api/search.json`, `https://www.gov.uk/api/content/{path}` |
| Licence | OGL v3.0 |
| Key | None |
| Rate limit | Default |
| Personal data | Decision titles, URL slugs and indexed text name the claimant. Names are stored only in `restricted_tribunal_parties` |

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

## Module 5 — CQC

| | |
| --- | --- |
| Source | CQC public API |
| Endpoint | `https://api.service.cqc.org.uk/public/v1` |
| Licence | OGL v3.0 |
| Key | **`CQC_SUBSCRIPTION_KEY`** — free registration. Sent as `Ocp-Apim-Subscription-Key` |
| Rate limit | Default |
| Personal data | Registered managers are named inside each location's regulated activities. Stored only in `restricted_cqc_location_contacts` |

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
| Sources | mySociety's published authority register (WhatDoTheyKnow); council disclosure logs |
| Endpoints | mySociety's sanctioned authority CSV; per-council disclosure log pages |
| Licence | mySociety data under CC BY-SA; council disclosure logs vary, most OGL v3.0 |
| Key | None |
| Rate limit | Default |
| Notes | **Publicly published FOI evidence, not all FOI responses.** WhatDoTheyKnow's `/search/` is disallowed by its robots.txt and its site is behind a bot challenge; this module uses the CSV mySociety publish for the purpose instead, which is why it covers 315 authorities rather than one |

---

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
