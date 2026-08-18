# Public UI refinement backlog

Status: agreed refinement backlog, 18 August 2026.

This backlog covers every public destination in the SectorTrace portal. The
operator interface under `/admin` is explicitly out of scope.

## Product direction

- Primary outcome: help visitors explore the sector.
- Primary audience: campaigners and unions.
- Visual direction: modern data newsroom.
- Default theme: follow the operating system, while retaining Light and Dark.
- Main problem: the current pages are too dense to scan quickly.
- Editorial pattern: short takeaways beside the evidence, with deeper context
  progressively disclosed.
- Sharing priority: visual, shareable takeaways.
- Mobile strategy: responsive and usable, but desktop remains the richer
  research environment.
- Detail pages: data workbenches rather than simple profiles.
- Scope: UI-first, using the current API and warehouse. New data work is a
  later-phase option and must be labelled as such.

## Global priorities

### Now

1. Establish a consistent page rhythm: page purpose, takeaway, evidence,
   caveat/provenance, then detail.
2. Reduce simultaneous visual competition by using one primary visual per
   section and moving supporting tables into expandable detail.
3. Add a reusable takeaway block with a short plain-language statement,
   evidence status, date, and a share/copy action.
4. Make chart titles state the message or measure, not only the dataset name.
5. Keep equivalent table/text views available for every meaningful chart.
6. Preserve distinct states for published, unverified, missing, suppressed,
   unavailable, and not-collected evidence.
7. Make the current filter, comparison selection, retrieval date, and source
   visible in shareable page states.

### Next

1. Add reusable collapsible context for methodology, caveats, licences, and
   provenance rather than repeating long warnings in the reading flow.
2. Add visual export/share affordances where the current route already has the
   data needed to produce them.
3. Introduce consistent section navigation or an in-page contents rail on the
   longest desktop pages.
4. Tune responsive layouts so cards stack into a deliberate reading order and
   tables expose their essential columns before optional detail.

### Later

1. Consider new narrative datasets, saved comparisons, alerts, or accounts
   only after usage evidence demonstrates that current UI improvements are not
   enough.
2. Consider richer social-image generation only after the citation and
   provenance state is reliably captured in the share flow.

## Page backlog

Each page below records what to keep, change, add, remove or merge, the target
section order, responsive treatment, and priority.

### 1. Overview — `/`

Current role: corpus snapshot with headline cards, source updates,
verification funnel, freshness, and largest notices.

Keep:

- Headline counts and the honest treatment of unsupported totals.
- Source freshness and the verification funnel.
- The explicit statement that missing values are not guessed.

Change:

- Reframe the hero as a dashboard snapshot: one sentence explaining what the
  portal covers, followed immediately by the most useful current signals.
- Group the cards into three labelled bands: coverage, evidence quality, and
  sector context. This prevents providers, notices, and workforce metrics from
  reading as one comparable scorecard.
- Give every card a short status label such as Published, Unverified, or
  Not collected.
- Turn the largest-notices chart into a secondary exploration module. Its
  caveat should be visible before the chart, not discovered after it.
- Add compact route cards for Pay, Places, Providers, Treatment, and Claims so
  the overview remains an exploration hub rather than only a metrics wall.

Add:

- A “What can I explore?” route strip beneath the headline cards.
- A “Read this first” context drawer covering evidence layers, update dates,
  and why the portal does not combine unrelated measures.
- Copy/share controls for individual headline snapshots where the existing
  source and retrieval metadata are sufficient.

Remove or merge:

- Merge “Sources and latest updates” with the freshness section into one
  compact “Evidence status” block with expandable source detail.
- Do not remove the verification funnel, but move it below the first useful
  dashboard row.

Recommended order:

1. Purpose and dashboard snapshot
2. Coverage and evidence-quality cards
3. Route cards for exploration
4. Evidence status: sources, freshness, verification
5. Largest notices and other secondary exploration
6. Method and limitations

Responsive:

- Keep the first four cards visible as a two-column grid where possible, then
  stack them in priority order.
