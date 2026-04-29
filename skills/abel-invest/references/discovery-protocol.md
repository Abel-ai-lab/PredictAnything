# Discovery Protocol

Use this reference after workspace preflight is complete.

## Purpose

Discovery answers one question:

Which causal graph candidates are worth considering for this session?

It does not define the branch runtime by itself. Discovery widens the search
space without pretending to pre-solve the strategy.

Live discovery is the normal session opening:

```bash
abel-invest init-session --ticker <TICKER> --exp-id <exp-id>
```

Use an explicit no-discovery fallback only when auth, service access, or
continuity constraints make live graph discovery unavailable:

```bash
abel-invest init-session --ticker <TICKER> --exp-id <exp-id> --no-discover
```

## Session Model

After live discovery, the session owns:

- `discovery.json`: candidate graph snapshot
- `readiness.json`: advisory coverage report
- `research_journal.md`: agent-owned research state
- `frontier.md`: factual exploration coverage

The branch then selects inputs from that session context in `branch.yaml`.
The evidence ledger later records whether those selected graph inputs were
actually read at runtime.

## Priority Order

Graph-first is a research priority, not a mechanical quota:

1. causal graph structure and input hypotheses
2. strategy/mechanism variants
3. parameter, threshold, filter, sizing, and window refinement

Direct parents are the default opening, not a guarantee that the final branch
should stay direct-only. If the first candidates look odd, do not discard them
just because they are obscure or low-attention; explain them before moving on.

## Practical Expansion

Use this as a search prior, not a hard recipe:

1. direct parents
2. other Markov blanket nodes, with `parents > children > spouses/co-parents`
3. children-derived hop-2 candidates
4. sector, market, or crypto peers only when they add a real mechanism

Expansion probes, ablations, and controls are useful because they create
contrast evidence. They should still be declared honestly in `branch.yaml`.

## Branch Cut

When moving from discovery into a branch:

- choose a small explicit input set
- write it into `branch.yaml` as `selected_inputs`
- use readiness to understand coverage, not to auto-ban ideas
- run `prepare-branch` before a recorded round
- after the round, check input realization facts before treating a declared
  graph-supported branch as graph-supported evidence

Readiness is advisory. Do not collapse every branch onto the latest common start
unless the branch thesis truly requires strict overlap.
