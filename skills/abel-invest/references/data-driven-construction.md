# Data-Driven Construction

Use this reference for ordinary alpha search, especially when the next idea is
drifting toward another hand-written rule, a low-capacity graph gate, or an
unscouted whole-universe basket.

This is the default construction stance, not a separate workflow. Runtime
legality, honest search-width accounting, and validation still decide what can
be reported.

## Default Posture

Build candidates by high-capacity empirical construction over a wide but scoped
universe. Usual ingredients include:

- target history and any validated baseline or catalog strategy
- live graph nodes and graph-derived feeds when available
- selected supplemental cross-asset, volume, liquidity, sector, or regime feeds
  when evidence or the user goal justifies them

The graph bounds and enriches the alpha universe. It does not prescribe one
tradable basket, and it is not satisfied by placing a few nodes into a simple
hand-written rule. The agent owns how to express the data.

Use broad inputs for scouting and construction, not as a reason to submit the
entire graph or feature matrix as one formal branch. Scout one sharp question:
the likely sign, horizon, node subset, feature family, model family, regime,
sizing, filter, or risk-shape issue. Then promote the strongest selected,
reproducible candidate shape.

## Construction Space

High-capacity construction can use many empirical degrees of freedom:

- deterministic feature factory over target + graph-derived fields
- top-N graph feature mean or weighted ensemble
- dense feature average selected from temporally legal screens
- weak-signal ensemble with diversity-aware member selection
- graph-node subset, lag, sign, transformation, ratio, spread, or rolling-window
  search
- model-family comparison such as linear, tree, GBDT, or hybrid models
- supervised target/graph model when label and horizon are temporally legal
- unsupervised denoise or compression such as PCA/ICA when temporally legal
- regime, sizing, or filter search layered on an otherwise plausible alpha

This list is not a route plan. Use the feature universe most likely to improve
the user's objective, and let observed behavior decide how the search evolves.

Formal candidates can be learned models, dense ensembles, feature-factory
outputs, graph-node subset models, or hybrids. Promote the discovered form
faithfully: if the scout lead is a model, feature factory, ensemble, or hybrid,
submit that form rather than a hand-written proxy that merely imitates it.
Formal promotion means temporally legal, reproducible, selected, and honestly
K-accounted. It does not mean low-complexity, low-capacity, or hand-written.

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

Scratch scripts, local probes, feature screens, dense ensemble screens, model
comparisons, and quick scans are allowed and useful. The preferred disposable
surface is `research/<ticker>/<session_id>/scratch/`; a one-off heredoc,
notebook cell, or query cell is equivalent when that fits the runtime better.
They are not validation evidence.

If the submitted branch was selected from a scan, grid, model comparison, HPO
run, node-subset choice, feature-factory screen, or other probe, record the
effective width with `--selection-trials N` or the current candidate search
metadata path. `N` is this round's search width only, never the campaign total.
Effective width is the number of materially compared variants used to select
the submitted candidate, not automatically the raw count of generated features
or available graph nodes.

Do not report a raw search winner as robust until it clears the gauntlet with
honest width accounting.

## Failure Reading

A failed empirical construction says that expression failed. It does not prove
the graph is useless, and it does not prove target-only should take over. Read
metric shape and evidence context before deciding whether the problem is the
expression, the data view, the model family, the risk treatment, or the search
scope.

Before claiming no edge, the ledger should show materially different empirical
search axes, not only a sequence of small hand-written mechanisms or
low-capacity graph gates.
