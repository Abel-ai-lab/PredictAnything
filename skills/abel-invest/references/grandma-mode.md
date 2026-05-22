# Simple/No-Leverage Profile Compatibility

Use this reference only when the user explicitly asks for a simple/no-leverage
strategy, legacy grandma behavior, or compatibility with the `grandma_daily`
validation profile.

This is a validation profile constraint, not a separate Abel Invest research
identity. Abel Invest still searches for the strongest allowed strategy; the
user has narrowed the allowed exposure, complexity, and pass/fail profile.

## Product Intent

The explicit simple/no-leverage profile focuses on positive return that survives
drawdown while keeping executed exposure unlevered.

The profile candidate gate is:

```text
total_return > 0
pnl_to_maxdd = total_return / abs(max_dd)
pnl_to_maxdd >= 1.5
max_abs_position <= 1.0
```

The profile currently allows unlevered long/short exposure in `[-1.0, 1.0]`.
Do not use margin, position scaling above one times notional, or local leverage
tuning to improve the ratio.

## Workflow

1. Start a compatibility session with
   `abel-invest init-session --mode grandma` only when this profile was
   explicitly requested.
2. Search within the user's constraint. Simple target-only candidates are
   allowed, but graph or supplemental inputs can still be used when they improve
   the constrained objective.
3. Keep `model_family=rule_signal` and `complexity_class=simple_signal` unless a
   clear empirical improvement requires more complexity and still honors the
   profile.
4. Before running, confirm prepared `inputs/runtime_profile.json` includes
   `validation_profile: grandma_daily` and `inputs/execution_constraints.json`
   includes `position_bounds: [-1.0, 1.0]`.
5. Read Edge results by total return, MaxDD, `pnl_to_maxdd`, and leverage status.

## What Not To Do

- Do not treat this profile as a way to ignore validation or search-width
  accounting.
- Do not promote a levered candidate even if total return looks attractive.
- Do not present the profile as a separate Abel Invest personality; it is an
  explicit user constraint and validation profile.
- Do not compare these constrained candidates by Sharpe, DSR, Position IC, or
  Omega as live pass/fail gates; those may be diagnostics, while `grandma_daily`
  owns the verdict.
