# Admin activation and rollback

Implementation does not activate a deployment. Retain the entire legacy static
tree and the previous generated admin build until the new build is accepted.
No schema migration or warehouse rewrite is part of this theme.

## Build and stage

Use the repository's supported Node toolchain and existing dependency lockfile:

```sh
cd frontend/admin
npm ci
npm run typecheck
npm run build
npm run test:e2e
cd ../..
node frontend/scripts/check-budgets.mjs
uv run python -m pytest
uv run ruff check pipeline tests
```

Copy the contents of `frontend/admin/.output/public` into
`<NUXT_DIST_DIR>/admin/`. The default parent is
`pipeline/web/static_nuxt`. Keep `index.html`, `200.html`, `404.html`, `_nuxt/`
and any generated supporting assets together. Node is not required by the
serving process. Stage a complete build before restarting the server; availability
is cached for the process lifetime.

## Serving policy

| `ADMIN_UI_VARIANT` | Admin behaviour |
|---|---|
| omitted | Follow `SERVE_NUXT` as before |
| `legacy` | Serve the retained legacy admin, even if `SERVE_NUXT=true` |
| `nuxt` | Serve the generated admin if present, independently of public |

`SERVE_NUXT` alone still controls public serving. Admin and public build
availability are resolved separately. A missing requested admin build falls
back to legacy and emits `web.admin_build_unavailable` with the requested variant,
fallback and directory. Invalid variants fail settings validation.
`ADMIN_UI_ENABLED=false` remains the first guard and removes admin UI/API access
regardless of variant. Same-origin JSON write checks, static path containment,
missing-asset 404s, cache policy and script-hash CSP remain in force.

For a local acceptance run set `ADMIN_UI_VARIANT=nuxt` and start the existing
web command bound to `127.0.0.1`. Check both `/admin` and the public `/`, inspect
the browser console and confirm `/admin/_nuxt/missing.js` returns 404. Exercise
current `#/review?...`, legacy `#review?...`, `/admin/analysis`, back/forward
and bare-admin resume. Run fixture-backed browser verification before pointing
operators at the build; it submits no real decisions.

## Roll back

Set `ADMIN_UI_VARIANT=legacy` and restart the web process. Do not change
`SERVE_NUXT` to roll back admin: doing so would also change public serving.
No database restore is needed. Existing endpoint contracts and audited
decisions are shared; browser acknowledgement gates are intentionally reset.
Legacy preferences were left intact. Remove the explicit variant later only
when you intend to restore the original `SERVE_NUXT` coupling.

The browser matrix is configured for Chromium, Firefox and WebKit. A browser
launch failure is not a passing compatibility test. On this Windows host,
Firefox 1538 currently cannot resolve its `mozglue` side-by-side assembly;
complete the Firefox gate on a working Playwright host before deployment.
The zoom checks exercise the 720-CSS-pixel layout corresponding to a 1440-pixel
window at 200%. Native browser zoom and assistive-technology checks should also
be completed on the deployment acceptance host; viewport emulation is not a
claim that those manual checks passed.
