# Branch Authoring

Use this reference after the workspace is ready and you are creating or revising
a candidate branch.
Commands below use the workspace `command_prefix` returned by
`workspace context --json` or doctor.

## Branch Model

- `graph_frontier.json` is the session graph-derived candidate universe.
- `readiness.json` is the session coverage/advisory report.
- `branch.yaml` declares candidate metadata and runtime intent.
- `prepare-branch` resolves inputs, writes the branch contract, and warms edge
  cache.
- `debug-branch` is the semantic preflight step.
- `run-branch` consumes prepared inputs and records evidence.

The graph frontier gives high-value leads, not answers. Readiness gives
coverage facts, not a veto. A branch is a candidate strategy expression:
objective, input universe, runtime constraints, and enough detail to make the
search reproducible and auditable.

## Candidate Audit Surface

Do not make every branch carry a full mechanism essay before it can run.
`branch.yaml` should unblock runtime and audit with compact facts. Split
metadata into two layers.

Minimum metadata for ordinary candidate exploration:

- objective or search goal
- `evidence_intent`: `candidate`, `control`, `diagnostic`, or `draft`
- `input_claim`: `graph_supported`, `target_only`, `supplement`, or `mixed`
- selected runtime inputs
- requested/effective window
- search width when the candidate was selected from multiple variants
- validation scope and runtime constraints

Explanation metadata, useful but not always blocking before a first run:

- mechanism family
- graph attribution or graph use contract
- invalidation scope
- narrative scout notes
- why a candidate family is worth further search or later explanation

The evidence ledger derives labels from explicit declaration fields plus actual
edge runtime facts. `frontier.md` and `frontier.json` report facts; they are not
a strategy advisor.

## Evidence Boundary

`branch.yaml` is a claim, not proof. For strong, comparable evidence, keep these
compatibility fields meaningful when possible. The field names are stable API
surface; they do not require the agent to write a pre-evidence theory:

- `hypothesis` (legacy field name for candidate note / search objective)
- `evidence_intent`
- `input_claim`
- `mechanism_family`
- `invalidation_condition`
- `requested_start`
- `selected_inputs`
- `model_family`
- `complexity_class`
- `exploration_role`

Incomplete explanation fields should not make a promising candidate impossible
to test. They can limit how much mechanism or graph attribution the result
supports until the agent writes a clearer post-evidence explanation.

`selected_inputs` is the one authoring field for branch inputs. Prefer
structured graph node entries when graph attribution matters:

```yaml
selected_inputs:
  - node_id: AAPL.price
    role: graph_input
    source: frontier
  - node_id: SPY.volume
    role: supplement
    source: external
    source_reason: market-liquidity contrast outside the current frontier
```

Input realization is recorded separately from declaration:

- declared input claim: what `branch.yaml` says the branch intends
- prepared auxiliary inputs: what `prepare-branch` made available
- actual auxiliary reads: what the engine read at runtime
- declared, prepared, and actual graph node read facts
- graph node read source: edge-native runtime facts or asset-read mapping
- realized input claim: what kind of evidence the round actually supports

If `input_claim=graph_supported` but runtime does not read the prepared graph
inputs, the round is a graph input read gap. It can still be useful strategy,
control, or diagnostic evidence, but the declaration alone does not prove graph
contribution.

## Graph Attribution Contract

CAP graph nodes are model-supported causal priors. Use a graph attribution
contract when a branch needs to claim graph-derived contribution or when a
failed result should be scoped carefully:

```yaml
graph_use_contract:
  nodes:
  construction:
  intended_role:
  unresolved_assumption:
  falsification_scope:
```

- `nodes`: the graph nodes the branch attempts to use.
- `construction`: how the nodes are transformed, combined, gated, or otherwise
  read by the strategy.
- `intended_role`: alpha, filter, sizing, regime, interaction, or another
  agent-defined role.
- `unresolved_assumption`: sign, lag, conditioning, interaction, or another
  assumption.
- `falsification_scope`: the broadest conclusion a failed round can support.

The contract is optional for pure target/baseline candidates and lightweight
graph-enriched experiments where graph attribution is not yet being claimed.

