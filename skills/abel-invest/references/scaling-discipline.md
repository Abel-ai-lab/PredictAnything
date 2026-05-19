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
exhaustion by ledger, never by vibe; account K honestly per-round and let the
gauntlet reject weak Sharpe.

Self-contained: abel-invest's own CLI + engine.py + branch flow only. No
abelian / external skill.

## Mandatory data-driven entry — not advice

- The FIRST recorded `candidate` round MUST be a machine feature factory over
  the **full directly-discovered frontier** (the depth-1 nodes `init-session`
  returns: parents + blanket + children — already a multi-node causal set,
  not a single parent), fed to a **heterogeneous** ensemble (≥2 model
  families, diversity-gated). Do NOT require 2-hop on the first round: depth-2
  nodes only exist after `frontier expand`, which `discovery-protocol.md`
  gates on an unresolved frontier question + recorded evidence. 2-hop
  enrichment is a later evidence-gated expansion, never a precondition for
  the first factory round.
- Hand-designed single-mechanism rounds are DIAGNOSTICS, never the baseline.
  A hand-picked-feature round before a machine-factory round is a violation.
- Denoise is first-class, ranked by evidence: unsupervised (PCA/ICA/AE)
  **>** filter-select **>** supervised (PLS). PLS overfits weak edges.
- This is Pillar-2 of `data-driven-construction.md` made obligatory, not
  optional. Skipping it = skipping the search.

## Honest-K accounting

- `--selection-trials` = THIS round's search width ONLY (model families ×
  HPO trials × denoise variants × feature-sets tried *in this round*). The
  framework accumulates the campaign total itself
  (`build_dsr_trials_context`: `K = Σ prior rounds' current_round_trials +
  this round`). Passing a running/cumulative total DOUBLE-COUNTS prior rounds
  and corrupts DSR — the cardinal K error. Per-round width, never cumulative.
- With correct per-round K, campaign K grows only ~linearly with rounds
  (≈ number of recorded rounds) — there is NO runaway "more-search-self-
  defeats" dynamic; a prior claimed "honest-K self-defeat law" was a
  cumulative-double-count artifact and is retracted.
- The real bound is mundane and sufficient: a weak-Sharpe construction fails
  the DSR gate even at honest per-round K. So the discipline is not "search
  less to protect K" — it is: run the mandatory data-driven entry, account K
  per-round honestly, and let the gauntlet reject weak Sharpe. Force the loop;
  trust the gate.
- **Final-K revalidation before any reported optimum — non-recorded.** K only
  grows; early survivors were gated at a smaller mid-campaign K and stored-
  metric ranking (`select_best_pass_strategy`) does NOT re-deflate them. The
  chosen argmax survivor is provisional until its DSR/gate is recomputed
  **analytically at the FINAL total K from its stored round artifacts**
  (`*-edge-frame.csv` pnl + `abel_edge._dsr`). Do NOT `run-branch` the recheck
  — a recorded re-run becomes final+1 and escalates with each failed-survivor
  recheck. The revalidation adds zero trials. Never report a candidate
  validated only at a stale smaller K, nor let the recheck inflate K.
- **Autoresearch is NOT round-limited.** There is no round cap, round budget,
  or "stop after N rounds / 1-2 tries". Keep iterating data-driven mechanisms
  for as long as untested high-quality directions remain. The ONLY stops are:
  (a) a gauntlet-PASS candidate at the target, or (b) ledger-proven exhaustion
  (Pillars 1-4 covered AND materially-different mechanism classes tried, all
  honest-K accounted). Never stop by round count — that is vibe, not ledger.

## Exhaustion is ledger-proven, never asserted

Before writing "exhausted / CLOSED / ceiling / no untested mechanism", the
ledger MUST show, all K-accounted:

1. machine feature factory ✓
2. ≥1 unsupervised denoise ✓
3. heterogeneous diversity-gated ensemble ✓
4. full discovered frontier used (≥3 graph nodes: parents+blanket+children;
   2-hop only if it was evidence-expanded per `discovery-protocol.md`) ✓

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
- Stopping by round count / round budget / "1-2 rounds then stop" instead of
  gauntlet-PASS or ledger-proven exhaustion. Rounds are unbounded.
- Letting preflight/ERROR-disqualified configs vanish from K (undercount):
  fold them into a later round's per-round `--selection-trials`.
- Un-K'd HPO / denoise / model-zoo search.
- Treating `data-driven-construction.md` as advice rather than contract.
- Inferring a standard instead of reading it (skill artifacts → read
  `AGENTS.md` + skill-creator + a same-type file FIRST).
- Selecting on a metric outside the gauntlet (see `guarded-optimization.md`).

## Cross-references

- `data-driven-construction.md` — the factory + ensemble this enforces.
- `guarded-optimization.md` — the gauntlet K-accounting this governs.
- `methodology.md` — why graph-first / evidence-boundary.
