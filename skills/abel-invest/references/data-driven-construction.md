# Data-Driven Construction

Use this reference for ordinary non-grandma alpha search, especially when the
next idea is drifting toward another hand-written rule.

This is the default construction stance, not a separate workflow. This file
owns candidate-expression choices; `experiment-loop.md` owns sequencing and
first-look scout mechanics, and `guarded-optimization.md` owns hard-target
reportability.

## Default Posture

Build candidates by high-capacity empirical construction over a scoped
universe. Usual ingredients include:

- target history and any validated baseline or catalog strategy
- live graph nodes and graph-derived feeds when available
- selected supplemental cross-asset, volume, liquidity, sector, or regime feeds
  when evidence or the user goal justifies them

The graph bounds and enriches the alpha universe. It does not prescribe one
tradable basket, and it is not satisfied by placing a few nodes into a simple
hand-written rule. The agent owns how to express the data.

## Construction Space

Data-driven construction can use many empirical degrees of freedom:

- deterministic feature factory over target + graph-derived fields
- weak-signal ensemble with diversity-aware member selection
- graph-node subset, lag, sign, transformation, ratio, spread, or rolling-window
  search
- model-family comparison such as linear, tree, GBDT, or hybrid models
- supervised target/graph model when label and horizon are temporally legal
- unsupervised denoise or compression such as PCA/ICA when temporally legal
- regime, sizing, or filter search layered on an otherwise plausible alpha

This list is not a route plan. Use the bounded feature universe most likely to
improve the user's objective, and let observed behavior decide how the search
evolves.

## Disposable Search Workbench

Temporary scripts, feature screens, quick model comparisons, CSV/JSON summaries,
notebook cells, query cells, or one-off shell heredocs are normal Abel Invest
research. Prefer `research/<ticker>/<session_id>/scratch/` for files. Scratch
outputs are not validation evidence; they help choose what is worth formal,
audited validation.

Use scratch to compare construction axes, not to create paperwork. A compact
first-look scout should score candidate-shaped variants closely enough to
choose what deserves formal validation. Prefer a ranked table over a prose-only
memo: target baselines, graph single-feature shapes, feature factories,
model-family variants, ensembles, filters, or sizing variants should be
compared with objective metrics such as Sharpe, total return, drawdown, and
turnover when feasible.

Diagnostic tables are raw material. IC, correlation, or feature-importance
screens can rank inputs, but they do not by themselves show whether a tradable
position rule or model expression works.

Useful construction surfaces include:

- target trend, momentum, reversal, and volatility-regime baselines
- graph single-feature threshold/vote variants across plausible lags, signs,
  horizons, transforms, spreads, and subsets
- feature factories that include rolling cumulative returns, trend deviation,
  volatility or regime context, not only one-day shifted returns
- model-family comparisons such as rolling linear/ridge, tree or GBDT, hybrid
  models, and lightweight ensembles when the feature set justifies them

These are examples, not a fixed route or minimum count. For prepared-data
ordering, prepare-only scout branches, and promotion into recorded rounds,
follow `experiment-loop.md`.

## What Simple Rules Are For

Simple target-only or graph-node rules are useful as:

- baselines and controls
- ablations against a richer candidate
- quick diagnostics of direction, sign, risk, or target-window difficulty
- refinements after an empirical construction finds a promising shape

They are not the default substitute for data-driven search. A branch can be
`graph_supported` because it reads prepared graph inputs and still be a narrow
hand-written mechanism.

## Search Accounting

If the submitted branch was selected from a scan, grid, model comparison, HPO
run, node-subset choice, or feature-factory screen, record the effective width.
K is an audit meter, not an exploration brake. `experiment-loop.md` owns the
per-round `--selection-trials` rule; `guarded-optimization.md` owns final-K
reportability.

## Failure Reading

A failed empirical construction says that expression failed. It does not prove
the graph is useless, and it does not prove target-only should take over. Read
metric shape and evidence context before deciding whether the problem is the
expression, the data view, the model family, the risk treatment, or the search
scope.

Before claiming no edge, the ledger should show materially different empirical
search axes, not only a sequence of small hand-written mechanisms.
