# SectorTrace public frontend redesign

Status: implementation-ready specification; implementation is not authorised by this document.

Implementation was subsequently authorised by the user's explicit goal, “implement the plan”. Work is in progress. See [implementation progress](frontend-redesign-progress.md) for verified changes and outstanding requirements. The planning-stage stop instructions below describe the original planning boundary and do not revoke that later authorisation.

The user subsequently expanded the goal to “implement the plan, I also want ansible-mirror updated to enable this new frontend”. Deployment configuration and checks under `deploy/ansible-mirror` are now explicitly in scope. Enable the generated frontend through the existing serving flag, retain a documented rollback and verify the built static entry assets before restart. The existing flag selects both public and admin Nuxt entry points, without changing admin application code or the Python APIs. This addition does not authorise dropping any redesign requirement, and it does not itself request a live deployment.

The user also explicitly requested regular commits and pushes to `beta`. Use reviewable checkpoints, stage only this task's files and record validation gaps honestly. A checkpoint commit is not a claim that the redesign is release-ready.

Prepared 6 September 2026 against branch `beta`, revision `f806799d`, following repository inspection and 48 explicit interview decisions. The subsequent instruction to proceed authorises completing this plan, not implementing or deploying the frontend. No application code, API, warehouse, ingestion or admin changes accompany this document.

## 1. Executive summary

Redesign the existing public Nuxt application as an entity-centred evidence workspace for a broad sector audience. A visitor should be able to identify a provider or authority, understand what evidence is held, follow documented connections, compare appropriate observations and inspect their sources without losing context.

The default is dark, using SectorTrace's canonical palette, Manrope and Space Grotesk. Search requires an explicit choice of Providers, Authorities or Documents. The homepage combines search, a neutral England authority locator, evidence categories and coverage/freshness. A grouped sidebar, context-aware links, inspectors and bookmarkable lenses connect the application. Detail is progressively disclosed. Provenance opens on demand, but material limitations remain visible.

MapLibre owns geography, modular ECharts owns conventional analysis, and narrowly imported D3 modules support structured relationships. Every visual has an equivalent data view. No application-wide keyboard shortcuts or command palette will be introduced. Existing URLs, browser collections and usable evidence remain accessible.

This is a public frontend project. Use existing `/api/v1/*` contracts and map assets; no new backend endpoints, migrations, collection, NLP, account system, evidence classifications or public exposure of operator data. Admin token adoption is deferred. The user's interview decision expressly selects the existing Nuxt migration despite the older no-framework/no-build-step wording in AGENTS.md. Python remains the serving runtime, with origin-only static assets.

## 2. Product definition

SectorTrace is public evidence infrastructure for England's substance misuse treatment sector. Its campaign origins are stated plainly in About and on campaign-authored statements; campaign framing does not dominate general research pages. The application distinguishes evidence held from the state of the sector.

The organising workflow is **orient → inspect → pivot → compare → verify**. Geographic entry is available without being compulsory. “Detect” means noticing published patterns or recorded changes; it does not authorise anomaly scores, model-generated findings or causal narratives.

Success is primarily understanding an entity: the reader knows which organisation or authority is represented, what evidence exists for it, what each observation means, what is missing, and what documented connection to follow next.

## 3. Audience priorities and success journeys

Serve researchers, commissioners, journalists, academics, union researchers and sector professionals through the same evidence model. Use plain labels before technical metadata. Experienced researchers gain coordinated views, source inspection, comparison and exports, rather than hidden gestures.

Required end-to-end journeys:

1. Find a provider → confirm identity/lineage → inspect a contract → open its process → inspect a source notice → return to the same provider lens.
2. Find an authority on the locator → see its boundary → understand documented commissioning connections → inspect a provider → compare like entities within one evidence lens.
3. Choose Documents → search the public corpus → read a passage alongside results → open its stable reader route → copy a source reference and save an evidence note.
4. Choose a treatment measure → inspect its definition and periods → select an authority → read values and available confidence intervals → export the correct evidence scope.
5. Inspect a discrepancy or revision from a record → see both observations and their dates → understand that a stored change is not necessarily a change in the world.

Do not measure success by evidence volume, graph size or time spent in the product. Acceptance is verified through these workflows and the tests in sections 39 and 42; no analytics service is added.

## 4. Existing frontend assessment

The repository contains a legacy public JavaScript portal and an independent Nuxt public app; admin likewise has legacy and Nuxt implementations. At inspection, trace.cglpay.us served the legacy public interface. The local generated Nuxt build was inspected at desktop and 390 px widths with no API attached. That established shell/error behaviour only, not populated-page or deployment correctness. Deployed admin navigation was blocked by the browser; admin styling and architecture were inspected from source. Existing untracked `.worktrees/`, `AGENTS.md`, `frontend/admin/test-results/` and `vue-plan.md` were left untouched.

The public app declares Nuxt 4, Vue 3.6 RC, Vue Router, TypeScript, Nuxt UI 4, Tailwind 4 and MapLibre. SSR is false; Vapor is currently false following a recorded mounting problem. Preserve the working runtime combination rather than reopening that migration. Public/admin builds and API clients are physically separate. ECharts and D3 are vendored in legacy but not declared public Nuxt dependencies.

Useful foundations: typed same-origin transport, request deduplication/cancellation, URL filter state, versioned local collections, safe text/link components, evidence tables, caveats, map lifecycle wrappers, bundle gates, Vitest and Playwright. Reuse and strengthen these foundations.

Specific defects the redesign must avoid carrying forward:

- Mobile Sections expansion squeezes the nav beside the brand and clips controls at 390 px.
- `/authorities` is an instruction to visit Places, not a usable directory.
- Generic comparison rendering fails to distinguish `charity.total_income/total_expenditure` from `contracts.count/value_gbp`; do not reuse a generic `row.amount` assumption.
- Coverage API returns `sources`, while the Nuxt coverage page reads `datasets`.
- Nuxt and legacy disagree about `/coverage` and `/timeline` semantics; resolve by explicit compatibility rules, not route renaming alone.
- Provider inventory adds PFD mentions to tribunal cases. Replace with separately labelled holdings; never recreate that aggregate elsewhere.
- `accredited = 0` is rendered too strongly in provider comparison: use “No match under the checked name at this retrieval”, not “Not accredited”.
- Map feature state needs the vector `sourceLayer`, explicit removal of stale values, unique colour thresholds and distinct missing-value styling.
- Document selection lives outside the URL and can be lost; concurrent passage loads need stale-response protection.
- The basic provenance component truncates hashes without full inspection; several endpoints do not supply a hash at all.
- Some route smoke tests prove navigation with no API, not usable evidence or parity.

These are frontend findings, not permission to repair backend semantics. Existing API aggregate values may be present but unsuitable for prominent display; their presence does not overrule CAVEATS.md.

## 5. Existing routes and compatibility contract

Keep hash history. In this document `/pay` means `/#/pay`; `/api/v1/*` denotes an HTTP API path. Stable public API documentation at HTTP `/api` remains the Python server's responsibility.

| Existing application route | Final responsibility | Compatibility |
|---|---|---|
| `/` | Search, locator, evidence categories, coverage/freshness | Retain |
| `/providers` | Compact searchable provider directory | Retain filters and entity links |
| `/providers/:key` | Identity and evidence holdings, routable lenses | Retain exact provider keys |
| `/authorities` | Searchable authority directory | Replace instruction-only content |
| `/authorities/:code` | Map-first authority profile | Retain ONS codes, no successor remapping |
| `/geography` | Places map/list workspace | Retain metric/year and table/map bookmarks |
| `/pay` | Question-led pay/workforce lenses | Retain source/provider/year/unit filtering |
| `/contracts` | Notices, patterns and separate payments lens | Retain existing notice/filter links |
| `/contracts/process/:ocid` | Procurement lifecycle | Preserve flattened Nuxt child-route behaviour |
| `/treatment` | Measure-first treatment analysis | Retain indicator, topic, substance and area state |
| `/cqc` | CQC registrations, map/list, inspector | Add scoped shareable selection |
| `/pfd` | Safety and legal evidence | Keep path; relabel navigation accurately |
| `/documents` | Public document search with adjacent passage reader | Preserve query, document and element bookmarks |
| `/claims` | Published evidence-backed statements | Keep claim identifiers and citations |
| `/relationships` | Commissioning lens of Connections | Keep centre and relationship selection |
| `/pathfinder` | Verified-path lens of Connections | Keep endpoint types/identifiers |
| `/cooccurrence` | Mentioned-together lens of Connections | Preserve repeated keys; no asserted graph edges |
| `/compare` | Same-type peers, one evidence lens | Preserve legacy arrays and single-entity starters |
| `/timeline` | Coverage history or explicit provider events | Resolve legacy and Nuxt forms below |
| `/coverage` | Evidence coverage guide/overview; entity history when selected | No-entity route remains useful |
| `/diary` | Procurement dated events | Keep provider/authority/OCID scope |
| `/discrepancies` | Source observations side by side | Preserve entity scope |
| `/revisions` | Procurement/document version differences | Preserve explicit A/B and subject selectors |
| `/changes` | Recorded warehouse changes | Keep type/source/since filters |
| `/calendar` | Publication cadence | Preserve stated/observed distinction |
| `/catalogue` | Dataset directory and `dataset` detail selection | Keep query-addressed detail |
| `/doctables` | Extracted grids and context | Keep document/table identifiers |
| `/links` | Recorded source-link/archival status | Preserve `url` selection |
| `/notebook` | Saved evidence notes | Preserve existing entries |
| `/saved` | Named views | Preserve saved URLs |
| `/journey` | Recent visits in this browser | Preserve storage and bounded history |
| `/api` | Public API reference links | HTTP `/api` remains unchanged |

Add only frontend routes: `/search`, `/documents/:id`, `/research-tools`, `/about`. No Services, Reviews, global Timeline or standalone company directory is invented.

Compatibility resolution is deterministic:

- `/timeline?provider=…` or `authority=…` retains the legacy coverage-history meaning. Replace its URL with `/coverage?lens=history&provider_key=…` or `ons_code=…` without adding a Back entry.
- `/timeline?provider_key=…` retains Nuxt provider events. Canonical new links include `lens=events`. `/timeline` without a selection offers Coverage history and Provider events, with readable entity pickers.
- `/coverage` without an entity is the coverage/limitations guide. Existing `provider_key`/`ons_code` bookmarks select history. New links make `lens=history` explicit.
- `/documents?doc=…&element=…` opens the new reader, preserving `q` and supported search context. Accept `element_id` as the canonical spelling. Do not silently substitute an element from a newer parse.
- Translate known legacy query names (`provider`, `authority`, `ons`, `providers`, `authorities`) only in the routes where legacy code uses them. Record the exact accepted forms from legacy filter readers in a fixture table before editing routing. Canonical keys win if both forms exist; show a non-blocking conflicting-filter explanation. Never map provider names or aliases to identities by guesswork.
- Existing server-returned hash links pass through the same compatibility adapter. Validate internal route structure and external HTTP(S) links; source-derived strings never become raw markup.

## 6. Data/API capability inventory

API existence is confirmed in code; population, completeness and current availability are deployment-dependent. The warehouse is not queried to manufacture example statistics for this plan. Source families available in storage but absent from the public API stay out of the redesign's data access.

All short paths in the following table are under `/api/v1/`.

