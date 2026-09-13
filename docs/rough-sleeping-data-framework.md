# Monthly Rough Sleeping Data Framework — feasibility (JON-40)

**Status: research only.** No code, migration or module changed. Written
against commit `5e0c338` with a clean tree, as the bounded assignment for
JON-40 ("Add monthly Rough Sleeping Data Framework alongside m29 annual
snapshots"), whose readiness label (Not scheduled / Post-V1) requires a named
human decision before any of §7 is built. This document verifies current
source availability, licensing, coverage and repository state, and sets out
an integration approach and open decisions — not an implementation, per the
ticket's own acceptance criteria.

Every factual claim below was checked live against the GOV.UK content API or
a downloaded copy of the current release's own ODS file, not against a
description of either. One useful negative result from that discipline: an
AI-generated summary of the release's landing page claimed each quarterly
edition "contains only current-quarter data" and that "London" is measured
as a single aggregate area rather than by individual borough. Both are
wrong — downloading the actual file and reading its own sheet headers and
rows shows every table restates the full history to date (§3), and Westminster,
Camden and the City of London all appear as their own separate rows with
their own ONS codes in the same table used to headline the release (§4). Where
this document states something as confirmed, it means confirmed against the
primary file or a live API call made while writing it, not against a
secondary summary of either.

## 1. What already exists (read before proposing anything new)

| Module | Covers | Evidence layer |
|---|---|---|
| `m29_rough_sleeping` | MHCLG annual autumn rough-sleeping snapshot (`rough_sleeping_snapshot`), 2010 to date, one count and one MHCLG-published rate per authority per year | `comparator` — never combined with sector evidence |
| `m30_statutory_homelessness` | MHCLG quarterly H-CLIC Table A1 (`statutory_homelessness_snapshot`) | `comparator` |
| `m31_temporary_accommodation` | MHCLG quarterly Table TA1 (`temporary_accommodation_snapshot`, `temporary_accommodation_breakdowns`) | `comparator` |

`m29_rough_sleeping.py` already knows this second source exists and already
excludes it, deliberately, in its own docstring and code:

> "the newer, differently-shaped quarterly 'Rough Sleeping Data Framework'
> management-information collection published on the same evergreen page — a
> separate source with its own metrics, not read by this module."

and its `SNAPSHOT_ATTACHMENT_RE = re.compile(r"rough sleeping snapshot", re.IGNORECASE)`
matches attachment titles containing "rough sleeping snapshot" only — a title
of "Rough sleeping data framework, April to June 2026 - data tables" does not
match, by construction, not by accident. **This ticket does not touch `m29`,
its table, its regex, or its docstring.** Nothing here changes because the
two sources now coexist; `m29` was already written expecting that.
`docs/CAVEATS.md`'s Module 29 entry, its "comparator, never combined" rule,
and the `EVIDENCE_LAYERS["comparator"]` classification in
`pipeline/web/datasets.py` all stay exactly as they are.

## 2. What the Rough Sleeping Data Framework actually is

MHCLG launched it in May 2023 with the Centre for Homelessness Impact and
five pilot areas (London, Greater Manchester, Newcastle, West Midlands, and
Bournemouth, Christchurch and Poole), then extended it to all English local
authorities. Local authorities submit monthly management information through
MHCLG's DELTA system; MHCLG publishes it quarterly, each release covering the
three months since the last one, alongside a technical note and a Power BI
dashboard.

It is layered on top of an older MHCLG monthly monitoring collection, not a
clean-slate replacement of it — confirmed directly in the current release
file, not asserted from memory: the plain monthly rough-sleeping count table
(`Table_1_Monthly`) has columns going back to **October 2020**, and the
single-night count (`Table_3_Single_Night`) back to **June 2020** — both
years before "Rough Sleeping Data Framework" as a name existed, from the
COVID-era emergency-accommodation monitoring MHCLG was already running. The
framework's own new indicator tables (institution-leaver breakdowns,
long-term rough sleeping, returners) start at **May 2023**, the framework's
launch month, and a further group (accommodated outcomes, nights-bedded-down
bands, returners from settled accommodation) starts at **June 2024** — a
second wave of additions, not present from launch. §4 has the full table.

**This is explicitly management information, not official statistics**,
stated by MHCLG in its own technical notes and printed verbatim on every one
of the 29 worksheets in the file itself:

> "All figures are estimates based on unverified management information."

