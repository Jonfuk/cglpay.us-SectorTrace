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
| Sources | mySociety's published authority register (WhatDoTheyKnow); WhatDoTheyKnow search feed; council disclosure logs |
| Endpoints | `/body/all-authorities.csv`; `/feed/search/<query>.json`; per-council disclosure log pages |
| Licence | mySociety data under CC BY-SA; FOI responses generally OGL v3.0; council disclosure logs vary |
| Key | None |
| Rate limit | Default (2s/host), conditional requests |
| Notes | **Publicly published FOI evidence, and discovery only — not full responses.** The feed returns a truncated search snippet per event and never a message body; full text needs `/request/<slug>.json`, which returns a Cloudflare 403 to automated clients and is not worked around. The feed is fetched under an explicit, logged exception to mySociety's robots.txt (`Settings.robots_exceptions`) — see `docs/mysociety-access-request.md`, which is the outstanding ask to put it on a permitted footing |

---

## Viability checks

Probed live on 2026-08-11 with the pipeline's own User-Agent, one request
each. Reachability is not the same as buildability — the notes say which.

### NHS Jobs — VIABLE, highest value of the candidates

| | |
| --- | --- |
| Endpoint | `https://www.jobs.nhs.uk/candidate/search/results?keyword=…` |
| Result | 200, 84 KB, server-rendered HTML, 10 adverts per page, **salary present in the markup** |
| robots.txt | Serves an HTML shell rather than rules — no directives to honour, but worth re-checking before a real crawl |
| Licence | Crown copyright; advert content is the employer's |

Advertised pay bands are **direct pay evidence**, not a proxy and not a
composite — the only candidate of which that is true. Vacancy duration and
re-advertisement are the empirical form of "we cannot recruit at this rate",
which the annual workforce census cannot show.

Note the coverage limit before anyone leans on it: NHS Jobs carries NHS and
some commissioned-provider adverts. A charity provider advertising only on
its own site is invisible here, so counts are a floor, never a total.

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

### Insolvency — VIABLE, but not by the proposed route

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
