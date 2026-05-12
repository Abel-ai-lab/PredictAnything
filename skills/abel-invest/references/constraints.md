# Runtime Legality And Safety

Use this reference when writing `engine.py`, reading semantic preflight, or
debugging runtime validity.

The branch-default safety story is:

- the system materializes the runtime world in `inputs/`
- strategy code reads market data through `DecisionContext`
- strategy code emits next-position intent
- semantic preflight explains visibility and timing violations before a
  recorded round

Any strategy that uses information it could not have seen at decision time is
invalid.

## Authoring Contract

1. Implement `compute_decisions(self, ctx)`.
2. Read the target through `ctx.target.series(...)`.
3. Read auxiliary feeds through `ctx.feed(name)...`.
4. Return `ctx.decisions(next_position)`.

That is the legal authoring surface for branch-default strategies.

## Stateful Strategies

Strategies may use rolling model files, checkpoints, scalers, and lightweight
caches when the mechanism needs state across paper runs. Put durable mutable
state behind the runtime state surface:

```python
model_path = ctx.state_dir / "model/latest.joblib"
scaler_path = ctx.state_dir / "model/feature_scaler.json"
```

Do not write durable state beside `engine.py`, under `inputs/`, or in ad hoc
temporary directories. Promotion can package declared initial state for the
first paper run, but hosted paper execution will only persist files that live
under the runner state directory.

## System-Owned Inputs

Treat these files as runtime facts supplied by the system:

- `inputs/runtime_profile.json`
- `inputs/execution_constraints.json`
- `inputs/data_manifest.json`
- `inputs/context_guide.md`
- `inputs/probe_samples.json`

The strategy should inspect them, then write against the world they describe.
Do not rediscover or override them in `engine.py`.

## Feedback Loop

```bash
abel-invest prepare-branch --branch ...
abel-invest debug-branch --branch ...
```

After `prepare-branch`, inspect:

- `inputs/context_guide.md`
- `inputs/data_manifest.json`
- `inputs/probe_samples.json`

After `debug-branch`, read the semantic verdict, warnings, and sampled traces.
Only then decide whether `run-branch` is warranted.

## What Not To Do

- do not call raw data helpers from inside `compute_decisions()`
- do not hand-roll alignment by reaching around `DecisionContext`
- do not emit an already-effective `position[t]` series when the contract asks
  for `next_position`
- do not treat a suspiciously good backtest as valid before semantic preflight
  and execution semantics agree

## Common Failure Meanings

- raw-helper error: the strategy tried to bypass `DecisionContext`
- shape mismatch: `ctx.decisions(next_position)` received the wrong length or
  type
- semantic blocker: strategy assumptions about feed visibility or execution
  timing do not match the runtime
- clipped output: the strategy asked for positions outside declared execution
  constraints

Static and regex-style look-ahead checks may exist as diagnostics, but they are
not the main contract. Their job is to provide extra warning signals, not to
define legality by themselves.
