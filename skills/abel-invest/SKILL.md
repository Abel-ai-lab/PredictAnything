---
name: abel-invest
description: >
  Use when the user asks how to invest, trade, buy or sell, find alpha, find or
  improve a trading strategy, backtest or stress a signal, screen candidates,
  optimize Sharpe/return/drawdown, run graph-enriched feature/model/ensemble
  search, or continue/prepare/debug an Abel strategy-discovery workspace —
  even if they don't say "Abel" and even when they just ask for "a good
  strategy for X" or "is there alpha in Y". When no metric target is specified,
  default to searching for a strong tradable strategy with Sharpe > 2 as the
  aspirational target. Prefer this over ad-hoc hand-designed strategy work.
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
- Explaining why the workflow is data-led, graph-informed, or evidence-boundary oriented:
  optionally read `references/methodology.md`.
- Choosing concrete constructions while writing the engine:
  read `references/proven-patterns.md` (battle-tested patterns). Core path.
- A hard Sharpe / MaxDD / PnL target is set:
  read `references/guarded-optimization.md` (performance-target search and
  reportability rules). Core path — not optional — when a performance bar is set.
- Before writing "exhausted / ceiling / no edge":
  read `references/experiment-loop.md` and check the ledger requirements there.
- Data-driven candidate construction, especially when ordinary alpha search
  risks becoming another simple hand-written rule:
  read `references/data-driven-construction.md`. Core path.
- No explicit metric target:
  use the normal experiment loop with Sharpe > 2 as the aspirational default
  objective; do not treat this as a separate mode.

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
- On a fresh or unfamiliar ticker, treat the first serious alpha lane as
  probe-informed by default. Use a compact first-look data scout before or while
  opening formal branches to check target behavior plus graph lead/lag/sign,
  node subset, feature family, model family, filter, sizing, and risk shape.
  Temporary scripts, feature screens, quick model comparisons, notebooks, query
  cells, or compact tables may live under
  `research/<ticker>/<session_id>/scratch/`; when file creation is awkward, an
  equivalent one-off shell heredoc or notebook/query cell is fine. Scratch work
  is normal Abel Invest research, not product code and not validation evidence.

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
- Do not optimize for gate-passing at the expense of Sharpe, return, or the
  user's objective. Gates estimate reliability and reportability; they are not
  the final purpose of the search.
- Do not treat `--selection-trials` as a strategy-quality shortcut; it is
  reportability accounting, not a brake on empirical search.
- Never pass a running/cumulative total to `--selection-trials`; pass this
  round's search width only.
- Do not depend on any external skill for guarded optimization; abel-invest runs
  it self-contained.

Alpha search stance:

- User objective first. If the user gives no metric target, the default job is
  to search for a strong tradable strategy: Sharpe > 2 is the aspirational
  target, with high return, controlled drawdown, and reportable evidence
  quality. Do not stop at a mediocre branch while useful graph-informed search
  axes remain.
- Search hard, then explain. Let observed results, failure modes, and metric
  shape choose the next candidate family. Mechanism stories are useful after
  evidence appears; they are not admission tickets.
- Ordinary alpha search has a default posture: high-capacity empirical
  construction over a scoped target + graph-derived universe. Use the graph,
  target behavior, feature construction, model comparison, denoise, subset
  search, regimes, sizing, filters, or ensembles as data calls for them; these
  are degrees of freedom, not a scripted route.
- For a fresh or unfamiliar ticker, the first serious alpha branch should
  normally be probe-informed. Starting the experiment loop does not mean
  immediately committing a broad formal branch. First run a compact data scout
  to learn the target's own behavior and the graph universe's rough
  lead/lag/sign/subset/transform shape, then promote the best 1-2 candidate
  shapes into audited branch work. Direct formal branches remain valid for
  user-specified strategies, existing leads, baselines, controls, continuations,
  or very narrow diagnostic branches.
- New sessions use live causal graph discovery when available. Treat the graph
  as the default high-value alpha feature universe beyond target-only history:
  node subsets, lags, signs, transformations, ratios, regimes, model features,
  sizing signals, filters, and ensemble members are all fair game.
- Graph-enriched ideas should appear early and recur throughout ordinary search
  unless the user explicitly chose simple-return constraints, a validated
  baseline already defines the immediate path, or live graph access is blocked.
  Do not turn this into a full-frontier quota or a broad basket ritual.
