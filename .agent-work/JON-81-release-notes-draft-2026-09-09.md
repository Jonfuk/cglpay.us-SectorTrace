# JON-81 release notes and final handoff — DRAFT (preparation-only)

**Drafted:** 2026-09-09
**Mode:** preparation-only release-note and handoff draft, not a publication and not release approval
**Repository:** `Jonfuk/cglpay.us-SectorTrace`
**Branch:** `beta`
**Draft reviewed SHA:** `62b4d161cf13cd00a21caf45c23317c7deef08a5` (repository baseline, NOT a frozen V1 candidate — see below)
**Human acceptance owner:** Jon Firth

## Boundary and preflight result

The issue packet permits a candidate-specific release-note and handoff draft that separates implemented, verified, unverified and deferred work. It explicitly forbids treating this draft as production launch, closing release gates, or rewriting the hand-maintained README. Those boundaries were observed: no README edit was made, no gate was closed, and no launch action was taken.

**This draft cannot be finalised yet, and says so explicitly, because its two required inputs do not exist:**

- **JON-82 (source candidate lock)** — status `Backlog`, not started. No frozen source SHA/configuration/build-input record exists in the evidence register beyond "not selected/verified".
- **JON-78 (immutable artefact manifest)** — status `Backlog`, `Needs preparation`. No image digest, static asset manifest, or verified serving evidence exists.

Per the candidate evidence register (`SectorTrace V1 execution and candidate evidence register`), candidate identity, runtime configuration, regression, manual/user acceptance, source/capability decisions, operations and release/production verification are all recorded as **not selected/verified / pending / not executed / not granted / not performed**. This draft therefore uses the current beta HEAD only as a **repository reference point for known limitations and deferred features**, not as the release candidate, and marks every field that depends on candidate/artefact identity as **pending**.

## 1. Candidate identity

| Field | Value |
|---|---|
| Candidate SHA | **Pending JON-82.** Repository reference point only: `62b4d161cf13cd00a21caf45c23317c7deef08a5` on `beta`. |
| Image / static asset digests | **Pending JON-78.** Not built or verified. |
| Configuration / feature flags | **Pending JON-82/JON-78.** No redacted configuration record exists yet. |
| Migration / extension set | **Pending.** Not captured against a locked candidate. |
| Build recipe / lockfiles | **Pending.** `Dockerfile`, frontend lockfiles and `uv.lock` exist in the repository but have not been captured as a frozen build record. |

## 2. Evidence-state summary (implemented / verified / unverified / deferred)

Sourced from `beta.md`, `performance.md`, `docs/frontend-redesign-progress.md` and the candidate evidence register. This is a repository-level status summary, not candidate acceptance.