| Capability | API/source | Entities | Geography | Time | Provenance | Comparison and frontend use |
|---|---|---|---|---|---|---|
| Authority spine/boundaries | `authorities`, `boundaries`, `/map/boundaries.json` | Authorities | ONS identities and polygons | Boundary edition where supplied | Map attribution/manifest and API metadata | Neutral locator, directory, boundary context |
| Analytical geography | `geography`, `atlas_layers`, `layers` | Authorities; registered locations | Published metrics/coordinates | Metric-specific `year` | Per-layer caveats; row metadata varies | One approved layer, map/list, inspect |
| Provider identity | `providers`, `providers/:key/lineage` | Tracked providers/identifiers | Only documented connections | Status and dated lineage | Returned lineage basis/source fields | Identity confirmation, no merged-history arithmetic |
| Provider evidence | `providers/:key/timeline` | Provider and associated records | CQC/local links when explicit | Source-specific event dates | Per event/row, not one source for all | Inventory, financials, filings, legal records, chronology |
| Procurement | `contracts`, `contracts/process/:ocid`, `contract_diary` | Notices, suppliers, buyers | Deterministically matched buyer | Publication/award/start/end | Notice URL, retrieval, hashes where returned | Notice discovery; existing distributions; lifecycle |
| Council payments | `council_spend` | Payment rows and source files | Authority and exact provider match | Published period labels | Row/file provenance and parse status | Separate payment table, no sums across files |
| Charity/provider finances | `pay`, provider timeline, `compare` | Provider-linked charity | Organisation-wide, not LA spending | Accounting year end | Source-specific rows | Income/expenditure in same-source view; no salary inference |
| Company information | Provider timeline/lineage, verified path responses | Company/registered provider identity | No invented operating footprint | Filing and lineage dates | Match basis, published filing links | Filings and verified identity pivots, no officer data |
| CQC | `cqc_locations`, provider timeline, `layers` | Registered locations/providers | Coordinates and matched authority | Rating, registration, inspection dates | API/bulk rating origin explicitly labelled | Current result-window map; inspection; no service counts |
| Advertised/provider pay | `pay`, `provider_compare` | Provider, advert, disclosure | Only fields supplied | Advert/disclosure/report dates | Published source text and provenance | Separate hourly/annual observations; no conversions |
| Workforce census | `pay` | Sector sample and segments | Sector aggregate | Individual census round | Verification flag, source/page where supplied | Tables by one round; no provider attribution or trend |
| Statutory/Living Wage/GPG | `pay`, `provider_compare` | Statutory band; checked employer/filing | National/provider identity | Effective/reporting/retrieval dates | Published band, checked-name basis | Separate lenses; no wage-floor ratio or accreditation inference |
| External workforce comparators | `pay` | ASHE/SfC populations | Published area/category | Source periods/versions | Observation text and source metadata | Separate tables, no market-gap arithmetic |
| NDTMS | `ndtms`, `treatment_metrics`, authority payload | Published estimates/cohorts | Matched LA, aggregates separately | Source periods, some catalogue ranges only | Row metadata and paired CI | Estimates with bounds; suppressed/raw cells retained |
| Fingertips | `fingertips`, `treatment_metrics` | Indicators/observations | LA and separate England series | `time_period_sortable` plus exact labels | LA row metadata; England provenance is less detailed | One measure and unit per chart; CI where returned |
| Grants and LA budgets | `geography`, authority, `compare` | Authority allocation/budget line | LA | Financial year/status | Grant row hashes; budget aggregates have limited metadata | Separate cash-value charts; no added ring-fence or inflation estimate |
| Tribunals/PFD/SAR/HSE | Provider timeline, `pfd`, `safety`, `safety_legal` | Cases/reports/mentions/notices | Coroner/board areas are not LA polygons | Different source date meanings | Match/relationship/result fields and sources | Separate lanes and source-specific tables |
| Committee/CDP documents | `document_search`, `documents/:id` | Promoted public document elements | No public provider/authority search facet | Publication/retrieval, active parse | Source/page/title basis; no hash in context response | FTS, passage reading, explicit name searches |
| Extracted tables/revisions | `document_tables`, `record_diff` | Documents/elements/versions/processes | Only original document context | Parse/source versions | Extraction state and returned source references | Raw grid inspection and differences, no re-extraction |
| Commissioning graph | `relationships`, `relationships/:id` | Authority/provider | Via exact entity identifiers | Edge validity and notice dates | AWARDED_TO, source/derived relationship basis | Structured bipartite view; dated evidence per edge |
| Verified paths | `relationship_path` | Provider/authority/supplier endpoints | Only recorded edges | Per-edge dates where supplied | Verified path; bounded traversal | Hop-by-hop diagram/list, no universal network |
| Co-mentions | `cooccurrence` | 2–5 provider/supplier keys | No general geographic query | Varies by record; some absent | Passage/record links, incomplete metadata | Up to 200 returned records; distinct meaning from relationship |
| Published claims | `claims` | Human-authored published claim/citations | As stated by claim | Returned dates | Resolution state of each citation | Read/cite/save, no editing or new claim synthesis |
| Contextual comparators | Authority payload | Rough sleeping/H-CLIC/TA observations | One LA | Snapshot/year/quarter | Rows, raw markers, caveats | Context-only tables; no cross-layer rates or TA peer trends |
| Coverage/freshness/cadence | `catalogue`, `freshness`, `coverage_timeline`, `publication_calendar`, `changes`, `meta` | Dataset/source/entity | Depends on dataset | Retrieval vs coverage vs publication vs change | Response-level definitions, licences and dates | Coverage guide and homepage status, no live-health claim |
| Source resilience | `source_link` | Exact source URL/archive observation | None | Last observed fetch | Recorded status/hash verification | Supporting provenance tool, not an archive download API |
| Saved research | Existing browser storage | Notes/views/recent visits | User-selected | Save timestamps | User notes explicitly not evidence | Local persistence/import/export, no server accounts |

Unavailable as public frontend capabilities: a canonical treatment-service directory; service-to-contract-to-commissioner joins; provider reviews; general public topic/entity-mention APIs; public semantic/vector/hybrid retrieval; model predictions; ICB board-paper search; arbitrary archive/PDF access; full ownership expansion; authenticated cross-device investigations. NLP and semantic retrieval exist on operator surfaces, not as permission to query them from public code.

## 7. Evidence-intelligence interaction contract

Use explicit IDs from public responses for entity pivots. Text search can suggest a lead but never creates an attribution. A provider “Search this name in documents” action opens `/documents?q=<canonical name>` with a visible explanation that this is a textual search, not a provider-linked evidence list. Authority names work the same way. Missing graph identities disable graph expansion, not the whole profile.

Entity names remain ordinary links with browser Open in new tab behaviour. Each relevant row also has visible Inspect, Compare, Save and View evidence actions. Clicking a map mark selects/inspects; Enter on its equivalent list item does the same. No double-click, right-click, shift-click, hover-only or drag-only action is essential. Do not build a custom context menu in v1.

Selection highlights only the exact ID or observation in compatible visible views. A highlighted authority does not filter provider-wide finance, and a selected provider does not filter national workforce census. Cross-filtering acts only where section 16 names a valid mapping. Hover is local and ephemeral; committed selections are shareable.

## 8. Final information architecture

Sidebar groups, in order:

- **Explore:** Overview, Search, Providers, Authorities, Places.
- **Evidence:** Contracts & payments, Pay & workforce, Treatment, CQC registrations, Safety & legal, Documents, Evidence-backed statements.
- **Research:** Compare, Connections, Verification tools.
- **Your work:** Saved views, Notebook, Recent visits.
- **Evidence coverage:** one entry opening the coverage area, whose local navigation is Guide, Catalogue, History, Freshness, Publication calendar, Recorded changes.

Connections uses local tabs linking `/relationships`, `/pathfinder`, `/cooccurrence`. Verification tools index links Revisions, Source discrepancies, Source links and Document tables. Contract diary is reached from Contracts and the tools index. No extra “Graph” navigation competing with Connections. About and API reference sit in the sidebar footer. Existing specialist URLs stay valid; grouping changes discovery, not access.

At initial desktop load Explore and Evidence are expanded, Research/Your work collapsed, with the active group always expanded. Sidebar collapse and group preference are browser-local. Collapsed mode uses labelled accessible icon buttons with tooltips. No module numbers or warehouse table names in primary navigation; schema names remain available in catalogue technical details.

## 9. Application shell and homepage

Use Nuxt UI dashboard primitives where compatible with the installed version; wrap them in public components rather than importing admin code. A fixed-height top bar contains brand, search-type selector, query box, and theme choice. On a phone it contains brand, Navigation and Search buttons. No keyboard shortcut hint or command parser.

Desktop sidebar width is 224 px expanded and 56 px collapsed. Top bar is 64 px. Main content fills remaining width; no `max-w-6xl` around analytical workspaces. Prose/reading blocks are capped separately at 70 characters. Use 24 px desktop and 16 px mobile content gutters.

Homepage:

```text
SectorTrace       [Providers | Authorities | Documents] [Search…]  Theme
Navigation        Understand providers and places through published evidence
                  Search / entity results       Neutral England locator
                  Evidence categories           Coverage and last retrieval
                  About the evidence · scope · methods · API
```

Default search type is Providers, visibly selected; changing type is explicit and changes the input label. This is an implementation default, not a global mixed search. Home embeds the same selector as `/search`. The neutral locator shows authority boundaries and names; no initial choropleth or provider-performance encoding. Selection opens an authority inspector with Open authority. Below it show a bounded, labelled list from catalogue/freshness, linking the full coverage area. Do not label the latest retrieval “live”. No headline contract total, composite quality score, cross-source evidence count or ranked provider list.

Render the introductory sentence, search and category links independently of data. Fetch directories and coverage independently; lazy-load map code when its reserved frame approaches the viewport. A failed map leaves authority search available; failed status data leaves investigation entry points usable.

## 10. Semantic design tokens

Create public tokens in the public CSS entry and map Nuxt UI tokens onto them. No admin import, runtime shared theme module or admin stylesheet edit. Tokens form a reusable vocabulary for a later admin project.

| Token | Dark default | Light |
|---|---|---|
| `--surface-base` | `#070707` | `#EFEFEF` |
| `--surface-panel` | `#141414` | `#FFFFFF` |
| `--surface-elevated` | `#202020` | `#E4E4E4` |
| `--surface-hover` | `#292929` | `#DCDCDC` |
| `--text-primary` | `#EFEFEF` | `#070707` |
| `--text-secondary` | `#B8B8B8` | `#454545` |
| `--text-muted` | `#9A9A9A` | `#595959` |
| `--border-subtle` | `#353535` | `#CCCCCC` |
| `--border-control` | `#7C7C7C` | `#767676` |
| `--interactive-primary` | `#3454D1` | `#3454D1` |
| `--on-primary` | `#EFEFEF` | `#EFEFEF` |
| `--interactive-link` | `#A6B5FF` | `#3454D1` |
| `--interactive-secondary` | `#34D1BF` | `#34D1BF` |
| `--on-secondary` | `#070707` | `#070707` |
| `--evidence-critical` | `#D1345B` | `#D1345B` |
| `--critical-text` | `#FF9BB2` | `#A51F40` |
| `--focus-colour` | `#34D1BF` | `#3454D1` |

Spacing scale: 4, 8, 12, 16, 24, 32, 48 px. Controls have 4 px radii; elevated overlays 8 px; analytical regions use borders and surfaces without decorative card rounding. Focus is a 2 px outline with 2 px offset, plus a contrasting separation where it crosses an accent surface. Borders carrying interaction meaning use the control token; subtle dividers need not imply a control. No opacity reduction on whole text containers.

Default dark is used when no preference exists. Dark/Light/System is available everywhere and persisted under a public-only versioned key. System follows `prefers-color-scheme`. Apply theme before the Vue mount using a local external asset; it must not depend on modifying Python's CSP. Synchronise root colour-scheme, Nuxt UI and visual wrappers. No inline script requiring a new server hash and no theme leakage into `/admin`.

