# OHID Fingertips / NDTMS contextual indicators — feasibility (JON-10)

**Status: research only.** No code, migration or module changed. Written
against commit `a459795` with a clean tree, as the bounded assignment for
JON-10 ("Explore OHID Fingertips contextual indicators"), whose readiness
label (Not scheduled / Post-V1) requires a named human decision before any
of §5 is built. This document is that decision material: feasibility,
access terms, provenance, integration approach and acceptance criteria,
per the ticket's own ask — not an implementation.

JON-10's brief was superseded mid-flight by a module-audit comment: Module
12 (Fingertips) already exists and covers the original ask, so this is not
a duplicate-collector proposal. It refocuses on two things the audit named
explicitly — Module 7 (NDTMS) cross-checks, and contextual indicators
including the Combating Drugs Outcomes Framework (CDOF) — plus the
population-context indicators (drug mortality, alcohol admissions, mental
health, homelessness, deprivation) named in JON-10's original description.

## 0. What already exists (read before proposing anything new)

| Module | Covers | Key caveat already in `docs/CAVEATS.md` |
|---|---|---|
| `m07_ndtms` | Annual NDTMS adult/young-people data-tables (mostly national; one LA sheet, deaths in drug treatment) + archived ViewIt wide export + live ViewIt Power BI capture | service-demand context, its own tables, never merged with the census |
| `m27_ndtms_monthly` | NDTMS monthly provisional statistics, per LA, scraped from the self-posting ASP.NET form | same evidence layer as m07 |
| `m12_fingertips` | 10 named indicator IDs (treatment numbers, successful completions, alcohol waiting times, OCU prevalence, treatment need, hospital admissions substance misuse 15–24) | unmet need not published/not derived; England/region rows kept as comparators only |
| `m29_rough_sleeping` / `m30_statutory_homelessness` / `m31_temporary_accommodation` | MHCLG rough-sleeping snapshot, H-CLIC Table A1, Table TA1 | comparator, never combined with sector evidence; no cross-layer arithmetic |
| `m09_cdp_documents` | Discovery of each authority's own CDP strategy / needs-assessment / **outcomes-framework** documents, human-confirmed | discovery, not extraction; nothing lands without a person |

`m09_cdp_documents` already has an `outcomes_framework` document-type pattern
— it finds a council's own local CDOF-related PDFs. That is unstructured
document discovery, unrelated to the structured national CDOF metrics this
document is about; the two are complementary, not overlapping.

## 1. What the Combating Drugs Outcomes Framework actually is

