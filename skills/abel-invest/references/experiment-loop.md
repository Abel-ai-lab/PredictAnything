# Experiment Loop

Use this reference after workspace preflight is complete and doctor is ready.
Commands below use the workspace `command_prefix` returned by
`workspace context --json` or doctor.

Before creating a new session, confirm the workspace context:

```bash
<command_prefix> workspace context --path . --json
```

Use the resolved workspace `research_root`. Do not pass `--root` unless this
is an intentional legacy/offline session outside a workspace; in that case pass
`--allow-outside-workspace` too.

## Start Or Resume

Examples assume the current directory is `<workspace_root>` and session paths are
relative to that root.

Run:

```bash
<command_prefix> init-session --ticker <TICKER> --exp-id <exp-id>
<command_prefix> frontier status --session research/<ticker>/<exp_id>
```

Live graph discovery should run by default when available. Its output is the
default high-value alpha feature universe, not a mandatory first branch and not
a requirement to run the whole depth-1 frontier as one basket. For ordinary
non-grandma alpha search, keep the search posture empirical, high-capacity, and
graph-informed over a scoped target + graph-derived universe, not another
hand-written single mechanism.

When the user gives no metric target, use the default reportable target: high
return, Sharpe > 2, and all required Abel Edge gates passing. This is the
internal stopping target, not a user-facing promise and not a separate mode.

When resuming, read:

- `agent_context.md` for compact factual state
- `frontier.md` for graph nodes, runtime reads, input realization, search
  concentration, metric failures, and path coverage
- `exploration_path.md` for the human-facing path log
- latest `edge-result.json` / `edge-validation.md` for concrete feedback

## First-Look Data Scout

For a fresh or unfamiliar ticker, the first serious recorded alpha candidate
should normally be probe-informed before a broad candidate is run. Starting the
experiment loop means learning the data shape, not immediately recording the
first broad branch.

This is not a request to measure data before data exists. `init-session`
provides graph frontier and readiness facts. Use those facts to choose a
bounded scout universe, then create and `prepare-branch` a narrow scout or
candidate branch so Edge materializes cache plus `inputs/data_manifest.json`,
`inputs/probe_samples.json`, and `inputs/context_guide.md`. Run the first-look
scout from those prepared inputs or the warmed cache before deciding what
deserves `debug-branch` / `run-branch`.

Do not run a flat or no-signal materialization branch just to warm cache or make
the scout official. A prepared branch may be prepare-only; `run-branch` is for
meaningful candidates, controls, diagnostics, or ablations.

Use a compact scored scout to choose, not just describe. The useful output is a
ranked short list of candidate-shaped variants with objective metrics such as
Sharpe, total return, drawdown, and turnover:

- target-only scored baselines: trend, momentum, reversal, volatility regime,
  and drawdown-aware controls
- graph candidate shapes: lead/lag/sign, node subset, transformation, spread,
  horizon, and single-feature threshold/vote variants
- construction choices: feature factories, model-family comparisons, ensembles,
  filters, sizing rules, and risk expressions that can be locally scored before
  formal validation

Diagnostic tables such as IC, correlation, and feature importance are useful raw
material, not the completed first-look scout when graph/model construction
remains available. Do not abandon the graph-derived universe unless graph
subset, lag/sign, transformation, model, or risk-expression alternatives have
been scored or intentionally ruled out.

Store temporary scripts or summaries in `research/<ticker>/<exp_id>/scratch/`
when useful. If the runtime discourages files, use an equivalent one-off shell
heredoc, notebook cell, or query cell. Promote only the best 1-2 shapes into
recorded branch work, and account for any selection width that materially chose
the submitted candidate.

Direct recorded branches remain valid for user-specified strategies, existing
leads, continuations, baselines, controls, or very narrow diagnostic branches.

## Search Loop

Each round should push toward the user's objective.

1. Build a bounded candidate universe from validated baselines, target-only
   features, graph nodes, graph-derived feeds, cross-assets, sector/regime
   context, proven patterns, feature factories, and user constraints.
2. Make empirical construction the main stance. Feature factories, weak-signal
   ensembles, model-family comparison, denoise/compression, graph-node subset
   search, lag/sign/transformation search, regimes, sizing, and filters are
   available degrees of freedom, not a fixed checklist.
3. For a fresh or unfamiliar ticker, begin serious search with a compact
   first-look scout before the first broad recorded run unless the path is
   user-specified, a continuation, a baseline/control, or a very narrow
   diagnostic. When that scout needs market data, materialize it through a
   prepared scout/candidate branch first; the branch can stop at prepare if
   its job is data/cache materialization. Probes are search workbench material,
   not validation evidence.
4. Keep graph-enriched ideas active early and throughout the search when live
   graph candidates exist. Use target-only candidates as baselines, seeds,
   ablations, and competitors, not as the default escape from graph search.
