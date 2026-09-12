# Crime and policing data — area-level contextual evidence feasibility (JON-34)

**Status: research only.** No code, migration or module changed. Written
against commit `55fde50` with a clean tree, as the bounded assignment for
JON-34 ("Explore data.police.uk area-level contextual evidence"), whose
description points at an outstanding decision from the 2026-09-09 `beta.md`
tracking review (Questions Requiring Human Input #2, BETA-014's research):
whether a crime comparator is worth the effort given `data.police.uk` is
street/LSOA-level, not local-authority-level. This document verifies current
source availability, geography, licensing and data quality live against the
primary sources — not against beta.md's own summary of them, and not against
third-party descriptions of either — and sets out an integration approach and
open decisions, not an implementation, per the ticket's own acceptance
criteria and its explicit instruction not to infer that a local-authority
aggregation is automatically appropriate.

**The central finding is that "crime data" here is two different published
products, not one, and the ticket names only one of them.** `data.police.uk`
(the site JON-34 names) is exactly what beta.md found: street-level, resolved
no finer than LSOA, with no local-authority rollup published anywhere in it.
But the Home Office publishes a second, separate product on plain GOV.UK
under a different name — "Police recorded crime and outcomes open data
tables" — that is not hosted on or linked from `data.police.uk`, is already
at Community Safety Partnership (CSP) geography (which the Home Office's own
user guide states "generally corresponds to single or combined Local
Authority boundaries"), carries a dedicated "Drug offences" breakdown, and
has an official ONS lookup to CSP's constituent local authorities on the same
Open Geography Portal `m00_geography` already draws from. Beta.md's research
did not find this second product; this document did, by checking what GOV.UK
itself lists under the Home Office's crime-statistics collection rather than
by widening the search on `data.police.uk` alone. Both routes are documented
below in full, because the ticket named the first and a defensible answer to
"is a crime comparator worth building" needs to weigh both, not silently
substitute one for the other.

## 1. What already exists (read before proposing anything new)

No module here collects crime or policing data today, and no LSOA geography
of any kind exists in this codebase — confirmed by grep: the only place the
string "LSOA" appears anywhere in `pipeline/`, `migrations/`, `docs/` or
`tests/` is `beta.md`'s own research note. Nothing to extend, nothing to
avoid breaking.

The nearest existing precedent is the **comparator pattern** established by
Modules 29–31 (`m29_rough_sleeping`, `m30_statutory_homelessness`,
`m31_temporary_accommodation`): local-authority-level, `EVIDENCE_LAYERS["comparator"]`
in `pipeline/web/datasets.py`, surfaced on the public authority page below the
sector's own evidence, **never combined with it** — `docs/CAVEATS.md`'s first
rule, restated in each of those three modules' own entries. Any crime data
this pipeline stores should sit in that same family, not a new one.

The other piece of existing infrastructure this ticket leans on hard is
`pipeline/modules/m00_geography.py`'s discovery mechanism: it finds ONS
reference layers by searching ArcGIS Online content under the
`ONSGeography_data` owner at run time, because "these are versioned by year
and the IDs change" rather than hardcoding an item id. Both geography
crosswalks this document identifies below (§3.4, §4.4) live under that same
owner and are discoverable the same way — this is not new infrastructure to
invent, it is `m00`'s existing pattern applied to two more lookups.

## 2. Source A — `data.police.uk` (the site the ticket names)

### 2.1 The API

Verified live against `https://data.police.uk/api/` and `/docs/` on
2026-09-12. Endpoints, per the docs page:

| Endpoint | Purpose |
|---|---|
| `/crimes-street/{category}` | Street-level crimes within 1 mile of a point, or within a polygon |
| `/crimes-at-location` | Crimes at one specific location id |
| `/crimes-no-location` | Crimes a force could not assign a location to |
| `/crime-categories` | The category vocabulary (below) |
| `/crimes-street-dates` | Which dates/forces have data available |
| `/crime-last-updated` | The latest month currently published |
| `/outcomes-for-crime`, `/outcomes-at-location` | Case outcome history |
| `/forces`, `/force`, `/senior-officers` | Force reference data |
| `/neighbourhoods*` | Neighbourhood policing team boundaries and contacts |
| `/stops-street`, `/stops-at-location`, `/stops-no-location`, `/stops-force` | Stop and search records |

A live GET of `/api/crimes-street/all-crime?lat=52.629729&lng=-1.131592&date=2026-06`
returns records shaped exactly like this (field names and nesting verified
from the real response, not the docs page's example):

```json
{
  "category": "anti-social-behaviour",
  "location_type": "Force",
  "location": {
    "latitude": "52.626211",
    "street": { "id": 1738624, "name": "On or near Parking Area" },
    "longitude": "-1.127979"
  },
  "context": "",
  "outcome_status": null,
  "persistent_id": "",
  "id": 136077677,
  "location_subtype": "",
  "month": "2026-06"
}
```

**There is no LSOA, ward or local-authority field anywhere in this response.**
The only geography the API returns is latitude/longitude plus an internal
"street" id/name pair the site invents for its own anonymised map points
(§2.3) — confirmed by inspecting a real record, not assumed from the docs.
Any area-level aggregation from the API alone would have to start from raw
points and a spatial join, not a published area code.

`/api/crime-categories`, fetched live, returns exactly 14 real categories
plus the `all-crime` pseudo-category: `anti-social-behaviour`,
`bicycle-theft`, `burglary`, `criminal-damage-arson`, **`drugs`**,
`other-theft`, `possession-of-weapons`, `public-order`, `robbery`,
`shoplifting`, `theft-from-the-person`, `vehicle-crime`,
`violent-crime` (labelled "Violence and sexual offences"), `other-crime`.
`drugs` is the one category name-matched to this project's own subject
matter; it is data.police.uk's own single, undifferentiated drug-offence
bucket — no possession/supply/class split, unlike the Home Office subcode
table in §3.3.

**The API's own history is a rolling 36-month window, not the full series.**
`/api/crimes-street-dates`, fetched live on 2026-09-12, returns exactly 36
monthly entries, newest `2026-07`, oldest `2023-08`. The newest available
month (July) on a September 12th check means roughly a six-week publication
lag; `data.police.uk`'s own about page does not state an explicit lag
figure, so this is an observed fact from one live check, not a published
schedule. **Anything before August 2023 is not reachable through the API at
all** — only the bulk downloads in §2.2 go further back.

The rate limit, per `/docs/api-call-limits/`, is 15 requests/second with a
burst of 30 (leaky bucket, HTTP 429 on breach) — well inside this pipeline's
own default of one request per two seconds per host (`docs/CAVEATS.md`'s
sibling rule in `README.md`/`pipeline/http.py`), so no rate-limit exception
would be needed here, unlike WDTK's own care-in-handling in Module 15.

### 2.2 Bulk CSV downloads (the only route to LSOA at all)

`https://data.police.uk/data/` offers custom-built downloads per force/date
range, and `https://data.police.uk/data/archive/` offers whole-dataset
monthly archives at `/data/archive/YYYY-MM.zip`. Both are described, from the
about page's own column table (verified against the live page,
2026-09-12), as containing these CSV columns for the crime/ASB file:

**Crime ID** (a one-way hash of the record) · **Month** (year-month only) ·
**Reported by** · **Falls within** (currently identical to Reported by) ·
**Longitude** / **Latitude** · **Location** · **LSOA code** · **LSOA name**
· **Crime type** (one of the same categories as §2.1) · **Last outcome
category** · **Context**.

**This is the only place LSOA appears in this source at all — not the API,
only the CSV.** LSOA is the finest and only sub-force geography this source
publishes; there is no ward, MSOA or local-authority column in either
product.

**Archives are cumulative rolling snapshots, not single-month files.** Per
the live archive page, each dated zip contains roughly the trailing 24–36
months of data as of that date, the same rolling-window shape as the API's
own 36-month limit (§2.1) — not one month of new data layered onto the last.
Archives exist back to **December 2013**; the page states outright that
"these archives were not being generated before December 2013," and a
separate standalone file covers the older neighbourhood-level series from
**December 2010 to June 2013**. **Consequence for anyone wanting the full
2010-to-date series: a single current fetch does not get it (unlike `m29`'s
evergreen-page shape) — reconstructing full history means walking multiple
historical archive snapshots and reconciling their overlaps, or accepting
whatever the current 36-month rolling window plus the pre-2013 standalone
file together cover, with a real gap in between that neither straightforwardly
fills.** This is the opposite failure mode from the Rough Sleeping Data
Framework finding (`docs/rough-sleeping-data-framework.md` §3): there, one
fetch already had everything; here, one fetch structurally cannot.

**The LSOA boundary itself changed underneath this source.** `data.police.uk`'s
own changelog states, for **June 2023**: "The LSOA data has been updated from
the 2011 data to the 2021 data." The rolling 36-month API/current-archive
window (from August 2023, per §2.1) therefore sits entirely on 2021 LSOA
codes; anything reconstructed from older archives would be on 2011 LSOA
codes and would need reconciling before the two eras could be compared or
combined. ONS's Open Geography Portal, searched live under the same
`ONSGeography_data` owner `m00_geography.py` already queries, has exactly
the reference layer this needs: **"LSOA (2011) to LSOA (2021) to Local
Authority District (2022) Exact Fit Lookup for EW (V3)."** This is not a gap
to build from scratch — it is one more item for `m00`'s existing discovery
pattern to find, the same way it already finds versioned LAD/region layers.

### 2.3 Anonymisation and geocoding

Verified from the live about page. Locations are snapped to one of a fixed
set of pre-chosen map points, not published as the crime's true coordinates:
each point is chosen "so that it appears over the centre point of a street,
above a public place such as a Park or Airport, or above a commercial
premise like a Shopping Centre or Nightclub," and each point's catchment
"contains at least eight postal addresses or no postal addresses at all." A
reported crime is matched to its nearest such point; if the nearest point is
more than 20km away, the coordinates are zeroed instead of snapped to a
distant, wrong-looking point. The point list was built in 2012 and refreshed
in 2022 from Ordnance Survey data.

**Even the anonymised point is not equally trustworthy everywhere.** The
about page states geocoding accuracy — whether a force's own submitted crime
location was placed correctly before anonymisation even happens — "ranges
from 60% to 97%" depending on the force, because "inconsistent geocoding
policies in police forces mean we cannot be confident that the location data
provided is fully accurate or consistent." This is a per-force accuracy
range on top of the deliberate anonymisation, not instead of it, and is a
different, additional caveat from anything already in `docs/CAVEATS.md`.

### 2.4 Coverage and known data-quality issues

43 geographic forces in England and Wales, British Transport Police, the
Police Service of Northern Ireland and (crime data only) the Ministry of
Justice, per the about page and confirmed live against `/api/forces`
(returns all 43 English/Welsh forces plus BTP, e.g. `avon-and-somerset`,
`metropolitan`, `city-of-london`). Stop-and-search coverage is a subset of
forces, confirmed live: `/api/crimes-street-dates` for 2023-08 lists 30 of
the 43+BTP forces reporting stop-and-search, not all of them. Neither BTP
nor PSNI provide outcome data. The about page also states six (unnamed)
forces are known to be duplicating certain ASB incident types, and that a
force's later correction to a record is only reflected here "if the force
decides to do a complete data refresh" — an unannounced, unflagged
retroactive change is otherwise invisible to a downstream consumer.

### 2.5 Licence

Open Government Licence v3.0, confirmed on the live open-data page ("all
data published on this page is available under the Open Government Licence
v3.0") — the same licence already registered for the large majority of
`pipeline/licences.py`'s entries. No new licence question.

## 3. Source B — Home Office "Police recorded crime and outcomes open data tables" (GOV.UK, not `data.police.uk`)

This is a **separate GOV.UK statistical publication**, not part of
`data.police.uk` and not linked from it (checked: nothing on
`data.police.uk`'s own pages references it). It is the Home Office's own
compiled recorded-crime series, produced to feed the quarterly "Crime in
England and Wales" release, and it is the route that actually reaches
local-authority-comparable geography — which is why this document treats it
as a real second candidate rather than a footnote.

### 3.1 Verified live via the GOV.UK content API

A live GET of
`https://www.gov.uk/api/content/government/statistical-data-sets/police-recorded-crime-and-outcomes-open-data-tables`
on 2026-09-12 returns `public_updated_at: 2026-07-23`, `first_published_at:
2025-04-24` (a republish under a new URL of an older, longer-running
series — the historic edition is still separately listed on GOV.UK as
"Historic police recorded crime and outcomes open data tables"), and 49
attachments. This document only inspects the two geography levels relevant
to an area-level comparator: Community Safety Partnership and Police Force
Area. The other 45+ attachments (knife/firearms subcodes, VAWG subcodes,
outcomes-only tables per year, fraud, transferred/cancelled crime) are noted
as existing but out of scope for this document.

### 3.2 Community Safety Partnership (CSP) geography — the closest fit to a local-authority comparator

Downloaded and unzipped directly (not summarised from a description): the
current file, `Police recorded crime Community Safety Partnership open
data, year ending March 2021 to year ending March 2026` (50 MB `.ods`), has
one sheet per financial year (`2020_21` … `2025_26`) with these columns,
read verbatim from the sheet's own header row:

**Financial Year · Financial Quarter · Police Force · CSP Name · Offence
Description · Offence Group · Offence Subgroup · Offence Code · Offence
Count**

— one row per CSP × offence code × quarter. A real row, read directly from
the file: `2020/21, Q1, Avon and Somerset, Bath and North East Somerset,
"Other drug offences", Offence Group "Drug offences", Offence Subgroup
"Possession of drugs", Offence Code 92C, Offence Count 0`. **"Drug
offences" is the exact Offence Group string in this file** (sentence
case, lowercase "o") — note this against §3.3's force-level file, which
uses "Drug Offences" (title case) for the same concept; a filter written
against one string will silently miss the other, and this document did not
find a shared, case-normalised offence-taxonomy table anywhere in either
publication.

**History is not one file.** The current edition spans year-ending-March
2021 to 2026; the full series back to year-ending-March 2003 exists only as
four further, closed, non-overlapping windowed files (2016–2020, 2012–2015,
2008–2011, 2003–2007), each its own separate GOV.UK attachment. This is
closer to the Rough Sleeping Data Framework's collection-walk case
(`docs/rough-sleeping-data-framework.md` §3, §6) than to `m29`'s single
evergreen file: getting full history means reading five separate files, not
one — though unlike RSDF, each window here is a closed, non-reopened
historical file rather than an evergreen page that might later add a sixth
window mid-series, so no ongoing "which edition is current" ambiguity once
built.

**Geography note, verified against the small (404-row) reference table this
publication itself ships** (`Recorded crime data geographical reference
table`, `recrime-geo-pfa.csv`): CSP names are mostly identical to current
local authority names (`Bath and North East Somerset`, `Barnsley`,
`Wolverhampton`, …), matching the Home Office's own user guide statement
that a CSP "generally corresponds to single or combined Local Authority
boundaries." But the reference table also carries real complications a
name-match alone would not catch:

- **It includes Wales** (`W`-prefixed ONS codes, e.g. `Wrexham,
  W14000006`) — out of scope for this England-wide pipeline and must be
  filtered the same way `m00_geography.py` already filters to English
  authority-type prefixes.
- **Historic sub-authority CSPs survive in the reference table under old
  district codes**, not the modern CSP entity code: `Wiltshire_Kennet`,
  `Wiltshire_North Wiltshire`, `Wiltshire_Salisbury`, `Wiltshire_West
  Wiltshire` each carry a legacy `E07` district code rather than an `E22`
  CSP code, alongside a modern unified `Wiltshire` row with its own `E22`
  code — because the file spans a series that predates the 2009 Wiltshire
  unitary merger. This is the same shape of problem `m27_ndtms_monthly`
  already solves for authority reorganisation (predecessor/successor
  resolution via `authority_successors`), applied to a source this pipeline
  does not yet read.
- **Most current-era rows use a distinct `E22` "Community Safety
  Partnership" ONS entity code**, not a local authority code from any of
  the `E06`/`E07`/`E08`/`E09`/`E10` prefixes `m00_geography.py` already
  recognises — a straight `ons_code` join against the existing `authorities`
  table will not work even where the name matches exactly; the join has to
  go through a name match or a proper lookup (below), not a shared code
  space.

**An official, versioned crosswalk for exactly this exists on the same
ONS Open Geography Portal `m00` already queries.** Searched live under the
`ONSGeography_data` owner: **"Local Authority District to Community Safety
Partnership to PFA"** lookups exist for multiple vintages back to January
2017 (December 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, and
April 2025 all found live), the same "versioned by year, discover at run
time" shape `m00` already handles. This is materially less new machinery
than the LSOA route in §2.2 needs: one lookup table, already covering the
right two geography levels directly, rather than a two-step LSOA→LAD chain
through an intermediate geography this pipeline has never stored a row of.

### 3.3 Drug-offence subcode detail — Police Force level, not CSP level

A further attachment, `Police recorded crime subcodes for drugs offences,
year ending March 2021 to year ending March 2026` (`.ods`, downloaded and
unzipped directly), is quarterly and **Police Force level** (43 forces plus
an `England and Wales` aggregate row) — coarser than the CSP table in §3.2,
not the same geography. Columns, read from the sheet header: **Financial
Year · Financial Quarter · Force Name · Offence Description · Offence Group
· Offence Subgroup · Offence Code · Subcode Description · Offence Subcode ·
Outcome Description · Outcome Group · Outcome Type · Force outcomes for
offences recorded in quarter · Force outcomes recorded in quarter**.

Real rows, read directly from the file: Offence Group **"Drug Offences"**
(title case — see the §3.2 case mismatch), Offence Subgroup **"Trafficking
of drugs"**, Offence Code `92A`, with Subcode Descriptions such as
"Manufacturing a scheduled substance" and "Possession on a ship of a
controlled drug intended for trafficking: Class A/B/C", each paired with an
Outcome Description (`Charged/Summonsed`, `Community Resolution`, `Evidential
difficulties: suspect identified; victim supports action`, `Not in public
interest (Police)`, …) and two separate counts distinguishing offences
recorded in the quarter from outcomes recorded in the quarter — the same
kind of recording-vs-outcome timing lag this project already handles
elsewhere (e.g. `m02_tribunals`'s judgment-only capture, or NDTMS's
provisional-vs-revised framing). **This document did not directly observe a
"Possession of drugs" subgroup row in this particular file** (only
"Trafficking of drugs" rows fell within the sample inspected) — the
offence-code family (`92A` trafficking, `92C` possession, per §3.2's CSP-level
row) implies possession rows exist here too, but that is an inference from
the shared coding scheme, not something this document confirmed by reading
a row.

This subcode table is the most clinically specific slice found anywhere in
either source — possession versus trafficking, drug class, and what
happened next — but it cannot be read at CSP or local-authority level at
all. A project wanting this detail would be trading geography precision
(force, not CSP/LA) for offence precision, not getting both from the same
row.

### 3.4 Statistics designation and comparability caveats

The Home Office's own user guide to this publication states plainly: **"Police
recorded crime data are published as official statistics, not accredited
official statistics."** This is a real, named category under the Statistics
and Registration Service Act framework — weaker than "Accredited Official
Statistics" (the old "National Statistics" designation) but a materially
different governance basis than `data.police.uk`'s own open-data feed, which
carries no statistics designation at all and ships its own accuracy caveats
(§2.3, §2.4).

Two comparability caveats, both quoted from primary sources rather than
inferred:

- The same user guide, on comparing areas or time: **"PRC figures can be
  considerably affected by changes in recording policy and practice and it
  is important to consider the impact of such changes when analysing time
  series based on PRC data or comparing between different police force
  areas."** It further states that HMIC's 2014 crime-data-integrity
  inspections led to "significant improvements in the accuracy of crime
  recording" that in turn "led to a discontinuity in several crime types" —
  a named break point, not a gradual drift, that any pre/post comparison
  needs to account for explicitly.
- ONS's own *User Guide to Crime Statistics for England and Wales* states,
  of drug possession specifically: **"There are some categories of crime
  (such as drug possession offences) where the volume of offences recorded
  is heavily influenced by police activities and priorities; in such cases,
  recorded crime figures may indicate police activity in this area rather
  than levels of criminality."** For a substance-misuse-sector project this
  is the single most important caveat of the two sources combined: a higher
  recorded drug-offence count in one authority than another can mean more
  enforcement activity (more stop-and-search, a local operation, a
  force-wide priority), not more drug use and not more unmet treatment
  need — the opposite of what a reader unfamiliar with this literature
  would likely assume on first seeing the figure.

ONS separately published its own re-hosted copy of the CSP-level dataset,
found live at
`ons.gov.uk/.../recordedcrimedatabycommunitysafetypartnershiparea`, but that
page states the dataset **"has been discontinued as of 24 October 2024,"**
directing users elsewhere. **The Home Office's own GOV.UK page (§3.1) is the
live, current source; the ONS mirror is not** — a distinction worth stating
explicitly since a future search is likely to surface the discontinued ONS
copy first.

### 3.5 Licence

Open Government Licence v3.0, confirmed on the live GOV.UK page. Same
licence as Source A and the large majority of this project's other sources —
no new licence question here either.

## 4. What this document did not verify

- Whether `data.police.uk`'s own figures and the Home Office's official CSP/PFA
  recorded-crime figures reconcile for the same force, area and period. They
  are two different published pipelines with different documented accuracy
  caveats (§2.3, §2.4 vs §3.4); this document treats that as an open
  question, not an assumption either way, and neither source's own pages
  state a reconciliation.
- Whether the ONS geography lookups named in §2.2 and §3.2 remain stable in
  content between now and any future build — only that items answering the
  right description exist today under the same discovery mechanism `m00`
  already trusts. `m00`'s own discovery-at-run-time pattern exists precisely
  because these items are versioned and superseded; the specific item ids
  found here are illustrative, not reserved.
- Any live fetch-parse-write run, because no module exists yet to run.
- Whether a CSP name with no exact match in `authorities` (the Welsh rows,
  the historic sub-district rows) resolves cleanly through the official
  lookup found in §3.2, or needs the same `review_queue`/NULL discipline
  `m00`, `m27` and `m29` already apply to their own unmatched-authority
  cases — plausible by analogy, not built or tested here.

## 5. What this pipeline must not compute from either source (draft caveats, not yet in `docs/CAVEATS.md`)

- **Never combined with the sector's own evidence** — the same first rule as
  Modules 29–31 and `docs/CAVEATS.md`'s own opening rule. A crime comparator,
  if built, is side-by-side only.
- **Never read a drug-offence count as a measure of drug use, prevalence or
  unmet treatment need.** §3.4's ONS caveat applies directly: a change or a
  difference between areas may be a change or difference in policing
  activity, not in the underlying behaviour this project's own sector
  evidence is about.
- **Never treat `data.police.uk`'s open-data feed and the Home Office's
  official CSP/PFA statistics as interchangeable or averaged.** They are
  different products (§4).
- **Never difference or compare figures across the 2014 recording-practice
  discontinuity (§3.4) without saying so**, the same discipline this project
  already applies to NDTMS's provisional/revised framing and to Module 30's
  pre-/post-2017 layout change.
- **Never assume a CSP name is a local authority.** Most are, by design; the
  reference table itself (§3.2) contains real counterexamples (combined
  CSPs, Welsh rows, historic sub-district rows) that a blind name-match
  would mis-handle. Unmatched names are `NULL` plus a `review_queue` row,
  never guessed — the same rule as every other geography-matching module in
  this pipeline.
- **Never mix the CSP-level "Drug offences" total (§3.2) with the
  force-level subcode breakdown (§3.3) as though they answered the same
  geography question.** One is per-authority-ish, the other is per-force; a
  reader could easily misread "the force's trafficking count" as "this
  authority's trafficking count."
- **Treat `data.police.uk`'s anonymised point locations as approximate by
  design, at a further, force-varying accuracy discount (60–97%, §2.3) on
  top of that** — never geocode or re-derive a more precise location from
  them.
- No small-number suppression marker (an `[c]`-style flag, in this
  project's existing vocabulary for MHCLG/NDTMS sources) was found in either
  source's file structure as inspected here. Any small-area, small-count
  publication from this data should have that checked explicitly before
  going live, not assumed absent because none was seen in the rows sampled.

## 6. Integration approach (recommended, not built)

1. **If a crime comparator is built, Source B's CSP-level "Drug offences"
   table (§3.2) is the recommended starting point, not `data.police.uk`
   itself.** It is closer in shape to the existing Modules 29–31 pattern
   (annual-ish, LA-adjacent geography, an official-statistics designation,
   OGL, one more row in the existing "Comparators" section) than the
   LSOA/street-level route, and its geography crosswalk is a single
   already-discovered ONS lookup rather than a two-step LSOA→LAD chain
   through a geography this pipeline has never stored.
2. **The `data.police.uk` LSOA route (§2) remains buildable** if street-level
   detail or monthly cadence specifically matters more than official-statistics
   status — beta.md's original framing ("buildable, but a materially bigger
   module") is confirmed accurate by this document, not overstated. It needs,
   at minimum: the CSV bulk-download path (never the API, which carries no
   LSOA field at all, §2.1), the LSOA(2011)→LSOA(2021) reference table
   (§2.2) for any history predating June 2023, the LSOA→LAD reference table,
   and a strategy for the rolling-window archive shape (§2.2) if full
   2010-to-date history is wanted rather than the current 36-month window.
3. **New module, new tables — this ticket does not extend `m29`/`m30`/`m31`.**
   A candidate module number is `m36` (next free after `m35_open_jobs`) and a
   candidate migration number is `0116` (next free after `0115`), both to be
   confirmed at build time rather than reserved now.
4. **A `geography_level` discriminator belongs in the schema from the start**
   if both the CSP-level totals (§3.2) and the force-level subcode detail
   (§3.3) are ever stored — the RSDF feasibility document
   (`docs/rough-sleeping-data-framework.md` §7.4) already flagged a related,
   still-open gap in this codebase (no field distinguishing management
   information from official statistics); this ticket's force-vs-CSP
   granularity mismatch is a second, separate case of "don't let two rows
   that look alike answer different questions," worth deciding once rather
   than improvising per source.
5. **Read the offence-group string exactly as published, per file, per era**
   — §3.2 and §3.3 already disagree on the case of "Drug offences" within
   the same Home Office publication family; do not normalise or assume a
   shared vocabulary without checking each file's own header row, the same
   discipline `m27`/`m29`/`m30` already apply to their own sources'
   inconsistent labels.
6. **English rows only** — filter Welsh CSP/PFA rows the same way
   `m00_geography.py` already filters to English authority-type prefixes,
   not by name-based guessing.

## 7. Offline fixtures

If Source B is built: a small hand-built fixture needs at minimum one CSP
whose name matches a live English authority exactly, one row using a
combined-CSP name with no exact authority match (to exercise the
`NULL`-plus-`review_queue` path), one row from the historic
sub-district-CSP shape (`Wiltshire_Kennet`-style) to exercise the
predecessor-authority case, and two quarters of the same CSP/offence-group
pair to exercise ordinary time-series storage. None of this requires a live
fetch to construct — the sheet shape in §3.2 is enough to hand-build a small
`.ods` fixture the same way existing module tests already do for `m29`/`m30`.

If Source A's LSOA route is built instead: a fixture needs one crime record
under a 2011 LSOA code and one under a 2021 LSOA code for the same real-world
area (to exercise the boundary-lookup path), one record whose LSOA has no
resolvable local authority (to exercise the unmatched case), and one record
spanning a monthly archive boundary to exercise the rolling-window
reconstruction problem in §2.2.

## 8. Recommended next decisions (none taken here)

1. **Is a crime comparator worth building at all, given the real effort
   involved — now asked about Source B specifically, not the street/LSOA
   route BETA-014 originally scoped.** This document narrows beta.md's open
   question rather than closing it: the CSP-level route is materially
   cheaper and better-shaped than the route beta.md evaluated, which may
   change the project owner's answer, but the decision itself is still
   theirs, not this document's.
2. **If yes, is "Drug offences" alone in scope, or the wider all-crime
   comparator set** — mirroring the scope discipline already applied when
   `m29` was built (one clean source done properly, not several at once).
3. **Is the force-level drugs subcode detail (§3.3) worth a second,
   coarser-geography table**, given it is the most clinically specific data
   found in either source but cannot be read at CSP/LA level.
4. **Is stop-and-search data (data.police.uk only, §2) in scope at all** —
   its ethnicity/age-band/gender breakdown carries a distinct,
   well-documented disproportionality sensitivity separate from the
   small-area privacy question beta.md already raised for street-level
   crime, and this document does not attempt to resolve either.
5. **Confirm the specific geography lookup(s) to use at build time** (§2.2,
   §3.2) rather than treating the ArcGIS item ids found during this
   document's research as reserved — `m00`'s own discovery-at-run-time
   design exists because these are versioned and will have moved on by
   then.

Every item above is a candidate for a named human decision, not an
implementation queue — consistent with this issue's Not-scheduled/Post-V1
readiness label.