| Area | State | Evidence |
|---|---|---|
| PostgreSQL-only platform (performance Phase 1) | Implemented (repository-level) | `performance.md` Phase 1 marked Complete; clean PostgreSQL suite/lint/compile gates reported passing at the time recorded. |
| Analysis/model-call reduction (Phase 2) | Implemented, shadow-only acceptance; suppression deferred | Suppression stays disabled until the adjudicated corpus passes the 99%/100% release-safety gate (BETA-034, still BLOCKED). |
| Incremental NLP / semantic search (Phase 3) | Implemented (repository-level) | Marked Complete in `performance.md`. |
| Shared writes / ingestion memory (Phase 4) | Partial | Full adoption across every ingestion/document/PDF/CSV/prediction path remains outstanding. |
| Archive/graph/PostgreSQL/backend serving (Phase 5) | Implemented (repository-level), one documented gap | Index/autovacuum/planner tuning gated on the telemetry observation period. |
| Nuxt frontend delivery (Phase 6) | Partial | Applications, build/cutover seam and most routes exist; PMTiles-vs-GeoJSON follow-up, full claims editor and pinned Lighthouse acceptance runs are the recorded remainder as of the latest checkpoint, and later frontend progress entries (2026-09-07/08) record further route work still needing production build/browser verification. |
| CI and regression protection (Phase 7) | Partial | Remaining acceptance gate: ten consecutive clean parallel/serial CI runs. |
| Public frontend redesign (route-level) | Partial, by route | Document tables, revisions, source links, discrepancies and notebook portability have recorded implementation and prior focused validation checkpoints; broader accessibility, race/failure coverage and a fresh production/browser run after later refinements remain open per the 2026-09-08 progress entries. |
| Assistant / semantic-publication capability (BETA-107–116) | Code-complete, **disabled behind release gate** | `beta.md` records this explicitly; it is not enabled for V1 and remains a Post-V1/gated capability. |
| Semantic-analysis claim layer (BETA-034) | **BLOCKED** | Requires a successful human-reviewed `pipeline nlp gate-034g` corpus; not a code gap. |
| Dataset completion campaign (GitHub #54) | Partial, live-environment dependent | PR #53 merged with read-only coverage baseline; later comments record a Railway backfill with three m16 review items still pending human review. |
| Request-cost/caching controls (GitHub #55–61) | Unclear against current beta | Issues remain open; no linked implementation evidence found in issue metadata. Requires human reconciliation against the current `performance.md` cache/HTTP-cache record before this draft can state a disposition. |

## 3. Known limitations and disabled/deferred features (draft, for candidate-specific confirmation)

- **Suppression** (Phase 2 semantic layer) is disabled pending an adjudicated human-review corpus and its safety gate (BETA-034 / gate-034g). Not enabled in this release.
- **Local analyst assistant / semantic publication** (BETA-107–116) is code-complete but explicitly disabled behind its release gate. Not enabled in this release.
- **AI-assisted promotion candidate scope** (BETA-011) has no specified candidate type/use case or human decision recorded; excluded from V1 unless separately resolved.
- **WDTK/WhatDoTheyKnow access exception** (BETA-005) is time-boxed to 2026-09-10 or an earlier mySociety reply, and is explicitly not decided by this draft. JON-89 (V1 decision — resolve WDTK access expiry and verify fail-closed collection) is `Todo`, unstarted, due 2026-09-10, priority Urgent. **This is the most time-sensitive open item found during this preparation pass** and is called out for Jon Firth regardless of its position in the ten-gate sequence.
- **Open Jobs (m35) shadow collector** enablement disposition is pending JON-5 (V1 decision), unresolved as of this draft.
- **Source-use permissions/expiries register** (discover/fetch/archive/process/display/redistribute, per source) is pending JON-98; unknown permission is explicitly not permission granted.
- Post-V1 items (40 external-data opportunities, GitHub #55–61 request-cost controls unless reconciled, BETA-030/031 deferred UI items) are out of V1 scope unless a documented scope decision moves them in.

## 4. Licensing

- Repository licence: **MIT License**, copyright (c) 2026 Jonfuk (`LICENSE`, verified verbatim in this checkout).
- Per-source licensing/usage terms are documented per module in `docs/SOURCES.md` and `docs/CAVEATS.md` (personal-data handling, restricted tables, per-source caveats). This draft does not re-derive or restate those terms; it references them by file rather than duplicating content that could drift from the source of truth.
- Source-use permission dispositions (discover/fetch/archive/process/display/redistribute) remain pending JON-98 and JON-89 as noted above.

## 5. Operating instructions (repository reference, not candidate-verified)

Drawn from `docs/DEPLOYMENT.md` and `docs/BACKUP.md`. These are the documented operating commands for the current repository; they have not been re-verified against a locked candidate/artefact for this release.

- Backup: `./start.sh backup [--label <reason>] [--keep N]`, `./start.sh list-backups`, `./start.sh restore <path> --force`. Same four commands cover SQLite and PostgreSQL backends; `DATABASE_URL` decides which warehouse is addressed. Every backup is verified (integrity check, row-count/hash comparison) before being called a backup.
- Cutover (SQLite → PostgreSQL) is a nine-step gated checklist in `docs/DEPLOYMENT.md` ("Cutover checklist"), including a pre-cutover labelled backup, dry-run, migrate, independent re-verification, and a first PostgreSQL snapshot before anything depends on one.
- Production is Railway (per `beta.md` and `docs/DEPLOYMENT.md`'s "Somewhere else: Railway" section). `deploy/ansible/` provisions a separate self-host VPS build. `deploy/ansible-mirror/` provisions disaster-recovery mirrors and beta-deployment boxes seeded from production.

## 6. Rollback references (repository reference, not candidate-verified)

- **Before PostgreSQL cutover (steps 1–7 of the checklist):** rollback is unsetting `DATABASE_URL`.
- **After cutover / dual maintenance:** rollback currency depends on the last `./start.sh sync-sqlite` run; `./start.sh sync-sqlite --check` reports drift. The documentation records a case where the SQLite copy was "12 migrations and 33,000 rows behind" at time of writing — rollback freshness must be checked, not assumed.
- **Restore semantics:** `restore` never deletes the existing warehouse; it renames it aside (`warehouse.db.superseded-<timestamp>` for SQLite, or an equivalent labelled snapshot for PostgreSQL) before restoring, and refuses backups that fail their own integrity check or reference migrations the checkout does not have.
- **No candidate-specific, artefact-tested rollback rehearsal exists yet.** JON-79 (Ansible, backup, and rollback rehearsal) is separately tracked and unresolved; JON-84 (production launch) requires its own recorded rollback decision at launch time, which this draft does not perform.

## 7. Reconciliation of beta/frontend checkpoints

This section defers to and does not duplicate the dedicated reconciliation already produced for JON-63 (`.agent-work/JON-63-reconciliation-2026-09-09.md` in this checkout), which crosswalks `beta.md`, `performance.md`, `docs/frontend-redesign-progress.md`, `docs/frontend-redesign-plan.md` and the related GitHub issues (#54, #55–61, #71, #84) against current Linear V1 gates. Key reconciled points relevant to this handoff draft:

- The autonomous `beta.md` queue is empty of `IN_PROGRESS` work; completed programmes are recorded, but that is not V1 candidate acceptance.
- The 2026-09-08 frontend progress entries are the latest dated checkpoint and explicitly state the full redesign and mirror integration remain active, superseding any older "complete" framing at the phase-summary level.
- GitHub issue open/closed status does not by itself prove absence or completion of work; dated comments and linked commits/PRs are the more reliable evidence, and several (#54, #71, #84) show substantial delivered work behind an issue that remains open pending final review or operational access.

## 8. Sign-off reference (not completed by this draft)

Per JON-81's acceptance criterion, final sign-off must be a **named human decision that references gates 01–09** (JON-47 through JON-55, i.e. scope through deployment proof, feeding JON-56). This draft does not supply that sign-off. It also does not supply the JON-80 evidence-safety/optional-gate disposition, which remains a separate `Human decision required` item.

## 9. Blockers found during this preparation pass

1. **JON-82 not started** — no source candidate lock exists; this draft cannot cite a real candidate SHA/configuration as the release candidate.
2. **JON-78 not started** — no artefact manifest or verified serving evidence exists.
3. **JON-89 (WDTK decision) is due 2026-09-10 and unstarted** — time-sensitive, flagged for immediate human attention independent of the ten-gate sequence.
4. **JON-98 (source-use permissions register) unresolved** — licensing/permission section above cannot be finalised without it.
5. **GitHub #55–61 (request-cost controls) status unclear against current beta** — needs human reconciliation before this draft can state whether that work is superseded, merged, or still outstanding.
6. **Instruction PR #119 unmerged and inaccessible** (`403 auth_insufficient_scope` on the Linear review resource) — not used as authority for this draft; repository `AGENTS.md`/`CLAUDE.md`/`docs/*` were used directly instead.

## Result and next human action

**Result:** A candidate-specific release-notes and handoff **draft skeleton** is prepared, with every candidate-dependent field explicitly marked pending rather than fabricated, and known limitations/deferred features/licensing/operating/rollback references populated from current repository documentation. This is not a publishable release note and does not constitute release approval or gate closure.

**Exact next human action:** Jon Firth should (a) resolve JON-89 (WDTK decision, due 2026-09-10) as the most time-sensitive item, (b) progress JON-82 (source candidate lock) and JON-78 (artefact manifest) so this draft's Section 1 and dependent sections can be completed with real values, (c) resolve JON-98 and the GitHub #55–61 reconciliation question, and (d) only then direct finalisation of this draft into a publishable release note ahead of JON-56 sign-off. No further action is available under this issue's preparation-only mode until those inputs exist.
