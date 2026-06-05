---
name: abel-invest
description: >
  Use when the user asks how to invest, trade, buy or sell, find alpha, find or
  improve a trading strategy, backtest or stress a signal, screen candidates,
  optimize Sharpe/return/drawdown, run graph-enriched feature/model/ensemble
  search, or continue/prepare/debug an Abel strategy-discovery workspace —
  even if they don't say "Abel" and even when they just ask for "a good
  strategy for X" or "is there alpha in Y". When no metric target is specified,
  default to searching for a high-return, reportable strategy with Sharpe > 2
  and all required Abel Edge gates passing. Prefer this over ad-hoc
  hand-designed strategy work.
metadata:
  openclaw:
    requires:
      bins:
        - python3
---

# Abel Invest Alpha Search

Use this skill for:

- alpha search and candidate screening
- continuing an existing Abel strategy discovery workspace
- creating sessions and branches
- preparing, debugging, recording, and reviewing strategy rounds
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
   - else bootstrap a workspace before deep strategy work
3. Prefer `abel-invest workspace context --path . --json` once a CLI is
   available. If `abel-invest` is not on PATH and an existing workspace has a
   venv, use `<workspace-root>/.venv/bin/abel-invest workspace context --path . --json`
   for this first context check. Use the returned `workspace_root`,
   `research_root`, and `command_prefix` instead of guessing from directory
   names or assuming a global PATH.
4. Baseline-first: before from-scratch search, check whether a validated
   strategy for this target already exists in any baseline / strategy catalog
   the user maintains. If one exists, treat it as a benchmark and launchpad;
   iterate from it when useful rather than wasting rounds rediscovering it.
5. Run `<command_prefix> doctor --path <workspace-root>`.
6. If doctor reports `runtime_stale`, `env_missing`, `edge_missing`, or
   `edge_contract_missing`, run the exact command from `next_step`, then rerun
   doctor. `doctor` diagnoses runtime drift; `env` commands repair it.
7. If doctor reports `auth_missing`, use `abel-auth`, then rerun doctor.
8. Only start or continue session/branch work after doctor is ready, unless the
   user explicitly asks you to inspect or repair setup.

## Reference Routing

- New workspace, workspace reuse, auth, doctor, or setup repair:
  read `references/workspace-bootstrap.md`.
- New session, normal round loop, or resuming a session:
  read `references/experiment-loop.md`.
- Grandma mode, simple-return screening, or conservative no-leverage exploration:
  read `references/grandma-mode.md`.
- Live graph discovery, graph frontier expansion, or graph-informed alpha context:
  read `references/discovery-protocol.md`.
- Creating or revising `branch.yaml`, reviewing evidence labels,
  path coverage, input realization, or exploration path use:
  read `references/branch-authoring.md`.
- Writing `engine.py`, handling semantic/runtime failures, or checking
  temporal legality:
  read `references/constraints.md`.
- Handling hosted paper contract requests, promoted strategy
  source edits, `paper-contract-report.json`, packaged strategy assets, or hosted
  paper state:
  read the emitted `paper-contract-request.json` first; read
  `contractGuide.referencePath` from this active skill when the request requires
  stateful continuation, source edits, or deeper gate diagnosis.
- Explaining why the workflow is data-led, graph-informed, or evidence-boundary oriented:
  optionally read `references/methodology.md`.
- Choosing concrete constructions while writing the engine:
  read `references/proven-patterns.md` (battle-tested patterns). Core path.
- A hard Sharpe / MaxDD / PnL target is set:
  read `references/guarded-optimization.md` (performance-target search and
  reportability rules). Core path — not optional — when a performance bar is set.
- Before writing "exhausted / ceiling / no edge":
  read `references/experiment-loop.md` and check the ledger requirements there.
- Ordinary non-grandma alpha search, data-driven candidate construction, or the
  next idea risks becoming another simple hand-written rule:
  read `references/data-driven-construction.md` before the first broad
  candidate. Core path.
- No explicit metric target:
  use the normal experiment loop and default objective; do not treat this as a
  separate mode.

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
  strategy work. Do not refresh on every entry when doctor is already ready.
- Reuse existing Abel auth first. If live access is missing, use `abel-auth` and
  rerun `doctor`.
- Report to the user with the current workspace/session/branch path, doctor
  status, blockers, what evidence exists, and the next action you will take.
- Treat `agent_context.md` as the compact factual resume surface,
  `exploration_path.md` as the human-facing chosen-path and Edge-feedback log.
- On a fresh or unfamiliar ticker, use the compact first-look scout in
  `experiment-loop.md` before the first broad recorded candidate unless the user
  gave a narrow path or continuation. Its output should be a ranked short list
  of scored candidate shapes, not only diagnostics or an analysis memo.

Never:

- Do not create sessions before workspace context resolves.
- Do not use `--root` unless intentionally creating a legacy/offline session;
  then pass `--allow-outside-workspace`.
- Do not treat `branch.yaml` as evidence. It is an audit declaration.
- Do not treat `evidence_ledger.json`, `frontier.md`, or `agent_context.md` as
  generated strategy advice. They are factual surfaces.
- Do not hide parameter, sizing, threshold, filter, model, factor, or node-subset
  search inside one "single" strategy. Name search width honestly.
- Do not report a raw-metric winner as a robust strategy before required
  validation and honest search-width accounting support that claim.