5. Use simple hand-written target or graph rules as diagnostics, controls,
   ablations, or refinements around an empirical lead; do not let them dominate
   the early search while the graph-derived feature universe is unsearched.
6. Declare enough branch metadata for runtime and audit: objective, input
   universe, evaluation window, effective search width, validation scope, and
   any graph-attribution claim you need to make.
7. Run `prepare-branch` to materialize branch inputs before trusting the
   candidate.
8. Run `debug-branch` to check semantic legality before recording evidence.
9. Run `run-branch` only when the selected candidate is ready to be recorded.
   If the candidate was selected from a search, pass `--selection-trials N`,
   where `N` is this round's effective search width only. Inline heredocs,
   notebook cells, and query cells count the same as saved scratch files when
   they materially select the submitted candidate.
10. Re-read `evidence_ledger.json`, `frontier.md`, and the latest Edge result.
11. Let metric shape and failure mode decide the next move. The framework shows
   facts; it does not prescribe the next driver, proxy, threshold, model
   family, or route.
12. Keep `exploration_path.md` covered with ledger ref, chosen path, compact
    reason, Edge feedback, and artifact refs before another recorded round.

Optimization is not a deviation. The failure mode is reporting an unvalidated
raw winner, not searching. Use honest K/search-width accounting and final
validation before claiming success.

## Branch Execution

Create one or more branches for selected candidates:

```bash
<command_prefix> init-branch --session research/<ticker>/<exp_id> --branch-id <candidate-branch>
```

Then prepare, debug, and record the agent-chosen candidate:

```bash
<command_prefix> prepare-branch --branch research/<ticker>/<exp_id>/branches/<candidate-branch>
<command_prefix> debug-branch --branch research/<ticker>/<exp_id>/branches/<candidate-branch>
<command_prefix> run-branch --branch research/<ticker>/<exp_id>/branches/<candidate-branch> -d "candidate search result"
```

If performance scouting happened before the recorded candidate, declare the
effective search width and record what happened in `exploration_path.md`. Treat
the result as search-informed rather than pretending it was one isolated idea.
K records the search cost honestly; it is not a reason to avoid pursuing a
high-ceiling lead.

## Layer Ownership

- session: graph frontier, candidate-universe context, expansion provenance, and readiness
- branch: branch declaration and `compute_decisions(self, ctx)`
- edge cache: market data reuse
- prepare step: branch input resolution and runtime contract materialization
- debug step: semantic preflight
- run step: evaluation, DSR trial-count declaration, and evidence recording

Session `backtest_start` is the default exploration target. When
`branch.yaml.requested_start` is explicit, that branch start should drive
prepare/debug/run for the branch.

`run-branch` writes `validation_context.dsr_trials.count` into the Alpha context
passed to `abel-edge evaluate`. The current round defaults to `1`. If a search
selected one submitted candidate from multiple variants, pass
`--selection-trials N`, where `N` is this round's width only, never a running
campaign total. `guarded-optimization.md` owns the final-K reporting rules.

## Before Ending Exploration

The loop defaults to `Exploring`. Enter `Completed` only after the completion
check passes.

Do not write "exhausted", "ceiling", or "no edge" from a single failed
candidate family, a small round count, or one candidate passing validation.
Exhaustion is a ledger conclusion.

Before making that claim, check that the ledger shows:

1. a bounded candidate universe was actually searched or intentionally ruled out
2. empirical construction was tried when the lane was available, rather than
   only simple hand-written mechanisms
3. graph-derived candidates were searched when live graph discovery was
   available, unless the user explicitly chose simple-return constraints
4. target/baseline performance was compared against graph-enriched performance
   where useful
5. materially different search axes were tried, not only one hand-written rule
6. all attempted width is K-accounted, including preflight or workflow ERROR
   variants that would otherwise be audited but skipped from future DSR

Before any final answer that ends exploration, run a completion check. Stop only
when the user objective is achieved, the default reportable target is achieved,
the user explicitly asked to pause or summarize, or the ledger supports that the
current bounded search is unlikely to reach the target. If none holds, stay in
`Exploring`, keep searching, and choose the next concrete action.

Do not stop by round count, a mediocre candidate, a high-Sharpe near-pass, an
easy-to-validate low-objective branch, `render` / `status` / `check` success,
path coverage completeness, visualization eligibility, or promotion blockage.

`render`, `status`, and `check` are audit actions. They can prepare a progress
checkpoint, but they do not move the session to `Completed`.

## Progress Checkpoint

Use this when the user asks for progress, asks to pause, or you must report
before `Completed`.

Report the current best so far, explain why exploration is not complete in plain
language, and name the next concrete search action. Do not call this completed
exploration and do not proactively ask for visualization from a checkpoint.

## Stop Report

Use this section only after exploration enters `Completed`. When
stopping exploration, report the current best strategy before the final summary.
For the session default, run the read-only command:

```bash
<command_prefix> best-strategy --session research/<ticker>/<exp_id> --json
```