- Collapse route cards into a horizontal-scroll-free vertical list.
- Keep the takeaway and status visible above any chart; put the detailed table
  behind an explicit “View data” control.

Priority: Now.

### 2. Pay & benchmarks — `/pay`

Current role: workforce story assembled from charity accounts, job adverts,
statutory rates, provider pages, Living Wage checks, gender pay gap filings,
ASHE, Skills for Care, and workforce census data.

Keep:

- The separation between indicative wage, advertised pay, statutory rates,
  provider-published pay, and external benchmarks.
- The caveats that prevent unlike figures being treated as one pay measure.
- The provider and year filters.

Change:

- Reorder the page around the workforce story: what is published, what is
  advertised, what is statutory, and what broader benchmarks can and cannot
  tell us.
- Start each layer with a one-sentence takeaway and a clear evidence-status
  badge before the chart or table.
- Visually separate direct sector evidence from contextual comparators with
  different section framing, not just different headings.
- Make “not a payroll” and “not a calculated gap” part of the visible result
  header instead of long repeated prose.
- Use small multiples for advert distributions and time views where the chart
  currently competes with several adjacent panels.

Add:

- A compact “How to read pay evidence” explainer at the top.
- A layer switcher or contents navigation: Accounts, Adverts, Published pay,
  Statutory floor, Workforce context.
- “What this does not show” expandable notes beside the most likely
  misinterpretations.
- Copy/share for a selected provider/year state, carrying the filter URL and
  evidence date.

Remove or merge:

- Merge the several comparator panels into a clearly labelled “Context only”
  section, keeping their individual provenance.
- De-emphasise any chart that has no current published rows instead of giving
  every empty layer the same visual weight.

Recommended order:

1. Workforce-pay takeaway and reading guide
2. Indicative wage evidence
3. Advertised roles and salary distribution
4. Provider-published and statutory pay
5. Workforce census status
6. External comparators
7. Sources, caveats, and downloads

Responsive:

- Stack layers vertically; do not place two caveat-heavy panels side by side
  below 720px.
- Make the selected provider/year state sticky inside the filter summary.
- Give tables a mobile “essential columns” view with the full row available
  through an accessible detail drawer.

Priority: Now.

### 3. Funding & contracts — `/contracts`

Current role: filtered contract notices, value concentration, quarterly
activity, fixed value bands, contract-end runway, procedure type, providers,
buyers, and notice table/export.

Keep:

- The distinction between notice count, published value, and the incomplete
  window of notices shown on screen.
- The fixed value bands and the concentration caveat.
- Source links, filters, and complete filtered export.

Change:

- Lead with “Where public money is going” rather than the generic title
  “Contracts”.
- Put buyer/provider/geography context before the detailed notice table.
- Use a primary summary row for notices matched, median notice value, date
  range, and priced/unpriced share; do not present a total value as a clean
  sector-spend headline.
- Use one primary trend chart and turn the remaining breakdowns into tabs or
  expandable panels.
- Add clearer labels for “published value” versus actual payment or budget.

Add:

- A “How to read a notice” explainer explaining ceiling values, missing prices,
  PSR notices, and the table window.
- A visual buyer/provider relationship summary using existing aggregates.
- A prominent “Download the complete filtered set” action near the table.
- Copy/share for a filtered contract view, including all active filters.

Remove or merge:

- Merge the quarter, value-band, and runway panels into a tabbed “Patterns”
  section.
- Move procedure type and provider breakdowns below the main money-flow
  summary unless the user explicitly opens them.

Recommended order:

1. Money-flow takeaway and interpretation guide
2. Summary metrics
3. Buyers, providers, and time pattern
4. Patterns: quarter, bands, procedure, runway
5. Filtered notice table
6. Complete export and provenance

Responsive:

- Keep the summary metrics in a two-column mobile grid.
- Make the notice table horizontally contained or convert rows to cards; the
  page must not create viewport-level overflow.
- Preserve the download action above the table on small screens.

Priority: Now.

### 4. Places — `/geography`

Current role: map with selectable metrics and a highest-20 list.

