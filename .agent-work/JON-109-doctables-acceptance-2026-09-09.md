# JON-109 route acceptance — extracted tables, ragged grids and exact-output exports

**Run:** 2026-09-09
**Mode:** tests-only acceptance run and evidence report after isolated preflight
**Repository:** `Jonfuk/cglpay.us-SectorTrace`
**Branch:** `beta`
**Base/head SHA:** `62b4d161cf13cd00a21caf45c23317c7deef08a5` (unchanged; no application/API/schema code was modified)
**Human acceptance owner:** Jon Firth
**Environment:** Node v22.23.2, npm 10.9.8, system Chromium 152.0.7977.82 (used via `PLAYWRIGHT_CHROMIUM_PATH`, since the pinned managed browser path `/opt/pw-browsers/chromium-1194/...` is absent in this sandbox and the packet permits falling back when that binary is absent)

## Boundary

Mode is tests-only. No API/schema change, shared export-semantics change, evidence-transformation change, dependency upgrade, live-source request, or production change was made. The only change is to the anonymous fixture-based Playwright spec `frontend/public/e2e/document-tables.spec.ts`. Manual assistive-technology evidence (screen-reader walkthrough) was **not** performed and remains explicitly pending, as permitted by the packet.

## Verified entry points (matched packet claims)

- `frontend/public/app/pages/doctables.vue` — present, 115 lines.
- `frontend/public/e2e/document-tables.spec.ts` — present, originally 56 lines with 2 tests.
- `frontend/public/package.json` — present; scripts `typecheck`, `lint`, `test`, `build`, `test:e2e` match the packet's command sequence.
- `frontend/public/playwright.config.ts` — present; confirms `baseURL: http://localhost:4173` and the `PLAYWRIGHT_CHROMIUM_PATH` fallback behaviour described in the packet.
- API: `frontend/public/app/composables/usePublicApi.ts` exposes `documentTables()` over `/api/v1/document_tables`, consistent with the packet.
- `~/utils/referenceExport` named in the packet does not exist under that name; the page actually imports `downloadEvidenceJson` from `~/lib/evidence-export` (`frontend/public/app/lib/evidence-export.ts`). This is a naming discrepancy in the packet text, not a missing feature — inspected before any shared-export change and no shared export code was touched.

## Commands run (isolated, this sandbox)

```
cd frontend/public
npm ci                                                     # 1058 packages, clean
npm run typecheck                                          # nuxt typecheck — no errors
npm run lint                                                # 0 errors, 6 pre-existing warnings unrelated to doctables
npm test                                                    # vitest run — 20 files, 71 tests passed
npm run build                                               # nuxt generate + spa-fallback — succeeded, .output/public + dist/200.html + dist/404.html written
PLAYWRIGHT_CHROMIUM_PATH=/usr/bin/chromium CI=1 npx playwright test --project=chromium e2e/document-tables.spec.ts
PLAYWRIGHT_CHROMIUM_PATH=/usr/bin/chromium CI=1 npx playwright test --project=chromium e2e/document-tables.spec.ts --repeat-each=2   # stability check
```

All commands exited 0 except where noted below.

## Results — existing tests, run unchanged first

Both pre-existing scenarios passed unchanged before any new test was added:

- `table previews open exact full grids and preserve cells in scoped downloads` — PASS
- `table parent mismatch prevents export and markdown-only extraction remains literal on mobile` — PASS

## Results — new boundary/race cases added (tests/fixtures only)

Five new fixture-only Playwright cases were added to close the packet's stated remaining oracles. All seven cases in the file pass, including a `--repeat-each=2` stability run (14/14 pass, no flakes observed).

