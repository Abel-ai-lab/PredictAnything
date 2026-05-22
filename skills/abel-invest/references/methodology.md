# Methodology

Use this optional reference when the user asks why Abel Invest is data-driven,
why the causal graph still matters, why search is allowed, or why validation
gates do not replace strategy search.

## Boundary

Abel Invest is an alpha-search product.

```text
framework = temporal legality, evidence facts, search-width accounting, reportability
agent = candidate generation, empirical search, and strategy judgment
```

`abel-edge` owns runtime legality and validation metrics. `abel-invest` owns
branch declarations, evidence labels, candidate-universe facts, search-width
accounting, and the exploration path surface. The agent owns what to try next.

## Core Stance

**Search hard, then explain.**
The job is to find a high-quality strategy for the user's objective. When the
user does not specify a target, default to Sharpe > 2 / strong tradable edge.
Mechanism stories organize results after evidence appears; they should not slow
the first useful empirical test.

**Empirical construction by default.**
The default posture is empirical construction over target and graph-derived
data. Feature factories, model families, denoise, subsets, ensembles, regimes,
filters, and sizing are degrees of freedom. Simple rules can benchmark,
diagnose, ablate, or refine an empirical lead, but they are not the default
search engine.

**Graph as alpha universe.**
Abel-discovered causal structure is a validated prior and should normally enter
candidate generation early. It expands the search beyond target-only price and
volume history. The graph supplies a rich node universe; data selects subsets,
lags, signs, transformations, model families, interaction terms, filters,
sizing signals, and regime roles.

**Target-only as benchmark, seed, and competitor.**
Target-only candidates are useful baselines, simple seeds, ablations, and
competing strategies. They should not become the default hiding place when live
graph candidates are available. Their main product role is to reveal whether
graph-derived information improves the objective or robustness.

**Empirical search is normal.**
Feature construction, model-family comparison, HPO, graph-node subset search,
lag/sign search, ensembles, regime filters, and sizing search are legitimate
exploration. Make the search width visible; do not pretend a selected winner
came from one isolated hand-written idea.

**Graph-supported is not enough.**
Runtime graph reads prove input realization. They do not by themselves prove the
agent searched the graph as data. Abel Invest should mine the graph-derived
universe for subsets, lags, transformations, models, regimes, filters, sizing
signals, and ensemble roles.

**Scout/probe first when the universe is wide.**
Temporary scripts, quick feature scans, and model comparisons help identify
sign, horizon, subset, feature family, and model family before a formal branch.
They are search aids, not validation evidence.

**Gate validates; it does not throttle.**
The gauntlet, DSR, leakage checks, walk-forward behavior, and promotion gate
decide what can be reported as robust. They should not prevent empirical
screening. A raw-metric winner is not a strategy success until it clears the
required validation with honest search-width accounting.

**Artifact completeness stays hard.**
`exploration_path.md` preserves each recorded round's selected path, compact
reason, Edge feedback, and ledger/artifact refs. It protects visualization and
replay completeness. Keep it short and evidence-linked; do not turn it into a
mechanism essay.

## Search Shape

The natural path is:

```text
default or user objective -> bounded candidate universe -> scout/probe -> formal candidate -> recorded validation -> explanation/reporting
```

Candidate-universe sources include:

- validated baselines or catalog strategies
- target history and target-only simple features
- causal graph nodes and graph-derived feeds
- sector, cross-asset, liquidity, volume, and regime feeds
- proven empirical patterns
- feature factories, learned models, and ensembles
- user constraints such as drawdown, no leverage, or explicit simple profile

The runtime path stays stable:

1. resolve workspace and doctor readiness
2. start or resume a session; run live graph discovery when available
3. search candidates empirically without temporal leakage
4. declare enough candidate metadata for runtime and audit
5. `prepare-branch` to materialize inputs
6. `debug-branch` to check semantic legality
7. `run-branch` to record selected candidates with `--selection-trials` when
   search width was used
8. read ledger/frontier/Edge facts
9. keep `exploration_path.md` covered
10. explain mechanism and graph contribution after there is evidence worth
    explaining