CDOF is **not a dataset, an API, or a Fingertips profile**. It is a
DHSC/Home Office/OHID cross-agency measurement framework under the 2021
drugs strategy ("From Harm to Hope"): 11 headline metrics and 22 supporting
metrics across three strategic outcomes (reduce drug use, reduce
drug-related crime, reduce drug-related deaths and harm) and three
intermediate outcomes (reduce drug supply, increase engagement in
treatment, improve recovery outcomes). Each metric is sourced from a
**different existing system** — there is nothing to fetch under a "CDOF"
name; every metric is (or isn't) already reachable through a source this
project already knows how to talk to, or doesn't.

Source: [National Combating Drugs Outcomes Framework — supporting metrics
and technical guidance (accessible
version)](https://www.gov.uk/government/publications/drugs-strategy-national-outcomes-framework/national-combating-drugs-outcomes-framework-supporting-metrics-and-technical-guidance-accessible-version),
Crown copyright, **OGL v3** ("licensed under the terms of the Open
Government Licence v3.0 except where otherwise stated"). Every metric's own
*data*, in turn, inherits its own source's licence — for every source named
below that is also OGL v3 / Crown copyright (ONS, NHS Digital, DfE, MHCLG,
GOV.UK collections, Fingertips). Fingertips itself states the same OGL v3
terms and asks for the citation "Office for Health Improvement &
Disparities. Public Health Profiles. [date accessed] fingertips.phe.org.uk
© Crown copyright [year]" on every indicator — consistent with the citation
convention `docs/SOURCES.md` already uses for other OGL sources.

## 2. Coverage assessment, metric by metric

Each CDOF metric below is dispositioned against what this project already
collects, what a genuine gap looks like, and what is out of reach or out of
scope. "LA-level" means the metric's own publication carries a per-local-
authority breakdown; "public" means reachable without a data-sharing
agreement.

### Reduce drug use

| Metric | Source | LA-level | Public | Disposition |
|---|---|---|---|---|
| OCU prevalence | GOV.UK prevalence estimates | Yes | Yes | **Already collected** — `m12` indicator 91117, correctly kept separate from treatment numbers (see unmet-need caveat below). |
| CSEW drug use in last year (16–24, 16–59) | Crime Survey for England and Wales (ONS) | Not clearly published below region | Yes | **Gap, low priority.** Survey-based; verify LA-level breakdown exists before treating as a candidate — not confirmed in this pass. |
| Young people's drug use (11–15) | NHS Digital "Smoking, drinking and drug use among young people" | Not stated | Yes | **Gap, low priority.** Biennial, school-based, no LA breakdown found. |
| Households owed a homelessness duty with a drug-dependency need | MHCLG statutory homelessness statistics (the same workbook `m30` already fetches) | Yes | Yes | **Gap, concrete integration path.** `m30`'s own docstring says it deliberately reads only Table A1 ("reading one table properly this cycle beats reading many badly") and explicitly names "multiple-disadvantage breakdowns" as one of the 40+ tables not read. The drug-dependency support-need breakdown lives in that unread table set. Extending `m30` to also read it is additive to an existing module, not a new collector — and it stays a **comparator**, under the same "never combined with sector evidence" rule as Table A1/TA1, because it is exactly the overlapping-population case that rule already exists for. |
| Children in need with drugs as an assessed factor | DfE, Explore Education Statistics | Yes | Yes | **Gap, new source, low priority.** Not touched by any current module; flagged, not recommended, given distance from the pay-campaign evidence this project exists to build. |
| Permanent exclusions/suspensions (drug/alcohol-related) | DfE education statistics | Yes (proportion of enrolments) | Yes | Same disposition as above. |
| Alcohol dependency prevalence | GOV.UK / OHID prevalence estimates | Yes | Yes | **Gap.** Distinct from the treatment-numbers indicators `m12` already has; would need its own Fingertips (or GOV.UK dataset) indicator ID confirmed before adding — see §3. |

### Reduce drug-related crime / reduce drug supply

Homicide, neighbourhood crime, reoffending, police-recorded drug offences,
county lines, organised-crime disruptions, seizures, prison drug finds,
modern-slavery referrals. **All out of scope.** Most are not published at
local-authority level (police force area, England-and-Wales, or England-
only aggregates); several — county lines closures, NCA/Home Office seizure
and disruption figures — are stated as internal management information,
i.e. not public at all. None of this sits near a substance-misuse
workforce pay campaign's evidence needs. **Recommendation: decline.**

### Reduce drug-related deaths and harm

| Metric | Source | LA-level | Public | Disposition |
|---|---|---|---|---|
| Deaths related to drug misuse | ONS deaths-related-to-drug-poisoning reference tables | Region-level in the headline table | Yes | Also published as a **Fingertips indicator** — confirmed live via the Fingertips indicator-search API: **indicator ID 92432**, "Deaths from drug misuse", present under area types 6/15/202/301/302/501/502 (the same England/region/LA area-type family `m12` already classifies). **Not currently in `pipeline/fingertips_indicators.py`.** Genuine, concrete gap — see §3. |
| Hospital admissions for drug poisoning / drug-related mental and behavioural disorders | NHS Digital | Yes | Yes | Distinct from `m12`'s existing indicator 90808 (substance misuse admissions, ages 15–24 only, from OHID's own "additional metric" list). The CDOF headline metric has no age restriction — a different Fingertips indicator ID, not yet identified in this pass. **Gap, needs its own ID lookup before it can be added.** |
| Deaths during treatment contact | OHID | Yes | **No** — explicitly "restricted OHID reporting (local-facing reports)" | **Decline — not public.** |
| Hepatitis C prevalence in people who inject drugs | Unlinked Anonymous Monitoring Survey | Not stated | Yes | **Gap, low priority**, different source family, COVID-affected recruitment noted in the framework's own text. |
| Alcohol-specific deaths | Fingertips, Local Alcohol Profiles for England | Yes | Yes | Confirmed live via the same search API: **indicator ID 91380**, present under area types 6/15/402/502 — the 402/502 pairing is the same discontinued/current-geography vintage split `m12` already handles for indicators 91123/91182. **Not currently collected.** Genuine, concrete gap — see §3. |
| Alcohol-attributable hospital admissions | NHS Digital / Fingertips (Local Alcohol Profiles) | Yes | Yes | Same profile family as alcohol-specific deaths; likely reachable the same way, indicator ID not yet identified in this pass. **Gap, needs its own ID lookup.** |

### Increase engagement in treatment / improve recovery outcomes

Numbers in treatment, prison continuity of care, treatment progress,
stable accommodation, paid/voluntary work, training/education, mental
health interventions, parental/family interventions, substance-specific
cessation in young people — every one of these is sourced "OHID/NDTMS",
England-only, LA-level.

This is the m07 cross-check the module audit asked about, and the
finding is **structural, not a data gap**: `m07`'s ViewIt Power BI capture
(`pipeline/transports/powerbi.py`) already walks report pages named
`"Mental health treatment need"`, `"Interventions"`, and `"Outcomes of
treatment received"` — the same categories these CDOF metrics live under —
and stores whatever cells that dashboard exposes generically as
`ndtms_powerbi_observations` / `ndtms_viewit_archive_rows.metrics_json`,
by design, precisely so the pipeline does not have to hardcode NDTMS's own
metric vocabulary. Numbers in treatment (the CDOF headline metric here) is
separately confirmed as already double-covered: `m07`'s own LA sheet and
`m12`'s indicators 92454/92455/91182 both carry it, from the same
ultimately-NDTMS-derived figures — see §4 for why that overlap is a
comparator opportunity, not a duplication to fix.

**What is genuinely missing is not collection, but a verified mapping**:
which `metric_raw` values already sitting in `ndtms_powerbi_observations`
correspond to which named CDOF supporting metric. That is a live-data
inspection task (reading what a real run actually captured), not a build —
recorded as an open question in §5, not attempted here since it needs a
populated database this research pass does not have.

Prison continuity of care is separately marked in the framework's own text
as "restricted OHID/CDP reporting" for its LA-level detail — **decline**
that one specifically, same reasoning as deaths-in-treatment above.

### Deprivation

CDOF does not reference deprivation indices anywhere in its own metric
list — this was in JON-10's original brief independently of CDOF, not
something the module audit connects to it. The standing candidate is the
**English Indices of Deprivation** (MHCLG, most recently IMD2019, next due
under the government's own release cycle), published per lower-layer super
output area and rolled up to an LA-level average score/rank. It is a
single flat-file release every several years, OGL-licensed, structurally
simple. Storing a published IMD score or rank verbatim is consistent with
the house style already applied to MHCLG's own `rate_per_100k` on rough
sleeping — "this pipeline never derives a rate itself" — not a new kind of
composite-score risk, because the composite is the source's own published
figure, not one computed here. **Gap, feasible, but a separate decision**
from CDOF; flagged for its own scoping if wanted.

### Mental health (general population)

CDOF's own "mental health interventions received" metric is an in-treatment
NDTMS measure, already covered above. JON-10's original brief also named
mental health as a broader population-context indicator; Fingertips
carries general mental-health profiles (e.g. severe mental illness
prevalence) separate from CDOF entirely. Not investigated further in this
pass — flagged as a distinct, lower-priority candidate requiring its own
indicator-ID lookup, not something this ticket's CDOF refocus obliges.

## 3. Integration approach for the confirmed Fingertips gaps

Both identified gaps — indicator 92432 (deaths from drug misuse) and 91380
(alcohol-specific mortality) — are additive entries in
`pipeline/fingertips_indicators.py`'s `INDICATORS` dict. `m12`'s `run()`
already iterates that dict generically; **no module code change is
needed**, only:

1. A human confirms each ID against `indicator_metadata/by_indicator_id`
   (the same metadata call `m12._store_metadata` already makes) before it
   is added — the file's own docstring is explicit that IDs are listed by
   hand rather than discovered by search precisely so a series cannot
   silently gain or lose a measure between runs; this document's
   search-API confirmation is a starting point for that check, not a
   substitute for it.
2. Each new ID gets its own `slug`/`topic`/`substance`, and an
   `AREA_TYPE_OVERRIDES` entry if — as the 402/502 area-type pattern found
   for 91380 suggests — its current-geography series is thin or
   discontinued, the same way 91123/91182 are handled today.
3. Two hospital-admissions candidates (drug poisoning/mental-behavioural
   disorders; alcohol-attributable admissions) need their own indicator-ID
   lookup before they can be added at all — not attempted here.

No new migration, no new provenance shape, no new licence question: these
land in the existing `fingertips_indicators` / `fingertips_la_values`
tables under the same OGL-v3 sourcing `m12` already carries.

## 4. NDTMS ↔ Fingertips "cross-check" — what it can defensibly mean

`m07` (NDTMS's own published LA sheet, monthly reports and ViewIt exports)
and `m12` (Fingertips, whose numbers-in-treatment indicators OHID itself
compiles from NDTMS) are two views of overlapping underlying data, not two
independent sources. Settled decision #2 ("no composite scores or
cross-source arithmetic") and the comparator convention already applied to
Modules 29–31 rule out one reading of "cross-check": this project cannot
compute a reconciliation delta between the two and present it as a
finding, for the same reason it does not subtract prevalence from
treatment numbers to manufacture "unmet need" — different vintages,
rounding and definitional boundaries would produce a difference that means
nothing.

What **is** defensible, in the same shape as the existing rough-sleeping /
statutory-homelessness "Comparators" pattern: a read-only query or portal
view placing `m07`'s own published LA numbers-in-treatment next to `m12`'s
Fingertips numbers-in-treatment indicator for the same authority and
period, each carrying its own `source_system` and provenance, with an
explicit caveat that any difference is a publication-vintage/definition
artefact and not a data-quality signal. That is a portal/query feature
(and, per settled decision #7, public-portal work — `/api/v1/*`, not
`/api/admin/*`), out of this research ticket's own scope; it is recorded
here as the one legitimate reading of "NDTMS cross-check" for whoever
scopes that work next.

## 5. Recommended next decisions (none taken here)

1. **Add indicators 92432 and 91380 to `m12`** once a human has confirmed
   both against the Fingertips metadata endpoint — smallest, lowest-risk
   item here, additive to an existing, working module.
2. **Look up indicator IDs** for the two hospital-admissions candidates
   (drug poisoning/mental-behavioural admissions; alcohol-attributable
   admissions) before deciding whether to add them alongside (1).
3. **Inspect a real populated `ndtms_powerbi_observations` run** to map
   its `metric_raw` vocabulary against CDOF's named recovery-outcome
   supporting metrics (stable accommodation, employment, mental health
   interventions, parental interventions, cessation) — a data-inspection
   task, not a build, and the concrete next step for the "m07 cross-check"
   the module audit asked about.
4. **Decide whether to extend `m30`** to read the MHCLG support-needs
   table (drug-dependency flag) alongside its existing Table A1 read, as
   a homelessness comparator attribute — same "never combined with sector
   evidence" caveat as today.
5. **Decide separately whether IMD deprivation data is wanted at all** —
   unconnected to CDOF, a standalone scoping question.
6. **Decline**: CDOF's crime/supply-side metrics (not LA-level for the
   most part, several literally internal-only), CDOF's own derived
   "unmet need" metrics (this project already refuses that arithmetic and
   the fact that CDOF's official framework computes it is not a reason to
   start), deaths-in-treatment-contact and prison-continuity-of-care
   detail (both explicitly restricted to CDP-only reporting), and the
   DfE children-in-need/exclusions metrics (public, but a new source
   family at a distance from this project's pay-campaign purpose).

Every item above is a candidate for a named human decision, not an
implementation queue — consistent with this issue's Not-scheduled/Post-V1
readiness label.
