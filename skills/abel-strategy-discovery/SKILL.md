---
name: abel-strategy-discovery
description: >
  Use when the user wants Abel strategy discovery, candidate screening,
  graph-grounded trading research, or continuing/preparing/debugging an Abel
  strategy discovery workspace.
---

# Abel Strategy Discovery

Use this skill for:

- strategy discovery and candidate screening
- continuing an existing Abel strategy discovery workspace
- creating sessions and branches
- preparing, debugging, recording, and reviewing research rounds
- interpreting `evidence_ledger.json`, `frontier.md`, `agent_context.md`, and
  `research_journal.md`

## Activation Checklist

Always start by resolving workspace state before strategy work.

1. Read `references/workspace-bootstrap.md`.
2. Resolve the workspace root:
   - if `alpha.workspace.yaml` is in the current directory, use the current
     directory
   - else if `abel-strategy-discovery-workspace/alpha.workspace.yaml` exists
     under the current directory, use that child workspace
   - else bootstrap a workspace before deep research work
3. Run `abel-strategy-discovery doctor --path <workspace-root>`.
4. If doctor reports `auth_missing`, use `abel-auth`, then rerun doctor.
5. Only start or continue session/branch work after doctor is ready, unless the
   user explicitly asks you to inspect or repair setup.

## Reference Routing

- New workspace, workspace reuse, auth, doctor, or setup repair:
  read `references/workspace-bootstrap.md`.
- New session, normal round loop, or resuming a session:
  read `references/experiment-loop.md`.
- Live graph discovery, graph/input expansion, or graph-first reasoning:
  read `references/discovery-protocol.md`.
- Creating or revising `branch.yaml`, reviewing evidence labels, pivot
  checkpoints, or research journal use:
  read `references/branch-authoring.md`.
- Writing `engine.py`, handling semantic/runtime failures, or checking
  temporal legality:
  read `references/constraints.md`.
- Explaining why the workflow is graph-first or evidence-boundary oriented:
  optionally read `references/methodology.md`.
- Looking for mechanism inspiration after the branch workflow is already
  runnable:
  optionally read `references/proven-patterns.md`.

## Operating Rules

1. Treat this as a workspace-first flow, not a one-shot answer flow.
2. Reuse the default workspace when it already exists.
3. Bootstrap the workspace before deep strategy work when it does not exist yet.
4. Use `abel-strategy-discovery` commands, not old command aliases.
5. Reuse existing Abel auth first. If live access is still missing, use
   `abel-auth`.
6. Treat `branch.yaml` as a research declaration, not evidence truth.
7. Treat `evidence_ledger.json` and `frontier.md` as factual evidence surfaces,
   not generated strategy advice.
8. Treat `agent_context.md` as the compact factual resume surface and
   `research_journal.md` as agent-owned research state.
9. New sessions are graph-first: live causal graph discovery is the opening
   search prior, then strategy variants, then parameters.
10. Do not treat branch count as proof of breadth. Graph/input concentration,
   strategy-variant coverage, and local refinement pressure are separate facts.
11. Do not call parameter, sizing, threshold, filter, or window tweaks broad
    exploration.
12. When evidence accumulates or a pivot checkpoint is due, update
    `research_journal.md` with agent-owned reflection and evidence references
    before continuing deep local refinement.
13. When a branch has meaningful candidate evidence worth inspecting, upload
    the branch evidence bundle to the skill dashboard with
    `abel-strategy-discovery upload-dashboard-bundle --branch <branch>
    --base-url <router-base-url>`. Upload only branch evidence from the current
    workspace surfaces; do not upload promotion bundles, replay snapshots,
    paper-trading summaries, or finished strategy narratives as dashboard
    input.
14. The framework defines evidence validity. The agent owns the strategy
    thinking.
