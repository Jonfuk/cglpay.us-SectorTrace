# Nomis labour-market context — feasibility (JON-16)

**Status: feasibility complete; no code, migration or module changed.** Written
against beta commit `5fece46` on 2026-09-13. This is the bounded research
deliverable for JON-16: verify Nomis capabilities, coverage, access terms,
provenance requirements, integration approach and acceptance criteria before
implementation.

The module-audit note ranks this as a Post-V1 contextual expansion (revised
rank 18; m21). The recommendation is **selective adoption**: use Nomis for
supported local-authority ASHE headline slices and residence/workplace
labour-market context, while retaining the existing direct ONS ASHE module for
occupation and industry earnings where Nomis does not publish local-authority
breakdowns.

## 1. Verdict

Nomis is feasible and useful for SectorTrace, but it must remain a contextual
evidence layer. It must not be used to attribute labour-market statistics to a
named provider, infer vacancies, or calculate cross-layer pay or workforce
ratios.

The recommended future scope is:

| Candidate | Nomis coverage verified | Recommended disposition |
|---|---|---|
| ASHE workplace headline earnings/hours | 2025 data; people working in an area; local authorities, constituencies, regions and countries | **Build selectively** for local-authority headline slices |
| ASHE resident headline earnings/hours | 2025 data; people living in an area; available from 2002 onwards | **Build selectively** for local-authority headline slices |
| Annual Population Survey (APSNEW) | Residence-based employment, unemployment, inactivity and qualifications; broken down where possible by gender, age, ethnicity, industry and occupation; local authority and above; quarterly | **Build selectively** for labour-supply context |
| Annual Population Survey workplace (APSW) | Workplace-based economic activity, country of birth, occupation, qualification and hours worked | **Consider as a second-phase workplace context feed** |
| Census 2021 occupation, industry and qualifications | Detailed England and Wales structural snapshots with Census definitions and disclosure control | **Use selectively as a dated baseline**, not a current time series |
| ASHE occupation/industry earnings at local authority level | Explicitly unavailable through Nomis | **Do not build through Nomis**; retain direct ONS regional/country ASHE path |
| ASHE below local-authority/constituency geography | Explicitly unavailable | **Do not infer or synthesize** ward/SOA estimates |

Nomis therefore complements, rather than replaces, the current `m21_ons_ashe`
implementation.

## 2. What already exists in SectorTrace

The existing beta branch already contains an ONS ASHE comparator in
`pipeline/modules/m21_ons_ashe.py`.

That module:

- reads ONS's `api.beta.ons.gov.uk/v1` ASHE datasets;
- keeps occupation and industry datasets separate;
- reads the API's current version and its own dimension options at runtime;
- queries pinned SOC/SIC groups individually by geography and code;
- records source URL, retrieval time, HTTP status, source system and payload
  SHA-256;
- stores non-numeric/suppressed observations as NULL with the original text and
  a parse-failure record;
- fails loudly on source transport failures rather than presenting an empty
  result as a successful run;
- limits its geography to UK and England for the current direct ONS comparator.

`docs/CAVEATS.md` already governs this module. In particular, ASHE is a
sample of PAYE employee jobs; it excludes the self-employed; suppressed cells
are NULL rather than zero; and advertised provider pay and ASHE are
side-by-side evidence only. No ratio such as “X% below the market” is computed.

JON-16 should not duplicate or silently relabel those ONS rows. A future Nomis
implementation needs an explicit source-system boundary and separate
provenance.

## 3. Nomis API capability

Nomis provides a REST API for structural discovery and data downloads. Its
official API guide documents:

- dataset/key-family discovery;
- dimensions, concepts and codelists;
- metadata for dates and codes;
- CSV, TSV, JSON, JSON-stat, SDMX XML/JSON, Excel and HTML outputs;
- GET and POST requests;
- filtering by dimension codes and dates;
- `latest`, `previous`, `prevyear` and `first` date selectors;
- `RecordLimit` and `RecordOffset` pagination;
- selected output columns, including dimension names, geography codes and
  observation status fields;
- a query-summary endpoint for validating a constructed request.

Nomis also says that concurrently running API requests are limited and asks
clients to keep concurrency low. CSV and JSON-stat downloads have a
1,000,000-cell limit. A collector should therefore use bounded, serial or
low-concurrency requests with explicit pagination and a hard response-size
limit.

The API guide says that all unspecified dimensions may default to all
available data unless `setallwherenotspecified=false` is supplied. A future
collector must specify every required dimension deliberately and reject a
changed dataset structure rather than silently downloading a broader or
different slice.

