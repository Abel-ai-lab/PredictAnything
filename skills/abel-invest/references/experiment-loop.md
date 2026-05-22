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
a requirement to run the whole depth-1 frontier as one basket. Keep the search
posture graph-informed and high-capacity: feature factories, model families,
ensembles, graph subsets, regimes, sizing, and filters are normal search
material, not late exceptions.

When resuming, read:

- `agent_context.md` for compact factual state
- `frontier.md` for graph nodes, runtime reads, input realization, search
  concentration, metric failures, and path coverage
- `exploration_path.md` for the human-facing path log
- latest `edge-result.json` / `edge-validation.md` for concrete feedback

## Default Objective

When the user does not specify a metric target, use Sharpe > 2 as the
aspirational target for a strong tradable strategy while controlling drawdown
and preserving reportable evidence quality. Treat explicit user targets as
overrides or additional constraints, not as permission that was missing before.

## Default Search Funnel

Use this shape for ordinary Abel Invest work:

```text
resolve workspace and doctor
-> start or resume session; run live graph discovery when available
-> build target + live graph candidate universe with high-capacity construction options
-> scout one sharp question: sign, horizon, node subset, feature family,
   model family, regime, sizing, filters, or candidate shape
-> promote the strongest discovered candidate shape faithfully, including
   feature factories, learned models, dense ensembles, or hybrids
-> prepare-branch
-> debug-branch
-> run-branch with honest current-round selection width
-> read Edge/ledger/frontier facts
-> iterate or report from evidence
```

Wide universe. Narrow question. High-capacity promotion. Harsh reporting.

- Scratch scripts, notebooks, local probes, quick feature scans, model-family
  comparisons, dense ensemble screens, and diagnostic sweeps are allowed and
  expected during exploration.
- Use `research/<ticker>/<exp_id>/scratch/` as the session-local disposable
  workbench. It can hold one-off scripts, notebooks, query snippets, compact
  probe outputs, and scout notes. If the runtime makes files awkward, an
  equivalent one-off shell heredoc, notebook cell, or query cell is acceptable.
- Scratch/probe outputs are not validation evidence. Their job is to answer a
  narrow scout question and summarize what candidate shape is worth promoting.
- If a probe influences which formal candidate is submitted, record the
  selection influence in `exploration_path.md` and account for effective width
  with `--selection-trials N` or final-K analysis.
- Effective width is the number of materially compared variants used to select
  the submitted candidate for this round. It is not automatically the raw number
  of graph nodes or generated features.
- Do not submit an unscouted whole-frontier or whole-feature basket as formal
  evidence when a narrow scout question could first identify sign, horizon,
  subset, feature-family, model-family, or risk-shape facts.
- A formal candidate can be a learned model, ensemble, feature-factory output,
  graph-node subset model, hybrid strategy, or compact rule. Promote the
  discovered form faithfully: do not turn an ML, feature-factory, ensemble, or
  hybrid lead into a simple proxy just to make the branch feel easier to
  explain. Formal promotion means reproducible, temporally legal, selected, and
  honestly K-accounted; it does not mean low-capacity.

## Search Loop

Each round should push toward the user's objective.

1. Build a wide but scoped candidate universe from validated baselines,
   target-only features, graph nodes, graph-derived feeds, cross-assets,
   sector/regime context, proven patterns, feature factories, and user
   constraints.
2. Make high-capacity empirical construction the main stance. Feature
   factories, weak-signal ensembles, model-family comparison,
   denoise/compression, graph-node subset search, lag/sign/transformation
   search, regimes, sizing, and filters are available degrees of freedom, not a
   fixed checklist.
3. Keep graph-enriched ideas active early and throughout the search when live
   graph candidates exist. Use target-only candidates as baselines, seeds,
   ablations, and competitors, not as the default escape from graph search.
4. Use simple hand-written target or graph rules as diagnostics, controls,
   ablations, or refinements around an empirical lead; do not let them dominate
   the early search while the graph-derived feature universe is unsearched.
5. Declare enough branch metadata for runtime and audit: objective, input
   universe, evaluation window, effective search width, validation scope, and
   any graph-attribution claim you need to make.
