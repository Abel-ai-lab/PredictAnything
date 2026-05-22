# Graph-Informed Alpha Context

Use this reference after workspace preflight is complete when live graph
discovery, graph-derived feeds, or frontier expansion are relevant.
Commands below use the workspace `command_prefix` returned by
`workspace context --json` or doctor.

## Purpose

The graph frontier answers one product question:

Which causal graph nodes are currently known, and how can they enrich the
alpha universe?

It does not prescribe the first strategy branch. It does not mean the whole
depth-1 frontier should be traded as one basket. CAP graph nodes are a validated
source of structure and should normally enter candidate generation early, but
data decides the tradable expression: subset, lag, sign, transformation, model,
filter, sizing signal, or ensemble role.

Live graph discovery is the normal session opening:

```bash
<command_prefix> init-session --ticker <TICKER> --exp-id <exp-id>
```

Use an explicit no-discovery fallback only when auth, service access, or
continuity constraints make live graph discovery unavailable:

```bash
<command_prefix> init-session --ticker <TICKER> --exp-id <exp-id> --no-discover
```

## Session Model

The session owns:

- `graph_frontier.json`: current graph node universe and expansion provenance
- `readiness.json`: advisory coverage report
- `exploration_path.md`: human-facing path, reason, and Edge feedback log
- `frontier.md`: factual search-context coverage

The branch selects inputs from this session context in `branch.yaml`. The
evidence ledger later records declared, prepared, and actual graph node read
facts.

## Alpha Universe

Use the graph as the default high-value expanded feature universe, and search it
like an alpha source rather than a checklist:

- target history and validated baselines establish the benchmark
- graph nodes and graph-derived feeds are the normal next place to look for
  incremental information when live graph candidates exist
- available cross-assets, sector peers, volume, liquidity, and regime variables
  can supplement the graph when the user goal or evidence supports them
- proven patterns, feature factories, ML models, and ensembles turn the universe
  into candidate signals

For ordinary alpha search, graph context should feed empirical construction
early. Feature factories, model comparisons, denoise/compression, node-subset
search, lag/sign/transformation search, regimes, sizing, filters, and ensembles
are possible expressions, not a checklist. A hand-written rule that happens to
read graph nodes is graph-realized evidence, but it is not by itself
data-driven graph search.

Use graph breadth to scout promising expressions before formal evidence. A large
frontier can be probed for sign, horizon, subset, model family, regime, filter,
or sizing role. Do not submit the whole frontier as one formal basket before a
small probe can narrow the candidate shape.

Target-only candidates are baselines, seeds, ablations, and competing strategy
candidates. Their job is to make graph-derived marginal contribution visible,
not to replace graph search as the default when graph candidates are live.

## CAP Role Interpretation

CAP graph nodes are model-supported causal priors, not trading instructions.
Trust that they carry target-relevant information, but do not infer disclosed
weight, exact lag, signed effect, or tradable direction from the role alone.

CAP graph roles expose causal-flow orientation when the role is specific enough,
not signed trading direction:

- `parent`: upstream of the target, `parent -> target`
- `child`: downstream of the target, `target -> child`
- `blanket`: Abel Invest's Markov-blanket discovery bucket/provenance label for
  nodes returned through MB scope after parent/child handling; it is not
  synonymous with `spouse` and does not by itself disclose one causal-flow
  direction

If more specific roles are present, use those roles for structural orientation.
The underlying graph is temporal, so treat graph relevance as lag-mediated
rather than contemporaneous by default. CAP does not disclose the exact lag; the
candidate search can test lag and transformation choices.

## Practical Use

Graph context can shape the search prior and feature universe:

- test graph-enriched feature factories
- search graph node subsets instead of assuming the whole frontier should move
  together
- test lag, sign, ratio, relative-momentum, volatility, and regime
  transformations
- compare linear, tree, ensemble, and hybrid model families when useful
- use graph-derived signals as alpha core, confirmation, filter, sizing signal,
  or regime context according to what the data supports
- keep weak standalone graph signals if they add diversity inside an ensemble

Local graph probes and model/feature scans are search aids, not validation
evidence. If they select the formal candidate, record their influence in
`exploration_path.md` and declare the effective current-round width when running
the selected branch.

Do not expand the graph merely to satisfy coverage. Expand when it helps the
empirical search question:

```bash
<command_prefix> frontier status --session research/<ticker>/<exp_id>
<command_prefix> frontier expand --session research/<ticker>/<exp_id> --anchor <NODE_ID> --mode all --limit 20
```

Use `--mode parents`, `--mode blanket`, or `--mode all` according to the
candidate-universe question. The result is new or updated nodes in
`graph_frontier.json`, not a recommendation to run a specific branch.

Good expansion reasons are evidence-led: missing motifs, availability or input
realization limits, user context, or a plausible external driver outside the
current frontier. Weak reasons include "more graph nodes are always good" or
"the product expects graph coverage."

Before expanding to a more distant frontier, consider whether the current graph
universe still has useful subset, lag, sign, transformation, model-family,
regime, or sizing search left. Prefer the path that is most likely to improve
the user's objective.

## Narrative Scout

Abel Ask and narrative context can improve search efficiency by generating
candidate features, supplemental drivers, graph expansion anchors, or
interpretation. Use them when they help the empirical search.

Narrative scout work can suggest:

- a supplemental driver to test
- a graph expansion anchor
- a sign, lag, regime, or transformation question
- a reason to stop spending search width on a weak candidate family

It is not validation evidence and it does not override CAP facts or Edge
results. If the narrative result is off-target or weak, record that plainly.

Efficient pattern:

```text
ledger/frontier facts -> candidate universe question -> optional narrative scout -> branch/search
```

Inefficient pattern:

```text
weak metric result -> expand graph broadly -> search new nodes only because coverage feels thin
```

## Branch Cut

When moving from graph context into a branch:

- choose inputs that match the candidate search question
- write selected runtime inputs into `branch.yaml`
- keep graph attribution lightweight before validation unless the branch needs a
  specific graph claim
- use readiness to understand coverage, not to auto-ban ideas
- run `prepare-branch` before a recorded round
- after the round, check input realization facts before treating a declared
  graph-supported branch as graph-derived evidence

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

Readiness is advisory. Do not collapse every branch onto the latest common start
unless the candidate expression truly requires strict overlap.
