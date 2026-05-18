# Data-Driven Construction (procedure)

Pillar 2 of two: construction generates the candidate space; guarded
optimization (`guarded-optimization.md`) searches it; the causal prior
bounds it.

**Why** — canonical in `methodology.md` ("Data-driven entry; mechanism is
post-hoc"). Not restated here. Apply the rules below.

Self-contained: abel-invest's own `engine.py` + branch flow only. No abelian /
external skill.

## Rule 1 — Entry is survival, not story

- A candidate enters ONLY on gauntlet / OOS survival.
- Write the mechanism narrative AFTER survival, as a post-hoc Insight Card.
- Graph / mechanism priors seed and bound the search; they never admit a
  candidate.

## Rule 2 — Generate features by machine, not by hand

- Run a deterministic factory over causal-frontier columns (price AND volume,
  at the discovered field / lag): cross-products × lags × rolling × ratios ×
  differences. Many weak features expected; low individual IC is normal.
- Use `proven-patterns.md` constructions as seeds, not the whole space.
- Do NOT hand-pick one intuitive feature.

## Rule 3 — Combine as a diversity-gated weak-signal ensemble (DEFAULT)

- Default construction = ensemble of many weak signals, not one strong signal.
- Diversity gate: drop a member whose OOS-prediction correlation with an
  already-kept member exceeds the diversity threshold, regardless of its
  standalone metric.
- Production strategies ARE ensembles: 7-Component = 60% DR + 40% × 4
  children; Dual Resonance = S2 + V3+Full + V1; DR-V2 = DR + PVV overlay.
  Single-signal single-mechanism is the rare exception.
- A weak signal failing standalone is NOT a kill — test its ensemble
  contribution and diversity first (extraction/ensemble failure ≠ structure
  absent).

## Pipeline

1. Causal frontier bounds the universe (K survivable).
2. Feature factory (Rule 2) + ensemble (Rule 3) → candidate space.
3. Guarded optimization searches it; the gauntlet gates every candidate.
4. Insight Card written post-hoc for the survivor — story after data.

## Anti-patterns

- Mechanism narrative used as an entry gate.
- One hand-designed mechanism / one strong signal instead of an ensemble.
- Hand-picking features instead of the deterministic factory.
- Killing a weak signal on standalone failure without an ensemble/diversity
  test.
- Any external-skill dependency.
