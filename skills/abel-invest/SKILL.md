---
name: abel-invest
description: >
  Use when the user wants Abel strategy discovery, candidate screening,
  graph-grounded trading research, or continuing/preparing/debugging an Abel
  strategy discovery workspace.
metadata:
  openclaw:
    requires:
      bins:
        - python3
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
   - else if `abel-invest-workspace/alpha.workspace.yaml` exists
     under the current directory, use that child workspace
   - else bootstrap a workspace before deep research work
3. Run `abel-invest doctor --path <workspace-root>`.
4. If doctor reports `auth_missing`, use `abel-auth`, then rerun doctor.
5. Only start or continue session/branch work after doctor is ready, unless the
   user explicitly asks you to inspect or repair setup.

## Reference Routing

- New workspace, workspace reuse, auth, doctor, or setup repair:
  read `references/workspace-bootstrap.md`.
- New session, normal round loop, or resuming a session:
  read `references/experiment-loop.md`.
- Live graph discovery, graph frontier expansion, or graph-first reasoning:
  read `references/discovery-protocol.md`.
- Creating or revising `branch.yaml`, reviewing evidence labels,
  journal coverage, input realization, or research journal use:
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
4. Use `abel-invest` commands, not old command aliases.
5. Reuse existing Abel auth first. If live access is still missing, use
   `abel-auth`.
6. Treat `branch.yaml` as a research declaration, not evidence truth.
7. Treat `evidence_ledger.json` and `frontier.md` as factual evidence surfaces,
   not generated strategy advice.
8. Treat `agent_context.md` as the compact factual resume surface and
   `research_journal.md` as agent-owned research state.
9. New sessions are graph-first: live causal graph discovery initializes
   `graph_frontier.json`; widen graph breadth with `frontier expand` before
   spending many rounds on strategy variants or parameters.
10. Do not treat branch count as proof of breadth. Graph-node concentration,
   strategy-variant coverage, and local refinement pressure are separate facts.
11. Do not call parameter, sizing, threshold, filter, or window tweaks broad
    exploration.
12. Every recorded round requires an agent-written `research_journal.md` entry
    with the round ledger reference before the next recorded round.
13. Treat input realization as an evidence fact: a graph-supported declaration
    only becomes graph-supported evidence when runtime reads the prepared graph
    inputs. When graph-node reads are inferred from asset reads, preserve that
    source as a fact rather than overstating edge-native field-level proof.
14. Do not create an online session view automatically. If a candidate round
    passes, ask the user whether to create an online visualization of this
    session. If the user agrees, or if the user explicitly asks to visualize
    the session, run
    `abel-invest visualize-session --session <session>`. Pass the session folder; the command builds
    the online view from local session evidence.
15. The default Abel router base URL is `https://api.abel.ai/router/`.
    `abel-auth` owns API key setup. Do not ask the user or agent to provide a
    router URL unless they are intentionally testing another router.
16. The framework defines evidence validity. The agent owns the strategy
    thinking.
