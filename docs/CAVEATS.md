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
not be used to infer that the workforce size overall" changed.

**Do not attribute any census figure to a named provider.** The census
publishes sector aggregates only; there is no provider-level breakdown. The
schema has no provider column for this reason.

**Do not read `indicative_wage_per_head` as a salary.** See below.

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
  not absent.

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

### CQC (Module 5)

- **This is not a service map.** CQC registration covers only some service
  types — residential detoxification, inpatient and certain prescribing
  services. Most community drug and alcohol provision is not CQC-registered.
- Counting locations per authority does not measure service coverage, and
  absence of a location does not mean absence of a service.

### Workforce census (Module 6)

- Years are not like-for-like (see above).
- **Every metric is unverified until a human checks it.** `verified = 0` is the
  default; `docs/verification/census_{year}_tables.md` pairs each parsed value
  with the source line it came from. Filter on `verified` before publishing.
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

- **Coverage is 1 of 153 authorities.** Both modules need each council's
  publication URL, which cannot be derived — council hostnames are genuinely
  unpredictable. The registry holds only entries verified by request; the other
  152 authorities are in `review_queue`. This is the binding limitation on both
  modules.
- Nothing is promoted without human verification. A candidate is a URL that
  looked right, which is not the same as a document that is what it claims.
- **ModernGov's document search cannot be driven by a GET request.** It answers
  with a 302; it is an ASP.NET form needing a POST with viewstate, which is not
  implemented. Affected authorities are recorded as
  `moderngov_search_requires_post` rather than reported as searched.

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
