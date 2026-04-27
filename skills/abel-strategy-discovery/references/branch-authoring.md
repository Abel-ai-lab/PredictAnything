# Branch Authoring

Use this reference after the workspace is ready and you are moving from
workspace setup into session and branch work.

## Branch Model

- `discovery.json` is only the session candidate snapshot
- `readiness.json` is only the session coverage/advisory report
- `branch.yaml` defines the branch research declaration and runtime intent
- `prepare-branch` resolves inputs, writes the branch contract, and warms edge
  cache before a recorded round
- `debug-branch` is the semantic preflight step
- `run-branch` should consume prepared branch inputs, not invent them at runtime
- session `backtest_start` is the default research target; `branch.yaml.requested_start` may override it explicitly

Discovery gives leads, not answers. Readiness gives coverage clues, not
permission. A branch is a hypothesis family: a coherent thesis, driver set,
mechanism, model family, and complexity class. The evidence ledger is where the
framework decides whether a run counts as candidate evidence, control evidence,
diagnostic evidence, or a blocker.

## Evidence Boundary

`branch.yaml` is a claim, not proof. Fill these fields before expecting a run
to count as protocol-complete candidate evidence:

- `hypothesis`
- `evidence_intent`: `candidate`, `control`, `diagnostic`, or `draft`
- `input_claim`: `graph_supported`, `target_only`, `supplement`, or `mixed`
- `mechanism_family`
- `invalidation_condition`
- `requested_start`
- `selected_inputs` or legacy `selected_drivers`
- `model_family`
- `complexity_class`
- `exploration_role`

Legacy `source_type` and `method_family` may still appear in old workspaces, but
declaration status ignores them. The generated `evidence_ledger.json` derives
the evidence label from explicit declaration fields plus actual edge runtime
facts. The generated `frontier.md` and `frontier.json` report coverage facts;
they are not a strategy advisor.

`agent_context.md` is the compact resume surface for the next agent turn. It
combines frontier facts, recent evidence rows, and agent-authored memory. Use
`add-memory` for your own insights, open questions, and directions; do not wait
for generated strategy guidance.

## Exploration Protocol

Use branch fields to describe the hypothesis family:

- `model_family`: `rule_signal`, `linear_model`, `tree_model`, `learned_model`,
  `ensemble`, `hybrid`, or `unspecified`
- `complexity_class`: `simple_signal`, `interaction`, `regime`, `portfolio`,
  `learned_model`, `hybrid`, or `unspecified`
- `exploration_role`: `candidate`, `control`, `ablation`, `expansion_probe`,
  `refinement`, `diagnostic`, or `unspecified`

Use `run-branch --changed-dimension` to describe what changed in a round:
`drivers`, `mechanism`, `model_family`, `complexity`, `sizing`, `thresholds`,
`filters`, `window`, or `implementation`.

Broad exploration means a new hypothesis family, driver set, mechanism family,
model family, complexity class, or expansion probe. Local refinement means
parameter, sizing, threshold, filter, window, or implementation work inside the
same family.

The default priority is graph/input first, strategy variants second, and
parameters last. Multiple target-only branch families can be useful controls,
but they do not cover graph/input breadth when live graph candidates exist.

At session start, make at least two agent-chosen hypothesis families explicit
before deep local refinement. The protocol exits for a narrow start are factual:
multiple recorded branch families or an agent-authored
`--single-branch-rationale`.

After repeated same-neighborhood validation failures, use
`--continuation-rationale` if continuing the branch still reflects your own
research judgment.

## Driver/Input Breadth And Memory

Driver/input breadth is about candidate input hypotheses. Target-only controls
are useful contrast evidence, but they do not cover graph-supported candidate
driver sets. `mixed` and `supplement` rows can be useful supplemental evidence,
but they do not close graph-first candidate coverage unless the branch declares
`input_claim: graph_supported` and actually reads discovered drivers.

Use `agent_memory.jsonl` as agent resume state. When frontier or warning facts
show enough evidence has accumulated, write your own `add-memory` insight with
`ledger:*` or `frontier:*` references before continuing deep refinement.

## What `prepare-branch` Produces

The branch contract is materialized under `inputs/`:

- `runtime_profile.json`
- `execution_constraints.json`
- `data_manifest.json`
- `context_guide.md`
- `probe_samples.json`
- `dependencies.json`

Those files are the system-owned description of the runtime world. The agent
should inspect them before changing strategy logic.

## What To Do

- state a branch thesis clearly
- prepare the branch inputs
- inspect the prepared inputs
- write `engine.py`
- read semantic preflight before recording a round
- inspect `evidence_ledger.json` and `frontier.md` after a recorded round
- record agent-owned memory when a result changes your research state
- interpret the result as evidence, protocol gap, runtime invalidity, or
  workflow blocker before choosing your own next research move

Alpha owns the bookkeeping so the branch can focus on mechanism, not file
management theater.

## Writing `engine.py`

Write against the branch-default contract:

- implement `compute_decisions(self, ctx)`
- inspect `ctx.target.series("close")` for the tradeable target
- inspect `ctx.feed(name).native_series(...)` for native feed cadence
- inspect `ctx.feed(name).asof_series(...)` when you need target-calendar as-of values
- inspect `ctx.points()` when you need point-level reasoning or debugging
- return `ctx.decisions(next_position)`

Prefer prepared branch inputs over discovery-side inference:

- inspect `inputs/context_guide.md`
- inspect `inputs/data_manifest.json`
- inspect `inputs/probe_samples.json`
- treat `runtime_profile.json` and `execution_constraints.json` as system-owned
  runtime facts, not something the strategy should guess or re-declare

Do not parse relative workspace files manually when the injected context already
contains the prepared branch payload.

Do not reach for raw loaders or ad hoc alignment helpers from inside
`compute_decisions()`. If you cannot express a read through `DecisionContext`,
surface that mismatch and fix the framework or branch inputs instead of writing
around the contract.

## Protocol Checklist

1. State the branch thesis in `branch.yaml`.
2. Run `prepare-branch`.
3. Inspect `inputs/context_guide.md`, `probe_samples.json`, and `data_manifest.json`.
4. Implement or revise `compute_decisions(self, ctx)`.
5. Run `abel-alpha debug-branch --branch ...`.
6. Read the semantic verdict and traces.
7. Run `abel-alpha run-branch --branch ...` when the declaration and debug facts
   are ready enough for the evidence label you want.
8. Read `evidence_ledger.json` and `frontier.md`; do not look for a generated
   next-strategy recommendation.
9. Record only your own grounded follow-up state with `add-memory`, using
   evidence references when the statement is meant as a research conclusion.

## Readiness

Keep readiness advisory:

- use it to understand coverage
- do not treat it as a hard permission system
- do not force all drivers to share the latest common start unless the branch thesis truly requires strict overlap
- do not confuse session start guidance with the branch's explicit requested start

## Research Judgment

- causal discovery is a prior, not an evidence label
- target-only controls are allowed, but declare them as controls or drafts
- explore means new information, a new transmission path, or a genuinely different mechanism
- branch count is not exploration breadth if every branch is the same family and input claim
- weird low-attention parents are not automatically noise; explain them before discarding them
- treat semantic failure as a signal about visibility or timing assumptions
- treat metric failure as direction, not as a prompt to hack metrics
- serial compounding beats pre-declaring a large experiment grid
- stop honestly when recent rounds are no longer improving and no high-quality new direction remains