The API guide is the authoritative implementation reference:
[Nomis REST API guide](https://www.nomisweb.co.uk/api/v01/help?uid=0xd57c2bd58aa382ddb5cae1383cbe476f36609e57).

### Proposed request discipline

1. Discover and cache the dataset definition.
2. Resolve the required dimension and geography codelists.
3. Construct a narrow query with explicit dataset, dimensions, codes and
   date/reference-period selection.
4. Request a small bounded page first and validate the response shape.
5. Page with `RecordLimit`/`RecordOffset` where required.
6. Persist the exact request URL, response status, retrieval time and payload
   hash.
7. Treat missing, suppressed, non-numeric or structurally changed results as
   reviewable outcomes, never as zero or absence.
8. Keep requests polite and stop on repeated source-side failure.

## 4. Coverage verified

### 4.1 ASHE headline earnings and hours

Nomis currently exposes two ASHE datasets:

- [ASHE resident analysis](https://www.nomisweb.co.uk/datasets/asher), API
  reference `ASHER`;
- [ASHE workplace analysis](https://www.nomisweb.co.uk/datasets/ashe), API
  reference `ASHE`.

The current Nomis ASHE dataset pages show **2025** as the latest reference
period. Both expose the headline dimensions needed for an area comparator:

- sex, including total, male, female, full-time and part-time categories;
- item, including number of jobs, median, mean, percentage changes and
  percentiles;
- pay, including gross weekly, weekly excluding overtime, basic, overtime,
  gross hourly, hourly excluding overtime, gross annual, annual incentive and
  paid-hours measures.

Nomis's own ASHE guidance states:

- resident analysis estimates relate to people living in an area and are
  available from 2002 onwards;
- workplace analysis estimates relate to people working in an area and are
  available from 1998 onwards;
- estimates are available for local authorities, parliamentary constituencies,
  regions and countries;
- estimates are not available below local authority or constituency level;
- occupation and industry earnings breakdowns are not available for local
  authorities or constituencies, and those analyses are available at region and
  country level on the ONS website.

This is the key JON-16 boundary. Nomis can provide a local-area headline
earnings context, but not a local-authority occupation-specific or
industry-specific ASHE comparator.

Nomis's current guidance:
[Annual Survey of Hours and Earnings — Nomis](https://www.nomisweb.co.uk/articles/1449.aspx).

### 4.2 Annual Population Survey

The current [APSNEW dataset](https://www.nomisweb.co.uk/datasets/apsnew) is a
residence-based labour-market survey. Nomis describes it as covering:

- population;
- economic activity, including employment and unemployment;
- economic inactivity;
- qualifications;
- gender, age, ethnicity, industry and occupation where available;
- local-authority level and above;
- quarterly updates.

The current page shows the latest reference period as **Apr 2025–Mar 2026**
and records a revision history, including reweighting and an identified
revision. Those revision and reference-period values must travel with any
stored observation.

The [APSW dataset](https://www.nomisweb.co.uk/datasets/apsw) is the workplace
variant. Nomis describes it as covering economic activity, country of birth,
occupation, qualification and hours worked. It is a potential workplace
context source, but the exact requested slice and geography must be resolved
from the live dataset definition before implementation.

APS is more appropriate than ASHE for employment, unemployment, inactivity and
qualification context. ASHE remains the better source for employee-pay
headline estimates. They must not be treated as interchangeable populations.

### 4.3 Census 2021 structural context

Nomis exposes Census 2021 tables suitable for a dated structural baseline:

- [TS060 — Industry](https://www.nomisweb.co.uk/datasets/c2021ts060), with
  detailed SIC categories;
- [TS064 — Occupation — minor groups](https://www.nomisweb.co.uk/datasets/c2021ts064),
  with SOC 2020 minor groups;
- [TS067 — Highest level of qualification](https://www.nomisweb.co.uk/datasets/c2021ts067).

The Census tables describe usual residents aged 16 and over, with employment
measures tied to the week before Census Day, **21 March 2021**. They apply
statistical disclosure controls, including record swapping and cell-key
perturbation.

Important limitations:

- Census 2021 occupation is coded to SOC 2020 and is not comparable with the
  2011 occupation categories in the detailed table;
- Census 2021 qualification categories are broadly comparable with 2011, but
  the question and grouping changed, so the values are not perfectly
  like-for-like;
- the Census is a snapshot, not a quarterly or annual labour-market feed;
- counts must retain their Census population, date, geography and disclosure
  control notes;
- a Census value is not a provider-level workforce count.

For a current labour-market context module, Census should be an explicitly
dated baseline beside APS, not silently combined with it.

## 5. Access terms and licensing

Nomis is provided by the University of Durham on behalf of ONS. The Nomis
terms state that:

- users accept that data are extracted from third-party sources outside the
  University's control;
- data are used at the user's own risk;
- Nomis may use the registered email address for service updates;
- misuse or abuse may result in account termination;
- National Statistics information on the web is subject to change without
  notice.

See the [Nomis terms and conditions](https://www.nomisweb.co.uk/home/terms.asp).

The ONS ASHE survey page states that ONS content is available under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)
except where otherwise stated. The [ONS ASHE page](https://www.ons.gov.uk/surveys/informationforbusinesses/businesssurveys/annualsurveyofhoursandearningsashe)
also confirms that ASHE data are anonymised and secure.

The future collector must still retain dataset-specific terms and the
publisher's attribution text alongside each source definition. “Open” does
not remove the need to preserve publisher, dataset, version, reference period,
methodology, caveats and access date.

No restricted or personal data is required for this proposal. The intended
inputs are published aggregate statistics only.

## 6. Quality, population and comparison rules

The following rules are mandatory for any future Nomis work and are consistent
with `docs/CAVEATS.md`:

- ASHE measures employee jobs in a 1% PAYE sample. It does not cover the
  self-employed and is not a provider payroll.
- ASHE resident and workplace analyses answer different questions. The
  analysis type must be a first-class field, never inferred from a label.
- APS is a residence-based or workplace-based survey depending on the dataset.
  Its survey reference period and revision state must remain attached.
- Census values are dated England and Wales snapshots with their own
  population and disclosure-control rules.
- A local-authority aggregate is not evidence about a named provider.
- An area employment or qualification count is not a vacancy count.
- Advertised provider pay, sector vacancies and labour-market context remain
  separate evidence layers.
- Never annualise an advertised hourly rate or convert between pay periods.
- Never compute “provider pay versus ASHE” ratios, pay gaps or workforce
  normalisations in this module.
- Never difference workforce or survey years unless the publisher explicitly
  defines a comparable series and the project has separately approved that
  operation.
- A suppressed or unavailable observation is NULL/unknown with its published
  text and status retained, not zero.
- A change in Nomis dimensions, codelists, geography type or response shape
  creates a review item and fails the affected source slice loudly.
- Data must be joined to existing authority records by a verified geographic
  code where available. Name-only provider or authority matching is not
  acceptable.
- The public catalogue must expose the source and limitations, not only a
  rendered number.

## 7. Proposed integration approach

This is a design for a later implementation issue. JON-16 itself does not
implement it.

### 7.1 Source boundary

Use a separate source-system identifier such as `nomis` or
`nomis_labour_market`. Do not write Nomis payloads into the existing
`ons_ashe` provenance namespace.

At minimum, distinguish:

- `nomis_ashe_resident`;
- `nomis_ashe_workplace`;
- `nomis_aps_resident`;
- `nomis_aps_workplace`;
- `nomis_census_2021`.

Keep direct ONS ASHE rows in their existing table/source namespace for regional
and country occupation/industry analyses.

### 7.2 Normalised observation contract

A future table or equivalent source-specific contract should retain:

- source system;
- Nomis dataset/API reference;
- dataset title and source publisher;
- analysis type, such as resident/workplace;
- dataset vintage/version if exposed;
- geography code, original Nomis geography code and geography type;
- resolved GSS/ONS code where a deterministic mapping exists;
- geography label as published;
- dimension names, codes and labels;
- measure/item/pay/sex/working-pattern selections;
- exact time/reference-period text;
- numeric value;
- original observation text;
- observation status, confidence, suppression or quality marker where
  published;
- source page URL;
- exact API request URL;
- retrieval timestamp;
- HTTP status;
- payload SHA-256;
- parser/collector version;
- review state and any failure reason.

The original Nomis codes and labels must be retained even after mapping to an
internal GSS code. A mapping change must not rewrite historical source
identity.

### 7.3 Update and revision handling

Nomis has rolling latest selectors and publishes revised values. The
collector should:

- discover the current dataset definition at run time;
- record the selected date/reference period explicitly;
- retain the source's revision or provisional wording;
- upsert by source dataset, analysis, geography, dimensions and reference
  period, with source version/provenance retained;
- preserve prior payloads or immutable source snapshots according to the
  existing archive policy;
- surface a changed value or revised source payload as a new provenance state,
  not silently overwrite the audit trail;
- avoid using “latest” in a public citation without recording which period it
  resolved to.

### 7.4 Failure and review handling

Use the existing shared HTTP, archive, review-queue and provenance
machinery where compatible. Add review outcomes for at least:

- dataset unavailable;
- dataset definition changed;
- required dimension or code missing;
- geography mapping unresolved;
- response shape changed;
- suppressed/non-numeric observation;
- source rate/concurrency refusal;
- partial pagination;
- revision or provisional status changed.

A source failure must not clear the previous successful evidence snapshot or
publish an empty replacement.

### 7.5 Public presentation

A future public view should label:

- Nomis/ONS as the publisher/service boundary;
- resident versus workplace analysis;
- source dataset and reference period;
- geography type;
- metric definition and unit;
- provisional/revised/suppressed state;
- the fact that the figure is area context, not provider evidence.

Any provider page may link to the context as a separate comparator, but the
system must not render a Nomis figure as though it describes that provider.

## 8. Implementation-ready acceptance criteria for a later build issue

A follow-on implementation issue should not be considered complete unless all
of the following are true:

1. A source-specific Nomis collector is added without changing the meaning of
   existing direct ONS ASHE rows.
2. The collector discovers and validates dataset definitions, dimensions,
   codelists and geography types before requesting observations.
3. The first supported slice includes both ASHE resident and workplace
   local-authority headline measures, with their analysis types explicit.
4. APSNEW is either implemented with a named supported slice or explicitly
   deferred with the reason and verified source boundary recorded.
5. No local-authority ASHE occupation/industry earnings query is attempted as
   though it were supported; direct ONS remains the documented path for
   regional/country breakdowns.
6. Every stored observation carries the complete source request, source page,
   dataset reference, reference period, source codes, retrieval timestamp and
   payload hash.
7. Authority joins use deterministic GSS/ONS mappings and retain the original
   Nomis geography code/type.
8. Source revisions, provisional values, suppressed values and changed
   codelists are represented explicitly and are never silently converted to
   zero or deleted.
9. API requests are polite, bounded and paginated, with tests covering
   concurrency limits, cell/record limits, timeouts, 4xx/5xx responses and
   changed response shapes.
10. The public projection keeps Nomis context separate from provider pay,
    vacancy observations, treatment data and other evidence layers.
11. No prohibited ratio, annualisation, cross-layer arithmetic or provider
    attribution is introduced.
12. Fixtures cover at least one resident ASHE response, one workplace ASHE
    response, one APS response, one suppressed/non-numeric observation, one
    revised/provisional period and one unmapped/changed geography outcome.
13. Operator review can inspect the raw aggregate payload and accept or reject
    a source change before public promotion.
14. Documentation updates `docs/CAVEATS.md`, `docs/SOURCES.md` and the data
    dictionary before enabling the source.
15. Tests pass offline against fixtures, and a live smoke test records the
    exact source versions and URLs used.

## 9. Decision

**Decision: feasible for selective Post-V1 implementation; do not implement in
JON-16.**

Prioritise:

1. ASHE resident/workplace local-authority headline earnings and hours;
2. APSNEW residence-based employment, inactivity and qualification context;
3. APSW only if a workplace-based question is required;
4. dated Census 2021 occupation, industry and qualification context where the
   historical baseline is useful.

Do not use Nomis for local-authority occupation/industry ASHE earnings. Keep the
existing direct ONS module for supported regional/country occupation and
industry slices. Create a separate implementation issue when the source is
scheduled, with explicit human approval before public enablement.

## 10. Sources checked on 2026-09-13

- [Nomis REST API guide](https://www.nomisweb.co.uk/api/v01/help?uid=0xd57c2bd58aa382ddb5cae1383cbe476f36609e57)
- [Nomis ASHE guidance](https://www.nomisweb.co.uk/articles/1449.aspx)
- [Nomis ASHE workplace dataset](https://www.nomisweb.co.uk/datasets/ashe)
- [Nomis ASHE resident dataset](https://www.nomisweb.co.uk/datasets/asher)
- [Nomis APSNEW dataset](https://www.nomisweb.co.uk/datasets/apsnew)
- [Nomis APSW dataset](https://www.nomisweb.co.uk/datasets/apsw)
- [Nomis Census 2021 TS060 industry](https://www.nomisweb.co.uk/datasets/c2021ts060)
- [Nomis Census 2021 TS064 occupation](https://www.nomisweb.co.uk/datasets/c2021ts064)
- [Nomis Census 2021 TS067 qualifications](https://www.nomisweb.co.uk/datasets/c2021ts067)
- [Nomis terms and conditions](https://www.nomisweb.co.uk/home/terms.asp)
- [ONS ASHE survey information](https://www.ons.gov.uk/surveys/informationforbusinesses/businesssurveys/annualsurveyofhoursandearningsashe)
- [ONS Open Government Licence statement](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)
- SectorTrace [`docs/CAVEATS.md`](https://github.com/Jonfuk/cglpay.us-SectorTrace/blob/beta/docs/CAVEATS.md)
- SectorTrace [existing direct ONS ASHE module](https://github.com/Jonfuk/cglpay.us-SectorTrace/blob/beta/pipeline/modules/m21_ons_ashe.py)
