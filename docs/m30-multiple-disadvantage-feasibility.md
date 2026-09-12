# Multiple Disadvantage Detailed Local Authority Data — feasibility (JON-39)

**Status: research only.** No code, migration or module changed. Written
against commit `55fde50` with a clean tree, as the bounded assignment for
JON-39 ("Extend m30 with Multiple Disadvantage local-authority data"): "Rank
7. Verify the reported August 2026 detailed LA file and its
definitions/coverage. Capture substance misuse, mental health, homelessness
and complex-need indicators as published, preserving suppression, periods
and geography. Avoid individual or provider attribution." The ticket's own
readiness label (Not scheduled / Post-V1) and acceptance criteria call for
verifying source availability, licensing, coverage and repository state and
setting out an integration approach — not an implementation.

Every factual claim below was checked against a live GOV.UK content-API call
or a downloaded copy of the current release's own ODS files, not against a
description of either. The three current editions were all downloaded and
read directly with the same `odfpy` library `m30_statutory_homelessness.py`
already imports, using the module's own row-extraction approach (`sheet_rows`
concatenates each cell's own paragraphs; this file's headers are wrapped
multi-line text inside single cells, not `m30`'s multi-row merged-header
blocks, so no adaptation was needed to read them for this document).

## 1. What already exists (read before proposing anything new)

| Module | Covers | Evidence layer |
|---|---|---|
| `m30_statutory_homelessness` | MHCLG quarterly H-CLIC Table A1 (`statutory_homelessness_snapshot`) — the flagship duty-assessment count | `comparator` — never combined with sector evidence |
| `m31_temporary_accommodation` | MHCLG quarterly H-CLIC Table TA1 (`temporary_accommodation_snapshot`, `temporary_accommodation_breakdowns`), imports `m30`'s discovery and sheet reader directly | `comparator` |

`m30`'s own module docstring and `docs/SOURCES.md`'s Module 30 entry already
name this gap explicitly: "The workbook carries 40+ other tables (temporary
accommodation, prevention/relief outcomes, **multiple-disadvantage
breakdowns**); reading one table properly this cycle beats reading many
badly" (module docstring), and `docs/SOURCES.md`: "the quarterly breakdown of
temporary accommodation, prevention/relief outcomes and **multiple-
disadvantage figures** are a possible later addition, not this module." One
correction to carry forward from that same sentence, confirmed below (§3):
Multiple Disadvantage is not a breakdown sheet *inside* the Table A1/TA1
workbook `m30`/`m31` already open — it is a **separate attachment, its own
small workbook**, published on the same evergreen page. `m30`'s test suite
already asserts the two are different table sets by name
(`tests/test_m30_statutory_homelessness.py::test_excludes_non_quarterly_or_duplicate_titles`,
parametrised with `"Multiple Disadvantage Detailed Local Authority Data:
July to September 2025 (revised)"` as a title `parse_quarter_title` must
return `None` for) — that test, and `m30`'s `TITLE_RE`, are correct as
written and this document does not touch either.

## 2. What Multiple Disadvantage Detailed Local Authority Data actually is

This is a **brand-new MHCLG statistical product, not a table this pipeline
was simply late to notice.** Every one of the three editions currently
attached to the evergreen page — July–September 2025, October–December
2025, and January–March 2026 — carries the identical `Released: 13 August
2026` line on its own Cover sheet, confirmed by downloading and reading all
three files directly, not inferred from one. MHCLG launched the whole
product on that date with three quarters of history released at once: the
two older quarters are already marked `Status: Revised` and the newest is
`Status: Provisional`, exactly `m30`'s own revision vocabulary, on day one.
This is also why the ticket's "August 2026 detailed LA file" and this
pipeline's own module audit ranked it a fresh, previously-unseen source
rather than a long-standing gap.

The Cover sheet states its purpose in its own words (quoted verbatim, not
paraphrased):

> "This dataset uses MHCLG accredited official statistics on Statutory
> Homelessness applications, duties, and outcomes for local authorities in
> England to report on the Local Outcome Framework metric, 'the percentage
> of duties owed where homelessness was prevented or relieved for households
> experiencing multiple disadvantage'."

and the Definitions sheet defines the qualifying condition precisely:

> "Households experiencing three or more of the following five
> disadvantages: homelessness/rough sleeping; substance dependence; mental
> health issues; domestic abuse; and contact with the criminal justice
> system."

