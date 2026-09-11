# SectorTrace: Linear → Orca → GitHub

Use Linear for scope and acceptance, Orca for an isolated task workspace, and GitHub for the reviewable change. Keep your existing agent and model settings.

## One-time settings

In Orca's SectorTrace task drawer, select Linear, team **Jon Firth (JON)**, project **SectorTrace**. Use a view filtered to **V1 required + Ready for pickup**, excluding completed work. Read the issue's execution mode: some ready tickets permit preparation only. Keep a separate view for **Human decision required** and **Waiting for input**. Orca remembers task source per repository.

Keep the repository base ref at **origin/beta**. The GitHub default is master, so check the PR base explicitly. Enable base-ref refresh for new worktrees, or fetch origin before creating each task. The original master checkout is not the V1 task workspace.

Keep issue status changes deliberate: **In Progress** when permitted work actually starts, **In Review** when evidence is ready, and **Done** after human acceptance. Creating a workspace is not acceptance. Orca's worktree-created → In Progress sync is opt-in; leave it off for preparation work. Do not assume Orca workspace status is the Linear issue status.

If Linear's native GitHub integration is enabled, verify its branch-specific rules for beta. Prefer PR-ready → In Review. Do not automatically close acceptance or release-gate issues on merge: they may still need manual or candidate-specific evidence. The integration's current mapping must be checked in Linear; it was not changed by this setup.

## Daily flow

1. Choose one ready leaf issue. Read its description, parent, blockers and latest handoff. Respect the existing limit of two technical execution tasks and two changes awaiting human review. Preparation is permitted only in the issue's stated mode.
2. Create a new worktree from that Linear issue in Orca. Use its suggested branch name, which contains JON-xxx. Check that the issue remains linked and that the base is origin/beta. Reuse an existing linked workspace when continuing the same task.
3. Start your usual agent in that worktree with the pickup prompt below. Record the actual base SHA, environment and output location. Worktrees do not isolate databases, ports or containers: use the issue's environment profile and disposable resources.
4. Run the scoped existing checks, then do only the permitted work. Record real results and missing evidence. After two materially equivalent failed attempts, report the blocker instead of repeating automatically.
5. Review the diff in Orca. Stage only the task's files, commit, and push the topic branch. Open a PR targeting beta and include the Linear issue URL, mode, base/head SHAs and validation. Use the repository's PR template once this workflow change is merged.
6. Put the PR and evidence on the Linear issue and move it to In Review when ready for human review. A draft/WIP PR alone does not mean review-ready. Jon accepts or returns it for fixes. Mark Done only when the issue's acceptance is met; release gates remain separate.
7. After merge and acceptance, fetch the updated base. Archive the Orca workspace only after confirming its work is pushed and no unique uncommitted evidence remains.

## Pickup prompt

Replace JON-xxx before use:

> Work on SectorTrace issue JON-xxx in this issue-linked Orca worktree. Read the current issue, parent, blockers and latest handoff, root AGENTS.md and CLAUDE.md, and docs/CAVEATS.md when relevant. If merged, read agent/README.md and agent/environments.md; otherwise consult the linked Linear dispatch guide and explicitly record any instruction conflict with pending PR #119. Capture the actual base SHA, branch and clean/dirty state. State the permitted mode, owned paths, deliverable, acceptance owner and isolated environment. Start only the work allowed by the packet and available inputs. Use the existing agent settings. Preserve unrelated work and the hand-maintained README. Run appropriate offline checks and report actual outcomes, failures and checks not run. Open a topic-branch PR against beta with the Linear issue link and evidence. Submit for human review; do not merge, deploy, collect live sources, change evidence policy or mark release acceptance complete as a side effect.

## Review handoff

- Issue and permitted mode:
- PR and base/head SHAs:
- What changed and why:
- Checks run and results; checks not run:
- Evidence and fixture IDs:
- Remaining blockers/manual acceptance:
- Exact next action for Jon:

## References

- [SectorTrace Linear project](https://linear.app/sectortrace/project/sectortrace-a1ad5a690310)
- [Existing release control room](https://linear.app/sectortrace/document/sectortrace-v1-release-control-room-4720314a1d0d)
- [Agent dispatch guide](https://linear.app/sectortrace/document/sectortrace-agent-dispatch-guide-and-execution-packet-32682c916aa8)
- [Agent-readiness PR #119](https://github.com/Jonfuk/cglpay.us-SectorTrace/pull/119)
- [Orca Linear workflow](https://www.onorca.dev/docs/review/linear)
- [Orca CLI reference](https://www.onorca.dev/docs/cli/reference)