Keep:

- The map as an entry point to authority pages.
- Explicit metric and year selection.
- Caveats preventing the map from being read as a league table.

Change:

- Present the page as a local-comparison tool, not a generic geography page.
- Put metric definition, year, unit, and data-status legend beside the map.
- Make the map’s primary action “Open authority page” and its secondary action
  “Compare selected places”.
- Replace “Highest 20” as the default visual emphasis with a neutral selected
  authority summary plus an optional sorted list.
- Use a single consistent colour scale per metric and visibly distinguish no
  data from low values.

Add:

- A “Choose a question” control with plain-language metric descriptions.
- Selected-authority tray with name, value, year, caveat, and links to detail
  and compare.
- Text/table alternative immediately below the map.
- A lightweight “How this map works” disclosure covering boundaries,
  aggregation, and missingness.

Remove or merge:

- Merge map instructions and caveats into one compact map key panel.
- Do not remove the sorted list, but make it secondary to the selected-place
  workflow.

Recommended order:

1. Local-comparison purpose and metric picker
2. Map with legend and selected-place tray
3. Table/list alternative
4. Optional highest/lowest exploration
5. Method and limitations

Responsive:

- On small screens, place the metric picker above the map and the selected
  authority summary below it.
- Provide a usable list-first fallback if the map canvas becomes too small.
- Ensure tooltip content is keyboard reachable and never the only place a value
  appears.

Priority: Now.

### 5. Providers — `/providers` and `/providers/:provider_key`

Current role: provider directory/chart plus provider detail pages covering
contracts, claims, PFD mentions, charity accounts, pay, and related evidence.

Keep:

- The provider search and direct provider pages.
- Cross-links to contracts, pay, claims, and safety/legal evidence.
- Provider-level provenance and caveats.

Change:

- Make the landing page a directory and market landscape: search first,
  evidence inventory second, aggregate charts third.
- Make each provider page a workbench with a sticky identity header, evidence
  coverage, and task-based tabs.
- Surface the strongest available evidence first, not the longest table.
- Use consistent provider status labels: tracked, partial evidence, no current
  evidence, or source-limited.

Add:

- Provider profile header with canonical name, aliases, evidence date, and
  quick links to Pay, Contracts, Claims, Safety/legal, and Compare.
- Evidence inventory showing which layers have rows and which are absent from
  collection.
- A “Build a briefing” action that opens a shareable provider state using
  existing deep links and filters.
- A provider-level source timeline where the current data supports it.

Remove or merge:

- Merge duplicate provider summary panels into one profile header.
- Group charity income, contracts/grants, and reports under “Financial
  evidence” with expandable detail.

Recommended order:

Landing page:

1. Search/directory
2. Evidence inventory
3. Market overview
4. Provider list and compare actions

Detail page:

1. Provider identity and briefing actions
2. Evidence inventory and headline takeaways
3. Pay
4. Contracts and funding
5. Safety/legal and claims
6. Financial evidence and source detail

Responsive:

- Keep search and provider identity visible above the fold.
- Use horizontally scrollable tabs only if keyboard and screen-reader labels
  remain clear; otherwise stack task links.
- Convert dense provider tables to expandable rows with the provider and date
  retained in the summary row.

Priority: Now for landing/detail hierarchy; Next for briefing composition.

### 6. Treatment data — `/treatment`

Current role: Fingertips and NDTMS indicators with authority selection,
  national/local series, estimates, and confidence intervals.

Keep:

- The paired treatment sources.
- Confidence intervals and suppression markers.
- Authority selection and source-specific caveats.

Change:

- Lead with interpretation: what the figures measure, who published them, and
  why demand, activity, and outcomes are not interchangeable.
- Make the selected authority and indicator visible in a single control row.
- Use a narrative sequence from national context to local detail.
- Give interval and suppression states a consistent legend across all charts.

Add:

- A plain-language indicator guide with “measures”, “does not measure”,
  period, geography, and source.
- A “National context” summary before local authority detail.
- A visible uncertainty panel explaining confidence intervals and why a blank
  or suppression marker is not zero.