**This is derived from the same H-CLIC collection `m30`/`m31` already read,
not a separately-submitted survey.** The Cover sheet states it plainly:
"MHCLG publish accredited official statistics on Statutory Homelessness
applications, duties, and outcomes... This dataset uses [that same]
accredited official statistics... to report on the Local Outcome Framework
metric." The five disadvantage flags are derived by MHCLG from existing
H-CLIC fields — reason for loss of accommodation, support needs, and referral
organisation — not a new question local authorities answer. The Definitions
sheet spells out exactly which underlying H-CLIC values populate each flag,
e.g. substance dependence: "'Drug dependency needs' support need" or
"'Alcohol dependency needs' support need." **A household is flagged if any
one of several underlying indicators is present** — this is a support-need
checkbox recorded at housing assessment, not a clinical diagnosis, a
treatment episode, or anything NDTMS/Fingertips would recognise as a
measurement of substance misuse. See §5 for why this must never be read
alongside this pipeline's own substance-misuse evidence.

Licensing is the same as the rest of this collection — no new licence
question. This dataset lives on `m30`'s own evergreen page
(`live-tables-on-homelessness`), part of the `homelessness-statistics`
collection `docs/SOURCES.md` already records as OGL v3.0 for Modules 29–31.

## 3. Verified live today — where it actually is

**A separate attachment, not a sheet inside `m30`'s own workbook.** A live
GET of `m30`'s own `CONTENT_URL`
(`https://www.gov.uk/api/content/government/statistical-data-sets/live-tables-on-homelessness`)
today returns 68 attachments, including three matching
`Multiple Disadvantage Detailed Local Authority Data: <quarter>`:

| Title | Content type | Attachment file |
|---|---|---|
| Multiple Disadvantage Detailed Local Authority Data: July to September 2025 (revised) | ODS | `MDIS_Tables_202509.ods` |
| Multiple Disadvantage Detailed Local Authority Data: October to December 2025 (revised) | ODS | `MDIS_Tables_202512.ods` |
| Multiple Disadvantage Detailed Local Authority Data: January to March 2026 | ODS | `MDIS_Tables_202603.ods` |

**The load-bearing finding: no new network surface is needed.** `m30`
already fetches this exact content-API URL every run and already receives
these three attachments in the same `details.attachments` list it filters
with its own `TITLE_RE`. A module reading this source needs a second regex
over the same already-fetched attachment list — e.g.
`MD_TITLE_RE = re.compile(r"^Multiple Disadvantage Detailed Local Authority Data:\s*...")`
— not a second content-API call. This is the same shape of finding JON-40's
RSDF document made for `m29`'s page (§7 there): the sibling source was
sitting in data `m30` already downloads, filtered out by construction.

**Revision handling fits `m30`'s existing convention exactly, unlike RSDF's
open question against `m29`.** MHCLG marks a republished quarter with the
identical `"(revised)"` title suffix `m30`'s own `TITLE_RE`/`discover_publications`
already parse and prefer — confirmed above: both older quarters already
carry it, the current quarter does not yet. `m30`'s "a later run silently
overwrites the earlier figures... this module always prefers a revised
edition over the original" (its own docstring, quoted in
`docs/CAVEATS.md`'s Module 30 entry) is directly reusable here with no new
design decision, because the source itself signals revisions the same way.