## 11. Colour system

The canonical five colours remain recognisable; neutrals and accessible text shades derive the interface, not a replacement navy/cyan identity. Labels and locally bundled icons identify source families. Colour indicates selection, metric magnitude or a specifically supported state, never a invented evidence-quality rank.

Blue is the primary action; turquoise highlights selection with a shape/border cue. Crimson flags errors or a source's explicit caution, not “bad provider”. Missing values use neutral styling and a written legend. For multi-entity charts, combine blue/turquoise and light/dark variants with line dashes and distinct point symbols; selected entities retain their series identity within an investigation. Do not assign arbitrary red/green performance meanings to higher/lower numbers.

Use one sequential blue ramp for numeric maps. Recompute thresholds only when metric/year changes, not when an authority is selected. Up to five quantile bands from returned finite values; deduplicate equal thresholds. A constant series uses one labelled band. Unknown values sit outside the ramp. Legends state that these are bands of the current distribution, not targets or statistically significant differences.

## 12. Typography, data formatting and editorial style

Retain local Manrope 400/600/700 and Space Grotesk 500/700; remove unused face preloads but not unrelated assets. Do not add a font service or change family. Use Manrope for body, controls, navigation and tables; Space Grotesk for headings and prominent numbers. Do not request nonexistent weights or pretend these static files have optical sizing axes.

| Role | Size/line-height | Weight/family |
|---|---|---|
| Homepage title | `clamp(28px, 3vw, 40px)` / 1.15 | Space Grotesk 700 |
| Page/entity title | `clamp(24px, 2.4vw, 32px)` / 1.2 | Space Grotesk 700 |
| Section/subsection | 22/18 px / 1.3 | Space Grotesk 500/700 |
| Body/reader | 16 px / 1.65 | Manrope 400 |
| Analytical body/table | 14 px / 1.5 | Manrope 400/600 |
| Navigation/controls | 14 px / 1.4 | Manrope 600 |
| Metadata/provenance | 13 px / 1.5 | Manrope 400 |
| Prominent figure | `clamp(24px, 3vw, 36px)` / 1.2 | Space Grotesk 500 |
| Hash/technical ID | 13 px / 1.5 | System monospace |

Apply tabular lining numerals to analytical values; right-align numeric table cells. UK grouping/currency and date formatting use `Intl` with `en-GB`. Full monetary values are the table/export default; compact chart ticks expose full values in details. Keep currency and pay period exactly as supplied. Never increase apparent precision; preserve original value text beside ambiguous/suppressed values. Use a source-specific formatter where a statutory rate has fixed published precision.

Date-only strings stay date-only (no UTC conversion shifting a day). Display instants with timezone explicitly, default Europe/London; expose the original ISO value in provenance. Preserve financial-year, quarterly and rolling-window labels. A zero is rendered as zero only where the source semantics make it one. Unknown, not stated, unavailable and suppressed use distinct labels only when the response establishes that distinction; otherwise say “Not available in this response”. Long source URLs/hashes wrap and can be copied in full.

All authored public copy must use natural British English: spelling, grammar, terminology, dates and punctuation. Prefer “organisation”, “analyse”, “visualisation” and “programme” where appropriate. Preserve official names, exact source quotations, identifiers and source text as published; editorial consistency must never change evidence.

Write like a knowledgeable sector researcher: direct, specific, restrained and useful. Avoid generic AI-style prose, marketing language, inflated claims, repetitive sentence patterns, rhetorical questions, canned introductions/conclusions and unnecessary adjectives. Do not use phrases such as “unlock insights”, “dive into”, “powerful insights”, “seamlessly”, “leverage”, “discover the story behind” or “explore your data like never before”. The interface should sound like an evidence application, not a conversational assistant. Prefer **Contracts awarded to this provider** to promotional descriptions, and **No matching evidence found** to **We couldn't uncover any insights right now**.

Do not use em dashes or semicolons in authored public prose. Use full stops, commas or parentheses as appropriate, keeping sentences natural and varied. Preserve punctuation in exact source quotations, official names and technical content. This prose rule does not remove the em dash used as the table's missing-value symbol.

This applies to navigation, headings, descriptions, tooltips, empty/error states, About/methodology text, accessibility labels and generated export annotations. Review copy in context before release for natural British usage, specificity and factual restraint. Automated spelling or phrase checks alone cannot establish editorial quality.

## 13. Component architecture

Build public-only components in a shallow hierarchy:

- Shell: `AppShell`, `Navigation`, `SearchControl`, `ThemeControl`, `PageHeader`, `ContextBar`.
- Entities: `EntityHeader`, `EntityPicker`, `EntityInspector`, `CompareTray`, `IdentityLineage`.
- Evidence: `EvidencePanel`, `EvidenceResult`, `PassageReader`, `ProvenancePanel`, `Caveat`, `SourceReference`, `EvidenceState`.
- Analysis: `ChartPanel`, `MapWorkspace`, `RelationshipView`, `EvidenceTable`, `TimelineView`, `FilterBar`.
- States/overlays: `LoadingState`, `EmptyState`, `ErrorState`, Nuxt UI-based modal/slideover/drawer wrappers.

Extend existing St* components where their contracts fit rather than leaving competing implementations. Do not build a component for each individual table cell. Use Nuxt UI controls for interaction/focus management; use native semantic tables and text for evidence.

Frontend-only types to introduce:

```ts
type EntityRef = { kind: 'provider' | 'authority'; id: string; label?: string }
type ObservationRef = {
  endpoint: string; rowKey: string; query: Record<string, string | string[]>
}
type EvidenceContext = {
  observation?: ObservationRef; sourceUrl?: string; retrievedAt?: string
  publishedAt?: string; payloadHash?: string; page?: string
  caveats: string[]; scope: 'row' | 'returned-series' | 'result-window'
}
type ChartSpec = {
  id: string; question: string; unit: string; periodLabel: string
  rows: readonly unknown[]; evidence: EvidenceContext
  // A route-specific adapter supplies exact columns and interactions.
}
```

These describe presentation references, never new evidence rows. Every field is populated through an explicit endpoint adapter. Do not coalesce differently defined fields merely because their names look similar. Do not add admin schemas, backend query functions or raw warehouse data to the browser bundle.

## 14. Search; command palette excluded

Search is a visible form with an explicit type selector, not a command palette. No Ctrl/Cmd-K, `/`, multi-key navigation or natural-language action parser. Standard form submission, Tab, arrow keys within controls and Escape within overlays remain supported.

Providers and Authorities load their complete directory endpoints once per app session and filter names/identifiers client-side. Matching is a discovery aid, not entity resolution: exact label/id matches first, then case-insensitive substring matches, stable alphabetical tie order. Do not invent aliases. Show at most 20 suggestions with a link to the complete filtered directory. Submit routes to `/providers?q=…` or `/authorities?q=…`. Documents submits to `/documents?q=…`; no background document request per keystroke.

`/search?type=providers|authorities|documents&q=…` is the shareable entry form and accessible mobile search destination. Type defaults to Providers. A global query never silently searches every source. Document search states “Committee and CDP documents” and links contracts, pay, treatment and safety/legal. Source-family abbreviations are expanded on first use.

## 15. URL state and local persistence

Extend `useFilterState` rather than adding a second authoritative filter store. Use named route serializers to distinguish API parameters from UI parameters. Common UI keys: `lens`, `view=chart|data|map|list`, `inspect`, `inspect_type`, and `pane=list|map|reader`. Domain keys retain server spellings. Entity/profile lenses use stable lower-case slugs; unknown lens values fall back to Overview with a visible explanation.

Committed entity selection, lens, measure, submitted query, semantic date scope, comparison set and reading anchor belong in the URL. Hover, keyboard focus, panel widths, scroll offsets, unsent text and animations do not. Page offset is preserved for result-window reconstruction. Route changes/committed lens changes use push; filter edits and in-pane selections use replace. Session scroll/focus restoration records the full route, not just its base path.

The comparison tray holds distinct provider and authority sets locally for navigation continuity. `/compare` uses repeated canonical `provider_key` or `ons_code`, so the shared URL reconstructs the selected set without browser storage. Display up to four peers per type; a mixed legacy URL renders separate provider/authority tabs and never silently drops either set. More than four legacy entries remain listed with an explicit choose-four step, rather than truncating evidence requests.

Source references saved into notes may hold the metadata actually returned at save time, labelled “Saved reference”. Opening the live route never presents that snapshot as a fresh API response. Existing `st.notebook`, `st.saved`, `st.journey` records and old hash links survive. Keep entry fields backward-compatible; new optional source-reference fields do not require destructive storage replacement.

Use a single reactive collection service per app instance so Save actions and collection pages agree immediately. Keep the existing version-one envelope readable; add optional fields and validate before writing. Imports accept a documented JSON envelope with a maximum 10 MB file size and 5,000 entries, show a review with valid/rejected/duplicate counts, and merge only after the user selects Import. Duplicate IDs with identical content are skipped; conflicting content receives a new ID and an “Imported copy” title so existing notes are preserved. Reject script/data URLs, unexpected object prototypes and invalid field types. Preserve original exported IDs/references inside the import record where needed for traceability. Reset/delete actions are explicit, and never clear all browser storage.

## 16. Analysis state and supported filter propagation

Keep a small derived `AnalysisContext` for the selected entity and a typed date meaning; read committed state from the current route. It is not an independent global query or a promise that all panels share a denominator. Store unsupported context as a visible, inactive crumb in the current session, not as a fake API filter. The active page says which context applies; returning to the prior page restores its own URL.

| Destination/API | Allowed request filters | Local-only behaviour and exclusions |
|---|---|---|
| Providers/authorities directories | None | Name/id search and stable sorting on complete returned arrays |
| `contracts` | `provider_key`, `buyer_ons_code`, `year_from`, `year_to`, `psr_only`, `q`, `since_retrieved_at`, `limit`, `offset` | Year means publication year; no procedure, value-band or quarter filter claimed as server-wide |
| `council_spend` | `authority_ons_code`, `provider_key`, `limit` | Any in-window text filter is labelled; no date aggregation |
| `pay` | `provider_key`, `year_from`, `year_to`, `role`, `source`, `pay_unit` | Preserve endpoint-defined year semantics per source; national layers may remain unfiltered and labelled |
| `geography` | `metric`, `year` | Authority selection highlights; directory search narrows list, not the England distribution |
| `fingertips` | `indicator_id`, `topic`, `ons_code`, `substance` | Period/visual selection on returned series; no provider filter |
| `ndtms` | `ons_code`, `table_ref` | Preserve raw periods/cohorts; do not guess exact periods from catalogue range |
| `cqc_locations` | `provider_key`, `authority_ons_code`, `registration_status`, `regulated_activity`, `service_type`, `rating`, `limit`, `offset` | Coordinates/map cover loaded page, not a full filtered census |
| `document_search` | `q`, `source_system`, `document_type`, `year_from`, `year_to`, `since_retrieved_at`, `limit`, `offset` | No provider/authority/topic/confidence filter; name-search action is explicit |
| `documents/:id` | `element_id`, `context` | Reader state is not a corpus search filter |
| `relationships` | Exactly one of `provider_key`, `ons_code` | No generic depth/topic/source filtering |
| `relationship_path` | `from_type`, `from_id`, `to_type`, `to_id`, `max_hops` | Types provider/authority/supplier; 1–6 hops; respect bounded result |
| `cooccurrence` | Repeated `key` | 2–5 tracked provider/supplier keys, up to 200 results; not a universal entity query |
| `compare`, `provider_compare` | Repeated `ons_code`/`provider_key`; latter 2–4 providers | One actual returned layer, local period display; no normalisation/differences |
| `safety_legal` | `source`, `relationship`, `provider_key`, `year_from`, `year_to` | Counts stay separated; unfiltered supporting PFD/SAR tables must not appear filtered |
| `coverage_timeline`, `discrepancies` | Exactly one provider/authority | No all-entity or topical inference |
| `contract_diary` | `provider_key`, `buyer_ons_code`, `year`, `ocid` | Dates remain published event types |
| `changes` | `kind`, `source`, `evidence_type`, `since`, `limit` | Bounded feed, no global historical completeness claim |
| `record_diff` | `kind`, `a`, `b`, `ocid`, `document_id` | Retain exact version selection and refusal states |
| `document_tables`, `source_link`, catalogue detail | `document_id`/`table_id`; `url`; dataset path ID | Subject-specific reads, no cross-source search |

