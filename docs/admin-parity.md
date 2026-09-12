# Admin workflow parity and acceptance ledger

The implementation oracle is the controls in `pipeline/web/static/app.js`,
`index.html`, `js/*.js`, the separate analysis page, and the existing Nuxt pages.
Historical roadmap suggestions are not additional requirements. Legacy assets
remain in place and are not imported, embedded or executed by the Nuxt app.

The table records replacement locations and acceptance procedures. Browser
procedures are fixture-backed; do not run collection or submit real decisions
to verify a theme. `frontend/admin/e2e/operator.spec.ts` supplies the automated
workflow and responsive checks. Server tests keep their existing safeguards.

| Legacy / existing capability | Nuxt replacement | Acceptance |
|---|---|---|
| Overview attention cards, mission control | `pages/index.vue`, independent cockpit and mission resources | A failed panel stays unavailable while others render; worklists and jobs open their workspaces |
| Warehouse reference and decision history | Overview supporting panels | Counts remain source-local; missing values are not zero; history remains below action panels |
| Grouped navigation, desktop collapse, mobile navigation | `AdminNavigation`, default dashboard layout, Nuxt slideover | 256/64px widths, persisted groups, 390px drawer, Escape and focus return |
| Reviewer and density | `useReviewer`, `useAdminPreferences` | Existing Nuxt preference wins; valid legacy preferences migrate; blocked storage still renders |
| Theme and command palette | colour-mode, workspace dialog, lazy catalogue | System/light/dark, independent storage, prepaint class; Ctrl/Cmd K opens navigation, typing is excluded |
| Review facets, filters, order, pagination, presets | `pages/review.vue`, `AdminPager` | URL retains status/module/type/q/order/offset; presets include note; back/forward uses the URL |
| Review clusters | Cluster table with worklist and explicit listed-ID actions | Display scan cap; confirmation states capped ID count; grouping itself never decides anything |
| Single and selected decisions | Review decision action and typed API | Exact `ids`, decision, reviewer and note payload; controls serialize writes |
| All matching decisions | Matching dialog | Require exact displayed count, retain server transactional recount and filter contract |
| Audited undo | Review in-memory prior-status groups | Mixed pending/approved selection restores separately; only updated IDs are retained; no replay of successful undo groups after a later failure |
| Notes, history, resolution, suggestions, sidecars | `AdminReviewDetail` | Escaped excerpt/hash/context; safe source link; check URL and resolve remain explicit; suggestions never preselect a target |
| Review shortcuts and narrow detail return | Review key handler, `useQueueFocus` | j/k/a/r/u/x/o and slash exclude inputs/dialogs; narrow detail focuses its heading and returns to the existing queue control |
| Candidate list/counts/kinds/authority filters | `AdminVerificationWorkspace` | Server filters/pager preserved; no implied success after list failure |
| Candidate preview, required fields, source opening | Candidate detail and in-memory opened set | Preview alone does not satisfy opening; required fields and a fresh source opening enable promotion |
| Candidate sequential batch and outcomes | Verification action bar | Separate requests; freeze kind/reviewer/fields for the batch; failures stay visible and selected; successful inputs clear |
| Census source reading, stale sources, history | Census mode of verification workspace | Fetch archived page before verification; stale-source warning and decision history remain visible |
| Census batch eligibility and results | Shared sequential action bar | Already verified/rejected/unread items explain ineligibility; eligible rows post individually |
| Claim drafting, editing, caveats, citations | `pages/claims.vue` | Attributed draft; resolve a citable evidence row; edit/uncite; no source HTML interpolation |
| Claim decisions and resets | Existing typed claims client and Nuxt dialogs | Published/rejected/retracted decisions and draft resets preserve audit requirements; failed edits remain entered |
| Extracted-candidate corrections/reasons/ontology/gate | `pages/claimreview.vue` | New/queued/accepted/dismissed list filters; approved/rejected/corrected decisions; exact correction fields and ontology values |
| Search filters, context and scores | `pages/search.vue` | Keyword/semantic/hybrid, source and date filters; model/fallback metadata, excerpts, score components and provenance |
| Export generation, downloads, staleness, provenance | `pages/exports.vue` | Exact export target, job following, guarded enumerated file/provenance links, stale warning |
| Authority URL override registry | Exports supporting panel | Existing override endpoint and verified URL information |
| Pipeline run/dry run and per-module controls | `pages/pipeline.vue` | Module/since/limit/workers, whole-run confirmation; conflict follows returned job ID |
| Dependency waves, job logs, ledger and comparison | Pipeline URL tabs, `AdminLog`, `AdminRunComparison` | Incremental `after` cursor, bounded 500-line window, pause scrolling and Follow latest; inspect historic runs |
| Analysis domains, runs, stop/resume | `pages/analysis.vue` | Domain selection is not reset on refresh; current run status updates; supported run actions remain explicit |
| Proposals, themes, releases and rollback | Analysis focused tabs/dialogs | Optional reasons retained in payloads; trigger details visible; explicit release/theme actions |
| Analysis model calls, reports and output inspection | Lazy operations/models/output panels | Model call/error/manifests inspectable; JSON/CSV/printable reports; filters for release/domain |
| Storage, health, extensions, freshness | `pages/health.vue` warehouse/freshness tabs | Each check has its own error state; integrity check follows its job |
| Coverage/completeness actions | `AdminCoverage`, `AdminCompleteness` | Authority matrix, definitions, review/run links; no automatic action or cross-layer total |
| Parse failures, audits, rules, URL overlaps | Health local tabs and `AdminFailures` | Server search/module/pagination, groups, raw fragments and source URLs; read-only audits/rules/overlaps |
| Alias resolution and supersession | `pages/aliases.vue` | Explicit target ID/reason/reviewer; prior accepted decision superseded; no fuzzy auto-resolution |
| QC draw/history/findings | `pages/qc.vue` | Reproducible seed/source/method/size; second-look finding appends without modifying original review |
| Parser replay and diff | `pages/parser-replay.vue` | Stored/proposed/archive output and unsupported-parser reason; no writes |
| Review analytics suppression | `pages/review-analytics.vue` | Suppressed source totals stay labelled suppressed; no targets or rankings |
| Data lineage | `pages/lineage.vue` | Filter node kinds/text; inspect recorded upstream/downstream relationships |
| Database catalogue/schema/relationships | `pages/database.vue` | Table selection, schema/FK inspection and cross-table links; values remain positional |
| Database server search/sort/page and reveal | Database resource and session reveal gate | Duplicate column names survive; URL/reload never restores reveal; server refusal remains authoritative |
| SQL, Explain, saved queries, 50-history, CSV | `pages/sql.vue` and typed positional results | Server read-only connection/timeouts; Explain prefixes `EXPLAIN`, never `ANALYZE`; current-result CSV and truncation notice |
| Independent activation and rollback | Settings and `NuxtAssets` | Variant/build-presence matrix, missing assets, CSP/path containment and public isolation; see activation guide |