**The workbook is small and structurally simple** — eight sheets total
(`Cover`, `Contents`, `Notes`, `Definitions`, and four data sheets), against
Table A1's single sheet or RSDF's 29. Headers are one row of wrapped
multi-line cell text (three stacked phrases per cell, e.g. "Assessed as owed
a duty" / "Owed a prevention or relief duty" / "Multiple disadvantage
total"), not `m30`'s multi-row merged-header block — reading them only
required calling `sheet_rows()`'s existing `_cell_text` paragraph-join, not
a new column-locating strategy.

## 4. Coverage

Four data sheets, confirmed by reading each one's own header row and England
totals row, not the Contents tab's summary alone:

| Sheet | Table | Columns (beyond `ons_code`/`Area Name`) |
|---|---|---|
| `Multiple_Disadvantage_values` | Table 1 — headline | The published percentage `[note 2]`, then three totals: assessed as owed a duty (multiple-disadvantage subset), households who secured accommodation ≥6 months after prevention duty ended, same after relief duty ended |
| `A_Multiple_Disadvantage` | Table 2 — assessed | The same "assessed as owed a duty" multiple-disadvantage total, then five category totals: domestic abuse, mental health, substance dependency, homelessness/rough sleeping, criminal justice contact |
| `P_Multiple_Disadvantage` | Table 3 — prevention outcomes | Same shape as Table 2, for households who secured accommodation ≥6 months after a **prevention** duty ended |
| `R_Multiple_Disadvantage` | Table 4 — relief outcomes | Same shape, after a **relief** duty ended |

Geography is identical to `m30`'s own: 296 local-authority rows per sheet
(confirmed by counting rows matching `m30`'s own `ONS_CODE_RE`,
`^E(?:0[6-9]|10)\d{6}$`), plus region rows (`E12xxxxxx`) and an
`E92000001`/`ENGLAND` row, plus a `Rest of England` aggregate row whose code
column literally reads the placeholder text `[z]` rather than a real ONS
code — `m30`'s existing `ONS_CODE_RE` filter already excludes all three
non-LA row kinds by construction, with no change needed.

England-level totals are **rounded to the nearest 10 and stated as such**
("Total figures are presented rounded to the nearest 10 households... Totals
may not equal the sum of components because of rounding" — Cover sheet,
verbatim). **Local-authority-level figures are the exact, unrounded counts**
— confirmed directly: Adur's Table 2 row reads `4, 9, 35, 13, 6, 4`, not
multiples of 10. A reader used to `m30`'s England/region rows sharing the
same precision as its LA rows should not assume that here.

**Missing-data handling is stated numerically and matches the file exactly.**
The Cover sheet states "8 out of 296 local authorities had missing data" for
both the assessment and outcome tables; a live scan of `A_Multiple_Disadvantage`
finds exactly 8 rows whose every value is the literal placeholder `[x]`
(Basildon, Bristol, Castle Point and five others) — the stated figure and
the file's own rows agree.

## 5. Data quality, comparability and what not to compute from it

- **This is homelessness administrative data, not sector treatment or
  clinical data, despite one column reading "substance dependency."** The
  flag is set from H-CLIC support-need/referral fields recorded by a housing
  officer at homelessness assessment — "Drug dependency needs" or "Alcohol
  dependency needs" as a self-reported or officer-recorded support need, not
  an NDTMS treatment episode, a diagnosis, or anything comparable to this
  pipeline's own NDTMS/Fingertips figures (Modules 7, 12, 27). **This must
  stay in the `comparator` evidence layer exactly as `m29`/`m30`/`m31`
  already do, and must never be combined, differenced or correlated with
  this pipeline's own substance-misuse treatment data** — the same rule
  `docs/CAVEATS.md`'s Module 30 entry already states for the parent source,
  reinforced here because the word "substance" appearing in a column header
  is exactly the kind of coincidence that invites the arithmetic the
  project's first CAVEATS rule forbids.
- **The five category totals are not mutually exclusive, and summing them
  wildly exceeds the qualifying total — do not reassemble one from the
  other.** England's Table 2 row: multiple-disadvantage total 7,340;
  domestic abuse 11,300; mental health 25,960; substance dependency 8,310;
  homelessness/rough sleeping 12,240; criminal justice 9,840. The five
  categories sum to 67,650 — over nine times the qualifying total — because
  qualifying for "multiple disadvantage" requires three or more of the five
  flags, so a single qualifying household is counted in at least three
  category columns simultaneously. Each category total answers "how many
  multiple-disadvantage households have this flag among their three-plus",
  never "households whose only disadvantage is this one." The same
  within-source double-counting caveat JON-40's RSDF document wrote for its
  own overlapping tables applies here, for the same reason.
- **The headline percentage is MHCLG's own published metric and this
  pipeline must store it, never recompute it.** Its own footnote (`[note
  2]`, Notes sheet) states it directly: "This metric is a proxy of inflow
  and outflow and takes into account all of the households assessed as owed
  a duty in the quarter, and the households where a prevention or relief
  duty came to a successful end in the quarter. Not all assessed households
  will have an outcome in the same quarter, therefore percentages may be
  more than 100%." A percentage that can legitimately exceed 100% is not
  safe to re-derive from the two totals beside it — store the published
  figure verbatim, the same discipline as `m29`'s `rate_per_100k` and ONS
  ASHE's published estimates.
- **Only two placeholders exist here, a narrower set than `m30`'s own
  table.** Confirmed by scanning every cell of all three downloaded
  editions: only `[x]` (missing data, non-submission or data quality issue)
  and `[z]` (not applicable — no area code, or a calculation such as a
  percentage with a zero denominator) appear; `m30`'s own `[n]` (no data —
  authority did not exist yet) and `[c]` (small-number suppression) do not
  occur anywhere in this source. **There is no small-number-suppression
  marker in this file at all** — genuine single-digit counts are published
  at local-authority level (Adur: 4; Wychavon: 3), unlike some MHCLG/ONS
  series that suppress small cells for disclosure control. This is worth
  confirming stays true in later editions rather than assumed permanent —
  smaller LA-level multiple-disadvantage counts are the kind of figure a
  future statistical-disclosure-control policy could start suppressing
  without notice.
