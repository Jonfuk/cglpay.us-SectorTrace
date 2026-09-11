# Agent execution packet

Replace bracketed fields before implementation dispatch. A field may be explicitly not applicable with a reason; missing authority or test oracles must not be guessed.

## Classification and output
- Linear issue: [ID]; task type: [implement / verify / research / prepare decision / coordinate / deploy].
- Scope: [V1 required / V1 decision / Post-V1]; readiness: [group label].
- Repair mode: [report-only / tests-only / bounded fixes].
- Agent deliverable: [PR or report and its exact destination]. Human acceptance owner: [name].
- Execution authority: [explicit dispatch and allowed local actions]; separate approvals: [production, schema, external/paid access, etc.].

## Baseline and current implementation
- Repository/base branch: [owner/repo and branch]; captured base SHA: [actual value].
- Required instructions/specification sections: [links].
- Starting files/symbols and existing tests: [verified paths].
- Already implemented/verified: [evidence]; remaining gap: [specific cases or reproduction].
- Shared-file coordination: [owner/conflicting task or none].

## Inputs and environment
- Profile: [F / P / C / read-only preparation]; actual versions/isolation: [record].
- Fixtures/corpus/configuration: [versioned locations and identities].
- Network/setup allowance, resource/time budget and credentials: [references only, no secret values].
- Blockers: [issue, exact missing input, owner and unblock condition].
- First action: [preflight and the first bounded test/inspection].

## Acceptance matrix
| Case/input | Expected observable result | Command/manual check | Evidence destination |
|---|---|---|---|
| [versioned fixture] | [independent oracle, null/missing/date/scope semantics] | [exact selector] | [retained report] |

List happy, negative, boundary, partial/failure and race cases applicable to this task. Separate manual/user interpretation from automated checks. A source change requires a new candidate identity and relevant revalidation.

## Change boundary
- Allowed paths/behaviour: [scoped changes; exact path list may be extended only with a reason within this boundary].
- Forbidden: unrelated refactors/upgrades, altered evidence semantics, invented source data, automatic promotion, production access, unapproved schema/API changes.
- Stop when: required inputs/permissions are absent, scope expands, runtime is unsafe, or the oracle is ambiguous.
- Defect policy: [small local regression + fix allowed, otherwise linked follow-up].

## Handoff
Base/result SHA; branch/PR; source/configuration/artefact identity; changed files; commands and exit codes; test/fixture versions; actual evidence links; failures and unrun checks; remaining risks; human decision required; next action. Agent-complete is ready for review, not human-approved or deployed.
