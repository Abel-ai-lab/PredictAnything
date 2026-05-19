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
