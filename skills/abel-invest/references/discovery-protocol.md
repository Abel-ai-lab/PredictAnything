# Graph Frontier Protocol

Use this reference after workspace preflight is complete.

## Purpose

The graph frontier answers one question:

Which causal graph nodes are currently known, and where can the agent widen the
search next?

It does not define the branch runtime by itself. Frontier expansion widens the
candidate node pool through CAP without pretending to pre-solve the strategy.

Live graph discovery is the normal session opening:

```bash
abel-invest init-session --ticker <TICKER> --exp-id <exp-id>
```

Use an explicit no-discovery fallback only when auth, service access, or
continuity constraints make live graph discovery unavailable:

```bash
abel-invest init-session --ticker <TICKER> --exp-id <exp-id> --no-discover
```

## Session Model

The session owns:

- `graph_frontier.json`: current graph node frontier and expansion provenance
- `readiness.json`: advisory coverage report
- `research_journal.md`: agent-owned research state
- `frontier.md`: factual exploration coverage

The branch then selects graph node inputs from that session context in
`branch.yaml`. The evidence ledger later records declared, prepared, and actual
graph node read facts.

## Priority Order

Graph-first is a research priority, not a mechanical quota:

1. causal graph structure and input hypotheses
2. strategy/mechanism variants
3. parameter, threshold, filter, sizing, and window refinement

Direct parents are an opening clue, not a guarantee that the final branch should
stay direct-only. If the first candidates look odd, do not discard them just
because they are obscure or low-attention; explain them before moving on.

## Practical Expansion

Use this as a search prior, not a hard recipe:

1. direct parents
2. other Markov blanket nodes, with `parents > children > spouses/co-parents`
3. children-derived hop-2 candidates
4. sector, market, or crypto peers only when they add a real mechanism

When the known frontier is too narrow, expand the graph itself before spending
rounds on strategy variants:

```bash
abel-invest frontier status --session research/<ticker>/<exp_id>
abel-invest frontier expand --session research/<ticker>/<exp_id> --anchor <NODE_ID> --mode all --limit 20
```

Use `--mode parents`, `--mode mb`, or `--mode all` according to the causal
question. The result is new or updated nodes in `graph_frontier.json`, not a
recommendation to run a specific branch.

## Branch Cut

When moving from discovery into a branch:

- choose a small explicit graph node input set
- write it into `branch.yaml` as structured `selected_inputs`
- use readiness to understand coverage, not to auto-ban ideas
- run `prepare-branch` before a recorded round
- after the round, check input realization facts before treating a declared
  graph-supported branch as graph-supported evidence

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

Readiness is advisory. Do not collapse every branch onto the latest common start
unless the branch thesis truly requires strict overlap.