6. Run `prepare-branch` to materialize branch inputs before trusting the
   candidate.
7. Run `debug-branch` to check semantic legality before recording evidence.
8. Run `run-branch` only when the selected candidate is ready to be recorded.
   If the candidate was selected from a search, pass `--selection-trials N`,
   where `N` is this round's effective search width only.
9. Re-read `evidence_ledger.json`, `frontier.md`, and the latest Edge result.
10. Let metric shape and failure mode decide the next move. The framework shows
   facts; it does not prescribe the next driver, proxy, threshold, model
   family, or route.
11. Keep `exploration_path.md` covered with ledger ref, chosen path, compact
    reason, Edge feedback, and artifact refs before another recorded round.

Search is not a deviation. The failure mode is reporting an unvalidated raw
winner, not searching. Use honest K/search-width accounting and final validation
before claiming success.

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
Do not count raw feature count as K unless those features were materially
screened as competing variants for the submitted candidate. Keep scratch work
under `research/<ticker>/<exp_id>/scratch/` or an equivalent disposable surface;
write durable branch code only after the scout identifies what to promote, and
preserve the discovered high-capacity form when it wins.

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

## Before Exhaustion Or No-Edge Claims

Do not write "exhausted", "ceiling", or "no edge" from a single failed
candidate family, a small round count, or a green per-candidate gauntlet.
Exhaustion is a ledger conclusion.

Before making that claim, check that the ledger shows:

1. a wide but scoped candidate universe was actually searched or intentionally ruled out
2. empirical construction was tried when the lane was available, rather than
   only simple hand-written mechanisms
3. graph-derived candidates were searched when live graph discovery was
   available, unless user constraints explicitly narrowed the allowed inputs
4. target/baseline performance was compared against graph-enriched performance
   where useful
5. materially different search axes were tried, not only one hand-written rule
6. all attempted width is K-accounted, including preflight or workflow ERROR
   variants that would otherwise be audited but skipped from future DSR

Stop conditions are a gauntlet-PASS candidate at the target or ledger-supported
exhaustion. Do not stop by round count.

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

Do not create an online session view automatically. When the strategy context
is mature enough to be useful to review visually, ask the user whether to
visualize the session. This can be after a strong candidate PASS, after several
informative candidate rounds, before promotion, or whenever the agent would
naturally summarize that the strategy is worth a visual review. If the user
agrees, or if the user explicitly asks to visualize the session, pass the
session folder to the command:

```bash
<command_prefix> visualize-session --session research/<ticker>/<exp_id>
```

The command builds the online view from local session evidence and uploads the
automatically selected best `PASS` strategy artifact when one is available. Use
`visualize-session --without-strategy-artifact` only when the user explicitly
asks for a session view without strategy artifact upload. If the command reports
`needs_agent_refactor`, read the emitted `refactor-request.json` and handle it
in the current skill loop. If `kind` is `state_intent_self_check`, inspect the
selected branch source and nearby model/checkpoint/cache files, then write
`state_intent.json`: either classify every durable state file required for
paper startup, or explicitly write an empty `entries` list with a `selfCheck`
summary explaining why the detected files are not durable paper state. If
`kind` is `agent_assisted`, edit only the promoted copy named there, write
`refactor-report.json`, and rerun the same command. Do not start a separate
agent process. The agent should not hand-assemble the payload or choose a
router URL.

Default router base URL: `https://api.abel.ai/router/`.
`abel-auth` is the canonical owner for API key setup. Maintainers should update
the default URL in the skill code if this endpoint changes.

## Alpha Search Discipline

Preserve this shape:

```text
user objective -> wide graph-capable alpha universe -> narrow scout question -> high-capacity formal candidate -> recorded validation -> explanation/reporting
```

Multiple branches on one input set can still be narrow if they do not change a
useful search axis. Parameter, threshold, model, factor, regime, sizing, and
node-subset changes are legitimate search axes when they are intentional and
K-accounted.

Graph-supported input realization is necessary for graph attribution, but it is
not the same thing as data-driven construction. A sequence of simple rules with
graph inputs is still a sequence of simple rules.
