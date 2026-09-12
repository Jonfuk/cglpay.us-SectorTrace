# JON-88 V1 progress reporting and burn-up metrics — initial dated baseline

**Snapshot timestamp:** 2026-09-09T17:58:20Z
**Mode:** preparation-only dated progress/readiness report (no automatic background reporting, analytics service, agent launch, or notification schedule created)
**Repository/candidate context:** `Jonfuk/cglpay.us-SectorTrace`, `beta` at `62b4d161cf13cd00a21caf45c23317c7deef08a5` — repository reference point only. **No source candidate is locked** (JON-82 not started) and **no artefact manifest exists** (JON-78 not started), so this baseline is issue/decision-status reporting, not candidate-accepted-work reporting. Per the packet: "project-wide Backlog/0% is not proof that no software exists" — substantial implementation is recorded in `beta.md`/`performance.md`/`docs/frontend-redesign-progress.md` (see JON-63's reconciliation, `.agent-work/JON-63-reconciliation-2026-09-09.md`), even though almost no Linear issue is yet marked started/accepted.
**Human acceptance owner:** Jon Firth
**Target date:** 31 October 2026 (V1 release)

## Data source and method

Queried via Linear MCP `list_issues` filtered to `project: SectorTrace`, one page, `hasNextPage: false` (complete result for this project at query time). Requirement→issue→evidence linkage draws on the candidate evidence register referenced throughout the V1 gate issues, and on the three preparation reports already produced today (JON-63, JON-81, JON-109; see `.agent-work/`). No parent gate and child leaf were double-counted: the ten top-level gates (JON-47–JON-56) are reported separately from their child leaf issues below, per the packet's "count leaf effort once; keep parent review overhead separate" instruction. Post-V1/Not-scheduled-labelled issues (source-integration exploration, identity research, deferred/research items — roughly 40 issues, e.g. JON-6 through JON-46, JON-57–62, JON-97–102) are excluded from this V1 burn-up entirely, per the packet.

## 1. V1-scoped issue population

**52 issues** carry `V1 required` or `Release gate` (excluding anything also labelled `Post-V1`). Status breakdown:

| statusType | Count |
|---|---|
| `unstarted` (Todo) | 7 |
| `backlog` | 45 |
| `started` | 0 |
| `completed` | 0 |

**0 of 52 V1-scoped issues have `startedAt` or `completedAt` set.** This is a Linear-tracking-state fact, not a software-completeness fact: per JON-63's reconciliation, real implementation exists in the repository (e.g. performance Phases 1/3/5 complete at repository level, several frontend route slices delivered) that has not yet been reflected as `started`/`completed` against these specific Linear issues. This gap between repository evidence and Linear status is itself a finding this report surfaces, not resolves.

## 2. The ten top-level release gates (JON-47 → JON-56)

| Gate | Title | Status | Due |
|---|---|---|---|
| JON-47 | V1 01 — Reconcile release scope and outstanding roadmap decisions | Todo | 2026-09-18 |
| JON-48 | V1 02 — Finish frontend foundations, discovery and profile acceptance | Backlog | 2026-09-25 |
| JON-49 | V1 03 — Complete specialist evidence and document route acceptance | Backlog | 2026-10-09 |
| JON-50 | V1 04 — Finish connections, comparisons and research portability | Backlog | 2026-10-09 |
| JON-51 | V1 05 — Pass accessibility, responsive and editorial release review | Backlog | 2026-10-16 |
| JON-52 | V1 06 — Establish performance baseline and pass frontend budgets | Backlog | 2026-10-23 |
| JON-53 | V1 07 — Close ingestion memory and parser acceptance gaps | Backlog | 2026-10-09 |
| JON-54 | V1 08 — Pass reproducible regression and consecutive CI gates | Backlog | 2026-10-28 |
| JON-55 | V1 09 — Verify generated serving, mirror deployment and rollback | Backlog | 2026-10-23 |
| JON-56 | V1 10 — Sign off evidence safety, optional gates and release handoff | Backlog | 2026-10-29 |

All ten gates are unstarted/backlog. None is complete. JON-47 is the earliest-due (2026-09-18, 9 days from this snapshot) and is itself blocked on its own children (JON-63, JON-64, JON-87, JON-90 — see below).

## 3. Blocked / needs-decision items and age

**9 V1-scoped issues carry `Human decision required`.** Of these, the most time-critical:

| Issue | Title | Priority | Due | Age since created (to snapshot) |
|---|---|---|---|---|
| **JON-89** | V1 decision — resolve WDTK access expiry and verify fail-closed collection | **Urgent** | **2026-09-10** | ~5h (created 2026-09-09T12:49Z) — **due in <24h from this snapshot, unstarted** |
| JON-98 | V1 decision — record source-use permissions, expiries and disabled operations | High | 2026-09-18 | ~5h |
| JON-64 | Confirm V1 scope and optional capability dispositions | High | 2026-09-18 | ~6h |
| JON-5 | V1 decision — verify existing Open Jobs shadow collector and enablement scope | High | 2026-09-18 | ~10h |
| JON-87 | V1 dependency and critical-path review | High | 2026-09-16 | ~5h |
| JON-80 | Evidence safety and optional-gate disposition | High | 2026-10-28 | ~7h |
| JON-83 | V1 go/no-go decision and release approval | High | 2026-10-30 | ~2h |
| JON-85 | V1 beta exit — accept five research journeys on the frozen candidate | High | 2026-10-28 | ~2h |
| JON-86 | V1 operational readiness, observability and incident runbook | High | 2026-10-23 | ~2h |
| JON-91–95 | Five research journeys (children of JON-85) | High | 2026-10-27 | ~1–2h |

**JON-89 is the single most urgent open item across the whole V1 scope**: it is due 2026-09-10, is `Todo`/unstarted, and its own text says the underlying WDTK access exception is time-boxed to that same date. This was independently flagged during JON-81's preparation work today and is repeated here as the burn-up report's top blocked-item callout.

**5 issues** carry `Waiting for input` (JON-90, JON-79, JON-72, JON-9, JON-96) — distinct from `Human decision required`: these are agent-readiness states meaning a dispatched preparation pass could not fully proceed without an additional input, not necessarily a pending human decision.

**22 issues** carry `Needs preparation` — not yet dispatched/started even at the preparation level.

**16 issues** carry `Ready for pickup` (including the four issues executed today: JON-63, JON-81, JON-109 completed their preparation-only packets; JON-88, this one, in progress). Per the packet: "a Todo item or Ready for pickup label is not proof of completed preflight, implementation or acceptance."

## 4. Evidence/handoff completion (JON-80/JON-81/JON-82/JON-78 chain)

- **JON-82 (source candidate lock):** Backlog, not started. **Blocking**: no candidate SHA/configuration is frozen yet.
- **JON-78 (artefact manifest):** Backlog, `Needs preparation`, not started. Depends on JON-82.
- **JON-80 (evidence-safety/optional-gate disposition):** Backlog, `Human decision required`, not started.
- **JON-81 (release notes and handoff):** A preparation-only draft skeleton was produced today (`.agent-work/JON-81-release-notes-draft-2026-09-09.md`); every candidate-dependent field is explicitly marked pending JON-82/JON-78, per that report's own findings. Linear status remains `Backlog` (this report does not change it).

**No candidate identity, artefact manifest, or safety-gate disposition exists yet.** Per the packet's "use the release evidence register under JON-82; missing evidence remains unknown" — this report records that gap rather than inferring readiness.

## 5. Milestone health

| Milestone | V1-scoped issue count observed | Notable status |
|---|---|---|
| Scope locked | JON-47, JON-64, JON-87, JON-90, JON-5, JON-9 and related | Earliest-due milestone (2026-09-16–18); all constituent issues unstarted |
| Evidence and ingestion | JON-49 and its route-acceptance children (JON-67, JON-96, JON-103–112) | JON-109 (one child) has a fresh preparation-only tests pass completed today (7/7 e2e tests, tests-only diff); the other ~11 sibling route-acceptance issues remain `Needs preparation`/`Backlog`, untouched |
| Performance and deployment | JON-52/53/54/55 and children (JON-72–79, JON-96) | All unstarted; JON-72 (performance instrumentation baseline) is `Waiting for input` and due 2026-09-18 |
| Release sign-off | JON-56, JON-80, JON-81, JON-83 | All unstarted; JON-81 has a preparation draft but candidate-dependent sections are pending upstream gates |
| V1 release | JON-84, JON-85, JON-86 and five journeys (JON-91–95) | All unstarted; JON-85's five journeys are `Human decision required` |

No milestone shows measurable percentage completion by Linear state; all are effectively 0% by ticket-status measure while carrying non-zero real implementation per JON-63's separate reconciliation. This divergence is the most important single finding for Jon Firth's review: **Linear status currently under-represents actual repository progress**, and the converse also holds — no Linear "Ready for pickup" label should be read as acceptance evidence.

## 6. Schedule variance against 31 October 2026

- **9 days remain** to the earliest gate (JON-47, due 2026-09-18) as of this snapshot, and that gate's own four children (JON-63, JON-64, JON-87, JON-90) are all still unstarted/Todo, with JON-63 alone in Linear terms being the only one with in-repository preparation work actually delivered today.
- **JON-89's due date (2026-09-10) is inside this 9-day window and is the single nearest deadline of any V1-scoped issue.** Missing it or extending it silently would itself be an evidence-safety violation per JON-89's own text ("this task does not extend it or authorise collection").
- **52 days remain** to the 31 October 2026 target. With 0 of 52 V1-scoped issues marked started or completed in Linear, and 10 of 10 top-level gates still unstarted, **schedule variance cannot yet be quantified as ahead/behind/on-track** — there is no started baseline to measure velocity against. This report itself establishes that starting baseline (0 started, 0 completed, as of 2026-09-09T17:58:20Z) so that next week's review has a comparison point.
- No monetary/token execution-cost budget has been supplied to this agent for this reporting pass; per the packet, "monetary/token budgets are human-supplied controls, not inferred estimates" — none is inferred or reported here.

## 7. Work-in-progress and review-queue signal (flow/risk reporting addition, 9 September 2026)

- **WIP against the provisional 2-task execution limit:** At the time of this snapshot, this agent executed JON-63 → JON-81 → JON-109 → JON-88 **strictly sequentially**, one at a time, per explicit user instruction — i.e. WIP of 1 throughout, not exceeding the 2-task provisional limit.
- **Review queue count/age:** Three preparation artefacts (JON-63, JON-81, JON-109 reports) and this JON-88 baseline are awaiting Jon Firth's review; all created within the same session (age: hours, not yet reviewed).
- **Rework:** None recorded this session; JON-109's e2e additions required two small self-corrected fixes (ragged-cell count assertion, ambiguous locator scoping) before the final passing run — noted as in-session iteration, not cross-session rework.
- **Agent execution resource exceptions:** No repeated retries beyond the two in-session e2e fixes noted above; no duplicate work; no missing provider/model/effort evidence to report; no exposed execution-cost/budget overrun (no budget was supplied to compare against).

## 8. Material-risk register (initial entries, for the release control room)

| Risk | Trigger / early warning | Owner | Mitigation | Contingency | Next review | Linked issue |
|---|---|---|---|---|---|---|
| WDTK access exception expiry | 2026-09-10 date passes without a recorded decision | Jon Firth | Resolve JON-89 before/at expiry; verify fail-closed control | Suspend affected FOI collection via configuration, not code change | 2026-09-10 | JON-89 |
| Candidate identity never frozen | JON-82 remains unstarted past its 2026-10-19 due date | Jon Firth | Prioritise JON-82 ahead of downstream JON-78/80/81/83/84 | Slip 31 Oct target explicitly rather than launch an unfrozen candidate | Weekly | JON-82 |
| Linear status/repository-evidence divergence | Continued 0%/Backlog reporting despite real delivered work (per JON-63) | Jon Firth | Periodically reconcile Linear state against `beta.md`/`performance.md`/frontend progress checkpoints | Treat JON-63-style reconciliation as a recurring input to this report, not a one-off | Weekly | JON-63, this issue |
| Suppression/assistant capability accidentally enabled | Any candidate build with these flags on before their safety gates pass | Jon Firth | JON-80 must explicitly re-verify disabled/deferred status against the actual candidate flags | Block JON-78 build sign-off until confirmed | At artefact build (JON-78) | JON-80, JON-57, JON-58 |
| Five research journeys unresolved | JON-91–95 remain `Human decision required`/Backlog close to 2026-10-27 due date | Jon Firth | Schedule JON-90 (fixture/journey design) before individual journey work | Slip beta-exit date (JON-85) rather than accept unverified journeys | Weekly | JON-90, JON-85, JON-91–95 |

## Result

**Initial dated V1 progress baseline established:** 52 V1-scoped issues (0 started, 0 completed in Linear terms), 10/10 top-level gates unstarted, 9 issues needing a human decision (JON-89 most urgent, due 2026-09-10), no candidate identity or artefact manifest yet locked, and a documented divergence between Linear tracking state and actual repository implementation evidence (per JON-63). No issue was marked complete without acceptance evidence; none of today's three preparation-only reports (JON-63, JON-81, JON-109) changed any Linear issue status, label, or assignment.

## Exact next human action

Jon Firth should (a) resolve JON-89 immediately given its 2026-09-10 due date, (b) review this baseline alongside the JON-63/JON-81/JON-109 reports, (c) confirm or correct the risk register above, and (d) direct whether Linear issue statuses should now be updated to reflect today's preparation-only completions (this report deliberately did not change any issue's status/labels, since JON-88's mode is report-only). Subsequent weekly reviews should diff against this baseline's counts (52/0/0, 10/10 gates unstarted, 9 human-decision items) to compute real velocity.
