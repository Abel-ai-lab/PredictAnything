---
name: abel-strategy-discovery
description: >
  Use when the user wants Abel strategy discovery, candidate screening, or
  workspace-first research.
---

Use this skill for:

- strategy discovery
- candidate screening
- continuing an existing Abel strategy workspace
- preparing or debugging a research branch

Operating rules:

1. Treat this as a workspace-first flow, not a one-shot answer flow.
2. Reuse the default workspace when it already exists.
3. Bootstrap the workspace before deep strategy work when it does not exist yet.
4. Treat runtime preparation and branch-loop handoff as part of this skill's ownership.
5. Reuse existing Abel auth first. If live access is still missing, use `abel-auth`.
6. Treat `branch.yaml` as a research declaration, not evidence truth.
7. Treat `evidence_ledger.json` and `frontier.md` as factual evidence surfaces,
   not generated strategy advice.
8. Treat `agent_context.md` and `agent_memory.jsonl` as agent-owned resume
   state; do not expect the system to generate next strategy directions.
9. Treat a branch as a hypothesis family. Early deepening of one branch should
   either have multiple branch families visible or an agent-authored
   single-branch rationale.
10. Do not call parameter, sizing, threshold, filter, or window tweaks broad
    exploration. Use changed-dimension and continuation-rationale fields to keep
    local refinement accountable.

Read `references/workspace-bootstrap.md` before bootstrapping a new workspace.
Read `references/branch-authoring.md` before creating or revising a branch.
Read the copied workflow references only when the current step needs them.