- A copy/share action for the selected authority, indicator, and period.

Remove or merge:

- Merge repeated source caveats into the indicator guide, retaining a short
  local caveat beside each chart.
- Hide low-value catalogue detail until the user opens “Browse all
  indicators”.

Recommended order:

1. What treatment data can answer
2. National context
3. Indicator and authority controls
4. Local chart and table
5. Confidence/suppression explanation
6. Source and download detail

Responsive:

- Use a stacked control block with large touch targets.
- Show a compact chart plus text summary first; make the full table an explicit
  secondary view.
- Preserve interval labels in the mobile summary, not only in tooltips.

Priority: Now.

### 7. Safety & legal — `/pfd`

Current role: Prevention of Future Deaths reports by year, coroner area,
  concern terms, provider mentions, and recent reports.

Keep:

- The separation between reports sent to providers and providers named in
  reports.
- Concern-term finding aids and report provenance.
- The restriction against exposing personal data.

Change:

- Use the title “Safety & legal evidence” with “Coroners’ reports” as the
  first section, making the public purpose clearer.
- Lead with a careful evidence takeaway and a statement of what the counts do
  and do not establish.
- Treat recent reports as the primary exploration entry point, with aggregate
  charts as context.
- Use human-readable labels and avoid implying that mention count equals
  fault, causation, or prevalence.

Add:

- A responsible-reading panel explaining report status, mention types, and
  what a concern-term match means.
- Topic/concern cards that open the existing evidence list.
- A visual “report trail” showing year, coroner area, organisation mention,
  and source link where supported.

Remove or merge:

- Merge repeated caveats into the responsible-reading panel.
- Keep the aggregate charts, but move them below recent/source-linked
  evidence.

Recommended order:

1. Responsible-reading takeaway
2. Recent reports and source links
3. Concern themes
4. Sent-to versus named-in views
5. Time and coroner-area context
6. Limitations and restricted-data notice

Responsive:

- Use report cards rather than wide tables for recent evidence.
- Keep the distinction between mention types in card headings and status
  colours/text, never colour alone.

Priority: Next.

### 8. Evidence-backed claims — `/claims`

Current role: published campaign claims with supporting evidence, caveats,
  reviewer/published metadata, and resolved citations.

Keep:

- Human-reviewed publication status.
- The explicit citation/evidence relationship.
- Claim-specific caveats and unresolved-source handling.

Change:

- Turn the page into campaign-ready claim cards rather than a dense register.
- Put the claim text, evidence status, and one-line caveat above the fold.
- Make supporting evidence expandable so the claim remains scannable.
- Add stronger thematic grouping when the current claim metadata supports it.

Add:

- “Copy claim with citation” and “Share visual” actions.
- A compact citation bundle containing claim, source label, URL, retrieval date,
  and caveat.
- Filters for theme/status only if they can be backed by current data; do not
  add controls that silently do nothing.
- A clear “What this claim does not prove” block for each claim.

Remove or merge:

- Merge repeated provenance fields into an expandable evidence drawer.
- Remove empty structural space when there are no published claims; replace it
  with a clear publication-state message.

Recommended order:

1. Purpose and responsible-use note
2. Claim cards
3. Supporting evidence drawers
4. Citation/share actions
5. Publication and review metadata

Responsive:

- Cards should be single-column with full-width copy/share buttons.
- Keep claim text and caveat together; never put the caveat below a long
  evidence table where it is easy to miss.

Priority: Now.

### 9. Authority pages — `/authorities` and `/authorities/:ons_code`

Current role: authority landing page plus detail workbench covering coverage,
  grant allocation, budgeted spend, budget drill-down, treatment, and
  contracts.

Keep:

- Direct authority deep links from search and map.
- Separate grant and budget figures.
- Coverage ticks and source-specific provenance.
- Compare links.

Change:

- Make the detail header a workbench identity bar: authority name, type,
  region, ONS code, evidence date, and actions for Compare, Share, and
  Download.
