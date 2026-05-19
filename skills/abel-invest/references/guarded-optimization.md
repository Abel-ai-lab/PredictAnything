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
   `abel-invest run-branch --branch <branch-path> -d "<change description>"
   --selection-trials <N>` where **`--branch` and `-d/--description` are
   REQUIRED** (CLI errors at arg-parse without them, recording nothing) and
   `N` = THIS config/round's search width ONLY — NOT a running total; the
   framework accumulates campaign K from prior rounds itself (see K rule).
5. Discard non-gauntlet-PASS candidates. A gauntlet-EVALUATED FAIL (verdict
   PASS/FAIL) is auto-counted by the framework in future K. But a config
   disqualified BEFORE Edge validation (semantic-preflight / workflow-blocker
   ERROR) is written as ERROR and is NOT in `completed_rows` → the framework
   will NOT count it. To keep K honest you MUST fold every such preflight/ERROR
   variant into a later round's per-round `--selection-trials` (else true
   search width is undercounted). Honest-K cuts both ways: never double-count
   (cumulative), never drop (preflight ERRORs).
6. Select `argmax(single objective)` over PASS survivors — PROVISIONAL only.
7. **Final-K revalidation (mandatory before reporting an optimum) — NON-
   RECORDED.** Early survivors were DSR-validated at a smaller mid-campaign K;
   the framework never retro-deflates prior rows and `select_best_pass_strategy`
   ranks stored metrics WITHOUT recomputing the gate. Recompute the argmax
   survivor's DSR/gate **analytically at the FINAL total campaign K** from its
   already-stored round artifacts (its `*-edge-frame.csv` pnl + `abel_edge`
   `_dsr(pnl, T, K_final)`) — do NOT issue another `run-branch` for the check.
   A `run-branch` re-run is recorded as a new PASS/FAIL row, so K becomes
   final+1 and each failed-survivor recheck deflates the next stricter — that
   corrupts the verdict. If the survivor fails the gate at K_final, it is NOT
   the optimum — analytically recheck the next survivor (still non-recorded).
   **K_final = (campaign K implied by recorded PASS/FAIL rounds) + (every
   preflight/workflow-ERROR-disqualified variant since the last counted round
   that was never folded into a recorded per-round `--selection-trials`).**
   `build_dsr_trials_context` counts PASS/FAIL rows only, so terminal ERROR
   variants after the last counted round (e.g. survivor PASSes, next config
   ERRORs, search stops) have no later round to absorb them — the analytic
   recompute MUST add them explicitly or it undercounts and can preserve a
   survivor that should fail DSR. The revalidation itself records nothing and
   adds zero *recorded* trials, but its K_final must include those unfolded
   terminal ERRORs. Never report an optimum validated only at a stale (smaller)
   K, and never let the revalidation itself create a recorded row.
8. Journal: search width, K, gauntlet outcomes, the final-K revalidation, the
   selected optimum.

## K rule

`--selection-trials N` = THIS round's search width only (every variant tried
*this round*, not the winner). The framework accumulates the campaign total
itself (`build_dsr_trials_context`: campaign K = Σ each prior round's
recorded `current_round_trials` + this round). Pass the per-round count, NEVER
a running/cumulative total — passing a cumulative total double-counts prior
rounds and corrupts DSR. Mandatory for any search width; the cardinal errors
are under-counting this round AND passing a campaign-cumulative value.

## Honest outcomes

- A survivor that clears the gauntlet **at the FINAL total campaign K**
  (step 7 revalidation) meets the target → report it. A PASS validated only
  at a smaller mid-campaign K is NOT a valid optimum.
- None clears the gauntlet at final K after a genuine K-accounted causal-
  bounded search → report that null honestly. Not "didn't try"; never an
  un-gated high metric relabeled as success.

## Anti-patterns

- Selecting on a metric outside the gauntlet.
- Unbounded (non-causal-frontier) universe.
- Under-counting `--selection-trials`.
- Mismatched or multi-objective-diluted scorer.
- Declining the search when a hard target was set.
- Reporting an argmax survivor without final-K revalidation (stored PASS
  metrics are not re-deflated at the larger final K — step 7 is mandatory).
- Any external-skill dependency.
