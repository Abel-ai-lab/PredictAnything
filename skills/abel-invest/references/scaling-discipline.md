# Scaling Discipline (procedure)

**When**: every abel-invest mandate — always-on temperament. Read at session
start and again before writing any "exhausted / ceiling / no edge" conclusion.

**First principle** (the fixed hierarchy — everything below serves it):

1. **Causal is a first-class citizen.** The causal graph/edge is the primary
   organizing object — the universe and candidate space are bounded BY it,
   never an unbounded feature soup with causality bolted on.
2. **Top-1-Kaggler-style ML is the temperament AND the methodology.**
   Extreme feature engineering + diversity-gated ensembling + genuine ML
   expertise, applied competitively and empirically — the disposition *and*
   the working method, never hand-designed single mechanisms.
3. **Top-tier engineering is the foundation.** Reproducible, vectorized,
   cached, deterministic, leak-safe execution is the base the rest stands on;
   without it the search is not trustworthy.
4. **The abel causal gauntlet is the heavy gates.** Multiple hard gating
   layers (semantic · gate/DSR/triangle · leakage · walk-forward · honest-K)
   admit nothing unworthy; the gate is incorruptible and final.

Derived from the **DR-series production existence proof** (the deployed ETH
winners embody 1-4 and reach Sharpe>3) — NOT from any single in-session
experiment.

**Why** — canonical in `methodology.md` (data-driven entry) +
`guarded-optimization.md` (the gauntlet gates). Not restated here. One line:
force the extreme causal-bounded data-driven loop by default and prove
exhaustion by ledger, never by vibe. (The "more search self-defeats on a weak
edge" dynamic is plausible but only trustworthy under correct per-round K
accounting — see the K rule below.)

Self-contained: abel-invest's own CLI + engine.py + branch flow only. No
abelian / external skill.

## Mandatory data-driven entry — not advice

- The FIRST recorded `candidate` round MUST be a machine feature factory over
  the **multi-hop** causal frontier (parents + blanket + children + 2-hop),
  fed to a **heterogeneous** ensemble (≥2 model families, diversity-gated).
- Hand-designed single-mechanism rounds are DIAGNOSTICS, never the baseline.
  A hand-picked-feature round before a machine-factory round is a violation.
- Denoise is first-class, ranked by evidence: unsupervised (PCA/ICA/AE)
  **>** filter-select **>** supervised (PLS). PLS overfits weak edges.
- This is Pillar-2 of `data-driven-construction.md` made obligatory, not
  optional. Skipping it = skipping the search.

## Honest-K is the scaling law's governor

- `--selection-trials` = THIS round's search width ONLY (model families ×
  HPO trials × denoise variants × feature-sets tried *in this round*). The
  framework accumulates the campaign total itself
  (`build_dsr_trials_context`: `K = Σ prior rounds' current_round_trials +
  this round`). Passing a running/cumulative total DOUBLE-COUNTS prior rounds
  and corrupts DSR — the cardinal K error. Per-round width, never cumulative.
- DSR deflates as the framework-accumulated campaign K grows. Therefore: on a
  real edge the breakthrough lands in **1-2 rounds**; if many rounds are
  needed, the edge is absent and more search is **negative-EV** (K rises
  faster than Sharpe). State this up front. (Caveat: this dynamic is only
  trustworthy with correct per-round K accounting — a cumulative-pass bug
  inflates K and can falsely manufacture the "self-defeat" signal.)
- Strong edge → scaling holds (force the loop hard). Weak/absent edge →
  scaling self-defeats (the gate correctly refuses to manufacture alpha).
  Do not mistake "more compute" for "more alpha".

## Exhaustion is ledger-proven, never asserted

Before writing "exhausted / CLOSED / ceiling / no untested mechanism", the
ledger MUST show, all K-accounted:

1. machine feature factory ✓
2. ≥1 unsupervised denoise ✓
3. heterogeneous diversity-gated ensemble ✓
4. multi-hop frontier (≥3 graph nodes) ✓

Missing any → the verdict is premature; run it first. A green per-candidate
gauntlet does NOT certify search exhaustiveness — it never has.

## Loop inversion

The candidate space is machine-generated (factory × zoo × denoise × frontier);
the agent scopes the mandate, audits the gate verdict, decides pivot/stop.
Agent hand-design is the exception and must carry an explicit journal
justification.

## Anti-patterns

- Hand-picked features as the baseline; machine factory as a "late lever".
- Declaring exhaustion without Pillars 1-4 in the ledger (premature CLOSED is
  the cardinal process violation — the recurring conclude-before-verify).
- Un-K'd HPO / denoise / model-zoo search.
- Treating `data-driven-construction.md` as advice rather than contract.
- Inferring a standard instead of reading it (skill artifacts → read
  `AGENTS.md` + skill-creator + a same-type file FIRST).
- Selecting on a metric outside the gauntlet (see `guarded-optimization.md`).

## Cross-references

- `data-driven-construction.md` — the factory + ensemble this enforces.
- `guarded-optimization.md` — the gauntlet K-accounting this governs.
- `methodology.md` — why graph-first / evidence-boundary.
