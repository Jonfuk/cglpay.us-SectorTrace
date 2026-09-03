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

## Static output layout

- Public: assets under `/_nuxt/**`, entry `index.html` (+ `200.html`/`404.html`).
- Admin: assets under `/admin/_nuxt/**`, entry `index.html` (+ fallbacks).

Immutable content-hashed assets under `_nuxt/**` are served with one-year
caching; HTML entry points are served `no-cache`. Delivery is origin-only (no
CDN).

## Frontend performance budgets (Phase 6)

Tracked as gates, tuned as routes are ported and code-split. Current foundation
measurements (gzip) are recorded so regressions are visible:

| Budget | Limit | Public foundation (gzip) |
|---|---|---|
| Shared JS (Nuxt/Vue/routing) | ≤ 120 KiB | ~135 KiB — **over**, untuned (full Nuxt UI, no route chunks yet) |
| Shared CSS (Tailwind/Nuxt UI) | ≤ 50 KiB | ~25 KiB — within |
| Overview route JS+CSS before data | ≤ 375 KiB | within |
| Admin initial route JS+CSS | ≤ 200 KiB | within |

The shared-JS overage is expected before tree-shaking, modular Nuxt UI imports,
and route-level dynamic imports land. It is not yet met and is not claimed to
be.

## Status

This is the **foundation** stage: workspace, two isolated apps, typed
same-origin API clients (dedup + `AbortController` cancellation), URL-authoritative
filter state, versioned browser storage, static generation with SPA fallbacks,
hash-route compatibility, and a verified reproducible build. Route parity with
the legacy portals is delivered stage by stage in subsequent commits; the legacy
applications under `pipeline/web/static/**` are retained untouched as parity
oracles until the final gated cutover.
