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
  `exploration_path.md`

## Activation Checklist

Always start by resolving workspace state before strategy work.

1. Read `references/workspace-bootstrap.md`.
2. Resolve the workspace context:
   - if `alpha.workspace.yaml` is in the current directory, use the current
     directory
   - else if `abel-invest-workspace/alpha.workspace.yaml` exists
     under the current directory, use that child workspace
   - else bootstrap a workspace before deep research work
3. Prefer `abel-invest workspace context --path . --json` once a CLI is
   available. If `abel-invest` is not on PATH and an existing workspace has a
   venv, use `<workspace-root>/.venv/bin/abel-invest workspace context --path . --json`
   for this first context check. Use the returned `workspace_root`,
   `research_root`, and `command_prefix` instead of guessing from directory
   names or assuming a global PATH.
4. Run `<command_prefix> doctor --path <workspace-root>`.
5. If doctor reports `runtime_stale`, `env_missing`, `edge_missing`, or
   `edge_contract_missing`, run the exact command from `next_step`, then rerun
   doctor. `doctor` diagnoses runtime drift; `env` commands repair it.
6. If doctor reports `auth_missing`, use `abel-auth`, then rerun doctor.
7. Only start or continue session/branch work after doctor is ready, unless the
   user explicitly asks you to inspect or repair setup.

## Reference Routing

- New workspace, workspace reuse, auth, doctor, or setup repair:
  read `references/workspace-bootstrap.md`.
- New session, normal round loop, or resuming a session:
  read `references/experiment-loop.md`.
- Grandma mode, simple-return screening, or conservative no-leverage exploration:
  read `references/grandma-mode.md`.
- Live graph discovery, graph frontier expansion, or graph-first reasoning:
  read `references/discovery-protocol.md`.
- Creating or revising `branch.yaml`, reviewing evidence labels,
  path coverage, input realization, or exploration path use:
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

Always:

- Work workspace-first. Resolve `workspace_root`, `research_root`, and doctor
  status before session or branch work.
- Reuse the default workspace when it already exists; reuse any resolved
  existing workspace before bootstrapping another one.
- Bootstrap the workspace before deep strategy work when no workspace exists.
- Use Abel Invest commands through the workspace `command_prefix` when
  available, not old aliases.
- On a fresh install where `abel-invest` is not installed, run
  `python3 <abel-invest-skill-root>/scripts/bootstrap_workspace.py --path abel-invest-workspace`.
  Do not import `abel_invest` with the system interpreter for first-run
  bootstrap.
- If a skill update changed the workspace runtime contract, `doctor` reports
  `runtime_stale`. Run the suggested `next_step` command and rerun doctor before
  research work. Do not refresh on every entry when doctor is already ready.
- Reuse existing Abel auth first. If live access is missing, use `abel-auth` and
  rerun `doctor`.
- Report to the user with the current workspace/session/branch path, doctor
  status, blockers, what evidence exists, and the next action you will take.
- Treat `agent_context.md` as the compact factual resume surface,
  `exploration_path.md` as the human-facing chosen-path and Edge-feedback log.

Never:

- Do not create sessions before workspace context resolves.
- Do not use `--root` unless intentionally creating a legacy/offline session;
  then pass `--allow-outside-workspace`.
- Do not treat `branch.yaml` as evidence. It is a research declaration.
- Do not treat `evidence_ledger.json`, `frontier.md`, or `agent_context.md` as
  generated strategy advice. They are factual surfaces.
- Do not call parameter, sizing, threshold, filter, or window tweaks broad
  exploration.
- Do not use local sweeps to choose a standard-discovery branch unless the user
  explicitly requests optimization.
- Do not treat `--selection-trials` as permission to brute-force candidates; it
  is DSR audit and penalty accounting.
- Do not treat user metric targets as optimization permission; report evidence
  honestly or ask for explicit optimization.

Research discipline:

- New sessions are graph-first: live causal graph discovery initializes
  `graph_frontier.json`.