- **A duty-outcome total here is a subset of `m30`'s own Table A1 total for
  the same quarter, not an independent count** — Table 2's "assessed as
  owed a duty" multiple-disadvantage figure and `m30`'s
  `total_owed_duty` describe overlapping but differently-scoped
  populations (all households owed a duty, vs. the subset experiencing
  multiple disadvantage). Presenting the two side by side as a proportion
  is exactly the source's own published metric (§ above); computing a
  different proportion by dividing this module's total by `m30`'s own
  stored `total_owed_duty` would silently recompute a rate the source
  already publishes, using two independently-fetched, independently-revised
  tables that may not be from the same edition at read time — the same
  cross-table-arithmetic risk `docs/CAVEATS.md` forbids generally.
- **Category label wording is not even consistent within this one
  workbook.** `A_Multiple_Disadvantage` and `P_Multiple_Disadvantage` both
  label the same column "Substance dependency total"; `R_Multiple_Disadvantage`
  labels the equivalent column "Substance misuse total" — confirmed by
  reading all three sheets' header rows directly, not assumed from one. Both
  columns are defined by the one "Substance dependence" entry on the
  Definitions sheet, so this is the source's own inconsistent labelling
  across its four sheets, not a difference in what is measured. A
  keyword-based column locator (the discipline `m30`'s own
  `locate_a1_columns` already uses for its cross-era layout differences)
  should match on the stable substring `substance` rather than either exact
  phrase.
- **The three editions currently on the page are, as far as this document
  has verified, the entire history MHCLG has published for this metric —
  there is no earlier "Multiple Disadvantage" edition to discover.** This
  follows directly from §2's finding that all three share one release date;
  no collection-walk equivalent to RSDF's 11-edition discovery is applicable
  here, because there is nothing published before the launch date to find.

## 6. Repository state and how this differs from the ticket's own title

The ticket is titled "Extend m30 with Multiple Disadvantage local-authority
data," but this document's own findings (§3) argue against literally
extending `m30_statutory_homelessness.py`'s existing `run()`/table:

- The data is a **separate attachment** (its own small workbook), not an
  additional sheet inside the Table A1 workbook `m30` already opens — closer
  to `m31`'s relationship to `m30` (same page, separate concern, sharing
  code rather than one function doing both) than to a sheet `m30` could add
  to its existing per-quarter loop.
- The natural key shape differs: `m30`'s Table A1 is one wide row per
  authority/quarter; this source is four tables — a headline percentage-plus-
  three-totals table, and three category-breakdown tables sharing one
  five-category shape — with only three quarters of history rather than
  `m30`'s multi-year series.
- `docs/SOURCES.md`'s own Module 30 entry already anticipates this as "a
  possible later addition, not this module" (§1).

This document's reading is that "extend m30" in the ticket's title most
usefully means *extend the H-CLIC coverage this pipeline reads from the same
page and the same source system*, which `m31`'s own precedent already
answers with a sibling module, not a change to `m30`'s own function or
table — but this is a naming/scope question for whoever picks up the build,
not something decided here (see §7).

## 7. Integration approach (recommended, not built)