If a branch combines multiple graph nodes as one same-direction, equal-weight,
or same-lag basket, declare that construction explicitly. A failed basket only
invalidates that construction unless other evidence supports a broader graph
conclusion.

## Search Shape

Use branch fields to describe the candidate family:

- `model_family`: `rule_signal`, `linear_model`, `tree_model`, `learned_model`,
  `ensemble`, `hybrid`, or `unspecified`
- `complexity_class`: `simple_signal`, `interaction`, `regime`, `portfolio`,
  `learned_model`, `hybrid`, or `unspecified`
- `exploration_role`: `candidate`, `control`, `ablation`, `expansion_probe`,
  `refinement`, `diagnostic`, or `unspecified`

Use `run-branch --changed-dimension` to describe factual round changes:

```bash
<command_prefix> run-branch --branch ... -d "..." \
  --changed-dimension drivers
```

Parameter, sizing, threshold, filter, window, model, factor, and node-subset
changes are legitimate search dimensions when intentional and K-accounted. Do
not relabel search width as a single isolated idea.

## Exploration Path

`agent_context.md` is the compact factual resume surface. `exploration_path.md`
is the single human-facing exploration log and remains a completeness gate
before another recorded round.

Each recorded round entry should be concise:

- ledger ref
- selected path
- compact reason
- Edge feedback
- key result facts and artifact references
- any search width or scout influence that selected the candidate

After a failed graph-enriched round, scope the conclusion to the actual
construction. Do not conclude that graph nodes are useless unless materially
different graph-derived constructions, target/baseline comparisons, and search
axes have been tested or intentionally ruled out.

When an insight should survive as a strategy conclusion, cite evidence such as
`ledger:<branch_id>:<round_id>`, `frontier.md`, or a raw artifact path.

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

## Candidate Self-Check

Before recording a branch, be able to state the minimum audit facts:

- the objective or metric target
- the input universe and why it is bounded
- whether the candidate is target/baseline, graph-enriched, mixed, or supplement
- any search width used to select the submitted candidate
- whether this is the empirical construction lane, a diagnostic/control, an
  ablation, or a refinement around an empirical lead
- whether semantic preflight confirmed legal reads
- what validation result would make this candidate worth refining or promoting

For graph-attribution claims, also state the selected graph nodes,
construction, intended role, unresolved assumption, and falsification scope.
Keep this compact before validation; expand it after a pass or meaningful
near-pass.

If a branch was chosen because it ranked best in a local metric scan, that is
normal candidate search. Declare the search width with `--selection-trials` and
record the selection influence in `exploration_path.md`.

## Minimal Runtime Path

1. State the audit-relevant candidate metadata in `branch.yaml`.
2. Run `<command_prefix> prepare-branch --branch ...`.
3. Inspect `inputs/context_guide.md`, `inputs/probe_samples.json`, and
   `inputs/data_manifest.json`.
4. Implement or revise `compute_decisions(self, ctx)`.
5. Run `<command_prefix> debug-branch --branch ...`.
6. Read the semantic verdict and traces.
7. Run `<command_prefix> run-branch --branch ...` when runtime facts are ready.
8. Read `evidence_ledger.json`, `frontier.md`, and the Edge result.
9. Keep `exploration_path.md` covered with ledger ref, chosen path, compact
   reason, Edge feedback, and artifact refs.

## Alpha Search Judgment

- causal discovery is a high-value prior, not a trading instruction
- target-only is a baseline, seed, ablation, and competitor; it should not
  become the default when graph candidates are live
- graph-enriched search should appear early and recur when graph discovery is
  available
- ordinary alpha search should keep an empirical construction posture over the
  bounded target + graph-derived universe; simple hand-written mechanisms are
  diagnostics, controls, ablations, or refinements
- branch count is not search breadth if every branch hides the same search axis
- weird low-attention graph nodes are not automatically noise
- narrative scout can inspire features, but it is not evidence truth
- semantic failure is a signal about visibility or timing assumptions
- metric failure is evidence about the candidate expression, not a reason to
  hack metrics
- stop honestly when recent rounds are no longer improving and no high-quality
  new direction remains after the bounded search is ledger-supported