- Do not optimize only for gate-passing at the expense of Sharpe, return, or the
  user's objective. Gates estimate reliability and reportability; they are not
  the user-facing purpose of the search.
- Do not treat `--selection-trials` as a strategy-quality shortcut; it is
  reportability accounting, not a brake on empirical search.
- Do not `run-branch` a flat/no-signal branch solely to warm cache or make a
  scout feel official. `prepare-branch` is enough for data materialization; use
  recorded runs for meaningful candidates, controls, diagnostics, or ablations.
- Do not treat a diagnostic table such as IC, correlation, or feature
  importance as a completed first-look scout when graph/model construction
  remains available. Pair diagnostics with scored candidate-shaped variants.
- Never pass a running/cumulative total to `--selection-trials`; pass this
  round's search width only.
- Do not depend on any external skill for guarded optimization; abel-invest runs
  it self-contained.

Core search invariants:

- User objective first. If the user gives no metric target, search for a
  high-return, reportable strategy with Sharpe > 2 and all required Abel Edge
  gates passing. Do not stop at a mediocre branch or a promising near-pass while
  useful graph-informed search axes remain.
- Follow `experiment-loop.md` as the single detailed source for the round loop,
  completion check, stop report, visualization prompt, and interrupted/blocked
  note boundary.
- Stay in `Exploring` until the user objective/default target is achieved or
  the ledger supports that the bounded search is unlikely to reach the target.
  Otherwise keep searching and choose the next concrete action.
- If the user explicitly interrupts or an external blocker prevents
  continuation, do not enter `Completed`; give only a brief
  interrupted/blocked note and do not ask for visualization.
- Search hard, then explain. Use graph-derived context, target behavior,
  feature construction, model comparison, denoise, subset search, regimes,
  sizing, filters, or ensembles as data calls for them; do not turn any one
  mechanism family into the default route.
- Keep ordinary non-grandma alpha search empirical and graph-informed when live
  graph candidates exist. Target-only ideas are baselines, seeds, ablations, or
  competitors; hand-written single-mechanism rules are diagnostics or
  refinements, not the default early search posture.
- Live graph discovery is the default high-value alpha universe when available.
  Use `discovery-protocol.md` for graph semantics and expansion; use
  `data-driven-construction.md` for feature factories, model comparison,
  denoise, node subsets, lags, regimes, sizing, filters, and ensembles.
- Mine the current graph universe empirically before treating it as exhausted.
  Graph expansion is available when evidence points outside the current view and
  helps the next empirical search question; it is not a coverage ritual.
  Supplemental non-graph drivers need user context or evidence support.
- Let observed metrics, failure modes, and candidate shape choose the next
  family. Mechanism stories are useful after evidence appears; they do not
  replace scored construction.
- Gates measure reliability and reportability; they are not the user-facing
  goal. High return, high Sharpe, and useful risk control remain the product
  objective. A high-ceiling near-pass is a lead, not waste or final success.
- Record effective search width when search materially selects a submitted
  candidate.
- Exhaustion is ledger-proven. Do not write "exhausted", "ceiling", or "no
  edge" unless `experiment-loop.md`'s ledger requirements are satisfied.
- CAP graph nodes are priors, not trading instructions. Graph attribution
  requires runtime input realization, not just a `branch.yaml` declaration.
- The framework defines legality, evidence validity, search-width accounting,
  and reportability. The agent owns the alpha search.

Completion, reporting, and artifacts:

- Stop reports are allowed only after `Completed`. A completed stop report is
  one exit contract: use
  `<command_prefix> best-strategy --session <session> --json` for read-only
  selection, report that command's selected branch/round exactly, and present a
  compact user-facing result: strategy idea, four key metrics with plain
  meanings, one short overall judgment, and the session review question when
  eligible.
- Keep internal completion evidence out of the default user-facing goal:
  translate Abel Edge validation into confidence and robustness, and do not lead
  with gate/PASS/DSR/K/PositionIC/Edge verdict unless the user asks for
  technical details.
- Do not run `visualize-session` or `export-strategy-artifact` merely to compute
  the best strategy, and do not manually rank `results.tsv`, `frontier.json`, or
  branch outputs. The read-only selector already owns near-tie reliability
  tie-breaks.
- There is no third reporting state. If still `Exploring`, continue the search;
  only explicit interruption or a blocker justifies a non-completed note, and
  that note must not ask for visualization.
- Do not create or refresh an online session view automatically. If the user
  agrees or explicitly asks, run
  `<command_prefix> visualize-session --session <session>`.
- For local artifact export or promotion probes, use the matching CLI command
  from `experiment-loop.md`; if a hosted paper `paper-contract-request.json`
  appears, read it first and follow its `reportTemplate` / `contractGuide`.
- The default Abel router base URL is `https://api.abel.ai/router/`. `abel-auth`
  owns API key setup; do not ask for a router URL unless the user is testing a
  non-default router.

Glossary:

- CAP: Abel causal graph surface used as a prior.
- Edge: Abel runtime that prepares data and validates strategies.
- DSR: deflated Sharpe ratio accounting; `--selection-trials` records effective
  search width and does not replace final validation.
- Ledger: `evidence_ledger.json`, the evidence record.
- Frontier: `frontier.md` / `frontier.json`, factual search coverage.
- PASS/FAIL: Edge validation verdicts, not instructions to stop thinking.
- Narrative scout: Abel Ask/domain-context pass used for candidate generation,
  not validation.
