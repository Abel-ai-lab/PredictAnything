# Principles To Test

Short staging area for plausible `abel-invest` principles before they become
canonical skill rules.

## Top-1-Kaggler-Style ML

Principle:
Causal-bounded strategy discovery should consider machine feature factories,
heterogeneous ensembles, and strong empirical ML practice as serious tools, not
late-stage extras.

Related impacts:
- Pushes the agent away from premature single-mechanism conclusions.
- Encourages broader candidate generation inside the causal frontier.
- Treats deterministic feature factories over causal-frontier fields, lags,
  rolling windows, ratios, and differences as a serious candidate-generation
  option when the current question justifies the added width.
- Treats weak standalone signals as possible ensemble members rather than
  automatic kills; ensemble contribution and diversity can matter more than
  one feature's standalone metric.
- Raises the need for honest `--selection-trials` accounting.
- Makes diversity, ensemble contribution, and overfit controls more important.
- Makes unsupervised denoise, model-family diversity, and HPO part of the search
  width when used; one plausible denoise priority is unsupervised PCA/ICA/AE
  before filter-select before supervised PLS, but that ordering is still part of
  the principle under test.
- Should not override causal graph boundaries, runtime legality, honest-K, or
  the Abel gauntlet.

Status:
Unproven as a canonical rule. Keep as a principle to test until supported by
skill evals and realistic `abel-invest` runs.

Real-run evidence (ETHUSD, 2026-05-19/20) — REFINES, does not promote:
Across realistic abel-invest runs on a causal-pure daily single-asset venue
(ETHUSD whose dominant discovered parent is SSTK), the ML-feature-factory /
heterogeneous-ensemble / selectivity tooling **consistently underperformed a
simple wide-distribution single-mechanism baseline** — 7 independent contrasts,
spanning the method spectrum:
- equal-weight rule-based 3-hop ensemble (baseline): Sharpe ~1.05
- GBDT walk-forward on the same feature factory: ~0.29
- walk-forward Ridge-learned weights: ~0.57
- downstream-cascade breadth extension: ~0.80
- autoresearch machine-factory+ensemble vs standard single-mechanism: 0.27 vs 0.34
- RYAM/WRLD CCA sizing restoration: 0.76 vs 0.95
- conformal + causal-cascade selectivity gates: 0.60 vs 1.05
Mechanism: the discovered causal edges are *aggregate statistical* (need a wide
trade base to integrate), not *per-day directional*; GBDT got marginally better
direction (IC +0.056) yet far worse Sharpe — the simple tanh-z × vol-target
SIZING was the alpha, not the fit. Each sophistication layer overfits the
residual already priced into the simple signal.
Refined principle (still under test): treat ML feature factories / ensembles as
serious tools, BUT measure every such candidate against a simple wide
single-mechanism baseline FIRST, and in causal-pure venues expect it to LOSE;
escalate to ML/selectivity ONLY with venue-specific evidence that it beats the
simple baseline through the gauntlet at honest K. The principle is
venue-conditional, not universal.

## Simple-First In Causal-Pure Venues

Principle (real-run-supported, staged for canon):
In a venue where the discovered causal signal is pure (one dominant parent edge,
e.g. SSTK->ETH), a simple wide-distribution single-mechanism signal tends to hit
the cloud-portable Sharpe ceiling (~1.0-1.15 on ETHUSD daily); adding
ML/optimization/selectivity layers tends to destroy alpha, not add it. Default
order: simple wide single-mechanism FIRST; treat each added layer as
guilty-until-proven and revert it if it does not beat the simple baseline
through the gauntlet.

Status:
Strongly supported by 7 ETHUSD contrasts (above) but on ONE venue. Test on
other causal-pure venues before promoting to canon. Do not over-generalize to
venues with diffuse/multi-parent causal structure.

## Multi-Hop Causal Frontier Extraction

Principle (real-run-supported, staged):
Discovery should consider 2-3 hop causal ancestors, not only depth-1 parents.
On ETHUSD, an Abel-discovered 3-hop chain (OKLO -> IMOUSD -> SSTK -> ETHUSD)
yielded a real standalone signal (~1.05 Sharpe, equal-weight distributed-lag
ensemble) that no depth-1 view surfaces. Children (downstream) lag the target
and add noise as predictors — use ancestors (upstream), not descendants.

Status:
Positive single-venue evidence. Test breadth before canon.

## Portfolio-Combine Uncorrelated Simple Mechanisms

Principle (real-run-supported, staged):
Combining two uncorrelated simple gauntlet-near-passing mechanisms beats
deepening a single one. On ETHUSD, a 3-hop causal ensemble and an S2-style
single-hop ML signal had position correlation ~0.21; a 50/50 combine lifted
analytic Sharpe above either standalone (the only positive lift found after the
single-mechanism ceiling). When stuck at a single-mechanism ceiling, prefer
orthogonal-mechanism portfolio combination over sophistication-stacking.

Status:
Positive analytic evidence on one venue. Validate through the gauntlet
(combined positions, honest K) before canon.
