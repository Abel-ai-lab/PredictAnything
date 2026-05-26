# Hosted Paper Rewrite

Use this reference when promotion or visualization returns
`needs_agent_refactor` with `kind=hosted_paper_rewrite`, or when the user asks
you to make a selected Abel Invest strategy paper-ready for hosted daily
execution.

## Goal

Rewrite the promoted copy so it preserves the selected research strategy's
decision semantics while running as one hosted daily paper step.

Think in this timeline:

```text
research backtest timeline -> selected round cutover -> future hosted paper days
```

The system provides facts and gates. You decide the strategy-specific rewrite.
Do not force the source into a fixed category such as ML, indicator, replay, or
hybrid. Read the strategy and explain the design you choose.

## Loop

1. Read `refactor-request.json`.
2. Edit only the promoted source named by `sourcePath`.
3. Use request `facts` as evidence: feeds, selected window, lookback hints,
   training calls, ordinal hints, branch files, and validation sample dates.
4. Implement `BranchEngine.get_paper_signal(as_of=...)`.
5. Write `refactor-report.json` beside the request.
6. Rerun the same `visualize-session`, `export-strategy-artifact`, or
   `promote-strategy` command.
7. If the gate returns another request, treat `validation.lastGateFailure` as
   diagnostics for the next edit.

Do not edit the original branch. Do not start by reading Abel-skills promotion
internals or Edge promotion-gate internals; the request is the workbench. Inspect
internals only after a refreshed request cannot explain a failure.

## Runtime Paths

Inside `get_paper_signal`, use the hosted path helper:

```python
from abel_edge.runtime_paths import context_runtime_paths

paths = context_runtime_paths(self.context)
paths.base_strategy             # read-only files packaged under strategy/**
paths.runtime                   # read-only runtime config under runtime/**
paths.state / "strategy" / ...  # strategy-owned mutable paper state
```

Rules:

- remove developer-local absolute paths such as `/home/...` or `/Users/...`;
- read immutable packaged assets through `paths.base_strategy`;
- write mutable strategy state only under `paths.state / "strategy"`;
- preserve `compute_decisions(ctx)` as the research/backtest authority unless
  the source is semantically unusable;
- do not implement `get_paper_signal` as a wrapper around full
  `compute_runtime_output(...)` or a full historical replay.

`get_paper_signal` returns a dict with finite numeric `next_position`.
`next_position` is the compiled absolute target exposure for `as_of`, matching
the selected round trade-log meaning. It is not an order delta, order size, or
only-on-change event.

## Design Questions

Answer these before coding:

- What market data is available on the next hosted paper day?
- What history is needed to compute one signal?
- What strategy-owned state, if any, must survive across paper runs?
- Does row order, `iloc`, `range`, modulo, retraining cadence, or signal holding
  require a calendar origin anchored to the research window?
- If startup state is needed, what state must exist at selected-round cutover so
  the next hosted paper day can continue?
- How does a repeated same-`as_of` call stay idempotent?
- What expensive work is avoided during daily hosted paper?

Simple bounded-history strategies often need no startup state. Walking-forward
or retraining strategies often need a real cutover state such as model, scaler,
feature window, retrain cursor, calendar ordinal, or latest strategy-owned
checkpoint. A same-day cache is useful for idempotence, but it is not by itself
cutover state.

If the strategy can only continue by replaying the full historical timeline,
declare that limitation instead of claiming hosted fast-paper readiness.

## Report

Write `refactor-report.json` with this shape:

```json
{
  "schema": "abel-invest.agent-refactor-report/v1",
  "kind": "hosted_paper_rewrite",
  "scope": "hosted_paper_rewrite",
  "summary": "brief rewrite summary",
  "paths": {
    "packagedFiles": [
      {
        "sourcePath": "branch/or/absolute/source.csv",
        "artifactPath": "strategy/assets/source.csv",
        "purpose": "read-only strategy asset"
      }
    ],
    "initialStateFiles": [
      {
        "sourcePath": "state/paper-state.json",
        "artifactPath": "runtime/initial-state/strategy/paper-state.json",
        "purpose": "startup strategy state seed"
      }
    ]
  },
  "paperSignal": {
    "implemented": true,
    "incrementalReady": true,
    "design": {
      "history": {
        "minBars": 120,
        "feeds": ["AAPL"],
        "reason": "history required for one paper signal"
      },
      "state": {
        "usesPersistentState": false,
        "stateFiles": [],
        "reason": "no strategy-owned state is needed"
      },
      "calendar": {
        "usesAbsoluteDecisionOrdinal": false,
        "origin": null,
        "reason": "logic is date/lookback based"
      },
      "cutover": {
        "requiresStartupState": false,
        "mode": "none",
        "dataHistoryStart": null,
        "stateEnd": null,
        "reason": "first paper day can compute from bounded history"
      },
      "dailyStep": {
        "reason": "load data through as_of, compute one absolute target exposure, persist strategy state only if needed"
      }
    },
    "liveReadiness": "how future hosted paper days continue"
  },
  "limitations": [],
  "replacements": []
}
```

`packagedFiles` are immutable files copied under `strategy/**`.
`initialStateFiles` are mutable startup seeds copied under
`runtime/initial-state/**` and hydrated into state by the hosted runner.
Do not list the same source file in both lists.

Generated research or promotion evidence is not a live strategy dependency.
Files under `outputs/**`, `promotions/**`, `edge/**`, and the current export
destination, including generated `trade-log.csv`, are validation evidence.
Gate failure expected values are diagnostics only; never encode them in assets
or initial state.

Use `paperSignal.design.cutover.mode` as follows:

- `none`: no startup state is needed.
- `minimal_cutover_state`: startup state is built once and is valid through the
  selected round end.
- `full_replay_required`: the strategy cannot be made continuing-ready for the
  current hosted fast-paper contract.

Set `paperSignal.incrementalReady=true` only when future hosted paper days can
continue beyond the selected research result.