- Move coverage into a compact evidence inventory immediately under the
  header.
- Present grant, budget, treatment, and contracts as task tabs or anchored
  sections with clear source boundaries.
- Add a short authority takeaway only when it is directly supported by a
  published figure; otherwise state that the page is an evidence inventory.

Add:

- A persistent “Compare this authority” action.
- A “What is held for this authority” summary with links into each available
  layer.
- Section-level download/share controls using current endpoint parameters.
- Table-first alternatives beneath the grant/budget charts.

Remove or merge:

- Merge the separate return links and compare links into one workbench action
  row.
- Keep detailed budget lines, but place them behind “View budget lines”.

Recommended order:

1. Identity and actions
2. Evidence inventory
3. Grant and budget
4. Treatment
5. Contracts
6. Detailed rows and provenance

Responsive:

- Keep authority name, region, and primary actions visible at the top.
- Stack charts and expose their tabular alternatives directly below each chart.
- Use expandable evidence layers instead of a long uninterrupted page.

Priority: Now.

### 10. Compare — `/compare`

Current role: choose two or more authorities/providers and draw shared axes
  for grant, budget, treatment, contracts, charity, or provider contracts.

Keep:

- The URL as the comparison state.
- Separate charts for separate evidence layers.
- Cross-layer caveat and entity picker.

Change:

- Frame the page as a safe comparison workspace with a three-step flow:
  choose peers, choose a layer, read the evidence.
- Make the selection tray persistent and show the number/type of entities.
- Give each chart a takeaway and a layer-specific caveat before rendering the
  visual.
- Prefer small multiples and direct labels over crowded legends.
- Make “not comparable” and “no data” explicit states.

Add:

- Clear/remove-all selection action.
- Peer suggestions from already available authority/provider lists, without
  implying a ranking.
- Copy comparison link and share visual actions.
- Table view for each comparison layer.

Remove or merge:

- Merge repeated cross-layer warnings into one persistent workspace notice,
  while retaining each chart’s local caveat.
- Avoid adding calculated difference or ratio views; they conflict with the
  evidence rules.

Recommended order:

1. Workspace purpose and safety notice
2. Selected entities
3. Choose comparison layer
4. Takeaway, chart, and table for that layer
5. Share/download state

Responsive:

- Make peer selection a full-width step before charts.
- Render one layer at a time on small screens rather than stacking every chart.
- Keep selected entity chips removable with keyboard and touch.

Priority: Now.

### 11. Coverage & limitations — `/coverage`

Current role: explains evidence meaning, boundaries, and source freshness.

Keep:

- Missingness and source freshness explanations.
- The explicit limitations language.
- The connection to the evidence portal’s broader rules.

Change:

- Reframe as a compact trust centre rather than a primary exploration page.
- Use an at-a-glance status grid first, then expandable methodology sections.
- Use consistent evidence-status labels shared with the rest of the portal.

Add:

- “How to cite this portal” guidance.
- Licence and source-reuse guidance linked to the existing provenance system.
- A concise glossary of evidence states.
- Direct links back to the affected pages.

Remove or merge:

- Merge repeated freshness explanations into one source-status component.
- Keep the full limitations text available, but collapse it by default.

Recommended order:

1. Trust-centre summary
2. Evidence-state glossary
3. Coverage and freshness
4. Caveats and prohibited interpretations
5. Sources, licences, citation, and API links

Responsive:

- Prefer a single-column glossary/status layout.
- Avoid dense tables unless they are accompanied by a readable mobile card
  view.

Priority: Next.

### 12. Downloads & API — `/api`

Current role: no-JavaScript technical reference for public endpoints,
  parameters, response shapes, provenance, and export routes.

Keep:

- The no-JavaScript reference.
- Endpoint examples and response-shape documentation.
- Provenance, licence, and complete-export explanations.

Change:

- Keep it low priority in navigation, but make the page easier to scan with a
  short “Choose your route” index grouped by purpose: browse, compare, map,
  treatment, claims, export.
- Put the most common examples first and move exhaustive endpoint detail into
  expandable sections.