1. **Read the same content-API fetch `m30` already makes; add a second
   title regex, not a second network call** — `MD_TITLE_RE` matched against
   the attachment `title`s already returned to `m30`'s `CONTENT_URL` GET.
   Given `m30`'s `discover_publications` is currently hardcoded to its own
   `TITLE_RE`, the reusable shape is to parameterise it by regex (or extract
   a shared "attachments-by-quarter" helper both `m30` and a new module
   call with their own pattern) — the same "share code for one source, no
   duplicated round trip" discipline `m31` already applies to
   `read_workbook_sheet`.
2. **A new module and new table(s)**, not a change to
   `statutory_homelessness_snapshot`'s schema — per §6's shape argument. A
   candidate module number is `m36` (next free after `m35_open_jobs`) and a
   candidate migration number is `0116` (next free after `0115`), both to be
   confirmed at build time.
3. **`read_workbook_sheet` (already shared between `m30`/`m31`) can be
   reused as-is** for the four new sheet names
   (`Multiple_Disadvantage_values`, `A_Multiple_Disadvantage`,
   `P_Multiple_Disadvantage`, `R_Multiple_Disadvantage`) — it is already
   generic over sheet name and both ODS/XLSX, and this source's simpler
   single-header-row shape needs no new parsing logic, only new
   keyword-matching column locators (matching on `substance` rather than an
   exact phrase, per §5).
4. **The revision-preference rule transfers directly** — no open design
   question the way RSDF's did against `m29`/`m30`'s two precedents (JON-40
   §6). This source already publishes the same `"(revised)"` marker `m30`
   trusts, so upserting on `(ons_code, quarter_start)` and preferring the
   revised edition is a direct reuse of `m30`'s own discipline, not a new
   decision.
5. **Evidence layer: `comparator`, same as Modules 29–31, not a new
   category** — despite one column reading "substance dependency," §5's
   finding that this is H-CLIC housing-assessment data, not treatment data,
   means it belongs beside `m30`/`m31` on the public authority page's
   existing "Comparators" section (BETA-017), carrying its own caveat text
   there, rather than beside NDTMS/Fingertips.
6. **Table shape is an open decision**: one row per authority/quarter with
   all four tables' columns flattened into a single wide table (headline
   percentage + 3 outcome totals + 3×5 category breakdowns = a similar
   column count to `m30`'s own A1 table), versus a narrower
   category-keyed table mirroring the shape JON-40's RSDF document
   recommended for its own wide indicator set. Given only four sheets (not
   RSDF's 29) and a stable, small column count, the wide-table shape looks
   like the better fit here, but this document does not decide it.
7. **`[x]`/`[z]` paired `_text`-plus-`NULL` columns**, `m30`'s existing
   convention, apply directly — no `[n]`/`[c]` handling is needed for this
   source (§5), though a future edition introducing either should not be
   assumed impossible.

## 8. Offline fixtures

A representative fixture needs, at minimum: one authority row with real
values across all four sheets, one authority row using the `[x]` placeholder
across every column (mirroring Basildon/Bristol/Castle Point's real shape),
one row using `[z]` (a `Rest of England`-style aggregate, to prove it is
excluded rather than misfiled as a local authority), and one worked example
where the five category totals are deliberately left summing to more than
the headline total, so a test can assert nothing anywhere adds them
together. None of this requires a live fetch to construct: the sheet and
column shapes in §4 are enough to hand-build a small `.ods` fixture the same
way `tests/test_m30_statutory_homelessness.py` already does for Table A1.

## 9. Recommended next decisions (none taken here)

1. **Decide new module vs. an in-place `m30` extension** (§6) — the shape
   argument favours a sibling module the way `m31` sits beside `m30`, but
   the ticket's own title says "extend m30," and that naming choice affects
   where the code and caveat text live.
2. **Decide the table shape**: one wide table across all four sheets, or a
   narrower category-keyed table (§7.6).
3. **Decide whether `discover_publications` is refactored to take a title
   regex parameter, or a new sibling function duplicates the same
   content-API response handling** (§7.1) — both work; only one avoids two
   near-identical copies of the same attachment-list-to-quarters logic.
4. **Confirm the `[x]`/`[z]`-only placeholder set holds in a fourth
   edition** (§5) before assuming it is permanent, given this is a very
   newly launched product with only three published editions to check
   against.

Every item above is a candidate for a named human decision, not an
implementation queue — consistent with this issue's Not-scheduled/Post-V1
readiness label.
