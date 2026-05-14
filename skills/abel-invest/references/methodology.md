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

CAP graph nodes are model-supported causal priors, not trading instructions.
Trust that they carry target-relevant information, but do not infer disclosed
weight, exact lag, signed effect, or tradable direction from the role alone.
Parent and child roles disclose causal-flow orientation; Abel Invest's
`blanket` role is a Markov-blanket discovery bucket, not a fixed causal-flow
direction.

Graph-first means using the graph to form input and mechanism hypotheses. Expand
the graph when a frontier question remains after reading current evidence. Do
not expand just because a few branches failed or because a local metric scan
found one attractive node.

Graph breadth should not outrun mechanism depth. Before widening to a more
distant frontier, ask whether the current graph neighborhood still has an
unresolved sign, lag, regime, interaction, control, or risk-shaping question. A
mechanism-deepening branch is preferable when it can answer one of those
questions without becoming parameter search.

**Mechanism-led discovery beats metric-led search.**
Standard discovery chooses a branch from graph context, mechanism reasoning,
recorded evidence, or a control/ablation purpose before metric search. Local
parameter, threshold, window, filter, sizing, driver, or asset sweeps are
optimization behavior unless the user explicitly requests them.

`--selection-trials` audits accidental or explicitly requested search width. It
does not make brute-force candidate selection part of standard discovery.

**Narrative scout is context, not evidence.**
Abel Ask and narrative context can generate mechanism hypotheses, supplement
driver ideas, and graph expansion questions. Treat them as domain-context scout
work: stronger than free association, weaker than CAP graph facts, and never a
substitute for Edge validation.

Use one narrative scout pass when the next research decision is ambiguous
between mechanism-deepening, graph expansion, or stopping. This is most useful
when graph nodes are hard to interpret, the current neighborhood lacks a clear
industry or supply-demand mechanism, or the journal cannot state what sign,
lag, regime, interaction, control, or risk-shaping question remains. If Abel Ask
is unavailable, off-target, or weak, record that plainly and continue with the
best graph/frontier evidence; do not launder narrative text into validation
evidence.

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
3. read ledger, frontier, and exploration path facts
4. use one narrative scout pass when the next decision is ambiguous between
   mechanism-deepening, graph expansion, or stopping
5. deepen the current mechanism when unresolved sign, lag, regime, interaction,
   control, or risk-shaping questions remain
6. expand `graph_frontier.json` only when current evidence leaves a frontier
   question unresolved
7. declare branch hypothesis and selected graph inputs
8. prepare branch inputs
9. write `compute_decisions(self, ctx)`
10. run semantic preflight
11. record evidence
12. inspect ledger/frontier facts
13. keep `exploration_path.md` covered before deep local refinement