1. **`large grid pagination preserves every ragged row without duplication or inferred headers`** — a synthetic 101-row grid with deliberately ragged row lengths (1–3 cells, `raggedRow(n) = (n % 3) + 1` cells). Verifies exactly 50 rows shown per local page (rows 1–50, then 51–100, then 101), no row duplicated or dropped across page boundaries, ragged row lengths preserved exactly (row 2 renders with its true 3 cells, not padded/truncated to a uniform width), and the final page's "Next page" control is disabled with no invented 102nd row. **PASS.**
2. **`missing table/grid arrays are distinct from returned empty arrays`** — confirms `tables` absent from the response renders "The table list was not supplied.", while `tables: []` renders "No tables were returned for the active parse."; and separately that `grid` absent renders "A valid grid array was not supplied." while `grid: []` renders "No structured cells were returned." These are two independently reachable UI states over four fixture responses, keyed to distinct fixture identifiers so each request is a genuine new fetch. **PASS.**
3. **`a slow response for a previous selection never displays under the current one`** — a request for `doc/slow` deliberately resolves 500ms after a subsequent, faster `doc/fast` selection made within the same SPA session (not a page reload). Confirms the page's own `key === signature.value` staleness guard: only "Fast document" is ever shown, and "Slow document" never appears even after the slow response resolves. This exercises the exact race the page's `current` computed is designed to prevent. **PASS.**
4. **`retry after a failed response keeps the exact request scope`** — first response is a 503; the page shows "Evidence is unavailable" with a Retry control (`StEvidenceState`); clicking Retry re-issues the identical request (same query parameter set, same key `document_id`) and succeeds on the second attempt. Confirms retry does not broaden or narrow the request scope. **PASS.**
5. **`the returned grid region is keyboard-focusable`** — confirms the extracted-grid `role="region"` carries `tabindex="0"` and can receive keyboard focus programmatically. This is the automatable slice of the packet's keyboard/assistive-technology requirement; it is **not** a substitute for a manual screen-reader walkthrough, which remains unperformed and pending. **PASS.**

## Test file diff

`git diff --stat`: `frontend/public/e2e/document-tables.spec.ts | 121 +++...` (121 insertions, 0 deletions; file grew from 56 to 177 lines, from 2 to 7 tests). No other file was modified. `git status --short` otherwise shows only the new untracked `.agent-work/` directory holding this and prior preparation reports.

## Oracles from the packet not exercised here

- **Manual assistive-technology evidence** (screen-reader announcement walkthrough) — explicitly stated in the packet as "stays pending until actually performed"; not performed in this automated pass.
- **Detailed metadata inspection** and **exact reader/source pivot without substituting a newer parse** beyond what the existing suite already covers (`Open document reader` link `element_id` propagation, tested in the original first scenario) — the packet's remaining-oracle list is otherwise covered by the five new cases above; no additional gap was identified requiring a new case beyond what is listed.
- **CSV quoting/newline/formula-protection edge cases beyond the existing fixture** (`=1+1`, embedded semicolon, em dash) were already covered by the original first test and were not further extended, since the packet describes that behaviour as already tested.

## Result

**Existing tests:** 2/2 passed, unchanged, before any new case was added.
**New tests:** 5/5 passed, stable across a repeated run (14/14 total across two repetitions).
**Full command sequence:** `npm ci`, `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`, `npm run test:e2e -- --project=chromium e2e/document-tables.spec.ts` — all exited 0.
**Files changed:** `frontend/public/e2e/document-tables.spec.ts` only (tests/fixtures, no application code).
**No API/schema/export-semantics/dependency changes were made.**

## Blockers

None that prevented running the specified test-only acceptance work. The one non-blocking discrepancy is the packet's reference to `~/utils/referenceExport`, which does not exist under that name — the actual module is `~/lib/evidence-export`; flagged for correction in a future packet revision but did not block this work since no shared export code was touched.

## Exact next human action

Jon Firth reviews this test-only diff and evidence report, confirms the five new boundary/race cases match the intended acceptance oracles for `/doctables`, and separately arranges the manual assistive-technology (screen-reader) walkthrough that remains outside this automated pass. This report does not constitute release sign-off, gate closure, or merge; per the packet, "agent completion is submission for review, not release sign-off."