When moving from authority to contracts, map its ONS ID to `buyer_ons_code`; to CQC/payments, `authority_ons_code`; to treatment, `ons_code`. Only publication-year filters carry between document search and procurement, and only with an explicit label stating their scope. Never transplant retrieval dates into publication filters. Clear pagination when substantive filters change. Parallel requests have independent error states; abort obsolete loads and reject late responses by request identity.

## 17. Entity inspector

Desktop inspector is a labelled non-modal complementary region beside content, 360 px initial width, resizable 320–560 px only when the main pane remains at least 480 px. It has an explicit Close button, entity name/type, verified identity context, separately labelled evidence availability, View evidence, Open profile, Compare and Save. Do not fetch every profile lens to show the inspector.

Authority/provider inspectors use directories for immediate identity and lazy detail requests for the selected item. Unknown IDs render a targeted “Entity unavailable” state, not the previous selection. Link to full profile without discarding source view state. CQC/notice/relationship inspectors show their own record types, not provider metrics substituted into a generic panel.

CQC has no location-by-ID detail endpoint. Share the exact query, offset and location ID. On reconstruction inspect that returned page; if the location is no longer present, explain that the result window changed and offer the directory/provider/source where actually known. Do not crawl every page or fabricate a permanent service profile. A future direct record endpoint is documented in section 44.

Mobile inspectors are full-height modal sheets with focus trap, inert background, accessible title, Close and focus restoration. Desktop non-modal inspection does not trap focus. Opening by a visible Inspect button moves focus to the labelled heading; closing restores the initiating control where it still exists.

## 18. Provider directory and profile

`/providers` starts with an accessible search field and compact list: canonical name, explicitly returned organisation identifiers, and separately labelled holdings where supplied. Search is local over the complete directory response. Name links open profiles; Inspect opens the adjacent inspector. Keep unavailable holdings distinct from zero. Do not rank providers by aggregated evidence counts or imply a comprehensive market directory.

`/providers/:key` opens on Overview: canonical identity, supplied registration identifiers, lineage link, and separate evidence holdings. Holdings link directly to the relevant lens. Use these bookmarkable `lens` values: `overview`, `contracts`, `finance-pay`, `registrations`, `safety-legal`, `connections`, `history`. Unknown lenses explain the invalid selection and offer Overview. Load the timeline/profile payload once through the shared client; load other endpoints only when their lens needs them.

Contracts shows provider-scoped notices and links to process and buyer profiles. Finance and pay separates charity finance, pay evidence, disclosures and company/charity filings into labelled sections. Never call charity wage-per-head a salary. Registration evidence shows CQC locations and inspection records with source-defined dates and rating provenance. Safety and legal keeps tribunals, PFD mentions and other supported types separate. Connections uses verified public identity edges and commissioning relations with their exact relationship names. History separates dated events from coverage periods.

Identity lineage states what the source establishes: a rename, merger or company relationship does not establish staff, contract or service continuity. A company being dissolved is not an insolvency finding. Show unresolved identifiers as text with provenance; invent neither profiles nor crosswalks.

Provide an explicit **Search documents for this name** action. Its destination is a textual query, labelled as such; no document holding count or name match creates a verified provider–document relationship. Notes can reference a profile, observation or exact document passage independently.

## 19. Authority directory and profile

`/authorities` is a working name/ONS-code directory with compact rows, Inspect and Open profile. Do not merge historic authorities with successors. `/authorities/:code` starts with a MapLibre boundary view, then commissioning context. This ordering is an explicit interview decision.

Profile lenses are `overview`, `commissioning`, `funding`, `treatment`, `contracts`, `context`, `history`. Overview shows identity, the selected boundary, separate holdings and a concise list of documented commissioning connections. Commissioning expands those connections, with inspectable relationship provenance. Contracts shows notices. Funding keeps grant allocations, allocation status, public-health budgets and payment evidence separate; drug/alcohol ringfenced allocations are part of the total grant, not an additional amount.

Treatment links into a selected measure and preserves area identity. Context contains rough sleeping, statutory homelessness and temporary accommodation in separate sections with source-specific caveats. Temporary accommodation remains a contextual table: no rate, cross-authority ranking or quarter-to-quarter calculation. Rough-sleeping estimation methods remain visible. None of these contextual series becomes an explanation for treatment outcomes.

The authority boundary is a locator until a user explicitly selects a supported metric. Missing geometry shows identity and evidence normally with a map-specific explanation. Commissioning connections use the relationships endpoint; the profile’s notice list is capped and must show its returned-versus-total scope. Budget aggregate rows lack row-level provenance in this response: expose available context accurately and use a supported source-specific route where useful, without borrowing metadata from another observation.

## 20. Services and CQC registrations

There is no public service registry or location-by-ID detail API. Do not create a Services navigation item or `/services/:id` route. The feasible experience is `/cqc`, labelled **CQC registrations**, with provider, authority, registration-status, activity, service-type and rating filters supported by the API.

Default to a compact list with a visible Map/Data switch. A desktop map can sit alongside the list and inspector. The map displays only located records in the loaded result window. State total matching registrations, loaded records and mapped records separately; the API’s `without_coordinate` count has its own response scope. A cluster means loaded locations nearby, not a treatment-service count or market share.

Do not split a regulated activity name on commas. Region facet values are not a server-supported region filter. Facet counts reflect the endpoint’s provider-based facet scope, not every currently active filter. Rating provenance distinguishes API and bulk-export origins. Status and rating are text first, with source dates, rather than a composite quality score.

Inspect opens the returned location record, CQC source link and any explicitly supplied provider link. Share selection through query, offset and record ID as described in section 17. The absence of a selected record after refresh produces a stale-selection state; it never opens a different location.

## 21. Places and MapLibre

`/geography` is the Places workspace: one active layer, linked authority list, inspector and visible layer/year controls. Start with a neutral locator when no metric was chosen. Offer only the eight atlas keys actually supplied: `grant_drug_alcohol`, `grant_total`, `grant_per_head`, `budget_public_health`, `treatment_numbers`, `contract_value`, `cqc_locations`, `coverage`. Show human labels, definitions, units, period and source caveats before activation. Contract value is a source-notice observation layer, not a headline contract total; coverage means holdings, not evidence quality.

Use the existing same-origin boundary manifest and PMTiles assets. Do not add external map styles, glyph servers or geocoders. Boundaries join by the exact ONS key supplied by the map manifest. Never assign a successor’s value to a historical boundary. Use layer-supplied periods/available years; a year selector must not imply that all layers describe the same period.

Selection highlights the authority in map and list and opens its inspector. A second click does not silently navigate. The name/Open profile control navigates. Keyboard users obtain the same selection and navigation through the list. Geographic panning changes the viewport only; it does not silently filter the evidence list. A visible **Search this area** control is excluded because the existing API has no corresponding spatial query.

Metric scales use at most five ordered bands, computed over the returned layer's valid numeric observations and labelled as display classification. Deduplicate thresholds; a constant-valued series gets one band. Zero, missing and out-of-scope each have distinct labels/styles. Show exact breakpoints and classification method in the legend. A selected authority remains outlined regardless of its data value. No diverging scale unless the measure has a meaningful supplied reference value.

