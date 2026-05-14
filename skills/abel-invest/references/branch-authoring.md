# Branch Authoring

Use this reference after the workspace is ready and you are creating or revising
a research branch.

## Branch Model

- `graph_frontier.json` is the session graph node frontier.
- `readiness.json` is the session coverage/advisory report.
- `branch.yaml` defines the branch research declaration and runtime intent.
- `prepare-branch` resolves inputs, writes the branch contract, and warms edge
  cache.
- `debug-branch` is the semantic preflight step.
- `run-branch` consumes prepared inputs and records evidence.

The graph frontier gives leads, not answers. Readiness gives coverage clues, not
permission. A branch is a hypothesis family: a coherent thesis, graph node input
set, mechanism, model family, and complexity class.

## Evidence Boundary

`branch.yaml` is a claim, not proof. Fill these fields before expecting a run
to count as protocol-complete candidate evidence:

- `hypothesis`
- `evidence_intent`: `candidate`, `control`, `diagnostic`, or `draft`
- `input_claim`: `graph_supported`, `target_only`, `supplement`, or `mixed`
- `mechanism_family`
- `invalidation_condition`
- `requested_start`
- `selected_inputs`
- `model_family`
- `complexity_class`
- `exploration_role`

`selected_inputs` is the one authoring field for branch inputs. Prefer
structured graph node entries:

```yaml
selected_inputs:
  - node_id: AAPL.price
    role: graph_input
    source: frontier
  - node_id: SPY.volume
    role: control
    source: external
    source_reason: market-liquidity contrast outside the current frontier
```

The evidence ledger derives labels from explicit declaration fields plus actual
edge runtime facts. `frontier.md` and `frontier.json` report coverage facts; they
are not a strategy advisor.

Input realization is recorded separately from declaration:

- declared input claim: what `branch.yaml` says the branch intends
- prepared auxiliary inputs: what `prepare-branch` made available
- actual auxiliary reads: what the engine read at runtime
- declared, prepared, and actual graph node read facts
- graph node read source: edge-native runtime facts or asset-read mapping
- realized input claim: what kind of evidence the round actually supports

If `input_claim=graph_supported` but runtime does not read the prepared graph
inputs, the round is a graph input read gap. It can still be useful control or
diagnostic evidence, but the declaration alone does not make it candidate
causal evidence.

## Exploration Shape

Use branch fields to describe the hypothesis family:

- `model_family`: `rule_signal`, `linear_model`, `tree_model`, `learned_model`,
  `ensemble`, `hybrid`, or `unspecified`
- `complexity_class`: `simple_signal`, `interaction`, `regime`, `portfolio`,
  `learned_model`, `hybrid`, or `unspecified`
- `exploration_role`: `candidate`, `control`, `ablation`, `expansion_probe`,
  `refinement`, `diagnostic`, or `unspecified`

Use `run-branch --changed-dimension` to describe factual round changes:

```bash
abel-invest run-branch --branch ... -d "..." \
  --changed-dimension drivers
```

Broad exploration means a new input hypothesis, mechanism family, model family,
complexity class, or expansion probe. Local refinement means parameter, sizing,
threshold, filter, window, or implementation work inside the same family.

The default priority is graph breadth first, strategy variants second, and
parameters last. Graph breadth still needs a frontier question: expand
`graph_frontier.json` when current evidence leaves a causal motif or anchor
question unresolved, not just because a branch failed. Target-only controls are
useful contrast evidence, but they do not cover graph-supported candidate input
breadth when live graph candidates exist.

Graph breadth should not outrun mechanism depth. Before moving to a more
distant frontier, ask whether the current graph neighborhood still has an
unresolved sign, lag, regime, interaction, control, or risk-shaping question. A
deeper mechanism branch is appropriate when the added complexity answers that
question instead of tuning toward a metric target.

CAP graph nodes are causal priors. They do not provide trading sign, lag, or
guaranteed strength; deeper nodes are weaker or more indirect priors unless
recorded evidence or domain context justifies them.

## Journal And Research Reflection

`agent_context.md` is the compact factual resume surface. `research_journal.md`
is the agent-owned research state.

Use the journal for:

- hypotheses and observations
- branch basis before strategy code when the choice could affect evidence
  interpretation
- any performance-like scout or sweep that influenced branch choice
- Abel Ask or narrative scout context, including when it was off-target or weak
- why narrative scout was skipped when the next step was already clear or when
  Abel Ask was unavailable
- failed neighborhoods
- open questions
- reasons to continue, pivot, add contrast evidence, or stop
- cross-branch comparisons
- final research summaries

When an insight should survive as a research conclusion, cite evidence such as
`ledger:<branch_id>:<round_id>`, `frontier.md`, or a raw artifact path.

Every recorded round needs its own agent-written journal entry before the next
recorded round. The entry does not need a fixed template, but it must cite the
round ledger ref and preserve the observation or insight that should guide later
exploration.

When `journal_coverage_complete=false`, use frontier facts and the journal to
close the missing entries. State whether you are continuing the neighborhood,
pivoting graph inputs, changing strategy family, adding contrast evidence, or
stopping. The framework exposes the shape of the search; it should not choose
the route.

## Prepared Inputs

`prepare-branch` materializes the branch contract under `inputs/`:

- `inputs/runtime_profile.json`
- `inputs/execution_constraints.json`
- `inputs/data_manifest.json`
- `inputs/context_guide.md`
- `inputs/probe_samples.json`
- `inputs/dependencies.json`

Inspect these files before changing strategy logic. Prefer prepared branch
inputs over frontier-side inference. `data_manifest.json` and
`dependencies.json` include selected graph node facts alongside the ticker feeds
used by the current runtime.

## Branch Self-Check

Before writing strategy logic, be able to state:

- the graph node, frontier question, recorded evidence, narrative scout, or
  control purpose that motivates the branch
- the mechanism being tested
- whether this is graph-breadth expansion or mechanism-depth work, and why that
  is the right next learning step
- whether an ambiguous deepen/expand/stop decision used or skipped one
  narrative scout pass, and what it changed about the mechanism or frontier
  question if used
- why chosen constants are mechanism defaults or simple priors, not
  backtest-selected values
- what evidence would invalidate the branch

If a branch was chosen because it ranked best in a local metric scan, it is not
a clean standard-discovery candidate. Declare the search width with
`--selection-trials`, journal the scout influence, and return to
graph/mechanism-led branch selection for the next standard round.

## What To Do

1. State the branch thesis in `branch.yaml`.
2. Run `abel-invest prepare-branch --branch ...`.
3. Inspect `inputs/context_guide.md`, `inputs/probe_samples.json`, and
   `inputs/data_manifest.json`.
4. Implement or revise `compute_decisions(self, ctx)`.
5. Run `abel-invest debug-branch --branch ...`.
6. Read the semantic verdict and traces.
7. Run `abel-invest run-branch --branch ...` when declaration and
   debug facts are ready enough for the evidence label you want.
8. Read `evidence_ledger.json` and `frontier.md`.
9. Update `research_journal.md` with grounded follow-up state.

## Research Judgment

- causal discovery is a prior, not an evidence label
- explore means new information, a new transmission path, or a genuinely
  different mechanism
- branch count is not exploration breadth if every branch is the same family and
  input claim
- weird low-attention parents are not automatically noise
- narrative scout can inspire a mechanism, but it is not evidence truth
- semantic failure is a signal about visibility or timing assumptions
- metric failure is evidence about the mechanism, not a prompt to hack metrics
- stop honestly when recent rounds are no longer improving and no high-quality
  new direction remains