This is a stronger and more specific caveat than "estimate" alone — MHCLG is
stating the underlying local-authority submissions are not independently
verified, on every sheet, not once in a methodology appendix. Whatever this
project stores from this source needs to carry that label somewhere a reader
sees it, distinctly from `m29`/`m30`/`m31`, none of which carry an
equivalent disclaimer (see §6).

Licensing is unremarkable and matches every other MHCLG source already in
`docs/SOURCES.md`: "© Crown copyright. This publication is licensed under
the terms of the Open Government Licence v3.0 except where otherwise
stated," confirmed on the current technical-notes page. No new licence
question.

## 3. Verified live today — where it actually is

**The current edition sits on the same evergreen page `m29` already fetches.**
A live GET of `https://www.gov.uk/api/content/government/statistical-data-sets/tables-on-rough-sleeping`
(`m29`'s own `CONTENT_URL`) today returns two attachments, not one:

1. `Rough sleeping snapshot in England: autumn 2025 - tables` (`.ods`, 356 KB) — the annual file `m29` reads.
2. `Rough sleeping data framework, April to June 2026 - data tables` (`.ods`, 1.43 MB) — the current RSDF edition.

`m29` fetches this same URL every run already; the current-quarter RSDF
attachment is sitting right there, unread, filtered out by
`SNAPSHOT_ATTACHMENT_RE` on every pass. A module reading the RSDF file could
reuse the exact same content-API fetch `m29` already makes rather than a
second network round trip — see §7.

**Each historical edition is also its own standalone GOV.UK publication.**
Unlike `m29`'s single evergreen page, RSDF editions are separate publications
under slugs like `/government/publications/rough-sleeping-data-framework-april-to-june-2026`,
collected under the `government/collections/homelessness-statistics`
document collection (the same collection `m29`/`m30`/`m31` already cite as
their `official_url` in `pipeline/web/datasets.py`) in a group titled "Rough
sleeping." Walking that collection's content API live today lists 11 dated
editions, oldest to newest:

| Edition | Published |
|---|---|
| Ending Rough Sleeping Data Framework, September 2023 | 2023-11-30 |
| Ending Rough Sleeping Data Framework, December 2023 | 2024-02-29 |
| Rough Sleeping Data Framework, June 2024 | 2024-10-02 |
| Rough Sleeping Data Framework, September 2024 | 2024-11-28 |
| Rough Sleeping Data Framework, December 2024 | 2025-02-27 |
| Rough Sleeping Data Framework, January to March 2025 | 2025-06-04 |
| Rough sleeping data framework, April to June 2025 | 2025-10-16 |
| Rough sleeping data framework, July to September 2025 | 2025-11-28 |
| Rough sleeping data framework, October to December 2025 | 2026-04-20 |
| Rough sleeping data framework, January to March 2026 | 2026-05-28 |
| Rough sleeping data framework, April to June 2026 | 2026-08-27 |

Two things worth carrying forward from that list alone: the title format
changed from a single month ("June 2024") to a quarter range ("April to June
2026") starting with the January–March 2025 edition, so a date cannot be
parsed reliably out of the publication title across the whole series — the
same lesson `m29`'s own `YEAR_HEADER_RE` already encodes (read the file's own
header row, not the filename or title). And earlier editions were titled
"Ending Rough Sleeping Data Framework" rather than "Rough Sleeping Data
Framework" — cosmetic, but another reason to match on the stable
`rough sleeping data framework` substring rather than the full title.

**The load-bearing finding: a single current fetch already captures the
whole history, the same shape as `m29`.** Downloading the April–June 2026
file directly and reading its own sheet headers (not the release page, not a
summary of it) shows every one of its 29 tables is one row per local
authority with one column per month, running from that indicator's own start
date to the current month — not reset each quarter. `Table_1_Monthly`'s
header row runs "October 2020, November 2020, December 2020, …" through to
the latest month; nothing about the file's shape suggests only the covered
quarter is present. This means the 11-edition collection walk above is not
needed to reach history — a single fetch of the evergreen page's current
attachment, read the same way `m29` reads its own file, already gets
everything MHCLG currently publishes for every indicator, back to whenever
that indicator started. The collection walk still has one legitimate use:
recovering an edition GOV.UK has since superseded, which matters for
revisions — see §6.

## 4. Coverage

The file has 29 worksheets. Grouping them by what they measure and when
their columns start (confirmed against the current file, not the technical
note's prose):

| Sheet(s) | Measures | Columns start | Frequency |
|---|---|---|---|
| `Table_1_Monthly` / `Table_2_Monthly_Rate` | People sleeping rough over the month, count and MHCLG's own rate per 100,000 | October 2020 | Monthly |
| `Table_3_Single_Night` / `Table_4_Single_Night_Rate` | People sleeping rough on a single night, count and rate | June 2020 | Monthly |
| `Table_6_Monthly_New` | New rough sleepers (not seen in that authority in the preceding 60 months) | May 2023 | Monthly |
| `Table_7_Institutions` | Left an institution (any of the categories below) in the last 85 days | May 2023 | Monthly |
| `Table_8_Prison` / `Table_9_OJA` / `Table_10_Hospital` / `Table_11_UKAF` / `Table_12_Asylum` | The five institution sub-categories: prison, other justice accommodation, hospital, UK armed forces, asylum support | May 2023 | Monthly |
| `Table_13_Under_25_Care` | Under-25 care leavers sleeping rough (no 85-day window) | May 2023 | Monthly |
| `Table_14_Under_25` | All under-25s sleeping rough | April 2022 | Monthly |
| `Table_15_Long_Term` | Seen sleeping rough in 3+ of the last 12 months | May 2023 | Monthly |
| `Table_16`–`Table_21` | Nights bedded down in the last 180 days, banded (1 / 2 / 3–5 / 6–10 / over 10 / unknown) | June 2024 | Monthly |
| `Table_22_Returners` | Returning after 2+ quarters with no contact | May 2023 | Monthly |
| `Table_23_Returners_from_accom` | Returners who had moved into settled accommodation in the last 12 months | June 2024 | Monthly |
| `Table_5_Accommodated` | Moved into accommodation over the month | June 2024 | Monthly |
| `Table_24_Gender` | Female / male / other / total | ~2025 | Monthly |
| `Table_25_Nationality` | UK / EEA / non-EU / unknown | ~2024 | **Quarterly** (columns step Jun→Sep→Dec) |
| `Table_26_Immigration` | Access-to-public-funds status categories | ~2024 | **Quarterly** |
| `Table_27_Monthly_RUC` / `Table_28_Single_Night_RUC` | Same monthly/single-night counts, by 2021 Rural Urban Classification instead of by authority | October 2020 | Monthly |
| `Table_29_Survey_Questions` | The survey instrument itself, not data | — | — |

Every table is local-authority-level: `Table_1_Monthly` alone has 296
individual authority rows (Westminster, Camden and the City of London each
their own row, not a London aggregate — confirmed by reading the rows, not
the release commentary). Coverage is stated by MHCLG as all English local
authorities, with imputed figures substituted for the roughly 2% of
authority-months that do not submit — an accuracy caveat, not a coverage
gap, and one this pipeline has no way to distinguish from a genuine
authority figure unless MHCLG marks it, which the file does not appear to
do in a separate column.

Two demographic-frequency details worth keeping distinct, confirmed from the
header rows themselves: gender is collected and published **monthly**
(`Table_24_Gender`'s columns step one month at a time); nationality and
immigration status are collected and published **quarterly**
(`Table_25`/`Table_26`'s columns step Jun→Sep→Dec). A module reading all
three tables generically needs to handle two different column cadences in
the same workbook, not one.

Definitions worth carrying into a schema's own documentation rather than
re-deriving from the numbers (from the file's own "Notes" sheet):

- **New**: not seen sleeping rough in that authority in the preceding 5
  calendar years (60 months) — or, absent 5 years of history, anyone seen
  for the first time while that history is being built up.
- **Institution leaver**: discharged from prison, other justice
  accommodation, hospital, UK armed forces or asylum support within the
  last 85 days (the CAS3 temporary-accommodation window); under-25 care
  leavers are included without the 85-day limit.
- **Long-term**: seen sleeping rough in 3 or more of the last 12 months.
- **Returner**: seen sleeping rough again after 2+ quarters (180 days) with
  no contact.
- **Returner from accommodation**: a returner who had moved into "settled
  accommodation" (MHCLG's own six-category definition, including social
  and private rented tenancies, supported accommodation, and longer-stay
  hostel placements) within the preceding 12 months.

## 5. Data quality, comparability and what not to compute from it

- **"Unverified management information," printed on every sheet** — treat
  every figure here with at least the same caution as `m30`'s "figure
  reflects whichever edition was last fetched" caveat, and more: MHCLG is
  explicitly not vouching for local-authority accuracy, not merely warning
  about methodology variance the way the annual snapshot's caveat does.
- **The framework's own technical note states its categories overlap.** A
  person can appear in more than one of `Table_6` (new), `Table_7`
  (institution leaver), `Table_15` (long-term) and `Table_22` (returner) in
  the same month — these are described as attributes of a rough sleeper
  that month, not mutually exclusive buckets. **Summing across these tables
  to reconstruct a total, or subtracting one from `Table_1_Monthly` to
  infer an "other" category, is exactly the arithmetic `docs/CAVEATS.md`'s
  first rule forbids** — narrower here than the usual cross-*source* case,
  because the double-counting risk is *within* this one source, across its
  own tables. Only `Table_1_Monthly` is a total; everything else is a
  labelled sub-population of it, and every sub-population figure should
  carry that framing wherever it is surfaced.
- **The "nights seen" bands (`Table_16`–`Table_21`) are stated by MHCLG to
  reflect outreach effort as much as street conditions** — an authority
  that does more outreach will record more distinct nights seen for the
  same person, so this indicator is explicitly flagged by the source itself
  as less comparable between authorities than the others.
- **Female rough sleeping is called out by MHCLG as under-captured**:
  outreach-based counting methods are stated to under-represent women's
  more hidden and intermittent rough-sleeping patterns. Any future portal
  surface of `Table_24_Gender` should carry that caveat, not present the
  ratio as a literal population split.
- **Revisions have no in-file marker, unlike `m30`.** `m30`'s workbook
  publishes a `(revised)` suffix on republished quarters, which that module
  reads and prefers explicitly. Nothing in RSDF's attachment titles, sheet
  names or the current file's own content signals that a given month's
  column has changed since an earlier edition published it — MHCLG's
  revisions policy (case-by-case correction notices for "substantial"
  errors) is prose on the technical-notes page, not a machine-readable flag
  in the data. Because every edition restates the full history (§3), a
  revision to (say) March 2024 would appear only as a silently different
  number in that column, in every edition published after the correction,
  with nothing marking that a change happened. See §6 — this is the
  concrete design tension the ticket's "preserve revisions" acceptance
  criterion is pointing at, and it needs a decision this document does not
  make.

## 6. Two existing, conflicting precedents for handling revisions

This project already has two different, both currently correct, answers to
"a monthly/quarterly source republishes a figure I've already stored — what
happens to the old value?", and RSDF's shape does not fit either one
cleanly:

- **`m27_ndtms_monthly`** keeps `report_version_id` in the row's natural key.
  A later NDTMS edition that changes a figure produces a *new* row rather
  than overwriting the old one — every version the source ever published is
  retained, distinguishable by which edition wrote it.
- **`m30_statutory_homelessness`** upserts on `(ons_code, quarter_start)`
  and explicitly overwrites: "a later run silently overwrites the earlier
  figures… this module always prefers a revised edition over the original."
  The file's own `(revised)` marker is what makes that safe — MHCLG is
  telling `m30` which edition to trust, in the data itself.

RSDF has `m30`'s single-natural-key shape (one figure per authority per
month per table, restated wholesale on every fetch) but not `m30`'s revision
marker to justify overwriting on that key. Adopting `m30`'s pattern here
would mean a correction silently replaces the previously stored figure with
no record that anything changed and no way to answer "what did MHCLG say
about March 2024 back in June 2024" after a later edition revises it —
exactly what JON-40's acceptance criterion ("preserve revisions") rules out.
Adopting `m27`'s pattern — an edition identifier (the collection-listed
publication slug, e.g. `rough-sleeping-data-framework-april-to-june-2026`,
or simply the edition's own covered-quarter label) as part of the natural
key alongside `(ons_code, month, table)` — keeps every edition's figure for
a given month as its own row, so a revision is visible as two rows differing
only in `source_edition`/`retrieved_at`, not a change nobody can see. That
is the recommendation this document makes for whoever scopes the build, not
a decision taken here: it is additive storage cost (one row per
edition-month-authority-table rather than one row per month-authority-table)
in exchange for the ticket's own stated requirement being actually met.

## 7. Integration approach (recommended, not built)

1. **Read the RSDF attachment from the same fetch `m29` already makes** — no
   second content-API call, just a second regex over the same `attachments`
   list already returned to `m29`'s `CONTENT_URL` GET, e.g.
   `RSDF_ATTACHMENT_RE = re.compile(r"rough sleeping data framework", re.IGNORECASE)`
   matched against attachment `title`. This gets the current edition's file
   with no new network surface.
2. **A single fetch is enough for history** (§3) — no collection walk is
   needed for the normal run, only for the edition-recovery case in §6 if
   that design is adopted; that would be a second, separate, occasional
   discovery path (walking `government/collections/homelessness-statistics`
   the way described in §3), not part of every run.
3. **New module and new tables**, not an extension of `rough_sleeping_snapshot`
   — the ticket is explicit that the annual snapshot stays unchanged, and
   the shapes do not fit the same table: RSDF is one row per
   authority-month(-edition), `m29` is one row per authority-year. A
   candidate module number is `m36` (next free after `m35_open_jobs`) and a
   candidate migration number is `0116` (next free after `0115`), both to
   be confirmed at build time rather than reserved now.
4. **A label distinguishing management information from official
   statistics does not exist anywhere in this schema today** — checked:
   `pipeline/web/datasets.py`'s `EVIDENCE_LAYERS` is a topical vocabulary
   (`comparator`, `treatment`, `finance`, …), not a statistics-status
   vocabulary, and no module or table carries an
   official-statistics/management-information flag. `m29`/`m30`/`m31` are
   all National/Official Statistics; RSDF is not. This needs a genuinely
   new field or a new documented convention (a `data_classification`
   column, or a per-dataset note in `pipeline/web/datasets.py` alongside
   the existing `caveat` string) — not something to bolt onto the existing
   `comparator` layer silently, since that layer's own label makes no
   statistics-status claim either way today.
5. **Every table needs its own natural key including the sub-population it
   represents** — a single `rsdf_observations` table with a `table_slug` or
   `indicator` column (mirroring `m07`'s generic `metrics_json` approach for
   NDTMS's own similarly wide indicator set) avoids 20+ near-identical
   tables, provided the natural key carries indicator identity explicitly so
   `Table_1_Monthly`'s total is never queried alongside `Table_6_Monthly_New`
   without a reader knowing they are different populations (§5).
6. **`[X]`/`[Z]` placeholders** appear in this workbook exactly as in `m29`'s
   (confirmed in the sheet header notes: "[X] = Not Available. [Z] = Not
   Applicable") — the same `_text`-plus-`NULL` pairing convention `m29`
   and `m30` already use applies directly, no new placeholder vocabulary to
   design.

## 8. Offline fixtures

A representative fixture needs, at minimum: one authority row with a full
run of months across a table-start boundary (to test the May-2023 and
June-2024 "table doesn't exist yet for this authority-month" cases), one
row using an `[X]`/`[Z]` placeholder, one quarterly-cadence demographic
table alongside a monthly one (to exercise the two-cadence-in-one-workbook
case from §4), and — if §6's edition-in-natural-key design is adopted — two
small fixture editions of the same month with a deliberately different
figure, to prove a revision produces two distinguishable rows rather than a
silent overwrite. None of this requires a live fetch to construct: the
sheet and column shapes above are enough to hand-build a small `.ods`
fixture the same way existing module tests already do for `m29`.

## 9. Recommended next decisions (none taken here)

1. **Decide the revision-preservation design** (§6) before writing any
   schema — this is the one decision that changes the shape of the natural
   key and therefore the migration, and the ticket names it explicitly as
   an acceptance criterion.
2. **Decide the management-information-vs-official-statistics labelling
   mechanism** (§7.4) — a new field/convention, scoped once rather than
   improvised per module later.
3. **Decide the table shape**: ~20 near-identical wide tables mirroring the
   workbook 1:1, or one generic `rsdf_observations`-style table keyed by
   indicator, weighing `m29`'s existing precedent of one purpose-built table
   per source against `m07`'s generic `metrics_json` precedent for a source
   this wide.
4. **Decide whether the demographic tables (`Table_24`–`26`) are in scope
   for this pass** — same source, same licence, but a materially different
   privacy/small-numbers profile than the headline counts, and no
   suppression convention (`m30`'s `[c]`) was found in this workbook's own
   placeholder set, worth confirming is genuinely absent rather than just
   unseen in the one edition inspected here.
5. **Confirm whether the edition-recovery collection walk (§3, §6) is worth
   building in the first pass** or deferred until a revision is actually
   observed in a live run — it adds a second discovery path for a case that
   has not yet been confirmed to occur in this source's actual history.

Every item above is a candidate for a named human decision, not an
implementation queue — consistent with this issue's Not-scheduled/Post-V1
readiness label.
