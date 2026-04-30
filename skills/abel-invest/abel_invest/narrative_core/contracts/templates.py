"""Static templates for generated strategy-discovery artifacts."""

from __future__ import annotations

ENGINE_TEMPLATE = '''"""Research engine for {ticker}. Replace the starter baseline when the branch thesis is ready.

Default backtest behavior should follow branch.yaml first and the injected context second.
If provided, self.context contains workspace/session/branch/discovery/readiness metadata from Abel strategy discovery.
Use branch.yaml to make the critical research choices explicit:
  - hypothesis
  - evidence_intent
  - input_claim
  - mechanism_family
  - invalidation_condition
  - target
  - requested_start
  - selected_inputs
  - overlap_mode
Write against DecisionContext instead of raw research helpers:
  - ctx.decision_index()
  - ctx.target.series("close")
  - ctx.feed(name).asof_series("close")
  - ctx.points()
  - ctx.decisions(next_position)
If data or runtime setup is broken, let the error surface and inspect it with `abel-invest debug-branch`;
do not hide setup failures behind synthetic outputs.
Current readiness warning: {readiness_warning}
Coverage hints: {coverage_hints_text}
"""

from __future__ import annotations

from abel_edge.engine.base import StrategyEngine


class BranchEngine(StrategyEngine):
    def compute_decisions(self, ctx):
        close = ctx.target.series("close")
        if close.empty:
            raise RuntimeError(
                "The default Abel strategy discovery baseline loaded no usable target bars. "
                "Confirm the requested window in branch.yaml, then rerun "
                "`abel-invest prepare-branch`."
            )
        # Debug-safe starting point: a simple target-trend starter baseline.
        # It exists to make the first branch runnable and comparable, not to
        # pretend that discovery has already been translated into a real edge.
        slow_mean = close.rolling(window=40, min_periods=15).mean()
        next_position = (close > slow_mean).astype(float).fillna(0.0)
        if len(next_position) > 0:
            next_position.iloc[0] = 0.0
        return ctx.decisions(next_position)
'''
