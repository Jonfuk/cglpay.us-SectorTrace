# Shared responsive design system (BETA-080)

Two front ends, one server, deliberately different identities:

| | `pipeline/web/static/public/` (portal) | `pipeline/web/static/` (operator) |
|---|---|---|
| audience | the public, citing evidence | one operator, working a queue |
| voice | a dense modern research desk | dense on purpose, no spacing to admire |
| stylesheet | `styles.css` (~1150 lines) | `styles.css` (~420 lines) |
| theme | dark-first, light via `data-bs-theme` | OS setting + `data-theme` toggle |
| accent token | `--accent-teal` | `--accent` |

They are **not** merged. What BETA-080 consolidates is the small set of
*primitives* both use — the shape of a focus ring, the spacing rhythm, the
skeleton animation — so a rule added later lands on an existing value instead
of a new one.

## Token inventory (portal `:root`)

| group | tokens | notes |
|---|---|---|
| background | `--bg-base` `--bg-surface` `--bg-elevated` | redefined under `[data-bs-theme="light"]` |
| accent | `--accent-teal` `--accent-amber` `--accent-green` `--accent-red` `--accent-purple` | |
| text | `--text-primary` `--text-secondary` `--text-muted` | |
| border | `--border-subtle` `--border-accent` | |
| semantic | `--caveat-bg` `--caveat-border` `--unverified-bg` | |
| spacing | `--space-1..6,8,10,12,16` | 4px scale, `--space-N == N*4px`. `--space-5` and `--space-10` were **missing** and referenced by live rules — an undefined custom property invalidates the whole declaration, so those gaps silently collapsed. Added in BETA-080. |
| radii | `--radius-sm,md,lg,xl` | |
| glass | `--glass-bg` `--glass-blur` `--glass-border` | the topbar's blur lives on `.topbar::before` so it does not become a containing block for the fixed drawer (BETA-069) |
| focus | `--focus-ring` `--focus-ring-offset` | **shared primitive** — same declaration on both front ends, each supplying its own accent. Consumed by `:focus-visible`. |
| type | `--sans` `--serif` `--display` `--mono` | |

The operator stylesheet keeps its own flat palette (`--bg` `--panel` `--ink`
`--muted` `--line` `--accent` plus `--approve/-bg`, `--reject/-bg`,
`--pending/-bg`, `--restricted`) and no spacing scale — that density is the
point. It gains only `--focus-ring` / `--focus-ring-offset`.

## Component classes (portal), and where they are shared

| primitive | classes | shared with admin? |
|---|---|---|
| button | `.btn` (`.primary` `.ghost` `.tiny`) | no — admin uses bare `button` + `.danger` |
| card / panel | `.panel` `.card` `.statcard` `.explore-card` `.tablecard` | no |
| disclosure | native `<details>` + `.read-first` `.context-note` `.section-disclosure` `.table-view` `.unavailable-diag` | pattern shared, classes not |
| status | `.badge` (`.good` `.bad` `.neutral` `.unverified` `.target` `.lifecycle`) | no — admin uses `.approve/.reject/.pending` |
| caveat | `.caveat-pinned` `.caveat-badge` `.caveat-body` | no |
| skeleton | `.shimmer` `.loading-state` | animation idiom shared, class not |
| filter chip | `.filter-chip` (`.is-active`) `.filter-clear` | no |
| table | `.tablecard` + Tabulator (`.tabulator*`) | no — admin has `table.dense` |
| chart wrapper | `.chartwrap` `.chart` `.chart-controls` `.chart-series-toggle` | no |
| workbench index | `.workbench-index*` `.workbench-totop` | portal only (BETA-076) |
| focus ring | `:focus-visible { outline: var(--focus-ring) }` | **yes** |

## Breakpoints

CSS cannot use a custom property inside `@media`, so the canonical values are
documented rather than tokenised. Every `@media` in the portal stylesheet is
written against one of:

| name | value | effect |
|---|---|---|
| narrow | `340px` | very small phones — tighter topbar padding |
| mobile | `720px` | phone layout — offcanvas drawer, card tables, single-column grids |
| tablet | `900px` | the offcanvas nav still applies |
| wide | `1100px` | two-column layouts (`.split`, `.maplayout`) collapse |

A new responsive rule uses one of these, not a new number.

## Migration map — what has moved, what is left

| done | in |
|---|---|
| `--space-5` / `--space-10` defined; the 5 rules that referenced an undefined `--space-5` now render their intended 20px | BETA-080 |
| `--focus-ring` / `--focus-ring-offset` primitive; `:focus-visible` on both front ends derives from it | BETA-080 |
| responsive tables (`priority`, collapse, view menu) | BETA-071 |
| shared chart wrapper controls (series toggles, zoom, missing-note) | BETA-074 |
| workbench section index | BETA-076 |
| grid `minmax(min(Xpx, 100%), 1fr)` so tracks shrink below their floor | BETA-071 |

Left for later, incrementally and with a browser check each time (never a
wholesale rewrite):

- fold the ad-hoc inline `style="..."` attributes still in a few page modules
  (`treatment.js`, `contracts.js` search form) into classes;
- a single `.stack` / `.cluster` spacing utility to replace repeated
  `display:flex; gap:var(--space-N); flex-wrap:wrap` blocks;
- name the operator status colours as `--status-{approve,reject,pending}` so
  the portal's `.badge` variants and the admin ones read from one place if
  they are ever unified (they are not today).
