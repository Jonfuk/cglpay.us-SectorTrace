# SectorTrace frontend (Phase 6)

Two **independent** Nuxt 4 applications that replace the hand-written DOM
portals described in `performance.md` Phase 6:

| App | Path | Served at | Purpose |
|---|---|---|---|
| `public/` | `@sectortrace/public` | `/` | Public evidence-atlas |
| `admin/`  | `@sectortrace/admin`  | `/admin/` | Operator operations-control-room |

Each app has its own dependency graph, lockfile, Nuxt config, pages, layouts,
composables, and CSS. There is no shared runtime code between them by design:
the public bundle must never contain admin routes, restricted schemas, or
privileged clients (portal isolation, unchanged from the settled decisions).

## Node is build-time only

Node builds these apps into **static client-rendered SPAs** (`ssr: false`).
The production Python image never runs Node, Nitro, or an ASGI server — it
serves the generated assets as files. The committed deliverables are:

- the pinned `package-lock.json` in each app (reproducible `npm ci`);
- the TypeScript/Vue/Nuxt source;
- at the cutover stage, the generated static output copied into the Python
  image's public and admin static namespaces.

`node_modules/`, `.nuxt/`, `.output/`, and `dist/` are never committed.

## Toolchain

- **Nuxt 4** (`4.5.2`), **Nuxt UI v4** (`4.11`), **Tailwind CSS v4** (via Nuxt UI).
- **Vue 3.6** (`3.6.0-rc.6`) with **Vapor enabled** (`vue.vapor: true`).
  Vue 3.6 is still a release candidate; it carries Vapor. The **completion gate
  for Phase 6 is the Nuxt 4 VDOM migration + route parity + static delivery** —
  Vapor is an enabled but non-critical optimisation track. A component that
  fails the Vapor interop/measured-benefit gate drops its `vapor` attribute and
  stays VDOM with no other change. `app/components/BuildIdentity.vue` is the
  first Vapor component and proves interop end to end.
- **Hash-history routing** (`app/router.options.ts`) preserves existing
  `#/route?filters` bookmarks byte-for-byte during cutover.

### `legacy-peer-deps`

Each app pins `legacy-peer-deps=true` in `.npmrc`. Nuxt 4's peer graph plus the
pinned Vue 3.6 RC trips a known npm arborist peer-set resolver bug on strict
installs; `legacy-peer-deps` routes around it deterministically so `npm ci`
reproduces the committed lockfile. Remove it once Vue 3.6 is stable and Nuxt's
peer ranges include it.

## Commands

```bash
cd frontend
npm run install:all      # npm ci per app (falls back to install)
npm run build            # generate both static outputs + SPA fallbacks
npm run build:public     # public only  -> public/.output/public (symlinked as dist/)
npm run build:admin      # admin only   -> admin/.output/public
npm run typecheck        # nuxt typecheck per app
```

`npm run build` runs `nuxt generate` (static) and writes explicit `200.html`
and `404.html` SPA fallbacks so the Python server can answer any unprerendered
deep link with the client shell.

### Tests

```bash
cd frontend
npm run test        # Vitest unit tests (public app)
```

Vitest covers the framework-agnostic units whose invariants matter: the
transport (request-key canonicalisation, in-flight dedup, `AbortController`
cancellation), `StLink` (only `http(s)` becomes a link; `javascript:`/`data:`/
relative render as inert text), and `StStat` (null/undefined → em dash, never
`0`). Composables that depend on Nuxt auto-imports are left to the browser/e2e
gate. The CI `frontend` workflow runs typecheck → unit tests → build → budgets.

## Static output layout

- Public: assets under `/_nuxt/**`, entry `index.html` (+ `200.html`/`404.html`).
- Admin: assets under `/admin/_nuxt/**`, entry `index.html` (+ fallbacks).

Immutable content-hashed assets under `_nuxt/**` are served with one-year
caching; HTML entry points are served `no-cache`. Delivery is origin-only (no
CDN).

## Frontend performance budgets (Phase 6)

Enforced by `npm run budgets` (`scripts/check-budgets.mjs`), which measures the
built output and exits non-zero on any violation. "Shared JS" is measured
precisely as the chunks the entry `index.html` loads — what every route pays on
first load — not the sum of all chunks. Current measured values (gzip):

| Budget | Limit | Measured | Status |
|---|---|---|---|
| Public shared JS (Nuxt/Vue/routing) | ≤ 120 KiB | ~115 KiB | ✅ |
| Public shared CSS (Tailwind/Nuxt UI) | ≤ 50 KiB | ~25 KiB | ✅ |
| Public overview route JS+CSS before data | ≤ 375 KiB | ~141 KiB | ✅ |
| Admin initial route JS+CSS | ≤ 200 KiB | ~158 KiB | ✅ |

The public app drops Nuxt UI's `<UApp>` overlay/toast host (it uses none), which
keeps the shared chunk under budget; the admin app keeps `<UApp>` for toasts and
still fits its larger 200 KiB budget. The gate also enforces two structural
rules: the **public bundle contains no admin code** (`/api/admin/`, `useAdminApi`,
the write methods), and no specialist library (MapLibre/PMTiles/Tabulator/ECharts)
appears yet — a boundary that tightens to per-route once those routes land.

Run `npm run verify` to build both apps and check budgets in one step.

## Deployment and the cutover seam

The two apps ship in the production image but do **not** serve traffic until a
flag flips — so the image is cutover-ready while the legacy portals keep serving.

- **Build:** the Docker `frontend` stage (`node:22`) runs `npm ci` + `npm run
  build` per app and the runtime stage copies the two `.output/public` trees
  into `pipeline/web/static_nuxt/{public,admin}`. Node never enters the runtime
  image — only the static files cross the stage boundary.
- **Serve (gated):** set `SERVE_NUXT=true` and, when the built assets are
  present, the Python server serves the Nuxt apps — public at `/`, admin at
  `/admin` — via `pipeline/web/nuxt_assets.py`. Off by default: the legacy
  portals under `pipeline/web/static/**` serve, and remain the parity oracles.
- **Never intercepted:** `/api` and `/api/**` always go to the Python API,
  regardless of the flag. The seam only ever answers frontend paths.
- **Cache policy:** content-hashed `_nuxt/**` assets are served `immutable`,
  one year; HTML entry points are `no-cache`. SPA deep links fall back to the
  app's `200.html`; a missing asset is a real 404, never the shell.
- **CSP:** Nuxt entry documents get a policy that hashes their own inline
  scripts (importmap + bootstrap) — strict `script-src 'self'` plus those
  hashes, no `'unsafe-inline'` for scripts — computed from the exact bytes
  served. `pipeline/web/static_nuxt/` is gitignored (built in Docker).

The flag is the cutover switch: flip it once the parity, budget, and browser
gates pass. `tests/test_nuxt_assets.py` pins the resolver, cache policy, and CSP.

## Status

This is the **foundation** stage: workspace, two isolated apps, typed
same-origin API clients (dedup + `AbortController` cancellation), URL-authoritative
filter state, versioned browser storage, static generation with SPA fallbacks,
hash-route compatibility, and a verified reproducible build. Route parity with
the legacy portals is delivered stage by stage in subsequent commits; the legacy
applications under `pipeline/web/static/**` are retained untouched as parity
oracles until the final gated cutover.