- Add a visible distinction between page-facing routes and technical API
  routes.

Add:

- Copy endpoint button where compatible with the no-JavaScript requirement;
  otherwise provide selectable code blocks.
- “Download this page’s data” links when the current export endpoint supports
  the page.
- A concise API stability/provenance note.

Remove or merge:

- Merge duplicated explanatory paragraphs where the same caveat is already
  documented in the portal or export contract.
- Keep the full reference content; do not remove technical endpoint coverage.

Recommended order:

1. What the API is for
2. Common routes by task
3. Endpoint reference
4. Export/provenance/licence rules
5. Examples and source notes

Responsive:

- Keep parameter tables readable through stacked key/value blocks below
  640px.
- Ensure long URLs wrap without creating page overflow.

Priority: Later.

## Shared shell backlog

### Navigation

- Keep the current question-based sections, but make the active destination,
  “More/tools” area, and current page title more visually distinct.
- Consider grouping Coverage, API, and Operator access under a quieter “Tools”
  treatment while keeping `/admin` clearly separate.
- Add an optional compact in-page section index for long routes.

### Filters and URL state

- Keep filters only on routes that consume them.
- Show active filters as readable chips with a visible count and Clear all.
- Make filter state part of every share/copy action.
- Ensure search/typeahead controls support keyboard movement, selected state,
  and escape-to-close.

### Themes and visual system

- Keep System/Light/Dark persistence.
- Rebalance the current dark-first tokens toward a newsroom system that works
  equally well in light and dark modes.
- Reserve accent colours for meaning and actions; never use colour alone for
  evidence state.
- Use a restrained chart palette with direct labels and consistent semantic
  colours across routes.

### Loading, empty, and error states

- Replace generic shimmer-only states with a short explanation of what is
  loading.
- Make empty states distinguish “not collected”, “collected but unavailable”,
  “no matching rows”, and “request failed”.
- Keep retry actions close to the failed section.

### Sharing and visual takeaways

- Add a reusable Share visual action that captures the selected chart/table,
  title, source, retrieval date, caveat, and URL state.
- Add Copy citation as a separate action; visual sharing must not replace
  defensible provenance.
- Ensure copied links restore route, filters, entity selection, metric, year,
  and comparison state.

### Accessibility and responsive quality

- Keep a text/table equivalent for every chart.
- Ensure chart titles, subtitles, units, source, and caveat are available in
  the DOM, not only in tooltips.
- Test keyboard focus, reduced motion, zoom, contrast, and 320px width.
- Prevent viewport-level horizontal overflow from tables, maps, charts, and
  long URLs.

## Evidence and design references

The backlog follows these external references:

- [GOV.UK data visualisation principles](https://brand.design-system.service.gov.uk/data/): clarity, accessibility, accuracy, consistency, and narrative purpose.
- [GOV.UK chart guidance](https://brand.design-system.service.gov.uk/data/charts/): message-led titles, subtitles, source notes, focused interactions, and small multiples.
- [GOV.UK accessible images and charts](https://design-system.service.gov.uk/styles/images/): written alternatives and equivalent text for complex visuals.
- [ONS data visualisation service manual](https://service-manual.ons.gov.uk/data-visualisation): chart selection, colour, and build guidance.
- [public-data.org](https://public-data.org/): comparable evidence-first separation of headline signals, source dates, caveats, and tools.

## Acceptance checklist

The refinement is complete when the resulting UI work is checked against:

- Every public route and deep-detail route listed above.
- The `/admin` interface remaining unchanged.
- Keyboard navigation and visible focus.
- Light, Dark, and System themes.
- 320px minimum width with no viewport-level horizontal overflow.
- Text alternatives and equivalent tables for all important charts.
- URL persistence for filters, comparisons, metric/year selections, and shared
  views.
- Source, caveat, retrieval date, and licence visibility.
- Clear distinction between published, missing, unverified, suppressed,
  unavailable, and not-collected evidence.
- A visitor understanding each page’s purpose and main takeaway before reading
  every chart or table.