## Verification boundaries

Automated browser cases cover responsive core screens, escaped source text,
decision payloads, undo, fresh reading/reveal gates, corrections, sequential
failure results, exports, run conflicts, analysis reasons, navigation, blocked
storage and preferences. The six core screens are inspected in both themes at
1440, 1024 and 390 pixels, plus the 720-CSS-pixel equivalent of a 1440-pixel
window at 200%. Native zoom remains a manual acceptance check. Keep the browser launch limitation in
`admin-activation.md` visible until Firefox is verified on a working host.

The Python suite exercises server protections rather than relying on browser
disabling: read-only SQL, PostgreSQL Explain, request-origin/content-type guards,
restricted responses, human review requirements, provenance and export policy.
Use a unique `PYTEST_XDIST_WORKER` value for separate simultaneous test commands:
the repository's test fixture otherwise reuses `pgtest_main` across processes.
Never point tests at the operating warehouse.

The acceptance matrix is not a claim that every possible production record
shape has been sampled. Activation remains separate from implementation; inspect
representative archived records and complete the supported-browser gate before
switching an operator deployment.

Release checks on the implementation host: admin typecheck and static build,
the frontend budget/isolation gate (approximately 162 KiB compressed admin
initial load against the unchanged 200 KiB limit), Ruff and 67 targeted
Python serving/isolation cases passed. All 54 Chromium and WebKit fixture
browser cases passed, including phone queue return, focus, preserved notes,
independent preferences and browser history. The matrix uses no live
evidence sources and includes Chromium and WebKit; Firefox's host launch failure
is recorded separately from application results.

The complete offline Python run reported 3,342 passed, 11 skipped and 37
deselected, with one new warning-capture assertion failing because earlier
tests redirected logging from stdout to the structured logger. The warning
itself was present. That assertion now captures structured events independently
of stream configuration; the serving/isolation tests were rerun after the fix.
The entire 46-minute suite was not repeated after this test-only correction.
