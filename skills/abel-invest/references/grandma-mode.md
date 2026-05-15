# Grandma Mode

Use this reference when the user asks for grandma mode, conservative screening,
simple-return candidates, or no-leverage strategy exploration.

## Product Intent

Grandma mode is a conservative abel-invest lane. It is less graph-ceremonial than
standard discovery and more focused on simple return that survives drawdown.

The default candidate gate is:

```text
total_return > 0
pnl_to_maxdd = total_return / abs(max_dd)
pnl_to_maxdd >= 1.5
max_abs_position <= 1.0
```

Grandma mode currently allows unlevered long/short exposure in `[-1.0, 1.0]`.
Do not use margin, position scaling above one times notional, or local leverage
tuning to improve the ratio.

## Workflow

1. Start a grandma session with `abel-invest init-session --mode grandma`.
2. Prefer simple target-only branches unless the user or evidence gives a clear
   reason to use graph inputs.
3. Keep `model_family=rule_signal` and `complexity_class=simple_signal` unless a
   real mechanism needs more complexity.
4. Before running, confirm prepared `inputs/runtime_profile.json` includes
   `validation_profile: grandma_daily` and `inputs/execution_constraints.json`
   includes `position_bounds: [-1.0, 1.0]`.
5. Read Edge results by total return, MaxDD, `pnl_to_maxdd`, and leverage status.

## What Not To Do

- Do not treat grandma mode as permission to brute-force metric targets.
- Do not promote a levered candidate even if total return looks attractive.
- Do not require graph-first breadth before a simple target-only candidate can be
  judged.
- Do not compare grandma candidates by Sharpe, DSR, Position IC, or Omega as live
  pass/fail gates; those may be diagnostics, while `grandma_daily` owns the
  grandma verdict.
