# Preparation-only pilot findings — 9 September 2026

These two pilots used connector reads at beta `62b4d161cf13cd00a21caf45c23317c7deef08a5`. They did not change application code, run application tests, capture representative-user sessions, start collection, change source permissions or deploy. A container clone attempt failed because that environment had no usable GitHub authentication; repository inspection continued through the authorised connector. This is an environment limitation, not an application test failure. No agent runtime is certified by this report.

## JON-109 — extracted tables

### Resolved starting points
- `frontend/public/app/pages/doctables.vue` (inspected source): exact selectors, supported request parameters, response signature/cancellation, parent match, preview paging and full-grid exports.
- `frontend/public/e2e/document-tables.spec.ts` (inspected existing tests): source fixtures and exact JSON/CSV assertions.
- `frontend/public/package.json`, `frontend/public/playwright.config.ts` and `.github/workflows/tests.yml`: commands and environment profile F.
- API consumed: `/api/v1/document_tables`. Shared export utilities are imported from `~/utils/referenceExport`; inspect the utility before changing it and coordinate other export tasks.

### Existing behaviour and tests
The page uses ten previews per local page and fifty grid rows per local page. It preserves ragged rows, has no inferred CSV header, converts null to empty for CSV and prefixes formula-like cells. JSON uses the original returned data. The existing spec covers exact special-character table/document IDs, scoped API parameters, literal markup, exact JSON and formula-safe CSV, mismatched-parent export blocking and a markdown-only mobile case. These are source/test-code observations, not freshly passed tests.

### Remaining bounded matrix
Use clearly synthetic fixtures, not real evidence: 10/11 previews; 49/50/51/101 grid rows; ragged/null/empty cells; missing arrays versus empty arrays; selection/page reset; delayed response A after selecting B; failed retry retaining exact scope; exact reader pivot with an unavailable older reference. Assert JSON equality to the fixture and independently specified CSV transformations. Verify no invented header/value/version. Add keyboard paging/focus checks and retain a separate manual assistive-technology result as pending until performed.

### Pickup outcome
The technical packet is prepared. First executable action is profile F preflight, then the two existing tests unchanged, then the new cases. Bounded local page/test fixes are allowed only on explicit implementation dispatch; shared export/API/schema changes need coordination/review. The current session's test execution outcome is **not run — no authenticated local checkout/browser preflight**. Keep the issue open for engineering and human acceptance.

## JON-96 — critical-source drift

### Resolved starting points
- `pipeline/quarantine.py` (inspected): existing `quarantine()` uses kinds rejected_candidate, failed_stage_input and archive_mismatch; stable kind/module/item identity; resolved items are not reopened by re-observation. Telemetry deliberately excludes source-shaped item identities/reasons/payloads. Do not create a second quarantine store or leak source content into telemetry attributes.
- `pipeline/http.py`, `pipeline/db.py`, `pipeline/registry.py` and the selected source modules are the next repository entry points to inspect, not a certified complete implementation map.
- Profile P and `.github/workflows/tests.yml` define disposable offline validation.

### Missing inputs and stop condition
JON-64 has not supplied the approved critical-source list. Required per selected source: module/parser entry point, authoritative shape/required fields, versioned archived fixture and hash, legitimate empty-result semantics, expected parse/failure result and owner. An exact collection-attempt implementation/test map still needs to be resolved in the checkout; the guessed path `pipeline/collection_attempts.py` was not found and must not be created merely to match a guess.

Proposed offline cases: missing required column; renamed field; HTML login/error body with HTTP 200; malformed document; valid zero-result response; field-level parsing degradation. Expected outcome must come from the selected source contract, not a universal minimum row count. Preserve past valid observations, raw-byte provenance, human promotion and bounded replay.

### Pickup outcome
**Waiting for input: JON-64 source/contract selection, owner Jon Firth.** Read-only mapping and a proposed contract table can proceed, but no collector/schema/runtime change is justified until those inputs exist. No source, corpus, licence or numeric threshold was invented. No application tests ran. This is the intended safe result of the second pilot, not a completed drift feature.
