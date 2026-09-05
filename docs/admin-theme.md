# SectorTrace operator theme

This theme is implemented only in `frontend/admin`. The public portal has no
runtime import from it. The requested existing Nuxt application is the explicit
task-specific exception to the repository's older no-build rule: generate static
assets during delivery and serve them through the existing stdlib HTTP server.
No Node service, Naive UI, UnoCSS, external font, icon service or YummyAdmin code
is needed in production.

## Colour system

The source is Jon's `palette.pdf`: cobalt `#3454D1`, turquoise `#34D1BF`,
raspberry `#D1345B`, soft grey `#EFEFEF`, and ink `#070707`. These exact colours
remain `--st-brand-*` tokens. Derived shades supply text and interaction contrast.

| Semantic token | Light | Dark |
|---|---|---|
| `--st-bg` canvas | `#F7F8FA` | `#10131B` |
| `--st-sidebar` | `#EFEFEF` | `#10131B` |
| `--st-surface` workspace/panels | `#FFFFFF` | `#181D2A` |
| `--st-elevated` hover/filters | `#F0F2F7` | `#20283A` |
| `--st-ink` body/headings | `#070707` | `#EFEFEF` |
| `--st-muted` secondary labels | `#596174` | `#A8B0C2` |
| `--st-accent` links | `#3454D1` | `#8CA4FF` |
| `--st-selected` navigation/queue | `#E9EDFB` | `#222E55` |
| `--st-positive` success text | `#087D73` | `#34D1BF` |
| `--st-error` error text | `#B52349` | `#F17C99` |
| `--st-focus` keyboard outline | `#3454D1` | `#34D1BF` |
| `--st-control` control boundary | `#7B8495` | `#73809B` |

White on the cobalt primary button is 6.30:1. Solid turquoise uses near-black
text (10.57:1), never white. Small error text uses the derived raspberry.
Success and rejection have words and symbols; selected rows use a cobalt edge.
Pending, unknown and unavailable states remain labelled neutrals. Missing data
must not become zero, an empty successful result or an implied healthy check.

## Typography and spacing

Use the local system sans-serif stack, 15px body, 14px tables, 13px secondary
notes and 12px metadata. Keep monospace for SQL, logs, hashes and identifiers.
Panel radii are 11–12px with subtle borders. Shadows belong to raised overlays.
Workspaces have 28px desktop padding, reducing to 16px on phones. Panels have
20px padding. Compact mode changes panels to 14px and row padding from 14px to
8px; essential text does not shrink. Source passages keep their natural line
breaks and comfortable reading width. Operational tables scroll horizontally.

The desktop navigation is 256px or a saved 64px rail; the fixed-width sidebar
does not offer resizing. A Nuxt UI slideover supplies navigation below 1024px.
Dashboard group, panel and navbar components keep the inset workspace aligned.
Nuxt dialogs handle confirmations and optional reasons. Local SVG controls and
the custom operator icon collection are bundled with the app.

## Component examples

```vue
<AdminPageHeader title="Review queue" description="Read the source before deciding."
  eyebrow="Review · Human judgement" />
<UButton>Primary action</UButton>
<UButton color="neutral" variant="outline">Secondary action</UButton>
<UButton color="error" variant="outline">Reject</UButton>
<StatusPill label="Verified" level="ok" />
<StatusPill label="Pending" />
<StatusPill :label="null" />
<AdminResourcePanel title="Storage" path="/api/admin/storage" field="storage" />
```

`AdminRows` handles server-defined records; Database and SQL render positional
arrays to preserve duplicate column names. `StLink` validates source URLs and
`AdminRecord` renders source values as escaped text. `AdminPager`,
`AdminLocalTabs`, `AdminLog` and the queue/detail pattern supply common workflows.

## Preferences and performance

`st.admin.theme` belongs only to admin; System is the default. Nuxt's inline
colour-mode script applies the stored mode before painting and tolerates blocked
storage. Other admin conveniences use versioned `st.admin.*` envelopes. Valid
legacy reviewer, density, location, presets and SQL preferences are copied only
when their Nuxt replacements are absent. Legacy keys remain for rollback.

Opened sources, extracted-page reading, restricted reveal and selection live in
memory. Neither migration nor URL parameters can restore acknowledgements.
Explicit links win over saved location; bare `/admin` resumes a valid workspace.

Pages, overlays, command catalogue and notifications load on demand. Generated
prefetch hints and automatic link prefetching are disabled so opening the desk
does not download every workflow. Pollers serialize requests, pause while hidden
and stop on unmount. Pipeline logs retain a bounded window and allow the operator
to stop following new lines while reading earlier output.