Set and clear vector feature state with the manifest's source and `sourceLayer: 'authorities'`. Clear stale values when layer/year changes, and synchronise current selection after style reload. This requirement follows MapLibre's [feature-state API](https://maplibre.org/maplibre-gl-js/docs/API/classes/Map/). Resize through a scoped observer; remove listeners, controls and map instances on unmount. A failed map chunk or WebGL context leaves the complete authority list usable.

Do not load the full atlas merely to draw the homepage locator. Provider footprint maps may show supplied CQC coordinates as registration locations, with the same result-window warning. Never infer treatment catchments, commissioning exclusivity or provider service coverage from points.

## 22. Evidence Explorer and specialist evidence lenses

Evidence Explorer is a shared interaction pattern across existing routes, not an invented universal-search endpoint. Each route has a title/question, definition and caveat, supported filters, results, optional chart, record inspector, source controls and scope-labelled export. Evidence-family entry points route to these concrete datasets.

**Contracts:** `/contracts?lens=notices` is the default. Display notice title, buyer, matched provider, notice type, publication date, source value and process link. Notice values remain attached to their records; do not promote `total_value_gbp`, concentration or a largest-provider metric to a headline. `lens=patterns` offers publication counts by year/quarter, procedure and value-band distributions, with the restrictions in section 40. `lens=payments` calls `council_spend` and keeps files, councils, periods and rows separate. No cross-file payment total. Local sorting/filtering/export states that it covers the returned response; this endpoint has no offset or general date filter.

**Procurement process:** `/contracts/process/:ocid` opens ordered source stages and their evidence, with a timeline/list switch only if the records contain usable dates. Preserve cancellations, replacements and amendments. A sequence of notices is not a sequence of separate awards. Each stage opens the original notice and available revision tools. The related diary is explicitly about procurement dates, not all sector events.

**Pay and workforce:** `/pay` first presents questions that select a source lens: charity wage observations; advertised roles; provider-published pay; statutory rates; living-wage name checks; gender pay gap; national workforce census; ASHE; Skills for Care context. Map source choices to the actual returned `source_groups`, not new backend enumeration values. Each lens has its own unit, population and period labels. Keep nationally scoped data labelled national when a provider is selected.

In the current pay implementation, year bounds constrain charity wage observations; do not imply that they filter adverts, census or statutory rows. Role/unit filters do not necessarily constrain precomputed `nhs_job_by_band` aggregates. Prefer individual advert ranges to a potentially mismatched band summary. Annual salary displays use the source's annual period, without converting hourly values. Missing min/max values remain missing. Repeat-advertised-role candidates stay explicitly labelled candidates for reading, never a finding or a vacancy count. A failed living-wage name match is not proof of non-accreditation. Gender-pay-gap employer IDs stay distinct.

**Treatment:** `/treatment` starts with the measure catalogue, including definition, source, unit, population, geography and period availability. Then select an authority. Fingertips uses its supplied period sorting; show the England comparator only with its actual provenance limitations. NDTMS without an authority is a catalogue, not an empty national series. With an authority, `estimates` supply `value`, `lower`, `upper` and `has_interval`; draw an interval only when both numeric bounds exist. Retain `other_rows`, suppression markers and original publication labels in the data view. Publication edition and observation period must never be substituted for each other. Do not manufacture monthly data or enumerate a `period_range` as if every intermediate period is held.

**Safety and legal:** `/pfd` becomes the entry to separate source lanes, using `safety_legal` and existing supporting public responses. Keep PFD sent-to/named distinctions, tribunal records, SAR material and HSE records separate; preserve source statuses such as appealed or withdrawn. Keyword hits are reading aids. Coroner areas are not authority boundaries. Verify which filters reach each response; supporting unfiltered PFD/SAR tables must be labelled accordingly.

**Statements:** `/claims` presents published campaign-authored statements with claim text, citations and caveats. “Evidence-backed statements” is the navigation label; authorship remains explicit. A missing/unresolved citation is visibly unresolved, not removed or replaced. No client-authored claims, automatic verification badge or claim generation is introduced.

## 23. Documents and passage reader

`/documents` uses a resizable results/reader split on wide screens. Search covers only the public committee-paper and CDP-document sources exposed by the API. Supported controls are query, source, document type, publication years and retrieval-since where explicitly labelled. Results show title and title basis, source, date type, page and excerpt. A generated title is not presented as the source's published title.

Selecting a result updates the URL's document and element IDs and loads bounded context. **Open reader** navigates to `/documents/:id?element_id=…`; both forms remain shareable. Preserve search context in a validated internal return link, not an arbitrary redirect. Reader headings show source URL, publication/retrieval dates and parser information when available, plus total elements and currently displayed range.

Use source element order, safe text nodes and semantic headings/paragraphs. Highlight the selected passage without changing quoted text. Previous/Next context uses supplied range and availability flags; never automatically download every element. Passage controls include Copy reference, Copy passage, Save note and Open source. Copy passage preserves the exact returned text and attaches a separate reference, not edits disguised as quotation.

The context endpoint exposes the active parse, so an old element may no longer resolve. Show that exact failure, retain its saved reference and allow an explicit current-document search. Do not substitute the nearest element. Extracted-table links use `/doctables` with exact IDs. The public API does not serve archived PDF bytes: Open source opens the original URL, and source-link inspection reports recorded archive status without inventing an archive-download action.

Documents are evidence objects with citations and explicit outbound pivots. A name in text is not automatically an entity relationship. No semantic search, NLP topic explorer, universal mention graph or unreturned document-to-provider joins are introduced.

## 24. Connections and D3 relationship views

Connections has three visibly separate lenses using retained routes: Commissioning (`/relationships`), Verified paths (`/pathfinder`) and Mentioned together (`/cooccurrence`). Their explanatory sentence stays next to the lens title so users cannot mistake one relationship class for another.

Commissioning uses a structured, deterministic authority-to-provider arrangement. D3 scales/shape/layout helpers may calculate geometry; Vue owns controls and safe textual content. Use parallel named columns and selectable edges, without force simulation, flying nodes, 3D or a background network fetch. Edge inspection shows relationship type, validity dates, source system, recorded confidence category and source metadata; edge detail opens supporting notices and their truncation warning.

Only recenter or open profiles when an explicit public provider key or ONS code is available. A graph `entity_id` is not interchangeable with either. Unresolved nodes remain inspectable graph records with source references. Do not infer identities from similar names. Show all returned edges in a paged semantic table even when the diagram initially displays a bounded subset; disclose visible-versus-returned counts and offer an explicit next group.

Verified paths has two endpoint pickers and a 1–6 hop bound. Show returned paths as ordered sequences, preserving evidence per edge. The bounded search's no-path result means no path returned under these limits, not that the entities are unconnected. Endpoint types are the actual supported provider/authority/supplier types, not every graph node type.

Mentioned together accepts 2–5 supported tracked keys. Present documents and structured records as lists with their actual matched names. The structured branch can match two or more selected keys while document matching requires all selected keys; use **Records naming multiple selected organisations**, not an all-selected guarantee. Returned results are bounded at 200 and are not an exhaustive relationship census. Co-mention never becomes a commissioning or ownership edge.

## 25. Comparison workspace

`/compare` uses a same-type selection tray for 2–4 authorities or 2–4 providers. One selection is a useful starter state. Preserve mixed legacy URLs by showing separate authority/provider selections and asking the user to choose a lens; do not send a mixed set into a misleading chart. More than four saved selections produce a visible selection correction, never silent truncation.

Choose one source lens at a time. Authority lenses from `compare` are grants, public-health budgets, treatment observations and contract-notice counts. Provider lenses are charity finance and contract-notice counts, plus `provider_compare` living-wage checks, gender pay gap, published pay and job adverts. Read exact response keys: charity uses `total_income`/`total_expenditure`; contract series use `count`/`value_gbp`; they do not share a generic `amount` field.

Use aligned small multiples where shared scales would imply equivalence that is not established. A shared numeric axis is allowed only within the same supplied measure, unit and comparable population. Keep financial-year-end dates and employer IDs visible. Do not calculate rankings, ratios, percentage change, per-employee values, correlation or a combined provider score. No pay annualisation or inflation adjustment.

A visible Chart/Data switch defaults to Chart when the selected evidence has a justified chart in section 40; otherwise use the evidence table. A missing observation keeps its entity in the comparison with an explicit gap. Both data/reference export and annotated chart export are first-class controls, with their scope made explicit.

## 26. ECharts implementation contract

Add ECharts only to the public app and lock its resolved version during implementation. Import the required chart, component and renderer modules into lazy chart components; avoid a global all-charts import. This follows the official [modular import guidance](https://echarts.apache.org/handbook/en/basics/import/). Register accessibility support deliberately and use patterns as well as colour where needed; ARIA is not automatic simply because a chart renders ([ECharts accessibility guidance](https://echarts.apache.org/handbook/en/best-practices/aria/)).

Prefer SVG for bounded line/bar/range views and straightforward export. Use canvas only after profiling a justified larger view; the data table is available in either case. Dispose chart instances on unmount, update through stable series IDs, observe container resize and remove event handlers. An obsolete request must not repaint a chart after filters change.

Charts have a textual question/title, unit, period, scope, legend, visible Chart/Data switch, source/caveat action and export controls outside the drawing. Tooltips contain entity, exact observation label, formatted and raw value where useful, unit, period and source status; they are never the only place to obtain these facts. Selection details appear in accessible HTML. Do not build source-controlled HTML tooltip strings.

Click only changes a supported filter. A category with no matching API filter merely highlights/inspects that aggregate and states its scope. Zoom changes display range; it does not imply a new source query. No smoothing, stacked cross-source sums, hidden interpolation, truncated bar baselines or decorative animations. Use gaps for missing points. Supplied uncertainty bands belong to the observation, not a separate optional decoration.

## 27. Tables and exports

Extend the existing semantic evidence table with typed column definitions, labelled sort buttons, explicit scope, pagination, row inspection and optional column visibility. Preserve native `table`, `th`, `caption` and row relationships. Use server pagination where supported. Sort only the returned window when the API cannot sort globally and label that limitation beside the control. Do not add a spreadsheet grid or virtualise ordinary 25–50 row pages.

Long text wraps in its primary column; numbers align right with tabular numerals; source links have meaningful labels. Null displays as an em dash with an accessible missing-value explanation, never zero. Suppressed original strings remain visible. A wide table scrolls inside its own labelled region rather than widening the whole page; mobile offers record cards only when every material column remains accessible.

Export is a scope contract. Existing `/export` supports only `summary`, `providers`, `authorities`, `contracts`, `pay`, `geography`, `fingertips`, `ndtms`, `pfd`, in CSV/JSON. `contracts` and `pfd` support the server's complete filtered stream; do not implement fetch-all pagination. `pay` exports charity wage series only, and `ndtms` exports estimates only. Use those only for a matching lens and explain excluded contextual rows. Never point an advert export at the pay export endpoint.

For unsupported export endpoints, provide **Displayed rows (N)** as a browser download and a companion JSON reference manifest with canonical query, export scope/time, source metadata actually available and caveats. JSON preserves original values. CSV protects spreadsheet-interpreted text formulas without converting numeric negatives into strings or changing the stored evidence. Local table export must not be called a complete dataset.

Annotated chart PNG export includes title/question, entity/measure/unit/period, filter scope, caveat summary, source references and application URL. Also offer the reference manifest so long citations are not squeezed into illegible footnotes. SVG may be offered where safely serialised and self-contained. Exports capture the current evidence view, not hidden points or personal notes by default. Map/graph image export is optional future polish; do not delay required chart-image and data/reference parity for it.

## 28. Timelines and date semantics

Use three distinct forms: source event chronology; procurement lifecycle; evidence coverage periods. Do not combine them into an undifferentiated sector timeline. Provider events use source-labelled lanes; safety/legal lanes never share a headline total. Procurement entries distinguish publication, start, end and other supplied date types. Source order is preserved when chronology is unknown.

Coverage history consumes `sources`, not `datasets`. Its `years` axis is a display scaffold, not an observation series. Preserve exact calendar-year, fiscal-year and textual period labels in cells and the accessible table. A blank cell means no holding represented in this response, not no underlying activity. Clicking a held cell opens the supplied source link or relevant evidence route with supported context.

Default timelines to ordinary semantic lists or a small CSS/SVG matrix; ECharts is reserved for numeric series. Use D3 only if a later measured interaction need exceeds these primitives. Do not calculate elapsed durations between imprecise dates or present unknown dates as 1 January.

## 29. Provenance and evidence UX

Every observation or relationship has an adjacent Source control. Essential caveats remain in the view; fuller provenance opens in a reusable drawer/popover with source URL, retrieval time, publication/observation dates separately, exact hash if supplied, source system, parser/version or page/element where supplied, and citation actions. Show **Not supplied in this response** for absent metadata, rather than inventing it or describing the source as unverified without evidence.

Keep row, series and result-window provenance distinct. The latest `source_link` observation for a URL cannot authenticate older bytes solely because the URL matches. Do not fetch a newer hash and attach it to an older row. Archive held/verified flags describe the returned archive record and do not create a public download URL.

Use **Source record**, **Derived relationship**, **Published estimate**, **Extracted passage** or other accurate supplied categories, with a short explanation. Do not invent a global confidence percentage, source-quality rank or “verified” badge. A census transcription verification flag does not certify the wider factual claim. Census `source_page` is zero-based; only that documented field receives +1 for human page display. Other page numbers retain their own semantics.

Copy reference contains the source title or its honestly labelled fallback, source URL, exact passage/page/record identifier where available, relevant dates and full hash if available. The reference never implies a hash was checked client-side. Notes contain user text separately from evidence excerpts and retain their original references even when the current source changes.

## 30. Freshness and evidence coverage

Evidence coverage is one navigation area with distinct Guide, Catalogue, History, Freshness, Publication calendar and Recorded changes views. Guide explains provenance, missing values, evidence-layer separation and interpretation limits. Catalogue preserves per-dataset definitions and existing IDs. History is entity-specific. Freshness shows recorded retrieval dates by source/table and clearly states that retrieval is not publication or successful completeness.

Publication calendar separates stated schedules from patterns inferred by the existing API. A next-expected date is an expectation, not a promised release. Recorded changes describes warehouse observations, not necessarily changes in a provider or sector. Keep successful reads, unavailable source information and failed UI requests distinct. Do not create a green global “all systems healthy” badge from sparse timestamps.

The homepage links to this area with a small secondary coverage/freshness summary. No aggregate quality score, completeness percentage across heterogeneous sources or live monitoring claim is added.

## 31. Overlays and panel behaviour

Reuse existing Nuxt UI primitives for navigation drawers, modal sheets, popovers, tooltips and split panels, wrapping them in SectorTrace components where behaviour is shared. The [component catalogue](https://ui.nuxt.com/docs/components/) is the implementation reference; validate actual installed props and keyboard behaviour rather than copying a newer example blindly. Do not add a second UI framework.

Only one modal overlay is active at a time. Source detail launched from a mobile inspector replaces its content with a clear Back action, rather than nesting inaccessible sheets. Desktop provenance can use a labelled popover for short records or the inspector panel for long ones. Tooltips explain controls; they contain no essential evidence or interaction unavailable elsewhere.

Map/list and document-result/reader splits may resize on wide screens. Persist proportions per workspace in local storage, constrain them to usable minima and provide Reset layout. Use a focusable separator with orientation, current value and standard arrow-key resizing; pointer dragging is an additional method. No arbitrary per-card resizing or drag-to-rearrange dashboard is introduced.

## 32. Desktop layouts

At widths of 1200 px and above, show the grouped 224 px sidebar, 64 px top bar and appropriate split workspace. The sidebar may collapse to 56 px with accessible named icons/tooltips. Main content keeps at least 480 px; if opening the inspector would violate that, collapse the secondary split or use an overlay. Document results start at 38% of the available split, reader 62%; Places list starts at 32%, map 68%. Apply the shared minimum sizes and local persistence, not fixed page widths.

Between 768 and 1199 px use collapsed navigation, one principal evidence pane and an overlay inspector. A visible Results/Reader or Map/Data control changes pane. Profiles use a single flowing column with wrapping lens navigation. Avoid horizontal page scrolling; reserve horizontal scroll for labelled tables or graph canvases with an equivalent list.

The homepage's wide layout gives search and entity entry roughly equal visual importance to the locator, rather than letting a metric dominate the first view. Evidence categories follow, then secondary coverage. A profile map has a bounded height so identity and commissioning context remain discoverable below it.

## 33. Mobile strategy

Below 768 px, show one pane at a time. Top bar contains brand, search entry, theme and Sections; Sections opens a navigation drawer rather than expanding into the brand's flex row. No tiny persistent icon rail. Search/type selection fits the width, filters open in a labelled drawer, and an active-filter count and Clear action remain visible in the results header.

Maps have explicit Map/Data controls; readers have Results/Reader controls. Preserve selection and scroll position when switching. An inspector is a full-height sheet with its own scroll region and an always reachable Close button. Comparison becomes vertically stacked entity panels under one measure header. A graph becomes an ordered edge/path list by default, with an optional diagram view.

Use at least 44 px touch controls as the design target. Avoid actions that require hover, double-click or drag. Do not intercept browser pinch zoom. At 320 px and 400% desktop zoom the shell and explanatory content reflow; wide evidence tables remain locally scrollable with a visible cue. Test real content lengths, long provider names, ONS codes, hashes and date labels.

## 34. Accessibility

Target WCAG 2.2 AA behaviour, with keyboard and screen-reader review as release criteria. Use a skip link, one main region, logical headings, labelled navigation groups, descriptive page titles, `aria-current` for current navigation and properly associated field errors. Standard browser links preserve Open in new tab and Copy link behaviour.

Only conventional keyboard interaction is included: Tab/Shift+Tab, activation, Escape for overlays, and standard arrows for selected widget patterns. No command palette or application-wide Ctrl+K, slash, letter sequences or custom shortcuts. Inspect buttons, export controls and pane switches are visible to all users.

Text contrast targets 4.5:1 for normal text; graphical controls and essential boundaries target 3:1. Test actual adjacent surfaces, focus rings, chart colours and both themes. Colour is accompanied by labels, line styles, symbols or patterns. A map is never the only geographic selector; a graph is never the only record list; a tooltip is never the only source of a value.

Async results use a polite status region for counts/errors without announcing every chart update. Loading regions use `aria-busy`; skeletons are hidden from accessibility APIs. Route navigation focuses the page heading after deliberate navigation, but filtering does not steal focus. Modals trap/restore focus; non-modal inspectors do not. Automated scans complement manual keyboard, zoom and screen-reader checks.

## 35. Performance architecture

Retain static Nuxt generation, hash routing and Python serving. Keep existing bundle-budget checks and deployment gates; do not raise thresholds merely to fit a dependency. Baseline the current production build before implementation. MapLibre, ECharts and D3 must be separate lazy features; document, coverage and basic directory routes must not fetch chart/graph bundles. The homepage loads the locator after primary search content becomes usable.

Load only same-origin fonts, icons, worker code, styles and map resources. Reuse local static font files, preload only the primary body face actually needed above the fold, and use font-display swap with stable fallback metrics. Do not introduce external analytics or font services.

Use shared deduplicated requests and AbortController; route-specific adapters whitelist API parameters separately from UI state. Document search runs on explicit submit, never on every keystroke; cancel obsolete requests. Local directory filtering may update immediately without a request. Cache complete provider/authority directories within the browser session; do not persist evidence payloads in local storage or serve stale response data as current after a failed reload. Saved references are explicitly labelled snapshots as specified in section 15.

Default document/table pages to bounded response sizes, normally 25–50 where supported. No automatic traversal of all CQC/documents/graph pages. Initially draw at most 100 graph edges and expose remaining returned edges through an explicit group selector/list. For more than 500 time points, keep the table and require a narrower displayed period or use source-preserving view reduction with clearly labelled omitted points; never aggregate new evidence to improve frame rate.

Release performance targets, measured on a documented representative device/profile, are LCP ≤2.5 s, INP ≤200 ms and CLS ≤0.1 for principal journeys. These are implementation targets, not measurements already achieved. Record compressed entry/lazy chunk sizes and request counts against baseline, and profile map resize/selection and document switching. Failure of a visual module leaves its data view and navigation operational.

## 36. SEO and shareability

Set client page titles and descriptions for profiles and reader routes using safe public identity text. Use canonical application URLs when copying or saving views, retaining repeated entity selections and meaningful lens/period state. Exclude transient panel widths, hover and personal note text from share URLs. A share link includes public evidence state, not the browser's notebook.

Hash routing and `ssr: false` limit per-entity indexing and social previews: a client-set title does not make server-rendered entity metadata available to crawlers. Do not promise Google discovery or rich previews for every profile. Preserve the existing root metadata and API reference. Server-rendered profile/reader pages, clean-path routing and a generated entity sitemap are separate future serving work, not silently included in this frontend project.

Saved views reconstruct from their URLs. If an ID, period or source is no longer available, display the saved selection and an explicit correction path. Do not quietly change the research question. About states campaign origins, evidence purpose, geographic scope and methodology links.

## 37. Loading, empty and error states

All routes use the same state vocabulary, with source-specific details:

| State | Required behaviour |
|---|---|
| Initial load | Stable heading/filter layout, appropriately shaped skeleton, busy region; no invented zero statistics |
| Refresh | Preserve previously shown content only with an explicit updating label; prevent it appearing to belong to newly applied filters |
| No selection | Explain the next choice with a visible provider/authority/measure picker; do not show an error |
| No matching records | State the active scope, offer Clear filters or another source; no implication that the event never occurred |
| Evidence not held/missing | Explain the response's missing value or coverage gap; retain caveat and useful source links |
| Partial response/window | State returned count and available total separately; export and visual scope match |
| Failed request | Human-readable endpoint-specific failure and Retry; independent successful panels remain available |
| Stale link/version | Preserve requested ID/version and explain it cannot currently resolve; no nearest-record substitution |
| Invalid filter | Identify the unsupported selection, offer explicit correction, never silently broaden a consequential query |
| Visualisation failure | Keep Data view, filters, source controls and retry; isolate chart/map errors from the shell |
| Storage unavailable/full | Keep current work in memory, show that persistence failed and offer export; never claim Saved |

Show raw technical request identifiers only in expandable diagnostics. Do not show backend tracebacks, restricted fields or an admin link as a recovery path. British English copy is factual: **No matching evidence found**, **Source details unavailable**, **Showing 50 of 214 returned matches** only when those counts are actually supplied.

## 38. Motion and micro-interactions

Use quiet functional motion: approximately 120 ms control feedback and 180 ms panel transitions. Honour reduced-motion preferences by removing non-essential movement, animated chart entry and smooth camera travel. Never animate numbers counting up. Loading does not shimmer indefinitely; a static skeleton or simple progress indication is sufficient.

Selection changes use a stable outline/background and text status. Toasts confirm Copy/Save/Export actions but are not the sole persistent indication of failure. Keep focus and scroll stable during data refresh. Route transitions do not slide the whole application or obscure evidence. No force-network motion, decorative map flights or parallax.

## 39. Testing strategy

Tests are offline and fixture-backed. Use actual public response shapes, including missing metadata and known edge cases. Intercept public HTTP responses in Playwright; fail a test on unexpected outbound requests. No test fetches a real source or writes data, logs, backups or browser fixtures into the repository.

Unit/component coverage is targeted at behaviours that can corrupt interpretation: URL alias precedence and repeated keys; filter adapters; out-of-order response rejection; null/suppressed formatting; exact comparison keys; graph identifiers; map state clearing; source/series/window scope; local-storage migration and import validation; chart export annotations. Do not write tests that merely restate a colour constant.

Browser tests cover the five journeys in section 3, every retained route's usable state, deep-link refresh and browser Back/Forward. Include populated, empty, partial, failed and stale-selection responses. Exercise dark/light/system, 390 px mobile, 1280 px desktop and a wide workspace; manually inspect 320 px and zoom reflow. Verify map controls and local assets in a real browser, not just module mocks.

Keyboard review covers navigation, filter drawer, split separator, inspector, provenance, document context paging, chart Data switch and exports. Check reduced motion, colour contrast, source links and full hash access. Use an automated accessibility checker where available alongside manual assistive-technology checks; do not claim conformance from a scan alone.

During implementation, run public `npm run typecheck`, `npm run lint`, `npm test`, `npm run build` and `npm run test:e2e` using the repository's supported runtime and lockfile. Run applicable existing bundle/CSP/offline-serving and portal-isolation checks, then the required offline `uv run python -m pytest` and `uv run ruff check pipeline tests` before release. Verify the generated public app through the Python server with fixture-backed public data; a development server alone does not prove serving compatibility. Check admin/public boundaries without editing admin.

This planning change does not alter application code. Plan validation consists of specification coverage, source/route checks, local link checks and review of the diff; it does not claim implementation tests have passed.

## 40. Data visualisation matrix

Every entry inherits this contract: visible filters come only from section 16; tooltip/selection contains exact labels, units, period and available source metadata; an HTML data equivalent includes every displayed observation and caveat; loading uses a stable placeholder; empty/missing/error states follow section 37; source controls follow section 29. Desktop/mobile behaviour, drill-down and exceptions are specified below. This common contract is part of every chart specification, not optional guidance.

| ID and question | API, dimensions and measures | Form/library and rationale | Interaction, filters and drill-down | Mobile, data and evidence details |
|---|---|---|---|---|
| V01 Where is this authority? | Boundary manifest; exact ONS/name; no numeric measure | Neutral MapLibre boundary locator; geographical orientation | Select/list-search authority; inspector → profile; viewport is not a filter | List equivalent; no numeric tooltip; missing boundary leaves identity usable; map attribution retained |
| V02 What is the spatial pattern of one published measure? | `geography`/atlas layer; authority × supplied period; one supplied measure/unit | MapLibre choropleth; spatial distribution with ≤5 labelled bands | Layer/year choice; inspect exact value → authority/lens; no arbitrary spatial search | Map/Data switch; one row per supplied authority; missing/zero distinct; show classification breaks and layer caveat |
| V03 Where are the loaded CQC registrations? | `cqc_locations`; location/coordinates; count of loaded points only | MapLibre points/clusters; locate registrations | Supported CQC filters; cluster expands loaded points; location inspector → CQC source | List default; expose loaded/mapped/total scopes; missing coordinates remain in table |
| V04 When were notices published? | `contracts.by_year`/`by_quarter`; publication period; `count` | ECharts bar chart; discrete publication counts | Year brush maps to publication `year_from/year_to`; quarter selection inspects aggregate only; notice list is scoped separately | Vertical bars or table; tooltip says notices, not awards/contracts; source-window caveats |
| V05 Which notice procedures/value bands appear? | `contracts.by_procedure_type.count`, `value_bands.count`; supplied categories | ECharts horizontal bars; compare API-defined categories | Highlight/inspect aggregate; no procedure/band filtering API; do not claim linked notice filtering | Table lists all returned categories including true zero bands; no sums of notice values |
| V06 What funding observations are published over time? | Authority/`compare` grant and budget rows; financial year; `amount`, grant `allocation_status` | Separate ECharts line/dot views; preserve series and indicative status | Select one source/authority set; point inspection → original observation/source | Small multiples or table; no ring-fence addition; budget source scope explained; missing years gap |
| V07 What does a charity report for each accounting period? | Provider timeline/`compare.charity`; year end; `total_income`, `total_expenditure` | ECharts grouped bars within one charity/source; distinguish two amounts | Select provider and supplied accounting period; source inspection → filing | Table first when few observations; bars start zero; no margin/ratio or inferred salary |
| V08 What annual pay range does an advert state? | `pay.nhs_job_adverts` or matched provider-comparison layer; advert; raw min/max and source period | ECharts interval/dot plot, one advert per row; no averaging | Provider/source/role/unit as supported; point → advert/source; no unimplemented global date filter | Bounded list with textual ranges; absent bound marked absent; no hourly conversion or duplicated-advert vacancy count |
| V09 How does one treatment measure vary over supplied periods? | `fingertips`; indicator/area/period; value and supplied CI, separate England values | ECharts line/points with interval marks; ordered observations | Measure then authority; supplied topic/substance; point inspection → source; display-range control only | One measure at a time; table includes lower/upper/value_note; no smoothing; England metadata limits visible |
| V10 What estimate and uncertainty were published? | `ndtms.estimates`; measure/area/period/age/publication; value/lower/upper | ECharts interval plot; preserve estimate and paired uncertainty | Authority/table selection; inspect exact estimate → source; no inferred monthly series | Table includes estimates and separate raw/context rows; no band if numeric bounds absent; publication year is separate |
| V11 Which authorities and providers have documented commissioning links? | `relationships`; explicit nodes/edges and validity; no financial edge weight | Structured D3/SVG bipartite diagram; readable verified connections | Select edge → relationship evidence; recenter only with explicit supported identity | Edge table default on mobile; same edges/caveats; no thickness suggesting contract value or relationship strength |
| V12 What verified path was returned? | `relationship_path`; ordered nodes/hops; no numeric score | D3/SVG ordered path; inspect each relation | Two valid endpoint selections, hop bound; edge evidence, optional explicit profile link | Ordered list with each edge source; bounded no-path caveat; no force graph |
| V13 Which periods have held evidence? | `coverage_timeline.sources`; source × original period; held state | Semantic matrix/CSS, optional SVG; presence is categorical | Entity selection, held-cell link → dataset/evidence | Source/period list; unheld not zero activity; preserve exact fiscal labels and source caveat |
| V14 What dated evidence belongs to this process/entity? | Process, provider timeline, `contract_diary`, `safety_legal`; event/type/date; no combined count | Semantic chronology with source lanes; chronology without false arithmetic | Source-supported date/entity filters; inspect event → record/revision/source | Vertical lane/list; undated entries separate; differing event-date meanings explicit |
| V15 How do peers compare within one measure? | `compare` source series; same-type entity × period; one of the measures above | ECharts small multiples using V06/V07/V09 or notice-count bars | 2–4 peers, one source lens, no ranking/normalisation; point → source/profile | Stacked panels and complete data; missing peer remains; no generic `amount` mapping |

Table-only by deliberate choice: council payment rows, workforce census rounds, living-wage name checks, gender-pay-gap filings initially, provider-published pay excerpts, ASHE/SfC context, temporary accommodation, source-link status, discrepancies, revisions, extracted document tables and co-mentions. They gain filtering/inspection/citation without a chart that adds an unsupported comparison. A later justified chart requires a new matrix entry, not a generic dashboard widget.

Exclude Sankey money flows, treemaps of overall contract totals, workforce/treatment scatter plots, radar scores, sector health gauges, provider review ratings, universal knowledge graphs and correlation heatmaps. Their apparent availability in a chart library does not establish evidential validity.

## 41. Implementation phases and dependencies

Implementation requires a subsequent user instruction. Each phase must leave the public app usable and preserve routes; do not switch serving flags or deploy as an incidental step.

| Phase | Work and dependencies | Completion gate |
|---|---|---|
| P0 Foundations | Baseline status/build; exact legacy URL fixtures; public tokens/theme/type; shell/nav; typed response adapters; state/provenance/table/error components; local-storage compatibility | Existing routes and saved data survive; dark/light/mobile shell, API whitelist and offline assets verified |
| P1 Discovery | Search/type chooser, homepage locator, authority/provider directories, coverage entry; depends on P0 | Find → inspect → profile works without a heavy full-atlas load; neutral map and Data fallback pass |
| P2 Entity intelligence | Provider/authority profiles, explicit lenses, Places/CQC inspectors; depends on P1 identities and provenance | Entity-understanding journeys work; historic IDs and result-window limitations remain explicit |
| P3 Evidence intelligence | Contracts/payments/process, pay, treatment, safety/legal, statements, documents/reader/tables; depends on P0 adapters and P2 pivots | Every evidence layer retained; source-specific filters, uncertainty, partial exports and stale passages verified |
| P4 Investigation | Connections, compare, contextual tools, saved views/notes imports/exports and chart images; depends on P3 evidence references | Same-source comparison, path semantics, citation export and round-trip research work pass |
| P5 Release readiness | Full route audit, accessibility, performance, provenance/export review, production-build browser checks and regression suite | All section 42 criteria and checklist pass; deployment is a separate explicitly authorised action |

Each implementation change should name its route scope, source assumptions, checks and remaining limitations. Stage only owned paths. Preserve unrelated checkout changes and admin outputs. If a backend deficiency blocks an optional enhancement, ship the documented feasible frontend behaviour and record the dependency; do not expand this project into a backend migration.

## 42. Route specifications and acceptance criteria

Each route inherits the shell/component hierarchy `AppShell → PageHeader/Breadcrumbs → supported FilterBar → EvidenceState → route view → inspector/provenance/export`, with no unused regions rendered. Its target users are the broad audience in section 3, narrowed by the question below. Common filters/URL behaviour are sections 15–16; overlays 17/31; desktop/mobile 32–33; accessibility 34; performance 35; SEO 36; states 37; tests 39; provenance 29. These inherited specifications cover those requirements for every route. A map or D3 view exists only when explicitly listed below; other routes have neither. Dependencies are the phase plus the listed API/component, never an unlisted new endpoint.

| Route | User purpose/question and content hierarchy | Data/layout/inspection and phase | Route-specific acceptance |
|---|---|---|---|
| `/` | Find an entity/evidence; search → neutral locator → categories → coverage | Summary/meta/directories, V01; P1 | Search type explicit; no metric ranking/oversized campaign hero; source failures do not remove search |
| `/search` | Find the selected kind; type → query → results | Local complete directories or `document_search`; compact results; P1 | Type-specific filters; no mixed unsupported full-text/semantic claim; return/back preserves query |
| `/providers` | Identify a provider; search → compact identity list | Directory, inspector; P1 | Exact keys, local search, separate holdings and conventional name links |
| `/providers/:key` | Understand identity and holdings; overview → lenses → source | Timeline/lineage and scoped lens APIs; V07/V14 optional; P2 | Every supplied evidence type remains reachable; no PFD+tribunal total; identity does not imply continuity |
| `/authorities` | Identify an area; name/code search → list | Directory, inspector; P1 | Usable directory; historic IDs preserved; empty result differs from unavailable request |
| `/authorities/:code` | Locate area and understand commissioning; map → context → lenses | Authority/relationships; V01/V06/V09 as selected; P2 | Map precedes commissioning context; contextual comparators stay in Context; capped notices labelled |
| `/geography` | Inspect one spatial measure; layer/period → map/list → inspector | Atlas/geography, V01/V02; P2 | One layer, exact join, missing/zero distinction, stale state cleared and keyboard list parity |
| `/cqc` | Inspect registrations; filters → loaded list/map → record | `cqc_locations`, V03; P2 | Loaded scope explicit; selected deep link never opens a different record; no service-equivalence claim |
| `/contracts` | Find notices or payments; lens → filters → evidence | Contracts/council spend, V04/V05; P3 | Notices default; payments separate; unsupported chart categories do not cross-filter; no headline value sum |
| `/contracts/process/:ocid` | Follow a process; identity → stages → evidence | Process, V14; P3 | OCID deep link resolves through flattened route; amendments not separate awards; source/revision accessible |
| `/pay` | Answer one pay/workforce question; lens → definition → evidence | `pay`, V07/V08 where valid; P3 | Correct filter scope, units and populations; no annualisation; failed accreditation match worded accurately |
| `/treatment` | Read one measure; catalogue → definition → authority → observations | Treatment metrics/Fingertips/NDTMS, V09/V10; P3 | Measure chosen first; bounds/markers/context retained; publication and observation dates distinct |
| `/pfd` | Read safety/legal records; source lane → chronology → evidence | Safety/legal and supporting APIs, V14; P3 | Source types, statuses and filter scopes explicit; no composite adverse-event count |
| `/claims` | Assess a statement; authorship → claim → citations/caveats | Published claims, textual list/detail; P3 | Campaign authorship and unresolved citations visible; no automatic truth badge |
| `/documents` | Find and read a passage; filters → results/reader | `document_search`/document context; P3 | Resizable desktop split, one pane mobile, selected element URL and safe text rendering |
| `/documents/:id` | Read/cite an exact passage; source → context → reference actions | Bounded document context; P3 | Refresh restores anchor or explains stale parse; no invented PDF archive link |
| `/relationships` | Inspect commissioning; centre → diagram/table → edge source | Relationships/detail, V11; P4 | Only supplied edges; no guessed profile IDs or weighted money flow |
| `/pathfinder` | Inspect a returned connection path; endpoints → path → evidence | Relationship path, V12; P4 | Hop bound and bounded no-path meaning explicit; every hop has inspection |
| `/cooccurrence` | Read records naming selected organisations; keys → matches | Co-occurrence table/list; P4 | 2–5 supported keys; record-specific matches; bounded results not asserted relationships |
| `/compare` | Compare peers within one lens; selection → source → chart/data | Compare/provider_compare, V15; P4 | Exact series adapters; no dropped peer or silent >4 truncation; exports capture selected scope |
| `/timeline` | Select coverage history or provider events | Compatibility adapter; V13/V14; P3 | Legacy `provider`/`authority` history and Nuxt `provider_key` events both preserved |
| `/coverage` | Understand held evidence/limitations; guide or selected history | Meta/freshness/history, V13; P1/P3 | No-entity guide works; history reads `sources`; no completeness/quality score |
| `/diary` | Inspect published procurement dates | Contract diary, V14; P3 | Date meanings and entity/process scope preserved; event → process/source |
| `/catalogue` | Understand a dataset; directory → selected definition | Catalogue/detail, table/text; P1 | `dataset` bookmarks retained; licence/definition/provenance available where returned |
| `/calendar` | Understand expected publication timing | Publication calendar, semantic list; P3 | Stated/observed expectations distinguished from releases and live monitoring |
| `/changes` | Inspect recorded data changes | Changes, bounded chronological list; P3 | Source/type/since filters work; changes not described as proved sector events |
| `/discrepancies` | Compare source observations; entity → paired evidence/caveat | Discrepancies, aligned table; P4 | No winner chosen automatically; both observation sources/dates retained |
| `/revisions` | Inspect exact version differences; subject → A/B → diff | Record diff, paired safe text/tables; P4 | Missing parse/version explicit; source changes separate from derived changes |
| `/doctables` | Inspect an extracted grid; document/table → grid → context | Document tables, native table; P3 | Extraction status, raw cell markers and page/context links; no derived totals/raw HTML |
| `/links` | Check recorded source-link status; exact URL → record/archive info | Source link; P4 | Recorded timestamp visible; no live-status or public archive-download invention |
| `/research-tools` | Find a verification action; task labels → tool links | Static index, no omnibus fetch; P4 | Discrepancy/revision/table/link tools discoverable and contextual entry points retained |
| `/saved` | Reopen/manage named public views | Local collection list/import/export; P4 | Existing version-one data survives; invalid URL import cannot execute code; browser-only scope clear |
| `/notebook` | Keep notes with evidence references | Local notes/detail/import/export; P4 | User text distinct from quotations; stale citation retained; save failure never reports success |
| `/journey` | Return to a recent view | Existing bounded local history; P4 | Current history preserved, max 50 retained, repeated navigation does not flood entries; clear is explicit |
| `/api` | Reach public API documentation | Static explanatory links; P1 | Existing HTTP `/api` remains reachable; no admin API link or changed API contract |
| `/about` | Understand purpose/origins and method | Static editorial content; P1 | Campaign origins and England scope plain; links to caveats/coverage/API; no unsupported independence claim |

Cross-page audit: entity → notice → process → source, map → authority → documented provider, document result → exact passage → citation, and peer selection → one-source comparison all have existing public support. Provider/authority → documents is explicitly a name search; CQC → service is not available; document mention → verified graph is not available; source archive → public archived bytes is not available. Show useful existing source/record links at these boundaries instead of dead controls. Browser Back must reconstruct the previous question, filters and selection across every supported pivot.

## 43. Risks and mitigations

| Risk | Mitigation and release evidence |
|---|---|
| Competing legacy/Nuxt meanings and saved URLs | Exact compatibility fixtures, canonical precedence and browser round-trip tests; no blanket redirect |
| Backend aggregates look safe to headline | Source-specific adapters and explicit forbidden display rules; review each figure against CAVEATS |
| Weak metadata tempts invented provenance | Row/series/window scope types and absent-field states; no URL-only hash substitution |
| Filter parameters imply more than they actually constrain | Whitelist plus source-lens scope copy; fixture tests for pay/supporting safety and local windows |
| Current dataset population differs from code examples | No plan claims about live coverage; populated/empty/partial/error fixture states and deployment smoke check |
| RC runtime/dependency upgrades disturb mounting | Preserve current Nuxt/Vue/Vapor settings; isolate locked visual dependencies; production browser verification |
| Local notes are lost or falsely presented as synced | Backward-compatible migration, validated import/export, storage-failure handling and browser-only wording |
| Maps/charts overwhelm mobile or initial load | Lazy modules, single-pane mobile, data equivalents and measured bundle/performance gates |
| Public work breaches admin isolation | Public-only imports/assets/APIs; existing portal isolation and diff review |
| Broad evidence positioning obscures campaign authorship | About disclosure and explicit campaign-statement attribution |
| SPA metadata is mistaken for full SEO support | State current indexing limits; keep server-rendered metadata as a separate dependency |

## 44. Future backend/API opportunities

These are excluded from the implementation phases above. Each has a feasible current alternative.

| Future capability | User benefit | Current frontend alternative |
|---|---|---|
| Public CQC record-by-ID endpoint | Stable location inspection independent of pagination | Exact query/window selection with stale-record explanation |
| Explicit public document–entity/topic relationships | Reliable entity-document pivots | Clearly labelled name search and exact passage/source links |
| Source/version-bound provenance and archive download contracts | Verify exact bytes from every observation | Show only returned metadata; inspect recorded source status; open original URL |
| Consistent source-specific pay filters/aggregates | Advert/date and summary views that share one scope | Separate lenses; local scope labels; individual advert evidence |
| Payment pagination/export and explicit file boundaries | Review complete supported payment selections | Returned rows/file scope, no fetch-all or cross-file total |
| Public service identities and verified joins | Service-to-provider/commissioner investigation | CQC registration records and supported provider/authority relations |
| Richer graph public identity keys and complete bounded metadata | Reliable recentering and completeness statements | Inspect unresolved graph nodes as records; only explicit identity pivots |
| Additional public search sources or semantic retrieval | Broader document discovery | Current public committee/CDP full-text corpus only |
| Server-rendered entity metadata/clean-path serving | Indexable profiles and rich shared previews | Hash links, client titles and honest root metadata |
| Optional account-backed research collections | Cross-device notes and collaboration | Browser-local views/notes with portable import/export |

Any such work requires a separately scoped design and implementation decision. Existing operator capability does not grant public access to it.

## 45. Explicit non-goals

No implementation or deployment in this planning task. In the later frontend project: no schema/ingestion/NLP changes; no new API contracts; no admin redesign; no accounts/authentication; no external CDN/analytics; no new evidence promotion; no personal-data exposure; no composite scores, causal claims, cross-layer arithmetic or headline contract total; no guessed identities, service registry, provider reviews or unsupported semantic search; no command palette or global shortcut system; no force network or decorative dashboards; no automatic broadening of filters, silent record substitution or complete-export claims for partial windows.

## 46. Decision register

The following records the 48 interview selections in order. They are product decisions, not claims that all capabilities already exist. API limits and evidential constraints determine the feasible implementation described above.

| ID | Confirmed decision | Consequence |
|---|---|---|
| D01 | Broad sector audience | Plain research entry points serve multiple professions |
| D02 | Search-and-choose homepage | Entity/document search leads alongside a map |
| D03 | Dark first, with light/system | Explicit persisted theme modes |
| D04 | Transparent campaign origins; general evidence infrastructure | About disclosure and accurate statement attribution |
| D05 | Progressive detail | Readable overview, deeper lenses/inspection |
| D06 | Success means understanding an entity | Entity journeys are primary acceptance criteria |
| D07 | Grouped collapsible sidebar | Stable research navigation with compact mode |
| D08 | Inspect alongside, conventional entity-name links | Inspect and navigation are separate visible actions |
| D09 | Carry relevant context; make unsupported filters explicit | Route/API filter adapters and explanatory drops |
| D10 | Choose search type | Providers/Authorities/Documents, no universal blended query |
| D11 | Provenance on demand | Essential caveats remain visible |
| D12 | Browser views and evidence notes with import/export and share URLs | Local persistence; no account dependency |
| D13 | Manrope and Space Grotesk | Local font system and tabular figures |
| D14 | Neutral ink/near-black surfaces | Canonical palette retained through semantic tokens |
| D15 | Labels before evidence-family colours | No evidence rainbow |
| D16 | Existing Nuxt foundation | Explicit exception to older no-framework/build wording |
| D17 | Public tokens now; admin adoption separately | No admin edits/shared-theme dependency |
| D18 | Selective map/evidence resizing | Local proportions with accessible reset |
| D19 | Neutral authority locator on homepage | No initial metric ranking |
| D20 | Homepage evidence categories | Direct entry to actual source lenses |
| D21 | Secondary coverage/freshness | Evidence status supports the main task |
| D22 | Compact searchable provider list | Identity-oriented directory |
| D23 | Provider identity and holdings first | Overview before analysis |
| D24 | Provider overview with bookmarkable lenses | Stable scoped URLs |
| D25 | Authority MapLibre map first, then commissioning context | Profile content order is fixed |
| D26 | Authority comparators in a separate Context tab | No cross-layer causal framing |
| D27 | Places map, linked authority list and inspector; one layer | Coordinated single-metric geography |
| D28 | Document results/reader resizable split | Search context stays alongside reading on desktop |
| D29 | Dedicated reader route and passage selection | Exact context deep links |
| D30 | Document scope and direct links to other evidence | Explicit supported links; name matches not asserted joins |
| D31 | Contract notices first | Notice-level evidence is the default |
| D32 | Separate Payments lens | Payment evidence retains file/source scope |
| D33 | Procurement process timeline and evidence | Stages remain source-backed |
| D34 | Question-led pay lenses | Units/populations and filter scope remain separate |
| D35 | Treatment measure chosen first | Definition and unit precede chart |
| D36 | Compare one source lens at a time | No composite peer score |
| D37 | Structured authority-to-provider graph | Deterministic readable commissioning view |
| D38 | CQC inspector/source with shareable selection | No invented service profile |
| D39 | Separate safety/legal chronology lanes | No aggregate adverse-event total |
| D40 | Contextual verification and tools index | Evidence inspection stays connected to its source |
| D41 | Separate Commissioning/Verified paths/Mentioned together | Relationship meanings cannot collapse |
| D42 | Evidence-backed statements with citations/caveats | Retain campaign authorship and unresolved references |
| D43 | One coverage area, distinct specialist views | Catalogue/history/freshness/calendar/changes remain findable |
| D44 | Mobile single pane, drawers/full-height inspector | Mobile interaction designed independently of desktop density |
| D45 | Quiet functional motion | No decorative chart/map animation |
| D46 | Chart-first with Chart/Data switch | Only when a justified chart exists |
| D47 | Data/references and annotated chart images equally important | Both included in export acceptance |
| D48 | Conventional accessible keyboard only | No command palette or custom global shortcuts |

Implementation defaults chosen to make the plan concrete, rather than additional interview answers: breakpoint values, panel widths/proportions, default Providers search type, 2–4 comparison limit, 100-edge initial diagram group, font sizes, motion timings, exact token derivatives and proposed lens/query spellings. Adjust these only for demonstrated accessibility/runtime constraints, recording the reason; changes to the confirmed product decisions need an explicit design discussion. No unresolved product choice blocks the frontend work described here.

## 47. Final implementation checklist

- [ ] Obtain a subsequent instruction to implement; inspect current branch/status and preserve unrelated work.
- [ ] Re-read README and CAVEATS; compare this plan's inspected revision with current public APIs before editing.
- [ ] Freeze legacy URL/storage fixtures and baseline the production build, route behaviour and bundle gates.
- [ ] Implement public-only tokens, fonts, shell and accessible state/inspection/table primitives.
- [ ] Whitelist route-specific API parameters; distinguish row, series and response-window scope.
- [ ] Complete P1–P4 routes and all existing feature/URL compatibility before release polish.
- [ ] Verify every plotted measure against section 40 and every route against section 42.
- [ ] Preserve nulls, suppression, confidence intervals, historical identifiers and source-specific date meanings.
- [ ] Test supported pivots, Back/Forward, refreshed deep links, stale selections and response races.
- [ ] Verify both export classes and local collection migration/import/export with accurate scope.
- [ ] Review dark/light/system, mobile, keyboard, zoom, reduced motion and data equivalents in a browser.
- [ ] Review all authored public copy for natural British English and the editorial rules in section 12; remove generic AI-style/marketing prose while preserving exact source text.
- [ ] Verify origin-only production assets and Python serving; run required offline checks and portal isolation.
- [ ] Review the final diff for admin/backend/restricted-data changes and unsupported analytical claims.
- [ ] Report completed scope, measured checks and remaining limitations; deploy only under separate authorisation.

Inspection references: [README](../README.md), [evidence caveats](CAVEATS.md), [public API routing](../pipeline/web/server.py), [public query implementation](../pipeline/web/public_queries.py), [public export implementation](../pipeline/web/public_export.py), [public Nuxt application](../frontend/public/package.json), [current upgrade roadmap](upgrade-roadmap.md). These are the source of capability constraints; the interview determines product choices.