This command only selects and reports; it does not export, upload, or promote
strategy artifacts. Do not run `visualize-session` or
`export-strategy-artifact` merely to compute the best strategy, and do not
manually walk `results.tsv`, `frontier.json`, or branch folders to invent a
different ranking. If the user explicitly named a branch or round, use that
explicit selection.

Explain the selected strategy in ordinary user language with:

- total return: how much the backtest made over the period
- Sharpe: whether the return was earned with reasonable risk-adjusted stability
- max drawdown: the deepest peak-to-trough pain during the run
- backtest period: the dates these numbers cover

Translate validation into confidence and robustness. Do not make "gate PASS" the
user's goal, and do not describe a high-return/high-Sharpe near-pass as a failed
strategy; describe it as a promising lead whose robustness evidence is not yet
enough for a final reportable strategy.

## Evidence Reading

After each render, treat:

- `evidence_ledger.json` as the evidence record
- `frontier.md` / `frontier.json` as factual search-context reports
- `agent_context.md` as the compact factual resume surface
- `exploration_path.md` as the single human-facing exploration log

`path_coverage_complete=false` means at least one recorded round still needs an
`exploration_path.md` entry with the round ledger ref, selected path, compact
reason, Edge feedback, and artifact refs.

Input realization separates declaration from runtime behavior. A branch can
declare `input_claim=graph_supported`, but if the strategy does not read
prepared graph inputs, that round is summarized as a graph input read gap and
should not be used as evidence for graph-derived contribution.

The generated surfaces should show what happened, not tell you which driver,
proxy, threshold, model family, or route to try next.

Abel Ask or narrative context can help form candidate features, graph expansion
anchors, and interpretation. It is scout context, not validation evidence.

## Session Visualization

Do not create an online session view automatically. A session becomes eligible
for visualization after at least one real candidate strategy round has been
recorded; eligibility does not make visualization part of every exploration
round. When exploration enters `Completed`, ask the user whether to
create a session review page if a recorded candidate exists, regardless of
whether the result is strong, weak, PASS, FAIL, or close to promotion. Do not
prompt after `init-session`, prepare-only scouts, cache warming, or diagnostic
tables that have not produced a recorded candidate strategy round. If the user
declines, avoid repeating the prompt unless they ask after later work. If the
user agrees, or if the user explicitly asks to create or publish the session
review page, pass the session folder to the command:

```bash
<command_prefix> visualize-session --session research/<ticker>/<exp_id>
```

The command builds the online view from local session evidence. Session
visualization reviews the whole exploration record, including weak attempts,
failed attempts, near-passes, and useful leads. By default, when the CLI selects
a hostable validation strategy, that visualization also includes strategy
artifact upload/promotion through the strategy-artifact capability. Strategy
artifact upload/promotion remains an independent capability when invoked
directly. If no hostable validation strategy exists, visual review can continue
without an artifact. If a selected strategy emits a hosted-paper contract
request, that session is `action_required` until the contract loop succeeds or a
hard blocker remains. Do not pre-audit Abel Invest implementation internals
before this command produces an actionable request.

Use the entrypoint that matches the user's request. For a read-only stop-report
selection, use `best-strategy --session <session> --json`; it does not export,
upload, or promote artifacts. For session visualization or upload, keep using
`visualize-session --session <session>` so the default strategy artifact
export/upload path stays attached. For local artifact export or validation
probes, use `export-strategy-artifact --session <session>`. For a
user-specified branch/round, use `promote-strategy --branch <branch> --round
<round>`. Do not manually traverse `results.tsv` or branch directories to choose
the best session strategy, and do not run `visualize-session` or
`export-strategy-artifact` merely to compute it.

If a visualization, export, or promotion command emits a hosted paper
`paper-contract-request.json`, read the request first and use its
`reportTemplate`. Open `contractGuide.referencePath` from the active Abel Invest
skill when the request requires stateful continuation, source edits, or deeper
gate diagnosis. Edit source only when `sourceEditPolicy` requires or genuinely
allows it, write `paper-contract-report.json`, and rerun the same command.
Leave contract-blocked sessions as `action_required` unless the user explicitly
asks to skip strategy artifacts. Do not start a separate agent process. The
agent should not hand-assemble the payload or choose a router URL.

Default router base URL: `https://api.abel.ai/router/`.
`abel-auth` is the canonical owner for API key setup. Maintainers should update
the default URL in the skill code if this endpoint changes.

## Alpha Search Discipline

Preserve this shape:

```text
user objective -> bounded alpha universe -> empirical construction/search -> recorded validation -> explanation/reporting
```

Multiple branches on one input set can still be narrow if they do not change a
useful search axis. Parameter, threshold, model, factor, regime, sizing, and
node-subset changes are legitimate search axes when they are intentional and
K-accounted.

Graph-supported input realization is necessary for graph attribution, but it is
not the same thing as data-driven construction. A sequence of simple rules with
graph inputs is still a sequence of simple rules.