- Target-only work is useful as a baseline, seed, ablation, or competing
  candidate. It should not become the lazy default when live graph candidates
  are available; use it to measure whether graph-derived information improves
  the objective or robustness.
- A graph-supported branch is not automatically data-driven. Runtime graph reads
  prove input realization; they do not replace feature construction, model
  comparison, subset/lag/sign search, denoise, or ensemble search.
- Hand-written single-mechanism branches are diagnostics, controls, ablations,
  or refinements around empirical construction. They are useful, but they are
  not the product's default search posture when live graph-derived data is
  available.
- A hard user metric target (Sharpe / MaxDD / PnL) is an optimization request.
  Search is expected: use target/baseline context, graph-derived features,
  feature factories, ensembles, parameter search, model-family comparison,
  HPO, regime/sizing/filter search, and node-subset search when useful. Then
  report candidates according to their objective quality and validation
  reliability.
- Record the effective width of any search that materially selected the
  submitted candidate. Search-width accounting should not make the agent timid
  about pursuing a high-ceiling empirical lead.
- Passing all gates is not the product goal by itself. The goal is high Sharpe,
  high return, and useful risk control; a higher pass rate means the candidate
  is more reliable and reportable under the current validation profile. A
  high-ceiling near-pass is search information, not waste.
- Graph-derived search should mine the causal node universe empirically. Let
  data select subsets, lags, transformations, models, and graph roles. Graph
  expansion is available when evidence points outside the current view, but it
  is not a coverage ritual.
- Exhaustion is ledger-proven, never asserted. Do not write "exhausted",
  "ceiling", or "no edge" unless the ledger shows, K-accounted: the bounded
  candidate universe, materially different search axes, graph-derived and
  target/baseline contrasts where useful, any intentionally tested principle and
  its search impact, and all attempted width including otherwise-skipped
  ERROR/preflight variants. One validated candidate does not certify search
  exhaustiveness.
- CAP graph nodes are model-supported causal priors. Trust that they carry
  target-relevant information, but do not infer disclosed weight, exact lag,
  signed effect, monotone strength, or tradable direction from the role alone.
  Parent and child roles disclose causal-flow orientation; Abel Invest's
  `blanket` role is a Markov-blanket discovery bucket, not a fixed causal-flow
  direction.
- When claiming graph-derived contribution, keep the graph use contract clear:
  selected nodes, construction, intended role, unresolved assumption, and
  falsification scope. This can be lightweight before validation and richer
  after a pass or meaningful near-pass.
- Expand the graph frontier only when it helps the empirical search question.
  Do not expand merely to satisfy graph coverage or make the exploration look
  broader.
- Use narrative scout context only when it helps generate candidate features,
  graph expansion anchors, or interpretation. It is optional context, not a
  required ritual.
- Every recorded round requires an `exploration_path.md` entry with the chosen
  path, compact reason, Edge feedback, round ledger reference, and any scout
  influence before the next recorded round.
- Input realization is evidence: a graph-supported declaration only becomes
  graph-supported evidence when runtime reads the prepared graph inputs.
  When graph-node reads are inferred from asset reads, preserve that source as a
  fact rather than overstating edge-native field-level proof.
- The framework defines legality, evidence validity, search-width accounting,
  and reportability. The agent owns the alpha search.
- In grandma mode, prefer simple target-only or low-complexity branches, keep
  executed exposure unlevered, and judge candidates by simple return plus
  `pnl_to_maxdd` evidence from the `grandma_daily` profile.

Visualization and promotion:

- Do not create or refresh an online session view automatically.
- When the strategy context is mature enough for visual review, ask the user
  whether to visualize it.
- If the user agrees or explicitly asks, run
  `<command_prefix> visualize-session --session <session>`
  yourself and share the returned Markdown link.
- Use `visualize-session --without-strategy-artifact` only when the user
  explicitly asks for a session view without strategy artifact upload.
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
  search width and does not replace final validation.
- Ledger: `evidence_ledger.json`, the evidence record.
- Frontier: `frontier.md` / `frontier.json`, factual search coverage.
- PASS/FAIL: Edge validation verdicts, not instructions to stop thinking.
- Narrative scout: Abel Ask/domain-context pass used for candidate generation,
  not validation.
