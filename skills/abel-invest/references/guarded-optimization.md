# Guarded Optimization (procedure)

**When**: a hard performance target (Sharpe / MaxDD / PnL) is set.

**Why** — canonical in `methodology.md` ("Mechanism seeds; the gauntlet
gates; optimization is first-class"). Not restated here. One line: optimize
*through* the gauntlet; never select on a raw metric outside it; the causal
frontier bounds K so the search stays DSR-survivable.

Self-contained: the agent runs this via abel-invest's own CLI only. No
autonomous optimizer is shipped; no abelian / external skill.

## Objective — single, matched

- Objective = ONE risk-adjusted scalar (Sharpe, or Lo-adjusted Sharpe),
  matched to the strategy goal. Production rule: the objective is primary; a
  mismatched scorer (accuracy/Brier) was discarded on evidence, Sharpe kept.
- MaxDD / PnL / LossYrs / Lo / IC / DSR / triangle are **gauntlet gates**,
  not objective terms. Do not blend a multi-objective profile.

## Gate — every candidate, no exception

Eligible only if it clears ALL of:

1. semantic preflight (legal reads, no look-ahead)
2. the recorded gate / DSR / triangle profile
3. leakage audit (feature-time AND discovery-time layers)
4. walk-forward across all regimes (never a window excluding the adverse one)

Fail any → disqualified regardless of objective value.

## Loop — abel-invest primitives only

1. `init-session` (graph-first).
2. `frontier` — this IS the search space; never optimize an unbounded universe.
3. Seed configs from `data-driven-construction.md` (feature factory +
   ensemble) and `proven-patterns.md`.
4. Per config: `init-branch` → `prepare-branch` →
   `run-branch --selection-trials <THIS config/round's search width only —
   NOT a running total; the framework accumulates campaign K from prior
   rounds itself (see K rule)>`.
5. Discard non-gauntlet-PASS candidates (they still increment K).
6. Select `argmax(single objective)` over PASS survivors.
7. Journal: search width, K, gauntlet outcomes, selected optimum.

## K rule

`--selection-trials N` = THIS round's search width only (every variant tried
*this round*, not the winner). The framework accumulates the campaign total
itself (`build_dsr_trials_context`: campaign K = Σ each prior round's
recorded `current_round_trials` + this round). Pass the per-round count, NEVER
a running/cumulative total — passing a cumulative total double-counts prior
rounds and corrupts DSR. Mandatory for any search width; the cardinal errors
are under-counting this round AND passing a campaign-cumulative value.

## Honest outcomes

- A gauntlet-surviving optimum meets the target → report it.
- None clears the gauntlet after a genuine K-accounted causal-bounded
  search → report that null honestly. Not "didn't try"; never an un-gated
  high metric relabeled as success.

## Anti-patterns

- Selecting on a metric outside the gauntlet.
- Unbounded (non-causal-frontier) universe.
- Under-counting `--selection-trials`.
- Mismatched or multi-objective-diluted scorer.
- Declining the search when a hard target was set.
- Any external-skill dependency.
