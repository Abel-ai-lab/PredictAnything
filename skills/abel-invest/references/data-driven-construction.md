# Data-Driven Construction

Use this reference for ordinary non-grandma alpha search, especially when the
next idea is drifting toward another hand-written rule.

This is the default construction stance, not a separate workflow. Runtime
legality, honest search-width accounting, and validation still decide what can
be reported. When the user gives no metric target, the ordinary objective is a
strong tradable strategy with Sharpe > 2 as the aspirational target.

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

For a fresh or unfamiliar ticker, a compact first-look scout is the usual start
to serious empirical construction. Use it to discover target behavior, graph
lead/lag/sign, node subset, transformation, feature family, model family,
filter, sizing, or risk shape. Do not turn scratch into paperwork; promote the
best shapes and record selection influence plus effective width when the scout
materially chose the submitted candidate.

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
run, node-subset choice, or feature-factory screen, record the effective width
with `--selection-trials N` or the current candidate search metadata path.
`N` is this round's search width only, never the campaign total.

Do not report a raw search winner as robust until required validation and
honest width accounting support that claim.

K is an audit meter, not an exploration brake. Large empirical searches are
allowed when the candidate ceiling justifies them; they simply carry their real
selection width.

## Failure Reading

A failed empirical construction says that expression failed. It does not prove
the graph is useless, and it does not prove target-only should take over. Read
metric shape and evidence context before deciding whether the problem is the
expression, the data view, the model family, the risk treatment, or the search
scope.

Before claiming no edge, the ledger should show materially different empirical
search axes, not only a sequence of small hand-written mechanisms.
