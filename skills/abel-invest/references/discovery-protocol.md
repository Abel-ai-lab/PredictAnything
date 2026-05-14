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
branch construction should declare or test its timing assumption.

## Practical Expansion

Use this as a search prior, not a hard recipe. Prefer small explicit node sets
whose use can be explained. Structural roles help name provenance and, when
specific enough, orientation. They do not prescribe strategy use.

When current evidence leaves a frontier question unresolved, expand the graph
itself before spending rounds on strategy variants:

```bash
abel-invest frontier status --session research/<ticker>/<exp_id>
abel-invest frontier expand --session research/<ticker>/<exp_id> --anchor <NODE_ID> --mode all --limit 20
```

Use `--mode parents`, `--mode mb`, or `--mode all` according to the causal
question. The result is new or updated nodes in `graph_frontier.json`, not a
recommendation to run a specific branch.

Good expansion reasons include a missing liquidity, supply-chain, market-state,
or demand-regime motif; current-frontier availability or input-realization
limits; or user/narrative context that names a plausible real-world mechanism
outside the current frontier. Weak reasons include "the last branch failed",
"graph breadth is always good", or "a local metric scan found one attractive
node, so expand around it until the result improves".

Before expanding to a more distant frontier, check mechanism depth in the
current neighborhood. If evidence still leaves a concrete sign, lag, regime,
interaction, control, or risk-shaping question, prefer one branch that answers
that question over wider graph expansion. Complexity is allowed when it adds
mechanism information; it is not allowed as metric-pressure tuning.

## Narrative Scout

Abel Ask and narrative context can improve exploration efficiency by generating
mechanism hypotheses before another branch cut or graph expansion. Use them to
ask what industry, demand, supply-chain, liquidity, macro, volume, or peer
mechanism could make a graph neighborhood matter.

Narrative scout work can suggest:

- a supplemental driver to test
- a graph expansion anchor
- a sign, lag, or regime question
- a reason to stop exploring a weak mechanism family

It is not validation evidence and it does not override CAP facts or Edge
results. If the narrative result is off-target or weak, record that plainly.

Use one narrative scout pass when ledger/frontier/journal facts do not make the
next research move clear: deepen the current mechanism, expand the frontier, or
stop. This is especially useful when the known graph nodes are obscure, the
target is driven by industry or supply-demand context, or the branch self-check
cannot name a real-world transmission path.

When using Abel Ask for this scout pass, keep it lightweight: start from the
Abel Ask narrative probe workflow, prefer `narrate` for a concrete candidate or
`query-node` for a broad theme, and return to Abel Invest branch evidence as
soon as the mechanism or frontier question is clear enough. If auth is missing,
the result is thin, or the narrative drifts off target, journal that fact and do
not treat the scout as branch evidence.

Efficient pattern:

```text
ledger/frontier facts -> narrative scout for mechanism context ->
frontier question -> optional CAP expansion or branch cut
```

Inefficient pattern:

```text
weak metric result -> expand graph broadly -> search new nodes for a metric win
```

## Branch Cut

When moving from discovery into a branch:

- choose a small explicit graph node input set
- write it into `branch.yaml` as structured `selected_inputs`
- state the graph use contract: selected nodes, construction, intended role,
  unresolved assumption, and falsification scope
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
