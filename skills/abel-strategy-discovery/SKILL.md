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
6. When a branch has meaningful recorded evidence, upload the branch evidence
   bundle to the skill dashboard with `abel-strategy-discovery
   upload-dashboard-bundle --branch <branch> --base-url <router-base-url>`.
   Upload only branch evidence from the workspace memory; do not upload
   promotion bundles, replay snapshots, paper-trading summaries, or finished
   strategy narratives as dashboard input.

Read `references/workspace-bootstrap.md` before bootstrapping a new workspace.
Read the copied workflow references only when the current step needs them.
