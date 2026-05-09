# Methodology

Use this optional reference when the user asks why the workflow is graph-first,
why evidence labels are strict, or why the framework refuses to recommend the
next strategy route.

## Boundary

The product boundary is:

```text
framework = evidence validity and exploration-shape facts
agent = strategy judgment and research insight
```

`abel-edge` owns runtime legality and validation metrics.
`abel-invest` owns branch declarations, evidence labels, frontier
facts, and the exploration path surface.

## Core Principles

**Causal graph first.**
Use Abel-discovered causal structure as the default search prior because it
reduces blind search and is more likely to survive regime change. Correlation
signals can still be useful, but they enter as supplements or controls unless
the branch declares and validates a stronger claim.

Graph-first means widening the graph frontier when the known node pool is too
narrow. It does not mean repeatedly choosing more tickers from a fixed branch
candidate list.

**Evidence labels are not strategy advice.**
Candidate/control/diagnostic/blocker labels say what kind of research evidence a
run produced. They do not choose the next driver, model, threshold, or mechanism.

**Runtime legality is non-negotiable.**
If a strategy reads information it could not have seen at decision time, the
backtest is invalid. The current authoring contract expresses legal reads
through `DecisionContext` and semantic preflight.

**Multi-dimensional validation beats single-metric selection.**
The validation profile can evolve, but the principle is stable: avoid promoting
strategies from one attractive metric when other evidence says the signal is
fragile, concentrated, or illegal.

**Serial compounding beats static grids.**
Each round should update the agent's understanding. Static parameter grids can
hide whether the search is learning or just overfitting a neighborhood.

**The exploration path is agent-readable and evidence-linked.**
`exploration_path.md` preserves the chosen path, why it was chosen, Edge
feedback, and ledger/artifact references between turns. It is the human-facing
research log, while evidence truth remains in the ledger and raw artifacts.

## Current Workflow Consequence

The branch-default path is:

1. resolve workspace and doctor readiness
2. start or resume a graph-first session
3. expand `graph_frontier.json` when graph breadth is still thin
4. declare branch hypothesis and selected graph inputs
5. prepare branch inputs
6. write `compute_decisions(self, ctx)`
7. run semantic preflight
8. record evidence
9. inspect ledger/frontier facts
10. keep `exploration_path.md` covered before deep local refinement