- Standard discovery chooses branches from graph context, mechanism reasoning,
  recorded evidence, or explicit control/ablation purpose before metric search.
  Do not run local parameter, threshold, window, filter, sizing, driver, or asset
  sweeps to choose a branch candidate unless the user explicitly requests
  optimization.
- CAP graph nodes are model-supported causal priors. Trust that they carry
  target-relevant information, but do not infer disclosed weight, exact lag,
  signed effect, monotone strength, or tradable direction from the role alone.
  Parent and child roles disclose causal-flow orientation; Abel Invest's
  `blanket` role is a Markov-blanket discovery bucket, not a fixed causal-flow
  direction.
- When using CAP graph nodes in a branch, state the graph use contract before
  treating the round as graph-supported candidate evidence: selected nodes,
  construction, intended role, unresolved assumption, and falsification scope.
  This contract describes the agent's current use of the nodes; it is not a
  fixed role implied by the graph.
- If a branch combines multiple graph nodes as one same-direction, equal-weight,
  or same-lag basket, declare that construction explicitly. A failed basket only
  invalidates that construction unless other evidence supports a broader graph
  conclusion.
- Expand graph breadth only when a frontier question remains after reading
  current evidence.
- Before expanding to a more distant frontier, check whether the current graph
  neighborhood still has an unresolved sign, lag, regime, interaction, control,
  or risk-shaping question. If yes, prefer mechanism-deepening.
- Branch count is not proof of breadth. Graph-node concentration,
  strategy-variant coverage, and local refinement are separate facts.
- Abel Ask or narrative context can scout mechanism ideas, supplemental drivers,
  or graph expansion questions. It is not validation evidence.
- Use one narrative scout pass when the next decision is ambiguous between
  mechanism-deepening, graph expansion, or stopping. Record weak, off-target,
  unavailable, or skipped scout context plainly in `exploration_path.md`.
- Every recorded round requires an `exploration_path.md` entry with the chosen
  path, why it was chosen, Edge feedback, round ledger reference, and any scout
  influence before the next recorded round.
- Input realization is evidence: a graph-supported declaration only becomes
  graph-supported evidence when runtime reads the prepared graph inputs.
  When graph-node reads are inferred from asset reads, preserve that source as a
  fact rather than overstating edge-native field-level proof.
- The framework defines evidence validity. The agent owns the strategy thinking.
- In grandma mode, prefer simple target-only or low-complexity branches, keep
  executed exposure unlevered, and judge candidates by simple return plus
  `pnl_to_maxdd` evidence from the `grandma_daily` profile.

Visualization and promotion:

- Do not create or refresh an online session view automatically.
- When the strategy context is mature enough for visual review, ask the user
  whether to visualize it.
- If the user agrees or explicitly asks, run
  `<command_prefix> visualize-session --session <session> --with-strategy-artifact`
  yourself and share the returned Markdown link.
- Use narrative-only `visualize-session` only when the user explicitly asks for a
  session view without strategy artifact upload.
- If visualization reports `needs_agent_refactor`, handle the emitted
  `refactor-request.json` in this same skill loop. For `state_intent_self_check`,
  write `state_intent.json`. For `agent_assisted`, edit only the promoted copy,
  write `refactor-report.json`, and rerun the same command.
- The default Abel router base URL is `https://api.abel.ai/router/`. `abel-auth`
  owns API key setup; do not ask for a router URL unless the user is testing a
  non-default router.

Glossary:

- CAP: Abel causal graph surface used as a prior.
- Edge: Abel runtime that prepares data and validates strategies.
- DSR: deflated Sharpe ratio accounting; `--selection-trials` records effective
  search width and is not permission to brute-force candidates.
- Ledger: `evidence_ledger.json`, the evidence record.
- Frontier: `frontier.md` / `frontier.json`, factual exploration coverage.
- PASS/FAIL: Edge validation verdicts, not instructions to stop thinking.
- Narrative scout: Abel Ask/domain-context pass used for hypothesis generation,
  not validation.
